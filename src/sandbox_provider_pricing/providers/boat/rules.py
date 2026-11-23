# SPDX-FileCopyrightText: BoxRouter, Inc.
# SPDX-License-Identifier: Apache-2.0
"""Boat: the per-sandbox usage record reports the sandbox's cost at list price.

GET /sandboxes/{id}/usage returns billable machine-seconds with the size multiplier already
applied and dollars at list price. The record counts when it names this sandbox and its meter is
not moving (`running` is false). `running: false` also occurs while a refused stop holds the meter
paused. Boat deletes the record with the sandbox, so the last read taken before the delete
counts too, as of that read: the meter stops when Boat receives the delete, so the figure can
fall short by the seconds between the read and the delete, never exceed it. A read of a sandbox
still up, with no end known, can still grow and does not count.
"""

from sandbox_provider_pricing.evidence import decimal_total
from sandbox_provider_pricing.types import BillableUsage, Document, Evidence
from sandbox_provider_pricing.usage import (
    latest_record,
    read_before_end,
    report_cost,
    spec_cost,
    spec_cost_read_before_end,
    waiting_for_record,
)

SOURCE = "boat.sandboxes.usage"


def billable(
    evidence: Evidence,
    billing: Document,
    *,
    as_of: str | None = None,
    **_: object,
) -> BillableUsage:
    result = waiting_for_record(evidence, billing, as_of=as_of)
    # The spec's cost lines first (Boat's in-process provider). An accruing report still counts
    # when it was the last read before Boat deleted the sandbox and its record, as the old record
    # did: Cloud reads just before Boat's own timer ends a sandbox, and no read after can answer.
    # The branch below is for the old adapter's report and stays until it is removed.
    if spec_cost(evidence, billing, result) is not None:
        return spec_cost_read_before_end(evidence, billing, result)
    return _from_record(evidence, result)


def _from_record(evidence: Evidence, result: BillableUsage) -> BillableUsage:
    """The old adapter's usage record, until it is removed after the switch."""
    record = latest_record(evidence, SOURCE)
    if record is None:
        return result
    body = record["body"]
    if not isinstance(body, dict):
        raise ValueError("Boat usage record must be an object")
    if body.get("sandboxId") != evidence.get("sandbox_id"):
        return result
    running = body.get("running")
    taken_at = read_before_end(evidence, record) if running is True else None
    if running is not False and taken_at is None:
        return result
    dollars = body.get("dollars")
    if not isinstance(dollars, (int, float, str)) or isinstance(dollars, bool):
        return result
    try:
        usd = decimal_total([dollars])
    except (ArithmeticError, ValueError):
        return result
    how = f"Boat's usage record for sandbox {body['sandboxId']}: dollars at list price."
    if taken_at is not None:
        how = (
            f"Boat's last usage record for sandbox {body['sandboxId']}, read at {taken_at} before "
            "Boat deleted the sandbox and its record: dollars at list price as of that read."
        )
    return report_cost(result, usd, how, taken_at=taken_at)
