# SPDX-FileCopyrightText: BoxRouter, Inc.
# SPDX-License-Identifier: Apache-2.0
"""How much of a resource a sandbox used: its size and billed time, in the rate's own unit."""

from __future__ import annotations

from collections.abc import Mapping
from decimal import ROUND_CEILING, Decimal

from sandbox_provider_pricing.calculator.findings import Findings, fact_source, usage_fact
from sandbox_provider_pricing.calculator.spans import (
    BYTES_PER_GB,
    BYTES_PER_GIB,
    CREATIONS_PER_MILLION,
    MIB_PER_GIB,
    SECONDS_PER_HOUR,
    ZERO,
    Span,
    as_decimal,
)
from sandbox_provider_pricing.types import Document

TIME_RESOURCES = ("cpu", "memory", "disk", "gpu")
BASES = ("allocated", "active", "larger_of_request_and_use")


def active_cpu_seconds(
    what: str, usage: Document, meter: Document, findings: Findings
) -> tuple[Span, list[str]] | None:
    """The CPU time the sandbox used, when the usage record says; None to bound it instead."""
    if what != "cpu":
        return None
    fact = usage_fact(usage, "active_cpu")
    seconds = as_decimal(None if fact is None else fact.get("seconds"))
    usable = findings.read(
        "The CPU time used",
        fact,
        seconds is not None,
        resource="cpu",
    )
    if not usable or seconds is None:
        return None
    if fact is None or fact.get("source") != "provider":
        findings.gap("Active CPU time must come from the provider.", "unreported_quantity", "cpu")
        return None
    if "minimum_seconds" in meter or "increment_seconds" in meter:
        findings.gap(
            "The CPU charge has a minimum or rounding for each period, "
            "but only the total time used is known.",
            "unreported_quantity",
            "cpu",
        )
        seconds = period_seconds(seconds, meter)
    return Span.exact(seconds), [fact_source(fact)]


def usage_size(
    what: str, usage: Document, price_class: Document, findings: Findings
) -> Decimal | None:
    """The sandbox's size of one resource in its base unit, from the usage record."""
    size = usage_fact(usage, "size")
    if size is None or size.get("source") == "unknown":
        findings.read("The sandbox's size", size, False, resource=what)
        return None
    amount = size_value(what, size, price_class)
    if amount is None:
        memory_steps = (price_class.get("meter") or {}).get("memory", {}).get("memory_steps_mib")
        memory_mib = as_decimal(size.get("memory_mib"))
        if what == "memory" and memory_steps and memory_mib is not None:
            findings.gap(
                f"The price version has no memory tier for {memory_mib} MiB.",
                "no_rate",
                "memory",
            )
        else:
            findings.gap(
                f"The provider did not report the {what} size.",
                "unreported_quantity",
                what,
            )
        return None
    if not findings.read("The sandbox's size", size, True, resource=what):
        return None
    return amount


def size_value(what: str, size: Document, price_class: Document) -> Decimal | None:
    """One resource's size in vCPUs, GiB or GPUs, less the free allowance; None if not given."""
    meter = price_class["meter"][what]
    if what in ("cpu", "gpu"):
        amount = as_decimal(size.get(what))
    else:
        mib = as_decimal(size.get(f"{what}_mib"))
        if what == "memory" and mib is not None:
            steps = meter.get("memory_steps_mib")
            if steps:
                tier = min((step for step in steps if Decimal(step) >= mib), default=None)
                if tier is None:
                    return None
                mib = Decimal(tier)
        amount = None if mib is None else mib / MIB_PER_GIB
    if amount is None:
        return None
    if what == "memory":
        amount = _raised_by_disk(amount, size, price_class)
    free = meter.get("free_quantity")
    return amount if free is None else max(amount - Decimal(free), Decimal(0))


def _raised_by_disk(memory: Decimal, size: Document, price_class: Document) -> Decimal:
    """Where disk is billed as memory at a stated ratio, memory is at least the disk's share."""
    ratio = (price_class["meter"].get("disk") or {}).get("disk_gib_per_memory_gib")
    disk_mib = as_decimal(size.get("disk_mib"))
    if ratio is None or disk_mib is None:
        return memory
    return max(memory, disk_mib / MIB_PER_GIB / Decimal(ratio))


def billed_seconds(usage: Document, meter: Document, findings: Findings) -> Span | None:
    """Seconds charged across the intervals in states the meter bills, with its rounding."""
    intervals = usage.get("intervals")
    if not isinstance(intervals, list) or not intervals:
        findings.gap(
            "The provider did not report the time in each state.", "unreported_quantity", "time"
        )
        return None
    total = ZERO
    usable = True
    for interval in intervals:
        state = interval.get("state") if isinstance(interval, Mapping) else None
        if state not in meter["billed_states"]:
            continue
        seconds = _interval_seconds(interval)
        if interval.get("source") != "provider":
            findings.gap(
                "The provider did not report the billed time.",
                "unreported_quantity",
                "time",
            )
            usable = False
            continue
        what = f"The time in {state}"
        known = findings.read(what, interval, seconds is not None, resource="time")
        if seconds is None or not known:
            usable = False
            continue
        if isinstance(interval.get("seconds"), Mapping):
            findings.gap(
                f"The provider did not report the exact time in {state}.",
                "unreported_quantity",
                "time",
            )
        total = total + Span(
            period_seconds(seconds.low, meter), period_seconds(seconds.high, meter)
        )
    return total if usable else None


def _interval_seconds(interval: Document) -> Span | None:
    seconds = interval.get("seconds")
    if isinstance(seconds, Mapping):
        low, high = as_decimal(seconds.get("low")), as_decimal(seconds.get("high"))
        return Span(low, high) if low is not None and high is not None and low <= high else None
    value = as_decimal(seconds)
    return None if value is None else Span.exact(value)


def period_seconds(seconds: Decimal, meter: Document) -> Decimal:
    """What one period in a billed state is charged for: at least the minimum, rounded up."""
    if seconds <= 0:
        return Decimal(0)
    minimum = meter.get("minimum_seconds")
    if minimum is not None:
        seconds = max(seconds, Decimal(minimum))
    step = meter.get("increment_seconds")
    if step is not None:
        seconds = (seconds / Decimal(step)).to_integral_value(rounding=ROUND_CEILING) * step
    return seconds


def creation_quantity(count: Decimal, rate: Document) -> Span:
    """Creation count in the unit named by its rate."""
    quantity = Span.exact(count)
    if rate["per"] == "million-creations":
        return quantity.divided_by(CREATIONS_PER_MILLION)
    return quantity


def egress_quantity(byte_count: Decimal, rate: Document) -> Span:
    """Egress bytes in the rate's decimal GB or binary GiB unit."""
    unit_bytes = BYTES_PER_GIB if rate["per"] == "gib" else BYTES_PER_GB
    return Span.exact(byte_count / unit_bytes)


def snapshot_storage_gb(byte_count: Decimal) -> Decimal:
    """Snapshot bytes in decimal GB, the stored quantity used by the cost calculator."""
    return byte_count / BYTES_PER_GB


def snapshot_storage_quantity(gigabytes: Span, billed_time: Span, month_hours: Decimal) -> Span:
    """Stored decimal GB over billed seconds in the version's GB-month quantity."""
    return gigabytes.times(billed_time).divided_by(month_hours * SECONDS_PER_HOUR)


def machine_rate_for_size(price_class: Document, size: Document) -> Document | None:
    """The flat per-size machine rate covering this size, or None when none matches.

    A machine rate matches on the bundle's published vCPU and memory figures; the size's other
    fields are part of the bundle and do not narrow it. A size missing cpu or memory_mib cannot
    be matched.
    """
    rates = price_class.get("rates")
    machine = rates.get("machine") if isinstance(rates, Mapping) else None
    if not isinstance(machine, Mapping) or not machine:
        return None
    cpu = as_decimal(size.get("cpu"))
    mib = as_decimal(size.get("memory_mib"))
    if cpu is None or mib is None:
        return None
    gib = mib / MIB_PER_GIB
    for entry in machine.values():
        if not isinstance(entry, Mapping):
            continue
        try:
            if Decimal(str(entry["cpu"])) == cpu and Decimal(str(entry["memory_gib"])) == gib:
                return entry
        except (ArithmeticError, KeyError, TypeError):
            continue
    return None


def base_unit_seconds(basis: str, amount: Decimal, seconds: Span) -> Span:
    """Size times time in base-unit seconds; where billed by use, anything up to all of it."""
    allocated = seconds.times(amount)
    return Span(Decimal(0), allocated.high) if basis == "active" else allocated


def in_rate_unit(rate: Document, unit_seconds: Span) -> Span:
    """Base-unit seconds in the rate's unit: a provider's own size unit (a core, a GB) covers
    `size_per_unit` base units, and a rate per hour counts hours."""
    per_hour_rate = rate["per"].endswith("-hour")
    divisor = SECONDS_PER_HOUR if per_hour_rate else Decimal(1)
    size_per_unit = rate.get("size_per_unit")
    if size_per_unit is not None:
        divisor *= Decimal(size_per_unit)
    return unit_seconds.divided_by(divisor)


def time_sources(usage: Document, meter: Document) -> list[str]:
    intervals: list[Document] = usage.get("intervals", [])
    return [fact_source(item) for item in intervals if item.get("state") in meter["billed_states"]]
