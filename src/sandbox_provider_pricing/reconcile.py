# SPDX-FileCopyrightText: BoxRouter, Inc.
# SPDX-License-Identifier: Apache-2.0
"""Compare normalized bill rows with the price version effective at each period start."""

from collections import Counter
from decimal import Decimal, InvalidOperation
from typing import Any

from sandbox_provider_pricing._util import decimal_text
from sandbox_provider_pricing.calculator import find_class, find_rate
from sandbox_provider_pricing.types import JsonObject
from sandbox_provider_pricing.versions import price_version

TOLERANCE_USD = Decimal("0.00000000001")


def _decimal_input(value: Any) -> Decimal:
    """Parse a finite decimal value, preserving its exact digits."""
    if isinstance(value, bool) or not isinstance(value, str | int | Decimal):
        raise ValueError("must be a decimal")
    try:
        amount = value if isinstance(value, Decimal) else Decimal(value)
    except InvalidOperation:
        raise ValueError("is not a decimal") from None
    if not amount.is_finite():
        raise ValueError("must be finite")
    return amount


def _decimal(value: Any, field: str, line_number: int) -> Decimal:
    try:
        return _decimal_input(value)
    except ValueError as error:
        raise ValueError(f"bill row {line_number} {field} {error}") from error


def _check_row(
    line_number: int,
    row: JsonObject,
    provider: str,
    versions: list[JsonObject],
) -> JsonObject:
    period_start = row.get("period_start")
    if not isinstance(period_start, str) or not period_start:
        raise ValueError(f"bill row {line_number} needs a period_start")
    selected = price_version(provider, period_start, versions)
    if selected is None:
        raise ValueError(
            f"bill row {line_number} has no {provider} price version effective at {period_start!r}"
        )
    price_class = find_class(selected, None)
    if price_class is None:
        raise ValueError(f"price version {selected['version']!r} has no default class")

    meter = row.get("meter")
    if not isinstance(meter, str) or not meter:
        raise ValueError(f"bill row {line_number} needs a meter")
    rate = find_rate(price_class, meter)
    if rate is None:
        raise ValueError(f"bill row {line_number} has no rate for meter {meter!r}")

    quantity = _decimal(row.get("quantity"), "quantity", line_number)
    cost = _decimal(row.get("cost_usd"), "cost_usd", line_number)
    rate_usd = _decimal(rate.get("usd"), f"{meter} rate", line_number)
    expected = quantity * rate_usd
    difference = abs(cost - expected)
    return {
        "line": line_number,
        "period_start": period_start,
        "price_version": str(selected["version"]),
        "meter": meter,
        "quantity": decimal_text(quantity),
        "unit": rate.get("per"),
        "rate_usd": decimal_text(rate_usd),
        "cost_usd": decimal_text(cost),
        "expected_cost_usd": decimal_text(expected),
        "difference_usd": decimal_text(difference),
        "matched": difference <= TOLERANCE_USD,
    }


def reconcile(rows: list[JsonObject], provider: str, versions: list[JsonObject]) -> JsonObject:
    """Compare normalized bill rows with their period-start rates."""
    checks = [_check_row(number, row, provider, versions) for number, row in enumerate(rows, 1)]
    counts = Counter(check["meter"] for check in checks)
    matched = Counter(check["meter"] for check in checks if check["matched"])
    result: JsonObject = {
        "price_versions": sorted({check["price_version"] for check in checks}),
        "tolerance_usd": decimal_text(TOLERANCE_USD),
        "meters": [
            {"meter": meter, "matched": matched[meter], "rows": rows}
            for meter, rows in sorted(counts.items())
        ],
        "checks": checks,
    }
    return result
