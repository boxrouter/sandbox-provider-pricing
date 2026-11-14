# SPDX-FileCopyrightText: BoxRouter, Inc.
# SPDX-License-Identifier: Apache-2.0
"""Agent37: the instance's compute spend, from the workspace usage report Core's cost report reads.

The adapter reports an instance's cost once the instance reads as deleted and the usage report
lists it. Its reading is the instance's whole spend (`total_micros`), which also
counts managed services (LLM, search, tools) billed to the instance. The sandbox's price is its
compute alone (`compute_micros` of the same usage entry): those services are not part of a
sandbox and the billing record leaves them out.
"""

from decimal import Decimal
from typing import TypeGuard

from sandbox_provider_pricing.evidence import core_report, sandbox_cost_readings
from sandbox_provider_pricing.types import BillableUsage, Document, Evidence
from sandbox_provider_pricing.usage import (
    covers_sandbox,
    latest_record,
    report_cost,
    waiting_for_record,
)

SOURCE = "agent37.usage"
METER = "instance_total"


def billable(
    evidence: Evidence,
    billing: Document,
    *,
    as_of: str | None = None,
    **_: object,
) -> BillableUsage:
    result = waiting_for_record(evidence, billing, as_of=as_of)
    report = core_report(evidence, "cost")
    readings = [] if report is None else sandbox_cost_readings(report, source=SOURCE, meter=METER)
    record = latest_record(evidence, SOURCE)
    if len(readings) != 1 or record is None or not isinstance(record["body"], dict):
        return result
    compute = _compute_micros(evidence, record["body"], readings[0])
    if compute is None or not covers_sandbox(evidence, result, readings):
        return result
    return report_cost(
        result,
        format(Decimal(compute) / 1_000_000, "f"),
        "Agent37's settled compute_micros for this instance in its workspace usage report; "
        "managed services billed to the instance are left out.",
    )


def _compute_micros(evidence: Evidence, body: Document, reading: Document) -> int | None:
    """The instance's compute spend in USD millionths, when the usage entry is this sandbox's
    and its total is the total the settled reading reports; otherwise None."""
    compute, total = body.get("compute_micros"), body.get("total_micros")
    sandbox_id = evidence.get("sandbox_id")
    if (
        not sandbox_id
        or body.get("id") != sandbox_id
        or not _micros(compute)
        or not _micros(total)
        or Decimal(total) != Decimal(reading["amount"]) * 1_000_000
    ):
        return None
    return compute


def _micros(value: object) -> TypeGuard[int]:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0
