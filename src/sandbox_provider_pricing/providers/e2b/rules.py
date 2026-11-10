# SPDX-FileCopyrightText: BoxRouter, Inc.
# SPDX-License-Identifier: Apache-2.0
"""E2B: billed time from its lifecycle events, and each run's size from the event that ends it.

Events come from E2B's webhook or lifecycle API, or from Core's usage report. Usage stays unknown
until there is a provider event for every lifecycle call that returned.
"""

from datetime import datetime
from typing import Any

from sandbox_provider_pricing.evidence import (
    report_number,
    validate_derived,
    validated,
)
from sandbox_provider_pricing.types import BillableUsage, Document, Evidence, JsonObject
from sandbox_provider_pricing.usage import (
    default_billable,
    parse_datetime,
    read_core_report,
    record_reason,
    unavailable,
)

SOURCES = ("E2B lifecycle webhook", "E2B lifecycle API")
EVENT_KINDS = {
    "sandbox.lifecycle.created": "created",
    "sandbox.lifecycle.paused": "paused",
    "sandbox.lifecycle.resumed": "resumed",
    "sandbox.lifecycle.killed": "ended",
}
CALL_EVENTS = {"create": "created", "pause": "paused", "resume": "resumed", "destroy": "ended"}
Execution = JsonObject


def billable(
    evidence: Evidence,
    billing: Document,
    *,
    as_of: str | None = None,
    **_: object,
) -> BillableUsage:
    given = evidence
    evidence = _core_events(evidence)
    times, executions = _lifecycle_times(evidence)
    derived = dict(evidence) | {"provider_times": times}
    validate_derived(given, derived)
    with validated(derived):
        result = default_billable(derived, as_of=as_of)
    reason = record_reason(evidence, billing, result["low"]["started"]["observed_at"])
    if result["low"]["intervals"][0]["source"] == "unknown" or _missing_events(evidence, times):
        return unavailable(result, reason)
    _apply_execution_sizes(result, times, executions)
    return result


def _lifecycle_times(
    evidence: Evidence,
) -> tuple[list[JsonObject], dict[tuple[str, datetime], Execution]]:
    """The provider times with each new E2B event added, and the execution each event reports."""
    times = [item for item in evidence["provider_times"] if item["kind"] in EVENT_KINDS.values()]
    executions: dict[tuple[str, datetime], Execution] = {}
    for record in evidence["provider_records"]:
        if record["source"] not in SOURCES:
            continue
        bodies = record["body"] if isinstance(record["body"], list) else [record["body"]]
        for body in bodies:
            event = _event(body, evidence.get("sandbox_id"))
            if event is None:
                continue
            kind, at, stamp, execution = event
            if isinstance(execution, dict):
                executions[(kind, at)] = execution
            if not any(
                item["kind"] == kind and parse_datetime(item["at"].get("value")) == at
                for item in times
            ):
                times.append(
                    {
                        "kind": kind,
                        "at": {"value": stamp, "source": "provider", "how": "E2B lifecycle event."},
                        "field": f"E2B event {kind}",
                    }
                )
    return times, executions


def _event(body: Any, sandbox_id: str | None) -> tuple[str, datetime, str, Any] | None:
    """One lifecycle event of this sandbox as (kind, time, timestamp, execution); None if not."""
    if not isinstance(body, dict):
        raise ValueError("E2B lifecycle record must contain event objects")
    event_type = body.get("type")
    if not isinstance(event_type, str):
        raise ValueError("E2B lifecycle event needs a type")
    kind = EVENT_KINDS.get(event_type)
    if (
        kind is None
        or sandbox_id is None
        or body.get("sandbox_id", body.get("sandboxId")) != sandbox_id
    ):
        return None
    stamp = body.get("timestamp")
    at = parse_datetime(stamp) if isinstance(stamp, str) else None
    if not isinstance(stamp, str) or at is None or at.utcoffset() is None:
        raise ValueError("E2B lifecycle event needs a timezone-aware timestamp")
    data = body.get("event_data", body.get("eventData")) or {}
    return kind, at, stamp, data.get("execution")


def _missing_events(evidence: Evidence, times: list[JsonObject]) -> bool:
    """Whether a lifecycle call returned more often than E2B reported its event."""
    for call, kind in CALL_EVENTS.items():
        returned = sum(
            item["name"] == call and item["outcome"] == "returned" for item in evidence["calls"]
        )
        reported = sum(
            item["kind"] == kind and item["at"].get("source") == "provider" for item in times
        )
        if returned > reported:
            return True
    return False


def _apply_execution_sizes(
    result: BillableUsage,
    times: list[JsonObject],
    executions: dict[tuple[str, datetime], Execution],
) -> None:
    """Give each running interval the allocation in the execution of the event that ends it."""
    terminals: list[tuple[datetime, str]] = [
        (at, item["kind"])
        for item in times
        if item["kind"] in ("paused", "ended")
        and item["at"].get("source") == "provider"
        and (at := parse_datetime(item["at"].get("value"))) is not None
    ]
    terminals.sort(key=lambda pair: pair[0])
    for usage in (result["low"], result["high"]):
        running = [item for item in usage["intervals"] if item["state"] == "running"]
        for interval, (at, kind) in zip(running, terminals, strict=False):
            execution = executions.get((kind, at)) or {}
            size = {
                key: execution[field]
                for key, field in (("cpu", "vcpu_count"), ("memory_mib", "memory_mb"))
                if field in execution
            }
            interval["size"] = size | {
                "source": "provider" if size else "unknown",
                "observed_at": interval["observed_at"],
                "how": (
                    "E2B event execution allocation; execution_time is not used."
                    if size
                    else "E2B's event did not include the sandbox's size."
                ),
            }


def _core_events(evidence: Evidence) -> Evidence:
    found = read_core_report(evidence, "usage")
    if found is None:
        return evidence
    report, observed_at = found
    records = list(evidence["provider_records"])
    for record in report.get("records", []):
        prefix = "E2B event "
        event_type = record.get("source", "").removeprefix(prefix)
        kind = EVENT_KINDS.get(event_type)
        if not record.get("source", "").startswith(prefix) or kind is None:
            continue
        event_time = next(
            (time["at"] for time in record.get("times", []) if time["kind"] == kind), None
        )
        if event_time is None:
            continue
        execution = {}
        for row in record.get("readings", []):
            meter, unit = row.get("meter"), row.get("unit")
            if meter == "cpu" and unit == "vCPU":
                execution["vcpu_count"] = report_number(row["value"])
            elif meter == "memory" and unit == "MiB":
                execution["memory_mb"] = report_number(row["value"], integer=True)
            elif meter == "execution_time" and unit == "ms":
                execution["execution_time"] = report_number(row["value"])
        records.append(
            {
                "source": "E2B lifecycle API",
                "read_at": observed_at,
                "body": {
                    "id": record["id"],
                    "type": event_type,
                    "timestamp": event_time,
                    "sandbox_id": evidence.get("sandbox_id"),
                    "event_data": {"execution": execution} if execution else {},
                },
            }
        )
    return {**evidence, "provider_records": records}
