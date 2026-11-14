# SPDX-FileCopyrightText: BoxRouter, Inc.
# SPDX-License-Identifier: Apache-2.0
"""Turn validated evidence into a reproducible, versioned price result."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from typing import NamedTuple, cast

from sandbox_provider_pricing._util import package_version, parse_time
from sandbox_provider_pricing.calculator import cost, per_hour
from sandbox_provider_pricing.evidence import normalize_evidence, validate_evidence, validated
from sandbox_provider_pricing.providers import billing, rules
from sandbox_provider_pricing.revisit import scheduled_revisit
from sandbox_provider_pricing.types import (
    BillableUsage,
    Cost,
    Document,
    Finding,
    JsonObject,
    TimeValue,
    bundled_copy,
)
from sandbox_provider_pricing.usage import (
    call_returns,
    provider_record_size,
    sandbox_end,
    sandbox_start,
    utc_text,
)
from sandbox_provider_pricing.versions import (
    bundled_pool,
    latest_version,
    price_version,
    seed_versions,
)

_LABEL_ORDER = {"unknown": 0, "calculated": 2, "reported": 3}


class Rated(NamedTuple):
    """The usage at each end, rated, and the end that schedules revisits of its records."""

    low: Cost
    high: Cost
    schedule_end: datetime | None


def price(
    evidence: Document,
    *,
    as_of: str | None = None,
    versions: Sequence[JsonObject] | None = None,
    ended_at: datetime | None = None,
) -> JsonObject:
    """Price evidence; `ended_at` optionally anchors revisit scheduling only."""
    evidence = normalize_evidence(evidence)
    validate_evidence(evidence)
    provider = evidence["provider"]
    bill = billing(provider)
    schedule_end = (
        None if evidence["sandbox_made"]["value"] is False else _canonical_end(evidence, ended_at)
    )
    # The bundle is only selected from here, so only the selected version is copied.
    pool = bundled_pool() if versions is None else list(versions)
    observation = as_of
    if observation is None and not _has_observation(evidence):
        if evidence["sandbox_made"]["value"] is not False:
            raise ValueError("as_of is required when evidence has no observation time")
        observation = latest_version(provider, pool)["effective_from"]
    with validated(evidence):
        # Only a rule that checks rates against a version reads the pool; the others take `**_`.
        usage = rules(provider).billable(evidence, bill, as_of=observation, versions=pool)
    _start_usage(evidence, usage)
    started = (
        usage["low"]["started"].get("at")
        or utc_text(usage["times"]["start"].value)
        or _started(evidence)
    )
    selected = price_version(provider, started, pool)
    if selected is None and evidence["sandbox_made"]["value"] is False:
        selected = latest_version(provider, pool)
    if selected is not None and versions is None:
        selected = bundled_copy(selected)
    _recorded_size(evidence, bill, selected, usage)
    low = cost(usage["low"], selected, as_of=observation)
    high = (
        low if usage["low"] == usage["high"] else cost(usage["high"], selected, as_of=observation)
    )
    return _result(evidence, usage, Rated(low, high, schedule_end), bill, selected)


def reproduce(result: Document, *, versions: Sequence[JsonObject] | None = None) -> JsonObject:
    """Re-rate stored usage with its recorded price version from the supplied or bundled pool."""
    try:
        result_versions = result["versions"]
        steps = result["steps"]
        usage = steps["usage"]
        stamp = result["as_of"]
    except (KeyError, TypeError) as exc:
        raise ValueError("result is missing versions, steps.usage, or as_of") from exc
    pool = seed_versions() if versions is None else versions
    selected = next((item for item in pool if item["version"] == result_versions["prices"]), None)
    if selected is None and result_versions["prices"] is not None:
        raise ValueError(f"price version {result_versions['prices']!r} is not bundled")
    low = cost(usage["low"], selected, as_of=stamp)
    high = cost(usage["high"], selected, as_of=stamp)
    replay = _priced(low, high)
    reproduced = dict(result)
    reproduced.update(replay)
    reproduced["steps"] = dict(steps) | {"rated": {"low": low, "high": high}}
    if result["basis"] == "provider_reported" and result.get("reported") is not None:
        reported = result["reported"]
        reproduced.update(
            label="reported",
            total={"low": reported["usd"], "high": reported["usd"]},
            lines=[],
            held_back_by=[],
            basis="provider_reported",
        )
    if _prepared_image(steps["evidence"]):
        _leave_unpriced(reproduced)
    return reproduced


def hourly(provider: str, size: Document, *, at: str | None = None) -> JsonObject:
    """Return the hourly range and its published basis for the price version in effect."""
    versions = seed_versions()
    selected = (
        latest_version(provider, versions) if at is None else price_version(provider, at, versions)
    )
    if selected is None:
        raise ValueError(f"no price version for {provider!r} at {at!r}")
    rate = per_hour(selected, size)
    sources = selected.get("sources", [])
    return {
        "low": None if rate is None else rate["low"],
        "high": None if rate is None else rate["high"],
        "basis_text": _basis_text(selected),
        "prices": selected,
        "source_url": sources[0]["url"] if sources else None,
        "checked_at": selected.get("retrieved_at", "")[:10],
    }


def _result(
    evidence: Document,
    usage: BillableUsage,
    ends: Rated,
    bill: Document,
    selected: Document | None,
) -> JsonObject:
    low, high, schedule_end = ends
    rated = _priced(low, high)
    reported = usage.get("reported")
    result = {
        "provider": evidence["provider"],
        **rated,
        "currency": "USD",
        "basis": "list_price_usage",
        "reported": reported,
        "excluded": high["exclusions"],
        "revisit": _revisit(
            evidence["provider"],
            schedule_end,
            high["as_of"],
        ),
        "final": _finality(evidence, schedule_end, high["as_of"]),
        "versions": {
            "package": package_version(),
            "rules": bill["rules_version"],
            "prices": None if selected is None else selected["version"],
        },
        "steps": {
            "evidence": dict(evidence),
            "times": {name: _time_value(value) for name, value in usage["times"].items()},
            "sandbox_start": _time_value(sandbox_start(evidence, usage)),
            "sandbox_end": _time_value(sandbox_end(evidence, usage)),
            "usage": {"low": usage["low"], "high": usage["high"]},
            "rated": {"low": low, "high": high},
        },
        "as_of": high["as_of"],
    }
    if _prepared_image(evidence):
        _leave_unpriced(result)
    elif (
        bill.get("reported_at_list_price", {}).get("value") is True
        and isinstance(reported, Mapping)
        and isinstance(reported.get("usd"), str)
    ):
        usd = cast(str, reported["usd"])
        result.update(
            label="reported",
            total={"low": usd, "high": usd},
            lines=[],
            held_back_by=[],
            basis="provider_reported",
        )
    return result


_PREPARATION_UNPRICED: Finding = {
    "code": "preparation_cost_unavailable",
    "resource": "image_preparation",
    "text": "No provider image preparation cost receipt.",
}


def _leave_unpriced(result: JsonObject) -> None:
    result.update(
        label="unknown",
        total=None,
        reported=None,
        final=False,
        lines=[],
        held_back_by=[*result["held_back_by"], _PREPARATION_UNPRICED],
    )


def _prepared_image(evidence: Document) -> bool:
    """Whether an image preparation ran for this sandbox.

    Core's receipt for it has no billing target, so the sandbox's records cannot show its cost,
    and the reservation made for it is never an actual.
    """
    return any(
        operation["name"] == "image.prepare" and operation["outcome"] != "not_reached"
        for operation in evidence.get("operations", ())
    )


def _priced(low: Cost, high: Cost) -> JsonObject:
    """Merge the earliest low and latest high into one conservative result."""
    labels = (low["label"], high["label"])
    label = min(labels, key=_LABEL_ORDER.__getitem__)
    low_total, high_total = low["total"], high["total"]
    if label == "unknown" or low_total is None or high_total is None:
        total = None
        label = "unknown"
    else:
        lower = low_total["low"]
        upper = high_total["high"]
        total = {"low": lower, "high": upper}
        if lower != upper:
            label, total = "unknown", None
    lines = high["lines"]
    held = _held_back(low, high)
    return {
        "label": label,
        "total": total,
        "lines": lines if label != "unknown" else [],
        "held_back_by": held,
    }


def _held_back(low: Cost, high: Cost) -> list[Finding]:
    reasons: list[Finding] = []
    for finding in [*low["held_back_by"], *high["held_back_by"]]:
        if finding not in reasons:
            reasons.append(finding)
    return reasons


def _started(evidence: Document) -> str | None:
    """Recorded creation selects a rate version only; never a billed interval."""
    for call in evidence["calls"]:
        if call["name"] == "create":
            sent = call.get("sent_at")
            if sent and isinstance(sent.get("value"), str):
                return cast(str, sent["value"])
    return None


def _has_observation(evidence: Document) -> bool:
    return bool(
        any(
            edge and edge.get("value")
            for call in evidence["calls"]
            for edge in (call.get("sent_at"), call.get("returned_at"))
        )
        or any(time["at"].get("value") for time in evidence["provider_times"])
        or any(
            fact and fact.get("value")
            for fact in (
                evidence["last_seen_alive"],
                evidence["noticed_gone"],
                evidence.get("deadline"),
            )
        )
        or evidence["provider_records"]
    )


def _time_value(value: TimeValue) -> JsonObject:
    out = {"value": _timestamp(value.value), "source": value.source, "how": value.how}
    return out


def _revisit(provider: str, ended: datetime | None, as_of: str) -> JsonObject | None:
    if ended is None:
        return None
    policy = scheduled_revisit(provider)
    if policy is None:
        return None
    next_read = policy.next_read(ended, last_read_at=parse_time(as_of))
    if next_read is None:
        return None
    ended_utc = ended.astimezone(UTC)
    after = ended_utc + timedelta(seconds=policy.after_s)
    until = ended_utc + timedelta(seconds=policy.until_s)
    return {
        "after": _timestamp(after),
        "until": _timestamp(until),
        "interval_s": policy.interval_s,
        "next_read_at": _timestamp(next_read),
    }


def _finality(evidence: Document, ended: datetime | None, as_of: str) -> bool:
    if ended is None:
        return evidence["sandbox_made"]["value"] is False
    policy = scheduled_revisit(str(evidence["provider"]))
    return policy is not None and not policy.may_change(ended, as_of=parse_time(as_of))


def _basis_text(version: Document) -> str:
    default = next((c for c in version["classes"] if c.get("default")), version["classes"][0])
    words = {
        "allocated": "allocated",
        "active": "active",
        "larger_of_request_and_use": "the larger of request and use",
    }
    names = {"cpu": "CPU", "memory": "memory"}
    by_basis: dict[str, list[str]] = {}
    for resource, meter in default["meter"].items():
        if resource in names and "running" in meter["billed_states"]:
            by_basis.setdefault(meter["basis"], []).append(names[resource])
    return (
        "; ".join(f"{words[basis]} {' and '.join(items)}" for basis, items in by_basis.items())
        or "a flat rate per sandbox size"
    )


def _timestamp(value: datetime | None) -> str | None:
    return None if value is None else value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _canonical_end(evidence: Document, ended_at: datetime | None) -> datetime | None:
    """Find a terminal scheduling anchor without treating a billed interval as sandbox end."""
    if ended_at is not None:
        if ended_at.tzinfo is None or ended_at.utcoffset() is None:
            raise ValueError("ended_at must be timezone-aware")
        return ended_at.astimezone(UTC)
    facts = [
        time["at"].get("value")
        for time in evidence["provider_times"]
        if time["kind"] in ("stopped", "ended") and time["at"].get("source") == "provider"
    ]
    facts.extend(call_returns(evidence, "destroy"))
    noticed_gone = evidence.get("noticed_gone")
    if noticed_gone is not None:
        facts.append(noticed_gone.get("value"))
    parsed = [parse_time(value) for value in facts if isinstance(value, str)]
    return max(parsed, default=None)


def _recorded_size(
    evidence: Document, bill: Document, selected: Document | None, usage: BillableUsage
) -> None:
    """Fill the usage size from the provider's own record where its declaration names one.

    A create that asks for minimums records no exact requested size; the provider's sandbox
    record says what was allocated. Its resolved size stands in for the requested one wherever
    no provider or measured size already does.
    """
    size = provider_record_size(evidence, bill, selected)
    if size is None:
        return
    for side in (usage["low"], usage["high"]):
        existing = side.get("size")
        if isinstance(existing, Mapping) and existing.get("source") in ("provider", "measured"):
            continue
        side["size"] = size


def _start_usage(evidence: Document, usage: BillableUsage) -> None:
    """Give a usage record with no provider start the sandbox's own start, when one is known."""
    start = sandbox_start(evidence, usage)
    if start.value is None:
        return
    for record in (usage["low"], usage["high"]):
        if record["started"].get("at") is None:
            record["started"] = record["started"] | {
                "at": utc_text(start.value),
                "source": start.source,
                "how": start.how,
            }
