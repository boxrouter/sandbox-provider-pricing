# SPDX-FileCopyrightText: BoxRouter, Inc.
# SPDX-License-Identifier: Apache-2.0
"""One cost line per charged resource: its quantity in the rate's unit, times the rate."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from sandbox_provider_pricing._util import decimal_text
from sandbox_provider_pricing.calculator.findings import (
    Findings,
    fact_source,
    uncertainty,
    usage_fact,
)
from sandbox_provider_pricing.calculator.quantities import (
    BASES,
    TIME_RESOURCES,
    active_cpu_seconds,
    base_unit_seconds,
    billed_seconds,
    creation_quantity,
    egress_quantity,
    in_rate_unit,
    machine_rate_for_size,
    month_hours,
    snapshot_storage_gb,
    snapshot_storage_quantity,
    time_sources,
    usage_size,
)
from sandbox_provider_pricing.calculator.spans import (
    ZERO,
    Span,
    as_decimal,
    span_text,
)
from sandbox_provider_pricing.types import Document, JsonObject


@dataclass(frozen=True)
class Charge:
    """One cost line, with the span its amount came from so a total need not parse it back."""

    line: JsonObject
    amount: Span


def find_rate(price_class: Document, what: str) -> Document | None:
    """The rate for one resource in a price class, if its rates document is usable."""
    rates = price_class.get("rates")
    rate = rates.get(what) if isinstance(rates, Mapping) else None
    return rate if isinstance(rate, Mapping) else None


def price_usage(
    usage: Document,
    price_class: Document,
    version: Document | None,
    multiplier: Span,
    findings: Findings,
) -> list[Charge]:
    intervals = usage.get("intervals", [])
    charges = []
    for what in TIME_RESOURCES:
        meter = (price_class.get("meter") or {}).get(what)
        segmented = (
            meter and meter.get("basis") != "active" and any("size" in item for item in intervals)
        )
        price_time = _time_segments if segmented else _time_charge
        charges.append(price_time(what, usage, price_class, multiplier, findings))
    charges.append(_machine_charge(usage, price_class, multiplier, findings))
    charges.append(_creation_charge(usage, price_class, multiplier, findings))
    charges.append(_egress_charge(usage, price_class, multiplier, findings))
    price_storage = (
        _snapshot_segments
        if any("snapshot_storage" in item for item in intervals)
        else _snapshot_storage_charge
    )
    charges.append(price_storage(usage, price_class, version, multiplier, findings))
    return [charge for charge in charges if charge is not None]


def _snapshot_storage_charge(
    usage: Document,
    price_class: Document,
    version: Document | None,
    multiplier: Span,
    findings: Findings,
) -> Charge | None:
    """Price stored GB over billed states as GB-months using this version's month length."""
    rate = find_rate(price_class, "snapshot_storage")
    fact = usage_fact(usage, "snapshot_storage")
    if rate is None or fact is None:
        return None
    gb = as_decimal(fact.get("bytes"))
    gb = snapshot_storage_gb(gb) if gb is not None else as_decimal(fact.get("gb"))
    max_gb = as_decimal(fact.get("max_gb"))
    known = findings.read(
        "The snapshot's stored size",
        fact,
        gb is not None,
        resource="snapshot_storage",
    )
    if known and gb is not None:
        size = Span.exact(gb)
    elif fact is not None and fact.get("source") == "unknown" and max_gb is not None:
        size = Span(Decimal(0), max_gb)
    else:
        return None

    meter = (price_class.get("meter") or {}).get("snapshot_storage")
    if meter is None:
        findings.gap(
            "The price version has a snapshot storage rate but no rule for when it is billed.",
            "no_rate",
            "snapshot_storage",
        )
        return None
    seconds = billed_seconds(usage, meter, findings)
    if seconds is None:
        return None
    month_length = month_hours(version)
    if month_length is None:
        findings.gap(
            "The price version has no positive month length for snapshot storage.",
            "no_rate",
            "snapshot_storage",
        )
        return None

    quantity = snapshot_storage_quantity(size, seconds, month_length)
    return _charge(
        "snapshot_storage",
        rate,
        quantity,
        multiplier,
        [fact_source(fact), *time_sources(usage, meter)],
    )


def _time_charge(
    what: str, usage: Document, price_class: Document, multiplier: Span, findings: Findings
) -> Charge | None:
    """One charged resource: its size and time (or its active use), in the rate's own unit."""
    rate_set = find_rate(price_class, what)
    if rate_set is None:
        return None
    if what == "gpu":
        rate = _usage_gpu_rate(rate_set, usage, findings)
        if rate is None:
            return None
    else:
        rate = rate_set
    meter = (price_class.get("meter") or {}).get(what)
    if meter is None:
        findings.gap(
            f"The price version has a {what} rate but no rule for how it is metered.",
            "no_rate",
            what,
        )
        return None
    basis = meter["basis"]
    if basis not in BASES:
        findings.gap(
            f"The price version meters {what} by '{basis}', which is not known here.",
            "no_rate",
            what,
        )
        return None
    used = active_cpu_seconds(what, usage, meter, findings) if basis == "active" else None
    if used is not None:
        unit_seconds, sources = used
    else:
        amount = usage_size(what, usage, price_class, findings)
        seconds = billed_seconds(usage, meter, findings)
        if amount is None or seconds is None:
            return None
        unit_seconds = base_unit_seconds(basis, amount, seconds)
        sources = [fact_source(usage_fact(usage, "size")), *time_sources(usage, meter)]
        if basis == "active":
            if what != "cpu":
                findings.gap(
                    f"The provider did not report active {what} time.",
                    "unreported_quantity",
                    what,
                )
            sources.append("unknown")
        elif basis == "larger_of_request_and_use":
            findings.gap(
                f"The provider does not report the {what} used above the requested allocation.",
                "unreported_quantity",
                what,
            )
    return _charge(what, rate, in_rate_unit(rate, unit_seconds), multiplier, sources)


def _time_segments(
    what: str, usage: Document, price_class: Document, multiplier: Span, findings: Findings
) -> Charge | None:
    meter = price_class["meter"][what]
    return _combine_charges(
        [
            part
            for interval in usage["intervals"]
            if interval.get("state") in meter["billed_states"]
            and (
                part := _time_charge(
                    what,
                    {
                        **usage,
                        "size": interval.get("size", usage.get("size")),
                        "intervals": [{k: v for k, v in interval.items() if k != "size"}],
                    },
                    price_class,
                    multiplier,
                    findings,
                )
            )
            is not None
        ]
    )


def _snapshot_segments(
    usage: Document,
    price_class: Document,
    version: Document | None,
    multiplier: Span,
    findings: Findings,
) -> Charge | None:
    return _combine_charges(
        [
            part
            for interval in usage["intervals"]
            if interval.get("state") == "stopped"
            and (
                part := _snapshot_storage_charge(
                    {
                        **usage,
                        "snapshot_storage": interval.get(
                            "snapshot_storage", usage.get("snapshot_storage")
                        ),
                        "intervals": [
                            {k: v for k, v in interval.items() if k != "snapshot_storage"}
                        ],
                    },
                    price_class,
                    version,
                    multiplier,
                    findings,
                )
            )
            is not None
        ]
    )


def _combine_charges(parts: list[Charge]) -> Charge | None:
    if not parts:
        return None
    quantity = sum((_interval_quantity(part.line["quantity"]) for part in parts), ZERO)
    amount = sum((part.amount for part in parts), ZERO)
    line = parts[0].line | {
        "quantity": span_text(quantity),
        "amount": span_text(amount),
        "quantity_source": max((part.line["quantity_source"] for part in parts), key=uncertainty),
    }
    return Charge(line, amount)


def _interval_quantity(value: Any) -> Span:
    if isinstance(value, Mapping):
        return Span(Decimal(value["low"]), Decimal(value["high"]))
    return Span.exact(Decimal(value))


def _usage_gpu_rate(rates: Document, usage: Document, findings: Findings) -> Document | None:
    """Resolve an allocated GPU's model-specific rate, recording a missing model as a gap."""
    size = usage_fact(usage, "size")
    count = None if size is None else as_decimal(size.get("gpu"))
    if count is None or count == 0:
        return None
    model = None if size is None else size.get("gpu_model")
    if not isinstance(model, str):
        findings.gap(
            "The size says GPUs are allocated but does not say which model.",
            "unreported_quantity",
            "gpu",
        )
        return None
    rate = rates.get(model)
    if rate is None:
        findings.gap(f"The price version has no GPU rate for {model}.", "no_rate", "gpu")
    return rate


def _machine_charge(
    usage: Document, price_class: Document, multiplier: Span, findings: Findings
) -> Charge | None:
    """A flat per-size machine rate: the bundle's rate times the billed seconds."""
    rates = price_class.get("rates")
    machine = rates.get("machine") if isinstance(rates, Mapping) else None
    if not isinstance(machine, Mapping) or not machine:
        return None
    meter = (price_class.get("meter") or {}).get("machine")
    if meter is None:
        findings.gap(
            "The price version has a machine rate but no rule for how it is metered.",
            "no_rate",
            "machine",
        )
        return None
    entry = _machine_entry(usage, price_class, findings)
    seconds = billed_seconds(usage, meter, findings) if entry is not None else None
    if entry is None or seconds is None:
        return None
    return _charge(
        "machine",
        entry,
        in_rate_unit(entry, seconds),
        multiplier,
        [fact_source(usage_fact(usage, "size")), *time_sources(usage, meter)],
    )


def _machine_entry(usage: Document, price_class: Document, findings: Findings) -> Document | None:
    """The machine size entry covering this sandbox's size, with a finding when there is none."""
    size = usage_fact(usage, "size")
    if size is None or size.get("source") == "unknown":
        findings.read("The sandbox's size", size, False, resource="machine")
        return None
    entry = machine_rate_for_size(price_class, size)
    if entry is None:
        findings.gap(
            "The price version has no machine size matching this sandbox.",
            "no_rate",
            "machine",
        )
        return None
    if not findings.read("The sandbox's size", size, True, resource="machine"):
        return None
    return entry


def _creation_charge(
    usage: Document, price_class: Document, multiplier: Span, findings: Findings
) -> Charge | None:
    rate = find_rate(price_class, "creation")
    if rate is None:
        return None
    fact = usage_fact(usage, "creations")
    count = as_decimal(None if fact is None else fact.get("count"))
    if (
        not findings.read("The number of creations", fact, count is not None, resource="creation")
        or count is None
    ):
        return None
    quantity = creation_quantity(count, rate)
    return _charge("creation", rate, quantity, multiplier, [fact_source(fact)])


def _egress_charge(
    usage: Document, price_class: Document, multiplier: Span, findings: Findings
) -> Charge | None:
    """Egress is charged only where the usage record carries it: a provider that does not bill
    it for this sandbox leaves it out, and one that cannot say records it as not known."""
    rate = find_rate(price_class, "egress")
    fact = usage_fact(usage, "egress")
    if rate is None or fact is None:
        return None
    sent = as_decimal(fact.get("bytes"))
    known = findings.read(
        "The network egress",
        fact,
        sent is not None,
        resource="egress",
    )
    if not known or sent is None:
        return None
    return _charge("egress", rate, egress_quantity(sent, rate), multiplier, [fact_source(fact)])


def _charge(
    what: str, rate: Document, quantity: Span, multiplier: Span, sources: list[str]
) -> Charge:
    """A cost line. Where the region multiplier is exact it is folded into the rate shown, so
    quantity times rate is the amount; where it is only bounded the rate is the base rate."""
    rate_usd = Decimal(rate["usd"])
    if multiplier.is_exact:
        rate_usd = rate_usd * multiplier.low
        amount = quantity.times(rate_usd)
    else:
        amount = quantity.times(rate_usd).times(multiplier)
    line = {
        "what": what,
        "quantity": span_text(quantity),
        "unit": rate["per"],
        "rate": decimal_text(rate_usd),
        "amount": span_text(amount),
        "quantity_source": max(sources, key=uncertainty),
    }
    return Charge(line, amount)
