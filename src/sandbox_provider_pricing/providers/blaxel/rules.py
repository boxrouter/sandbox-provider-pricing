# SPDX-FileCopyrightText: BoxRouter, Inc.
# SPDX-License-Identifier: Apache-2.0
"""Blaxel: the sandbox's hourly cost buckets, from Core's cost report or the metrics API.

Blaxel's hourly buckets are not final straight after the sandbox ends, so both sources are read
only once the billing record's revisit delay has passed.
"""

from datetime import datetime
from typing import Any

from sandbox_provider_pricing.evidence import decimal_total, sandbox_cost_readings
from sandbox_provider_pricing.types import BillableUsage, Document, Evidence, JsonObject
from sandbox_provider_pricing.usage import (
    covers_sandbox,
    latest_record,
    parse_datetime,
    read_core_report,
    report_cost,
    revisit_end,
    waiting_for_record,
)

SOURCE = "Blaxel metrics API"
CORE_SOURCE = "Blaxel account metrics API"


def billable(
    evidence: Evidence,
    billing: Document,
    *,
    as_of: str | None = None,
    **_: object,
) -> BillableUsage:
    result = waiting_for_record(evidence, billing, as_of=as_of)
    end = revisit_end(evidence)
    found = read_core_report(evidence, "cost")
    if found is not None and found[0].get("readings"):
        report, read_at = found
        return _from_core_report(evidence, result, report, read_at, billing)
    record = latest_record(evidence, SOURCE)
    if record is not None:
        _from_metrics(result, record, evidence.get("sandbox_id"), end, billing)
    return result


def _from_core_report(
    evidence: Evidence,
    result: BillableUsage,
    report: JsonObject,
    read_at_text: str,
    billing: Document,
) -> BillableUsage:
    """Report Core's cost readings, once the sandbox's end is known and the delay has passed."""
    read_at = parse_datetime(read_at_text)
    end = revisit_end(evidence)
    if (
        end is None
        or read_at is None
        or (read_at - end).total_seconds() < billing["revisit"]["after_s"]
    ):
        return result
    readings = sandbox_cost_readings(report, source=CORE_SOURCE, meter="hourly_cost")
    if readings and covers_sandbox(evidence, result, readings):
        usd = decimal_total(row["amount"] for row in readings)
        how = "Blaxel per-sandbox Core cost report at verified list price."
        report_cost(result, usd, how, readings)
    return result


def _from_metrics(
    result: BillableUsage,
    record: Document,
    sandbox_id: str | None,
    end: datetime | None,
    billing: Document,
) -> BillableUsage:
    """Report the sum of the sandbox's metric buckets, once the delay has passed."""
    read_at = parse_datetime(record["read_at"])
    if (
        read_at is None
        or read_at.utcoffset() is None
        or (end is not None and (read_at - end).total_seconds() < billing["revisit"]["after_s"])
    ):
        return result
    buckets = _sandbox_buckets(record["body"], sandbox_id)
    if buckets is not None:
        uuid, costs = buckets
        # The sandbox's cost is the sum of its hourly buckets (groupBy=resource_uuid).
        how = f"Sum of hourly cost buckets for Blaxel resource_uuid {uuid}."
        report_cost(result, decimal_total(costs), how)
    return result


def _sandbox_buckets(body: Any, sandbox_id: str | None) -> tuple[str, list[Any]] | None:
    """The sandbox's resource UUID and the cost of each of its buckets, if exactly one row is it."""
    if not isinstance(body, dict) or not isinstance(body.get("data"), list):
        raise ValueError("Blaxel metrics record must contain a data list")
    rows = [
        row
        for row in body["data"]
        if isinstance(row, dict)
        and row.get("resourceType") == "sandbox"
        and row.get("resourceName") == sandbox_id
        and isinstance(row.get("resourceUuid"), str)
    ]
    if len(rows) != 1:
        return None
    series = rows[0].get("timeseries")
    if not isinstance(series, list) or not series:
        return None
    costs = []
    for bucket in series:
        if not isinstance(bucket, dict):
            raise ValueError("Blaxel metrics timeseries must contain bucket objects")
        costs.append(bucket.get("cost"))
    return rows[0]["resourceUuid"], costs
