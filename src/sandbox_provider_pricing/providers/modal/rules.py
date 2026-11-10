# SPDX-FileCopyrightText: BoxRouter, Inc.
# SPDX-License-Identifier: Apache-2.0
"""Modal: the hourly billing rows of an App that held only this sandbox or image preparation.

Modal reports cost per App and hour, not per sandbox. A report counts only when its body proves
the App held this one sandbox in the workspace and environment its report target names, it was
read at least the revisit delay after the sandbox ended, and its rows cover each hour it ran, once.

An image preparation has no sandbox: its report target names only its own App. Its report counts
only when the App was stopped, a complete read found no sandbox, function or class in it, the
report was read the revisit delay after the App stopped, and its rows cover each hour the App
existed. An hour with no row is USD 0 only when the request covered it and it had closed before
the read.
"""

import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Literal

from sandbox_provider_pricing.evidence import decimal_total
from sandbox_provider_pricing.types import BillableUsage, Document, Evidence, JsonObject
from sandbox_provider_pricing.usage import (
    latest_record,
    parse_datetime,
    report_cost,
    waiting_for_record,
)

SOURCE = "Modal Workspace.billing.report"
PREPARATION_OUTCOMES = ("succeeded", "failed", "cancelled", "unknown")
_SHA256 = re.compile(r"[0-9a-f]{64}")


@dataclass(frozen=True)
class AppReport:
    """A billing report body for one App, already matched to the sandbox and its namespace."""

    app_id: str
    workspace: str
    environment: str
    rows: list[Any]
    interval: tuple[datetime, datetime] | None
    holds: str


def billable(
    evidence: Evidence,
    billing: Document,
    *,
    as_of: str | None = None,
    **_: object,
) -> BillableUsage:
    result = waiting_for_record(evidence, billing, as_of=as_of)
    accepted = _accepted(evidence, billing, result)
    if accepted is None:
        return result
    report, readings = accepted
    how = (
        f"Modal's hourly billing rows for {report.workspace}/{report.environment} "
        f"App {report.app_id}, proven to hold only {report.holds}."
    )
    empty_hours = [item["interval_start"] for item in readings if item.get("how")]
    if empty_hours:
        how += (
            " The report covered "
            + ", ".join(empty_hours)
            + " and returned no billing row for those hours; each is read as USD 0."
        )
    return report_cost(result, decimal_total(item["amount"] for item in readings), how, readings)


def billed_hours(
    evidence: Evidence, billing: Document, *, as_of: str | None = None
) -> list[tuple[str, str, str]] | None:
    """The (App, hour start, USD) readings a reported cost counts, so totals count each once."""
    result = waiting_for_record(evidence, billing, as_of=as_of)
    accepted = _accepted(evidence, billing, result)
    if accepted is None:
        return None
    report, readings = accepted
    return [(report.app_id, item["interval_start"], item["amount"]) for item in readings]


def _accepted(
    evidence: Evidence, billing: Document, result: BillableUsage
) -> tuple[AppReport, list[JsonObject]] | None:
    """The matched report and its hourly readings, or None while any proof is missing."""
    record = latest_record(evidence, SOURCE)
    if record is None:
        return None
    preparation = _is_preparation(evidence)
    report = (_preparation_report if preparation else _app_report)(record["body"], evidence)
    if report is None:
        return None
    span = _settled_span(record["read_at"], result, evidence, billing)
    if span is None:
        return None
    if preparation and span != _lifecycle(record["body"]):
        return None
    closed_by = parse_datetime(record["read_at"]) if preparation else None
    readings = _hourly_readings(report, _hour_starts(*span), closed_by=closed_by)
    return None if readings is None else (report, readings)


def _is_preparation(evidence: Evidence) -> bool:
    """An image preparation's evidence and report target both name no sandbox."""
    target = evidence.get("report_target")
    return (
        evidence.get("sandbox_id") is None
        and isinstance(target, dict)
        and "sandbox_id" in target
        and target["sandbox_id"] is None
    )


def _app_report(body: Any, evidence: Evidence) -> AppReport | None:
    """The report, if it names one App holding only this sandbox in the requested namespace."""
    found = _namespaced_report(body, evidence)
    if found is None:
        return None
    app_id, workspace, environment = found
    sandbox_id = evidence.get("sandbox_id")
    if body.get("sandbox_ids") != [sandbox_id] or not sandbox_id:
        return None
    rows = body.get("rows")
    if not isinstance(rows, list) or not rows:
        return None
    interval = _report_interval(body.get("interval"))
    return AppReport(app_id, workspace, environment, rows, interval, f"sandbox {sandbox_id}")


def _preparation_report(body: Any, evidence: Evidence) -> AppReport | None:
    """The report, if it names the target's own App and proves it held only one preparation.

    Membership is proof only as complete reads: `sandbox_ids`, `function_ids` and `class_ids`
    each exactly empty. A missing list is an incomplete read, never zero members.
    """
    # pylint: disable=too-many-return-statements
    found = _namespaced_report(body, evidence)
    if found is None:
        return None
    app_id, workspace, environment = found
    if _target_ids(evidence, "app") != [app_id]:
        return None
    if any(body.get(name) != [] for name in ("sandbox_ids", "function_ids", "class_ids")):
        return None
    preparation = body.get("preparation")
    if not isinstance(preparation, dict) or set(preparation) != {"key", "image_id", "outcome"}:
        return None
    key, image_id, outcome = preparation["key"], preparation["image_id"], preparation["outcome"]
    if not isinstance(key, str) or _SHA256.fullmatch(key) is None:
        return None
    if outcome not in PREPARATION_OUTCOMES:
        return None
    if not (image_id is None or (isinstance(image_id, str) and image_id)):
        return None
    if outcome == "succeeded" and image_id is None:
        return None
    if _lifecycle(body) is None:
        return None
    rows = body.get("rows")
    if not isinstance(rows, list):
        return None
    image = f"image {image_id}" if image_id else "no image"
    holds = f"image preparation {key} ({outcome}, {image}) and no sandbox, function or class"
    return AppReport(
        app_id, workspace, environment, rows, _report_interval(body.get("interval")), holds
    )


def _lifecycle(body: JsonObject) -> tuple[datetime, datetime] | None:
    """The stopped App's provider-reported creation and stop times, when both are valid."""
    app = body.get("app")
    if not isinstance(app, dict) or app.get("state") != "stopped":
        return None
    created = parse_datetime(app.get("created_at"))
    stopped = parse_datetime(app.get("stopped_at"))
    if (
        created is None
        or stopped is None
        or created.utcoffset() is None
        or stopped.utcoffset() is None
        or stopped <= created
    ):
        return None
    return created, stopped


def _namespaced_report(body: Any, evidence: Evidence) -> tuple[str, str, str] | None:
    """The body's App, workspace and environment, if they match the report target's account."""
    if not isinstance(body, dict):
        raise ValueError("Modal billing report record must contain an object body")
    app_id = body.get("app_id")
    if not isinstance(app_id, str) or not app_id:
        raise ValueError("Modal billing report body must identify its App")
    expected = _target_namespace(evidence)
    namespace = body.get("namespace")
    if expected is None or not isinstance(namespace, dict):
        return None
    workspace, environment = namespace.get("workspace"), namespace.get("environment")
    if not (
        isinstance(workspace, str) and workspace and isinstance(environment, str) and environment
    ):
        return None
    if expected != (workspace, environment):
        return None
    return app_id, workspace, environment


def _report_interval(value: Any) -> tuple[datetime, datetime] | None:
    """The requested report window when both bounds are valid timezone-aware times."""
    if not isinstance(value, dict):
        return None
    start = parse_datetime(value.get("start"))
    end = parse_datetime(value.get("end"))
    if (
        start is None
        or end is None
        or any(at.utcoffset() is None for at in (start, end))
        or end <= start
    ):
        return None
    return start, end


def _target_namespace(evidence: Evidence) -> tuple[str, str] | None:
    """The (workspace, environment) in the report target's one account identity, if well formed.

    The identity id is JSON text with exactly the non-empty string keys `workspace` and
    `environment`; the adapter writes it compact with sorted keys. Anything else is no proof.
    """
    ids = _target_ids(evidence, "account")
    if ids is None or len(ids) != 1 or not isinstance(ids[0], str):
        return None
    try:
        namespace = json.loads(ids[0])
    except ValueError:
        return None
    if not isinstance(namespace, dict) or set(namespace) != {"workspace", "environment"}:
        return None
    workspace, environment = namespace["workspace"], namespace["environment"]
    if not (
        isinstance(workspace, str) and workspace and isinstance(environment, str) and environment
    ):
        return None
    return workspace, environment


def _target_ids(evidence: Evidence, scope: str) -> list[Any] | None:
    """The report target's identity ids in `scope`, if the target is this sandbox's or none's."""
    target = evidence.get("report_target")
    sandbox_id = evidence.get("sandbox_id")
    if not isinstance(target, dict) or target.get("sandbox_id") != sandbox_id:
        return None
    if sandbox_id is None and not _is_preparation(evidence):
        return None
    return [
        item.get("id")
        for item in target.get("identities", [])
        if isinstance(item, dict) and item.get("scope") == scope
    ]


def _settled_span(
    read_at_text: str, result: BillableUsage, evidence: Evidence, billing: Document
) -> tuple[datetime, datetime] | None:
    """The sandbox's provider start and end, if the report was read after its revisit delay."""
    read_at = parse_datetime(read_at_text)
    observed_at = parse_datetime(result["low"]["started"]["observed_at"])
    if (
        read_at is None
        or read_at.utcoffset() is None
        or observed_at is None
        or observed_at.utcoffset() is None
        or read_at > observed_at
    ):
        return None
    started = _provider_time(evidence, "created", choose="min")
    ended = _provider_time(evidence, "ended", choose="max")
    if started is None or ended is None or ended <= started:
        return None
    revisit = billing.get("revisit")
    if not isinstance(revisit, dict):
        return None
    after_s = revisit.get("after_s")
    if not isinstance(after_s, int) or isinstance(after_s, bool) or after_s < 0:
        raise ValueError("Modal revisit.after_s must be a non-negative integer")
    if (read_at - ended).total_seconds() < after_s:
        return None
    return started, ended


def _hourly_readings(
    report: AppReport, hours: set[datetime], *, closed_by: datetime | None = None
) -> list[JsonObject] | None:
    """One reading per hour, or None unless rows or a covering request account for each hour.

    With `closed_by`, an hour with no row also had to close by then to count as USD 0.
    """
    # pylint: disable=too-many-return-statements
    readings = []
    seen = set()
    for row in report.rows:
        if not isinstance(row, dict):
            raise ValueError("Modal billing report rows must be objects")
        if row.get("object_id") != report.app_id or row.get("environment") != report.environment:
            return None
        start = parse_datetime(row.get("interval_start"))
        if start is None or start.utcoffset() is None:
            raise ValueError("Modal billing rows need timezone-aware interval_start values")
        if start.minute or start.second or start.microsecond:
            raise ValueError("Modal billing intervals must start on the hour")
        if start not in hours or start in seen:
            return None
        seen.add(start)
        readings.append(
            {
                "interval_start": start.isoformat(),
                "interval_end": (start + timedelta(hours=1)).isoformat(),
                "amount": _row_cost(row),
            }
        )
    missing = hours - seen
    if not missing:
        return readings
    if report.interval is None or not hours:
        return None
    start, end = report.interval
    final_hour_end = max(hours) + timedelta(hours=1)
    if start > min(hours) or end < final_hour_end:
        return None
    if closed_by is not None and max(missing) + timedelta(hours=1) > closed_by:
        return None
    readings.extend(
        {
            "interval_start": hour.isoformat(),
            "interval_end": (hour + timedelta(hours=1)).isoformat(),
            "amount": "0",
            "how": "The report covered this hour and returned no billing row.",
        }
        for hour in sorted(missing)
    )
    return readings


def _row_cost(row: JsonObject) -> str:
    """A row's cost, checked against the sum of its per-resource costs."""
    cost = decimal_total([row.get("cost")])
    resources = row.get("cost_by_resource")
    if not isinstance(resources, dict) or not resources:
        raise ValueError("Modal billing rows need a cost_by_resource object")
    if abs(Decimal(decimal_total(resources.values())) - Decimal(cost)) > Decimal("0.00000001"):
        raise ValueError("Modal billing row cost must match its resource total within 1e-8 USD")
    return cost


def _provider_time(
    evidence: Evidence, kind: str, *, choose: Literal["min", "max"]
) -> datetime | None:
    times = [
        at
        for item in evidence["provider_times"]
        if item["kind"] == kind
        and item["at"].get("source") == "provider"
        and (at := parse_datetime(item["at"].get("value"))) is not None
    ]
    if not times:
        return None
    return min(times) if choose == "min" else max(times)


def _hour_starts(started: datetime, ended: datetime) -> set[datetime]:
    current = started.replace(minute=0, second=0, microsecond=0)
    starts = set()
    while current < ended:
        starts.add(current)
        current += timedelta(hours=1)
    return starts
