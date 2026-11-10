# SPDX-FileCopyrightText: BoxRouter, Inc.
# SPDX-License-Identifier: Apache-2.0
"""Source-free price quotes for one supplied sandbox lifecycle."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal, localcontext
from typing import Literal, TypeAlias, TypedDict

from sandbox_provider_pricing._util import CONTEXT, decimal_text
from sandbox_provider_pricing.calculator import TIME_RESOURCES, find_class
from sandbox_provider_pricing.calculator.charges import find_rate
from sandbox_provider_pricing.calculator.quantities import (
    BASES,
    creation_quantity,
    egress_quantity,
    in_rate_unit,
    machine_rate_for_size,
    period_seconds,
    size_value,
    snapshot_storage_gb,
    snapshot_storage_quantity,
)
from sandbox_provider_pricing.calculator.spans import Span
from sandbox_provider_pricing.types import Document

_STATES = ("running", "paused", "stopped")
_PeriodDemand: TypeAlias = tuple[str, Decimal, Decimal | None, Decimal | None]


@dataclass(frozen=True)
class _QuoteDemand:
    periods: list[_PeriodDemand]
    creations: Decimal
    egress_bytes: Decimal | None


@dataclass(frozen=True)
class _QuoteContext:
    size: Document
    price_class: Document
    multiplier: Decimal


@dataclass(frozen=True)
class LifecyclePeriod:
    """One state interval and the optional resource demand supplied for that interval."""

    state: Literal["running", "paused", "stopped"]
    seconds: int | float | Decimal
    active_cpu_seconds: int | float | Decimal | None = None
    snapshot_bytes: int | float | Decimal | None = None


class LifecycleQuote(TypedDict):
    """A conditional price for the lifecycle demand supplied by the caller."""

    kind: Literal["lifecycle_quote"]
    status: Literal["known", "unknown"]
    amount_usd: str | None
    price_version: str
    held_back_by: list[str]
    excluded: list[str]


def lifecycle_quote(  # pylint: disable=too-many-arguments
    version: Document,
    size: Document,
    periods: Sequence[LifecyclePeriod],
    *,
    region: str | None = None,
    class_name: str | None = None,
    creations: int | float | Decimal = 1,
    egress_bytes: int | float | Decimal | None = None,
) -> LifecycleQuote:
    """Price one supplied lifecycle at list rates, without creating provider evidence.

    The result is conditional on these demand values. It is not an expected task charge, a
    reservation ceiling, or the actual cost of a sandbox.
    """
    demand = _validate_inputs(version, size, periods, region, class_name, creations, egress_bytes)
    result: LifecycleQuote = {
        "kind": "lifecycle_quote",
        "status": "unknown",
        "amount_usd": None,
        "price_version": version["version"],
        "held_back_by": [],
        "excluded": list(version.get("exclusions", [])),
    }
    price_class = find_class(version, class_name)
    if price_class is None:
        result["held_back_by"].append("The price version has no matching class.")
        return result

    multiplier, region_reason = _region_factor(price_class, region)
    if region_reason is not None:
        result["held_back_by"].append(region_reason)
    total, reasons = _quote_amount(version, size, demand, price_class, multiplier)
    for reason in reasons:
        _append_reason(result, reason)
    if result["held_back_by"]:
        return result
    result["status"] = "known"
    result["amount_usd"] = decimal_text(total)
    return result


def _validate_inputs(  # pylint: disable=too-many-arguments, too-many-positional-arguments, too-many-locals, too-many-branches
    version: Document,
    size: Document,
    periods: Sequence[LifecyclePeriod],
    region: str | None,
    class_name: str | None,
    creations: int | float | Decimal,
    egress_bytes: int | float | Decimal | None,
) -> _QuoteDemand:
    if not isinstance(version, Mapping) or not isinstance(version.get("version"), str):
        raise ValueError("version must have a string version id")
    if not isinstance(size, Mapping):
        raise ValueError("size must be a mapping")
    if not isinstance(periods, Sequence) or not periods:
        raise ValueError("periods must be a non-empty sequence")
    if region is not None and not isinstance(region, str):
        raise ValueError("region must be a string or None")
    if class_name is not None and not isinstance(class_name, str):
        raise ValueError("class_name must be a string or None")
    for field in ("cpu", "gpu", "memory_mib", "disk_mib"):
        value = size.get(field)
        if value is not None:
            if isinstance(value, Decimal):
                raise ValueError(f"size.{field} must be a JSON number")
            _finite_nonnegative(value, f"size.{field}")
    model = size.get("gpu_model")
    if model is not None and not isinstance(model, str):
        raise ValueError("size.gpu_model must be a string")

    demand: list[_PeriodDemand] = []
    for period in periods:
        if not isinstance(period, LifecyclePeriod):
            raise ValueError("periods must contain LifecyclePeriod values")
        if period.state not in _STATES:
            raise ValueError("period state must be running, paused or stopped")
        seconds = _finite_nonnegative(period.seconds, "period seconds")
        active = (
            None
            if period.active_cpu_seconds is None
            else _finite_nonnegative(period.active_cpu_seconds, "active_cpu_seconds")
        )
        snapshot = (
            None
            if period.snapshot_bytes is None
            else _finite_nonnegative(period.snapshot_bytes, "snapshot_bytes")
        )
        demand.append((period.state, seconds, active, snapshot))

    creation_count = _finite_nonnegative(creations, "creations")
    if creation_count != creation_count.to_integral_value():
        raise ValueError("creations must be a non-negative integer")
    egress = None if egress_bytes is None else _finite_nonnegative(egress_bytes, "egress_bytes")
    return _QuoteDemand(demand, creation_count, egress)


def _finite_nonnegative(value: object, name: str) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        raise ValueError(f"{name} must be a finite non-negative number")
    number = Decimal(str(value))
    if not number.is_finite() or number < 0:
        raise ValueError(f"{name} must be a finite non-negative number")
    return number


def _region_factor(price_class: Document, region: str | None) -> tuple[Decimal, str | None]:
    multipliers = price_class.get("region_multipliers")
    if multipliers and region is None:
        return Decimal(1), "The price version requires a region."
    if not multipliers:
        return Decimal(1), None
    if not isinstance(multipliers, Mapping):
        return Decimal(1), "The price version has an invalid region multiplier map."
    try:
        factor = Decimal(str(multipliers.get(region, "1")))
    except ArithmeticError:
        return Decimal(1), "The price version has an invalid region multiplier."
    if not factor.is_finite() or factor < 0:
        return Decimal(1), "The price version has an invalid region multiplier."
    return factor, None


def _billed_states(meter: Document) -> frozenset[str] | None:
    states = meter.get("billed_states")
    if (
        not isinstance(states, list)
        or not states
        or any(not isinstance(state, str) or state not in _STATES for state in states)
    ):
        return None
    return frozenset(states)


def _resource_rate(
    what: str, rate_set: Document, size: Document
) -> tuple[Document | None, str | None]:
    rate: Document | None = rate_set
    reason = None
    if what == "gpu":
        model = size.get("gpu_model")
        if not isinstance(model, str):
            reason = "gpu: the allocated model is missing."
            rate = None
        else:
            candidate = rate_set.get(model)
            if isinstance(candidate, Mapping):
                rate = candidate
            else:
                reason = f"gpu: the price version has no rate for {model}."
                rate = None
    return rate, reason


def _quote_amount(
    version: Document,
    size: Document,
    demand: _QuoteDemand,
    price_class: Document,
    multiplier: Decimal,
) -> tuple[Decimal, list[str]]:
    reasons: list[str] = []
    total = Decimal(0)
    rates = price_class.get("rates")
    if not isinstance(rates, Mapping) or not rates:
        reasons.append("The price class has no rates.")
    context = _QuoteContext(size, price_class, multiplier)
    with localcontext(CONTEXT):
        runtime_amount, runtime_reasons = _runtime_amounts(demand.periods, context)
        total += runtime_amount
        reasons.extend(runtime_reasons)
        extra_amount, extra_reasons = _creation_and_egress_amounts(demand, context)
        total += extra_amount
        reasons.extend(extra_reasons)
        snapshot_amount, snapshot_reasons = _snapshot_amount(version, demand.periods, context)
        total += snapshot_amount
        reasons.extend(snapshot_reasons)
    return total, reasons


def _runtime_amounts(
    periods: list[_PeriodDemand], context: _QuoteContext
) -> tuple[Decimal, list[str]]:
    time_amount, time_reasons = _time_amounts(periods, context)
    machine_amount, machine_reasons = _machine_amount(periods, context)
    return time_amount + machine_amount, time_reasons + machine_reasons


def _creation_and_egress_amounts(
    demand: _QuoteDemand, context: _QuoteContext
) -> tuple[Decimal, list[str]]:
    total = Decimal(0)
    reasons: list[str] = []
    creation_rate = find_rate(context.price_class, "creation")
    if creation_rate is not None:
        quantity = creation_quantity(demand.creations, creation_rate)
        total += quantity.low * (Decimal(creation_rate["usd"]) * context.multiplier)
    egress_rate = find_rate(context.price_class, "egress")
    if egress_rate is not None:
        if demand.egress_bytes is None:
            reasons.append("egress: explicit egress_bytes are required.")
        else:
            quantity = egress_quantity(demand.egress_bytes, egress_rate)
            total += quantity.low * (Decimal(egress_rate["usd"]) * context.multiplier)
    return total, reasons


def _meter_periods(
    what: str, periods: list[_PeriodDemand], price_class: Document
) -> tuple[Document | None, Mapping[str, object] | None, list[_PeriodDemand], str | None]:
    all_meters = price_class.get("meter")
    meters = all_meters if isinstance(all_meters, Mapping) else {}
    meter = meters.get(what)
    rate_set = find_rate(price_class, what)
    billed: list[_PeriodDemand] = []
    reason = None
    if rate_set is None and meter is None:
        pass
    elif meter is None or not isinstance(meter, Mapping):
        reason = f"{what}: the price version has no metering rule."
    elif what == "disk" and rate_set is None and meter.get("disk_gib_per_memory_gib") is not None:
        # The memory size owner applies this published disk coupling in size_value().
        pass
    else:
        states = _billed_states(meter)
        if states is None:
            reason = f"{what}: the billed states are unknown."
        else:
            billed = [period for period in periods if period[0] in states]
            if billed and rate_set is None:
                reason = f"{what}: the price version has no matching rate."
    return rate_set, meter if isinstance(meter, Mapping) else None, billed, reason


def _time_amounts(
    periods: list[_PeriodDemand],
    context: _QuoteContext,
) -> tuple[Decimal, list[str]]:
    total = Decimal(0)
    reasons: list[str] = []
    for what in TIME_RESOURCES:
        amount, resource_reasons = _time_resource_amount(what, periods, context)
        total += amount
        reasons.extend(resource_reasons)
    return total, reasons


def _time_resource_amount(
    what: str,
    periods: list[_PeriodDemand],
    context: _QuoteContext,
) -> tuple[Decimal, list[str]]:
    total = Decimal(0)
    rate_set, meter, billed, reason = _meter_periods(what, periods, context.price_class)
    if what == "gpu" and not context.size.get("gpu") and billed:
        return total, []
    if reason is not None:
        pass
    elif billed and rate_set is not None and meter is not None:
        basis = meter.get("basis")
        if basis not in BASES:
            reason = f"{what}: the metering basis is unknown."
        elif basis == "larger_of_request_and_use":
            reason = f"{what}: the larger of request and use cannot be quoted."
        else:
            rate, rate_reason = _resource_rate(what, rate_set, context.size)
            if rate_reason is not None:
                reason = rate_reason
            elif rate is not None and basis == "active" and what != "cpu":
                reason = f"{what}: this demand contract does not identify active use."
            elif rate is not None:
                for period in billed:
                    unit_seconds, quantity_reason = _time_unit_seconds(
                        what, basis, period, meter, context
                    )
                    if quantity_reason is not None:
                        reason = quantity_reason
                    else:
                        quantity = in_rate_unit(rate, Span.exact(unit_seconds))
                        total += quantity.low * (Decimal(rate["usd"]) * context.multiplier)
    return total, [] if reason is None else [reason]


def _time_unit_seconds(
    what: str,
    basis: object,
    period: _PeriodDemand,
    meter: Mapping[str, object],
    context: _QuoteContext,
) -> tuple[Decimal, str | None]:
    _, seconds, active_cpu_seconds, _ = period
    if basis == "active":
        if active_cpu_seconds is None:
            return Decimal(0), "cpu: active CPU seconds are missing for a billed period."
        return period_seconds(active_cpu_seconds, meter), None
    amount = size_value(what, context.size, context.price_class)
    if amount is None:
        return Decimal(0), f"{what}: the resolved size is missing."
    return amount * period_seconds(seconds, meter), None


def _machine_amount(
    periods: list[_PeriodDemand], context: _QuoteContext
) -> tuple[Decimal, list[str]]:
    total = Decimal(0)
    reasons: list[str] = []
    _, meter, billed, reason = _meter_periods("machine", periods, context.price_class)
    if reason is not None:
        reasons.append(reason)
    elif billed and meter is not None:
        entry = machine_rate_for_size(context.price_class, context.size)
        if entry is None:
            reasons.append("machine: the resolved size or its rate is missing.")
        else:
            for _, seconds, _, _ in billed:
                quantity = in_rate_unit(entry, Span.exact(period_seconds(seconds, meter)))
                total += quantity.low * (Decimal(entry["usd"]) * context.multiplier)
    return total, reasons


def _snapshot_amount(
    version: Document,
    periods: list[_PeriodDemand],
    context: _QuoteContext,
) -> tuple[Decimal, list[str]]:
    total = Decimal(0)
    rate, meter, candidate_periods, reason = _meter_periods(
        "snapshot_storage", periods, context.price_class
    )
    billed = [period for period in candidate_periods if period[1] > 0]
    if reason is None and billed and rate is not None and meter is not None:
        month_hours = _month_hours(version)
        if month_hours is None:
            reason = "snapshot_storage: a positive month_hours value is required."
        else:
            for _, seconds, _, snapshot_bytes in billed:
                if snapshot_bytes is None:
                    reason = "snapshot_storage: snapshot_bytes are missing for a billed period."
                else:
                    billed_time = Span.exact(period_seconds(seconds, meter))
                    quantity = snapshot_storage_quantity(
                        Span.exact(snapshot_storage_gb(snapshot_bytes)), billed_time, month_hours
                    )
                    total += quantity.low * (Decimal(rate["usd"]) * context.multiplier)
    return total, [] if reason is None else [reason]


def _month_hours(version: Document) -> Decimal | None:
    value = version.get("month_hours")
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
        return None
    hours = Decimal(str(value))
    return hours if hours.is_finite() and hours > 0 else None


def _append_reason(result: LifecycleQuote, reason: str) -> None:
    if reason not in result["held_back_by"]:
        result["held_back_by"].append(reason)
