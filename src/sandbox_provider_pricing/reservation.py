# SPDX-FileCopyrightText: BoxRouter, Inc.
# SPDX-License-Identifier: Apache-2.0
"""Rate-card reservation ceilings, separate from provider-sourced sandbox costs."""

from decimal import Decimal, localcontext
from typing import Literal, TypedDict

from sandbox_provider_pricing._util import decimal_text
from sandbox_provider_pricing.calculator import CONTEXT, TIME_RESOURCES, Span, find_class, find_rate
from sandbox_provider_pricing.calculator.quantities import (
    creation_quantity,
    in_rate_unit,
    machine_rate_for_size,
    period_seconds,
    size_value,
)
from sandbox_provider_pricing.types import Document

COVERAGE_KINDS = (
    "cpu",
    "memory",
    "disk",
    "creation",
    "egress",
    "snapshot_storage",
    "image_storage",
    "volume_storage",
    "requests",
)
# Kinds a quote can price: running resources over time, and the one creation fee.
_QUOTED_KINDS = ("cpu", "memory", "disk", "creation")
_RATE_OF = {"egress": "egress", "creation": "creation", "cpu": "cpu", "memory": "memory"}


class ReservationQuote(TypedDict):
    kind: Literal["reservation_quote"]
    status: Literal["bounded", "unbounded", "unknown"]
    ceiling_usd: str | None
    price_version: str
    held_back_by: list[str]
    excluded: list[str]


def reservation_quote(  # pylint: disable=too-many-arguments
    version: Document,
    size: Document,
    duration_seconds: int | float | Decimal,
    *,
    region: str | None = None,
    class_name: str | None = None,
    creation: bool = True,
) -> ReservationQuote:
    """Quote one running reservation plus optional creation, at full metered use.

    Egress and retained storage are outside this resource-duration quote. A rate billed on
    the larger of request and use has no finite ceiling from these inputs. The version's
    `coverage` must state every billable charge as in the quote, not billed or unbounded;
    a charge it leaves unstated makes the quote `unknown`. No usage evidence is fabricated
    and neither price() nor cost() is called.
    """
    if isinstance(duration_seconds, bool) or not isinstance(
        duration_seconds, (int, float, Decimal)
    ):
        raise ValueError("duration_seconds must be finite and non-negative")
    seconds = Decimal(str(duration_seconds))
    if not seconds.is_finite() or seconds < 0:
        raise ValueError("duration_seconds must be finite and non-negative")
    if not isinstance(creation, bool):
        raise ValueError("creation must be a boolean")
    price_class = find_class(version, class_name)
    result: ReservationQuote = {
        "kind": "reservation_quote",
        "status": "unknown",
        "ceiling_usd": None,
        "price_version": str(version["version"]),
        "held_back_by": [],
        "excluded": [*version.get("exclusions", []), "Network egress and retained storage"],
    }
    if price_class is None:
        result["held_back_by"].append("The price version has no matching class.")
        return result
    gaps = _coverage_gaps(version, price_class)
    if gaps:
        result["held_back_by"] = gaps
        return result
    result["excluded"] += _unbounded_charges(version)
    with localcontext(CONTEXT):
        total, reasons, unbounded = _running_quote(price_class, size, seconds)
        result["held_back_by"] = reasons
        unbounded = _state_unbounded_coverage(version, reasons) or unbounded
        if unbounded:
            result["status"] = "unbounded"
        elif not reasons:
            multiplier = Decimal((price_class.get("region_multipliers") or {}).get(region, "1"))
            rate = find_rate(price_class, "creation") if creation else None
            if rate is not None:
                total += creation_quantity(Decimal(1), rate).low * Decimal(rate["usd"])
            result["status"] = "bounded"
            result["ceiling_usd"] = decimal_text(total * multiplier)
    return result


_RUNNING_KINDS = ("cpu", "memory", "disk")


def _coverage_gaps(version: Document, price_class: Document) -> list[str]:
    """Why the version's coverage cannot back a quote: a charge left unstated or contradicted."""
    coverage = version.get("coverage")
    if not isinstance(coverage, dict):
        return ["The price version states no coverage of its billable charges."]
    gaps = [
        f"{kind}: the price version does not say whether it is billed."
        for kind in COVERAGE_KINDS
        if kind not in coverage
    ]
    rates = price_class.get("rates", {})
    for kind, entry in coverage.items():
        treatment = entry["treatment"]
        rate = rates.get(_RATE_OF.get(kind, ""))
        if treatment == "in_quote" and kind not in _QUOTED_KINDS:
            gaps.append(f"{kind}: a quote does not price it, so it cannot be in the quote.")
        if treatment == "not_billed" and isinstance(rate, dict) and Decimal(rate["usd"]) > 0:
            gaps.append(f"{kind}: stated as not billed, but the class has a rate for it.")
        if treatment != "in_quote" and kind == "creation" and "creation" in rates:
            gaps.append("creation: the class has a creation rate that the quote would price.")
        if treatment == "in_quote" and kind == "creation" and "creation" not in rates:
            gaps.append("creation: stated as in the quote, but the class has no creation rate.")
    return gaps


def _state_unbounded_coverage(version: Document, reasons: list[str]) -> bool:
    """Add a reason for each running charge the coverage calls unbounded; whether any is."""
    found = False
    for kind in _RUNNING_KINDS:
        entry = version["coverage"][kind]
        if entry["treatment"] == "unbounded":
            if not any(reason.startswith(f"{kind}:") for reason in reasons):
                reasons.append(f"{kind}: {entry['note']}")
            found = True
    return found


def _unbounded_charges(version: Document) -> list[str]:
    return [
        f"{kind}: {entry['note']}"
        for kind, entry in version["coverage"].items()
        if entry["treatment"] == "unbounded" and kind not in _RUNNING_KINDS
    ]


def _running_quote(
    price_class: Document, size: Document, seconds: Decimal
) -> tuple[Decimal, list[str], bool]:
    total, reasons, unbounded = Decimal(0), [], False
    for what in TIME_RESOURCES:
        meter = price_class.get("meter", {}).get(what, {})
        rate = find_rate(price_class, what)
        if rate is None or "running" not in meter.get("billed_states", []):
            continue
        if meter["basis"] == "larger_of_request_and_use":
            reasons.append(f"{what}: the rate card cannot bound use above the request.")
            unbounded = True
            continue
        if what == "gpu":
            if not size.get("gpu"):
                continue
            rate = rate.get(str(size.get("gpu_model")))
        amount = size_value(what, size, price_class)
        if rate is None or amount is None:
            reasons.append(f"{what}: the resolved size or its rate is missing.")
            continue
        if meter["basis"] not in ("allocated", "active"):
            reasons.append(f"{what}: the metering basis is unknown.")
            continue
        # Active meters assume full use, while minimums/increments still apply per meter.
        quantity = in_rate_unit(rate, Span.exact(amount * period_seconds(seconds, meter)))
        total += quantity.low * Decimal(rate["usd"])
    machine = find_rate(price_class, "machine")
    meter = price_class.get("meter", {}).get("machine", {})
    if machine and "running" in meter.get("billed_states", []):
        entry = machine_rate_for_size(price_class, size)
        if entry is None:
            reasons.append("machine: the resolved size or its rate is missing.")
        else:
            quantity = in_rate_unit(entry, Span.exact(period_seconds(seconds, meter)))
            total += quantity.low * Decimal(entry["usd"])
    if (
        total == 0
        and not reasons
        and not any(find_rate(price_class, what) for what in (*TIME_RESOURCES, "machine"))
    ):
        reasons.append("The price version has no running resource rates.")
    return total, reasons, unbounded
