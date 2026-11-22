# SPDX-FileCopyrightText: BoxRouter, Inc.
# SPDX-License-Identifier: Apache-2.0
"""A cost in the spec's shape (`reported`, `calculated` or `usage` lines) is priced here.

Core's report keeps the spec's `source` and the line's item as `meter`, marks an `accruing` cost
`final: false`, and gives a `usage` line a quantity and unit with no amount. Finality and the
delay stay this package's: a reading counts only after the adapter says `final` and the
provider's own `revisit.after_s` has passed since the sandbox ended.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from sandbox_provider_pricing import price

ROOT = Path(__file__).resolve().parents[1] / "providers"
#: The Blaxel fixture's destroy returns at this time.
END = datetime.fromisoformat("2026-10-19T19:39:04+00:00")
START = datetime.fromisoformat("2026-10-19T18:39:03+00:00")
AFTER_S = 600


def _text(at: datetime) -> str:
    return at.isoformat().replace("+00:00", "Z")


def _line(source: str, item: str = "memory", **fields: Any) -> dict[str, Any]:
    return {
        "amount": None,
        "currency": "USD",
        "meter": item,
        "interval_start": _text(START),
        "interval_end": _text(END),
        "scope": "sandbox",
        "source": source,
    } | fields


def _evidence(
    readings: list[dict[str, Any]], *, read_after_s: int = AFTER_S + 1, final: bool = True
) -> dict[str, Any]:
    evidence: dict[str, Any] = json.loads(
        (ROOT / "blaxel" / "fixtures" / "core-cost-report" / "evidence.json").read_text()
    )
    cost: dict[str, Any] = {"status": "available", "reason": None, "readings": readings}
    if not final:
        cost["final"] = False
    evidence["provider_reports"] = {
        "read_at": _text(END + timedelta(seconds=read_after_s)),
        "cost": cost,
    }
    return evidence


def test_spec_cost_reported_prices_as_the_sum_of_its_lines_after_the_delay() -> None:
    lines = [_line("reported", amount="0.0010"), _line("reported", "snapshot", amount="0.0005")]
    result = price(_evidence(lines))
    assert (result["label"], result["basis"]) == ("reported", "provider_reported")
    assert result["total"] == {"low": "0.0015", "high": "0.0015"}


def test_spec_cost_reported_still_waits_30_s_after_the_end() -> None:
    result = price(_evidence([_line("reported", amount="0.0010")], read_after_s=30))
    assert (result["label"], result["total"]) == ("unknown", None)


def test_spec_cost_reported_waits_while_the_adapter_says_accruing() -> None:
    result = price(_evidence([_line("reported", amount="0.0010")], final=False))
    assert (result["label"], result["total"]) == ("unknown", None)


def test_spec_cost_ignores_a_report_that_covers_only_part_of_the_sandbox() -> None:
    short = _line("reported", amount="0.0010", interval_end=_text(END - timedelta(minutes=10)))
    assert price(_evidence([short]))["label"] == "unknown"


def test_spec_cost_a_line_without_a_period_is_a_fee_and_adds_to_the_sum() -> None:
    fee = _line("reported", "create", amount="0.0001", interval_start=None, interval_end=None)
    result = price(_evidence([_line("reported", amount="0.0010"), fee]))
    assert result["total"] == {"low": "0.0011", "high": "0.0011"}


def test_spec_cost_usage_is_priced_from_its_quantities_with_our_price_sheet() -> None:
    """4 GB for 3,600 s is 14,400 GB-seconds, at the stored $0.0000115 per GB-second."""
    line = _line("usage", quantity="14400", unit="gb_second")
    result = price(_evidence([line]))
    assert (result["label"], result["basis"]) == ("calculated", "list_price_usage")
    assert result["total"] == {"low": "0.1656", "high": "0.1656"}
    assert result["lines"][0]["quantity"] == "14400"


def test_spec_cost_usage_converts_time_units() -> None:
    hours = price(_evidence([_line("usage", quantity="4", unit="gb_hour")]))
    assert hours["total"] == {"low": "0.1656", "high": "0.1656"}


def test_spec_cost_usage_in_gib_converts_only_where_the_sheet_states_its_gb_size() -> None:
    """Blaxel's memory rate says one of its GB is one base unit (`size_per_unit`), so a quantity in
    GiB is priced by it, as the calculator prices a size. A rate with no such statement never takes
    GiB for GB (`test_spec_cost_providers`)."""
    gib = price(_evidence([_line("usage", quantity="14400", unit="gib_second")]))
    assert (gib["label"], gib["total"]) == ("calculated", {"low": "0.1656", "high": "0.1656"})


def test_spec_cost_usage_ignores_an_amount_the_adapter_sent() -> None:
    line = _line("usage", quantity="14400", unit="gb_second", amount="99")
    assert price(_evidence([line]))["total"] == {"low": "0.1656", "high": "0.1656"}


def test_spec_cost_usage_waits_for_the_delay_and_for_final() -> None:
    line = _line("usage", quantity="14400", unit="gb_second")
    assert price(_evidence([line], read_after_s=30))["label"] == "unknown"
    assert price(_evidence([line], final=False))["label"] == "unknown"


def test_spec_cost_usage_of_an_item_with_no_rate_is_unknown() -> None:
    line = _line("usage", "request", quantity="3", unit="each")
    result = price(_evidence([line]))
    assert (result["label"], result["total"]) == ("unknown", None)


def test_the_old_adapter_readings_are_still_read() -> None:
    old = json.loads(
        (ROOT / "blaxel" / "fixtures" / "core-cost-report" / "evidence.json").read_text()
    )
    assert price(old)["label"] == "reported"
