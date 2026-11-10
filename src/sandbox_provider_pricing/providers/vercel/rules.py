# SPDX-FileCopyrightText: BoxRouter, Inc.
# SPDX-License-Identifier: Apache-2.0
"""Vercel: billed time, active CPU and egress from its session records.

Each session record gives a running interval. The gap before the next session is a stopped
interval, priced for the snapshot that links the two sessions.
"""

from datetime import datetime
from typing import Any, NamedTuple

from sandbox_provider_pricing.evidence import report_number
from sandbox_provider_pricing.types import BillableUsage, Document, Evidence, JsonObject, TimeValue
from sandbox_provider_pricing.usage import (
    default_billable,
    parse_datetime,
    read_core_report,
    record_reason,
    unavailable,
    utc_text,
)

SESSIONS = "vercel.sessions.get"
SNAPSHOTS = "vercel.snapshots.get"


class Session(NamedTuple):
    """One completed session record."""

    started: datetime
    stopped: datetime
    read_at: str
    active_cpu_ms: int | float
    egress: int
    body: JsonObject


def billable(
    evidence: Evidence,
    billing: Document,
    *,
    as_of: str | None = None,
    **_: object,
) -> BillableUsage:
    evidence = _core_sessions(evidence)
    result = default_billable(evidence, as_of=as_of)
    records = [record for record in evidence["provider_records"] if record["source"] == SESSIONS]
    if not records:
        observed_at = result["low"]["started"]["observed_at"]
        return unavailable(result, record_reason(evidence, billing, observed_at))
    sessions = _sessions(records)
    if isinstance(sessions, str):
        return unavailable(result, sessions)
    _apply_sessions(result, evidence, sessions)
    return result


def _sessions(records: list[JsonObject]) -> list[Session] | str:
    """The latest record of each session, in start order, or the reason to keep waiting."""
    latest: dict[Any, JsonObject] = {}
    for record in records:
        body = _session_body(record)
        key = body.get("id", body.get("startedAt"))
        previous = latest.get(key)
        if previous is None or record["read_at"] > previous["read_at"]:
            latest[key] = record
    sessions = []
    for record in latest.values():
        session = _session(record)
        if isinstance(session, str):
            return session
        sessions.append(session)
    sessions.sort(key=lambda session: session.started)
    return sessions


def _session_body(record: JsonObject) -> JsonObject:
    body = record["body"]
    if not isinstance(body, dict):
        raise ValueError("Vercel session record must be an object")
    session: JsonObject = body.get("session", body)
    return session


def _session(record: JsonObject) -> Session | str:
    """One session record, checked; the reason to wait if it is not complete yet."""
    body = _session_body(record)
    started_at, stopped_at = body.get("startedAt"), body.get("stoppedAt")
    active_cpu_ms = body.get("activeCpuDurationMs")
    network = body.get("networkTransfer")
    egress = network.get("egress") if isinstance(network, dict) else None
    if started_at is None or stopped_at is None:
        return "Waiting for Vercel's completed session record."
    if not isinstance(started_at, str) or not isinstance(stopped_at, str):
        raise ValueError("Vercel session record needs startedAt and stoppedAt")
    started, stopped = parse_datetime(started_at), parse_datetime(stopped_at)
    if (
        started is None
        or stopped is None
        or started.utcoffset() is None
        or stopped.utcoffset() is None
        or stopped < started
    ):
        raise ValueError("Vercel session record has invalid session times")
    if active_cpu_ms is None or egress is None:
        return "Waiting for Vercel's session CPU and network usage."
    if (
        isinstance(active_cpu_ms, bool)
        or not isinstance(active_cpu_ms, (int, float))
        or active_cpu_ms < 0
    ):
        raise ValueError("Vercel session record needs a non-negative activeCpuDurationMs")
    if isinstance(egress, bool) or not isinstance(egress, int) or egress < 0:
        raise ValueError("Vercel session record needs non-negative networkTransfer.egress bytes")
    return Session(started, stopped, record["read_at"], active_cpu_ms, egress, body)


def _intervals(evidence: Evidence, sessions: list[Session]) -> list[JsonObject]:
    """A running interval per session, and a stopped interval for each gap between two."""
    intervals: list[JsonObject] = []
    for session, following in zip(sessions, [*sessions[1:], None], strict=True):
        running: JsonObject = {
            "state": "running",
            "seconds": round((session.stopped - session.started).total_seconds(), 3),
            "source": "provider",
            "observed_at": session.read_at,
            "how": "Vercel session startedAt to stoppedAt from vercel.sessions.get.",
        }
        allocation = {
            key: session.body[field]
            for key, field in (("cpu", "vcpus"), ("memory_mib", "memory"))
            if field in session.body
        }
        if allocation:
            running["size"] = allocation | {
                "source": "provider",
                "observed_at": session.read_at,
                "how": "Vercel session resource configuration.",
            }
        intervals.append(running)
        if following is None:
            continue
        gap = round((following.started - session.stopped).total_seconds(), 3)
        if gap < 0:
            raise ValueError("Vercel session records overlap")
        if gap:
            intervals.append(
                {
                    "state": "stopped",
                    "seconds": gap,
                    "snapshot_storage": _snapshot_fact(
                        evidence, session.body, following.body, following.read_at
                    ),
                    "source": "provider",
                    "observed_at": following.read_at,
                    "how": (
                        "Gap between stoppedAt and the next startedAt in "
                        "vercel.sessions.get records."
                    ),
                }
            )
    return intervals


def _apply_sessions(result: BillableUsage, evidence: Evidence, sessions: list[Session]) -> None:
    intervals = _intervals(evidence, sessions)
    active_cpu_seconds = 0.0
    for session in sessions:
        active_cpu_seconds += session.active_cpu_ms / 1000
    egress_bytes = sum(session.egress for session in sessions)
    observed_at = sessions[-1].read_at
    for usage in (result["low"], result["high"]):
        usage["intervals"] = intervals
        usage["creations"] = {
            "count": len(sessions),
            "source": "provider",
            "observed_at": observed_at,
            "how": "One session record for each Vercel sandbox session.",
        }
        usage["active_cpu"] = {
            "seconds": active_cpu_seconds,
            "source": "provider",
            "observed_at": observed_at,
            "how": "Sum of activeCpuDurationMs from vercel.sessions.get records.",
        }
        usage["egress"] = {
            "bytes": egress_bytes,
            "source": "provider",
            "observed_at": observed_at,
            "how": "Sum of networkTransfer.egress from vercel.sessions.get records.",
        }
        if any(interval["state"] == "stopped" for interval in intervals):
            usage["snapshot_storage"] = {
                "gb": None,
                "source": "unknown",
                "observed_at": observed_at,
                "how": "Waiting for Vercel's snapshot sizeBytes record.",
            }
        usage["started"] = {
            "at": utc_text(sessions[0].started),
            "source": "provider",
            "observed_at": observed_at,
            "how": "Vercel session startedAt.",
        }
    result["times"] = {
        "start": TimeValue(sessions[0].started, "provider", "Vercel session startedAt."),
        "end": TimeValue(sessions[-1].stopped, "provider", "Vercel session stoppedAt."),
    }


def _core_sessions(evidence: Evidence) -> Evidence:
    found = read_core_report(evidence, "usage")
    if found is None:
        return evidence
    report, observed_at = found
    records = [
        item for item in evidence["provider_records"] if item["source"] not in (SESSIONS, SNAPSHOTS)
    ]
    for record in report.get("records", []):
        if record.get("source") == "vercel.Session" and record.get("scope") == "session":
            body = _core_session_body(record)
            records.append({"source": SESSIONS, "read_at": observed_at, "body": body})
        elif record.get("source") == "vercel.Snapshot" and record.get("scope") == "snapshot":
            size = next(
                (
                    row["value"]
                    for row in record.get("readings", [])
                    if row.get("meter") == "snapshot_size" and row.get("unit") == "byte"
                ),
                None,
            )
            body = {"id": record["id"], "sourceSessionId": record.get("related_id")}
            if size is not None:
                body["sizeBytes"] = report_number(size, integer=True)
            records.append({"source": SNAPSHOTS, "read_at": observed_at, "body": body})
    return {**evidence, "provider_records": records}


def _core_session_body(record: JsonObject) -> JsonObject:
    times = {time["kind"]: time["at"] for time in record.get("times", [])}
    body: JsonObject = {
        "id": record["id"],
        "startedAt": times.get("started"),
        "stoppedAt": times.get("stopped") if record.get("final") else None,
    }
    for row in record.get("readings", []):
        meter, unit = row.get("meter"), row.get("unit")
        if (meter, unit) in (("cpu", "vCPU"), ("memory", "MiB"), ("active_cpu", "ms")):
            key = {"cpu": "vcpus", "memory": "memory", "active_cpu": "activeCpuDurationMs"}[meter]
            body[key] = report_number(row["value"], integer=meter == "memory")
        elif meter == "egress" and unit == "byte":
            body["networkTransfer"] = {"egress": report_number(row["value"], integer=True)}
    return body


def _snapshot_fact(
    evidence: Evidence, previous: JsonObject, following: JsonObject, observed_at: str
) -> JsonObject:
    snapshots = [
        item["body"].get("snapshot", item["body"])
        for item in evidence["provider_records"]
        if item["source"] == SNAPSHOTS and isinstance(item["body"], dict)
    ]
    matches = [
        row
        for row in snapshots
        if (
            following.get("sourceSnapshotId") is not None
            and row.get("id") == following["sourceSnapshotId"]
        )
        or (previous.get("id") is not None and row.get("sourceSessionId") == previous["id"])
    ]
    size = matches[0].get("sizeBytes") if len(matches) == 1 else None
    known = isinstance(size, int) and not isinstance(size, bool) and size >= 0
    return {
        **({"bytes": size} if known else {"gb": None}),
        "source": "provider" if known else "unknown",
        "observed_at": observed_at,
        "how": "Vercel snapshot sizeBytes linked to its source session."
        if known
        else "Waiting for Vercel's snapshot sizeBytes record.",
    }
