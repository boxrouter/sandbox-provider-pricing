# SPDX-FileCopyrightText: BoxRouter, Inc.
# SPDX-License-Identifier: Apache-2.0
"""boxd's complete USD machine usage, checked against the stored list rates."""

from collections.abc import Sequence
from decimal import Decimal

from sandbox_provider_pricing.types import BillableUsage, Document, Evidence
from sandbox_provider_pricing.usage import (
    covers_sandbox,
    latest_record,
    report_cost,
    sandbox_start,
    stored_rates_match,
    utc_text,
    waiting_for_record,
)

SOURCE = "boxd.machines.usage"
#: boxd's micro-USD usage rates, keyed by the stored-rate resource each field prices.
RATE_FIELDS = {
    "cpu": "vcpu_hour_micro",
    "memory": "ram_gib_hour_micro",
    "disk": "disk_gib_hour_micro",
}


def billable(
    evidence: Evidence,
    billing: Document,
    *,
    as_of: str | None = None,
    versions: Sequence[Document] | None = None,
) -> BillableUsage:
    result = waiting_for_record(evidence, billing, as_of=as_of)
    record = latest_record(evidence, SOURCE)
    if record is None or not isinstance(record["body"], dict):
        return result
    body = record["body"]
    cost = body.get("cost_micro")
    usable = (
        bool(evidence.get("sandbox_id"))
        and body.get("machine_id") == evidence.get("sandbox_id")
        and body.get("complete") is True
        and body.get("currency") == "usd"
    )
    if not usable or not isinstance(cost, int) or isinstance(cost, bool) or cost < 0:
        return result
    # boxd reports no lifecycle times, so the sandbox's start is its recorded create. Price takes
    # the same start to select the version it rates with.
    rates_match = stored_rates_match(
        "boxd",
        result["low"]["started"].get("at") or utc_text(sandbox_start(evidence, result).value),
        body.get("rates"),
        RATE_FIELDS,
        versions,
    )
    if rates_match is None or not isinstance(body.get("period"), dict):
        return result
    if not rates_match:
        for usage in (result["low"], result["high"]):
            usage["intervals"][0]["how"] = (
                "boxd usage rates do not match the stored USD list rates."
            )
        return result
    period = body["period"]
    periods = [{"interval_start": period.get("start"), "interval_end": period.get("end")}]
    if not covers_sandbox(evidence, result, periods):
        return result
    return report_cost(
        result,
        format(Decimal(cost) / 1_000_000, "f"),
        "boxd's complete machine usage cost_micro in USD, with rates checked against list price; "
        "not an invoice settlement.",
    )
