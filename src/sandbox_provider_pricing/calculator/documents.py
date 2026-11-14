# SPDX-FileCopyrightText: BoxRouter, Inc.
# SPDX-License-Identifier: Apache-2.0
"""The calculator's two answers: a sandbox's `cost` document and an hourly `per_hour` rate."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from decimal import Decimal, localcontext

from sandbox_provider_pricing._util import CONTEXT, decimal_text
from sandbox_provider_pricing.calculator.charges import Charge, price_usage
from sandbox_provider_pricing.calculator.findings import Findings, usage_fact
from sandbox_provider_pricing.calculator.quantities import (
    BASES,
    TIME_RESOURCES,
    base_unit_seconds,
    in_rate_unit,
    machine_rate_for_size,
    size_value,
)
from sandbox_provider_pricing.calculator.spans import (
    ONE,
    SECONDS_PER_HOUR,
    ZERO,
    Span,
    as_decimal,
)
from sandbox_provider_pricing.types import Cost, Document
from sandbox_provider_pricing.versions import find_class

# The usage facts that say when they were observed; the latest is the default `as_of`.
FACTS_WITH_TIMES = (
    "started",
    "region",
    "size",
    "class",
    "creations",
    "active_cpu",
    "egress",
    "snapshot_storage",
)
CREDITS_EXCLUSION = "Credits and discounts"


def cost(usage: Document, version: Document | None, *, as_of: str | None = None) -> Cost:
    """The cost of one sandbox's usage at one price version, as a `cost` document.

    `as_of` is when the cost was worked out, so a running sandbox's cost reads "so far"; by
    default it is the latest time any usage fact was observed. `version` is the price version in
    effect when the sandbox started; None means there was none, which gives `unknown`.
    """
    stamp = as_of or _latest_observation(usage)
    if stamp is None:
        raise ValueError("as_of is required when no usage fact says when it was observed")
    with localcontext(CONTEXT):
        findings = Findings()
        charges: list[Charge] = []
        price_class = _select_class(usage, version, findings)
        if price_class is not None:
            multiplier = _region_multiplier(usage, price_class, findings)
            charges = price_usage(usage, price_class, version, multiplier, findings)
            if not charges and not findings.gaps:
                findings.gap(
                    "The price version has no rate for anything this sandbox used.",
                    "no_rate",
                    "usage",
                )
        return _document(findings, version, charges, stamp)


def per_hour(  # pylint: disable=too-many-locals
    version: Document,
    size: Document,
    *,
    class_name: str | None = None,
    region: str | None = None,
) -> dict[str, str] | None:
    """The price per hour of a sandbox that keeps running, as `{low, high}`; None if unpriced.

    `size` has the usage record's size fields (`cpu`, `memory_mib`, `disk_mib`, `gpu` and
    `gpu_model`); a resource it does not list is not priced. `class_name` None selects the default
    class; `region` None applies no regional multiplier. Creation fees and egress are not hourly,
    and a period's minimum or rounding does not apply to an hour that carries on.
    """
    with localcontext(CONTEXT):
        price_class = find_class(version, class_name)
        if price_class is None:
            return None
        multiplier = Decimal(1)
        if region is not None:
            multiplier = Decimal((price_class.get("region_multipliers") or {}).get(region, "1"))
        total = ZERO
        priced = False
        for what in TIME_RESOURCES:
            rate, unpriced = _per_hour_rate(what, size, price_class)
            if unpriced:
                return None
            if rate is None:
                continue
            meter = (price_class.get("meter") or {}).get(what)
            if meter is None or "running" not in meter["billed_states"]:
                continue
            amount = size_value(what, size, price_class)
            if amount is None:
                if what == "memory" and "memory_mib" in size:
                    return None
                continue
            if meter["basis"] not in BASES:
                return None
            unit_seconds = base_unit_seconds(meter["basis"], amount, Span.exact(SECONDS_PER_HOUR))
            quantity = in_rate_unit(rate, unit_seconds)
            total = total + quantity.times(Decimal(rate["usd"]) * multiplier)
            priced = True
        machine = _machine_per_hour(price_class, size, multiplier)
        if machine is UNPRICED:
            return None
        if isinstance(machine, Span):
            total = total + machine
            priced = True
        return (
            {"low": decimal_text(total.low), "high": decimal_text(total.high)} if priced else None
        )


class _Unpriced:
    pass


UNPRICED = _Unpriced()


def _machine_per_hour(
    price_class: Document, size: Document, multiplier: Decimal
) -> Span | _Unpriced | None:
    """The hourly machine charge at this size: a Span, None without a machine rate to apply,
    or UNPRICED when the version meters machine time but prices no size that matches."""
    machine = (price_class.get("rates") or {}).get("machine")
    meter = (price_class.get("meter") or {}).get("machine")
    if (
        not isinstance(machine, Mapping)
        or meter is None
        or "running" not in meter["billed_states"]
        or size.get("cpu") is None
        or size.get("memory_mib") is None
    ):
        return None
    entry = machine_rate_for_size(price_class, size)
    if entry is None:
        return UNPRICED
    return in_rate_unit(entry, Span.exact(SECONDS_PER_HOUR)).times(
        Decimal(entry["usd"]) * multiplier
    )


def _per_hour_rate(
    what: str, size: Document, price_class: Document
) -> tuple[Document | None, bool]:
    """The rate for this size, with whether an allocated GPU has no price."""
    rate_set = price_class["rates"].get(what)
    if rate_set is None:
        return None, False
    if what != "gpu":
        return rate_set, False
    count = as_decimal(size.get("gpu"))
    if count is None or count == 0:
        return None, False
    model = size.get("gpu_model")
    if not isinstance(model, str):
        return None, True
    rate = rate_set.get(model)
    return rate, rate is None


def _select_class(usage: Document, version: Document | None, findings: Findings) -> Document | None:
    """The rate set that applies, or None with a gap saying why nothing can be priced."""
    if version is None:
        if _time_unreported(usage):
            # Without the provider's times there is no start to choose a version by.
            findings.gap(
                "The provider did not report the billed time.", "unreported_quantity", "time"
            )
        else:
            findings.gap(
                f"No price version is in effect for {usage.get('provider')}.", "no_rate", "usage"
            )
        return None
    if version.get("provider") != usage.get("provider"):
        findings.gap(
            f"The price version is for {version.get('provider')}, "
            f"but this sandbox ran on {usage.get('provider')}.",
            "no_rate",
            "usage",
        )
        return None
    fact = usage_fact(usage, "class")
    name = None if fact is None else fact.get("name")
    if fact is None:
        classes = version.get("classes", [])
        if len(classes) == 1:
            price_class = find_class(version, None)
        else:
            findings.gap("The provider did not report the class.", "unreported_quantity", "class")
            return None
    elif name is None or fact.get("source") == "unknown":
        findings.read("The class", fact, False, resource="class")
        price_class = find_class(version, None)
    else:
        if not findings.read("The class", fact, True, resource="class"):
            return None
        price_class = find_class(version, name)
        if price_class is None:
            findings.gap(
                f"No class of the price version covers the class {name}.", "no_rate", "class"
            )
    if price_class is None and not findings.gaps:
        findings.gap("The price version has no default class.", "no_rate", "class")
    return price_class


def _time_unreported(usage: Document) -> bool:
    """True when the start or any interval did not come from the provider."""
    started = usage_fact(usage, "started")
    if started is None or started.get("at") is None:
        return True
    intervals = usage.get("intervals") or []
    return any(
        not isinstance(interval, Mapping) or interval.get("source") != "provider"
        for interval in intervals
    )


def _region_multiplier(usage: Document, price_class: Document, findings: Findings) -> Span:
    """What the class's rates are multiplied by for the sandbox's region."""
    multipliers = price_class.get("region_multipliers")
    if not multipliers:
        return ONE
    region = usage_fact(usage, "region")
    name = None if region is None else region.get("name")
    if name is None:
        findings.read("The region", region, False, resource="region")
        return ONE
    if not findings.read("The region", region, True, resource="region"):
        return ONE
    return Span.exact(Decimal(multipliers.get(name, "1")))


def _document(
    findings: Findings, version: Document | None, charges: list[Charge], as_of: str
) -> Cost:
    if any(not charge.amount.is_exact for charge in charges) and not findings.gaps:
        findings.gap(
            "The provider did not report the exact quantity.", "unreported_quantity", "usage"
        )
    if findings.gaps:
        label, reasons = "unknown", findings.gaps
    else:
        label, reasons = "calculated", []
    worked_out = label != "unknown"
    exclusions = [] if version is None else [*version.get("exclusions", []), CREDITS_EXCLUSION]
    total = sum((charge.amount for charge in charges), ZERO)
    high = decimal_text(total.high)
    return {
        "label": label,
        "total": {"low": decimal_text(total.low), "high": high} if worked_out else None,
        "lines": [charge.line for charge in charges] if worked_out else [],
        "held_back_by": reasons,
        "exclusions": exclusions,
        "price_version": None if version is None else version.get("version"),
        "as_of": as_of,
    }


def _latest_observation(usage: Document) -> str | None:
    facts = [usage_fact(usage, name) for name in FACTS_WITH_TIMES]
    intervals = usage.get("intervals")
    if isinstance(intervals, list):
        facts += [item if isinstance(item, Mapping) else None for item in intervals]
    seen: list[tuple[datetime, str]] = []
    for fact in facts:
        text = None if fact is None else fact.get("observed_at")
        if not isinstance(text, str):
            continue
        try:
            moment = datetime.fromisoformat(text)
        except ValueError:
            continue
        seen.append((moment if moment.tzinfo else moment.replace(tzinfo=UTC), text))
    return max(seen)[1] if seen else None
