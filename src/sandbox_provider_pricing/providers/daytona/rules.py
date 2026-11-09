# SPDX-FileCopyrightText: BoxRouter, Inc.
# SPDX-License-Identifier: Apache-2.0
"""Daytona: the sum of its billed usage periods, from Core's cost report or the usage API."""

from typing import Any

from sandbox_provider_pricing.evidence import core_report, decimal_total, sandbox_cost_readings
from sandbox_provider_pricing.types import BillableUsage, Document, Evidence
from sandbox_provider_pricing.usage import (
    covers_sandbox,
    latest_record,
    parse_datetime,
    report_cost,
    waiting_for_record,
)

SOURCE = "Daytona usage API"
CORE_SOURCE = "Daytona GET /organization/{organizationId}/usage/sandbox"


def billable(
    evidence: Evidence,
    billing: Document,
    *,
    as_of: str | None = None,
    **_: object,
) -> BillableUsage:
    result = waiting_for_record(evidence, billing, as_of=as_of)
    report = core_report(evidence, "cost")
    if report is not None:
        readings = sandbox_cost_readings(report, source=CORE_SOURCE, meter="total")
        if readings and covers_sandbox(evidence, result, readings):
            usd = decimal_total(row["amount"] for row in readings)
            how = "Daytona per-sandbox Core cost report at verified list price."
            report_cost(result, usd, how, readings)
        return result
    record = latest_record(evidence, SOURCE)
    prices = None if record is None else _period_prices(record["body"])
    if prices is not None:
        # The reported figure is the sum of the price of each billed period.
        how = "Sum of price fields in Daytona's billed usage periods."
        report_cost(result, decimal_total(prices), how)
    return result


def _period_prices(periods: Any) -> list[Any] | None:
    """Each billed period's price, or None unless every period has a valid start and end."""
    if not isinstance(periods, list) or not periods:
        return None
    prices = []
    for period in periods:
        if not isinstance(period, dict):
            raise ValueError("Daytona usage record must contain period objects")
        try:
            start = parse_datetime(period.get("startAt"))
            end = parse_datetime(period.get("endAt"))
        except ValueError:
            return None
        if (
            start is None
            or end is None
            or start.utcoffset() is None
            or end.utcoffset() is None
            or end < start
        ):
            return None
        prices.append(period.get("price"))
    return prices
