# SPDX-FileCopyrightText: BoxRouter, Inc.
# SPDX-License-Identifier: Apache-2.0
"""A provider's cost periods are reported only when they leave out none of the sandbox's life."""

from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from sandbox_provider_pricing import price

ROOT = Path(__file__).resolve().parents[1] / "providers"
START = datetime.fromisoformat("2026-10-19T18:39:03+00:00")
#: The fixtures create it at 18:39:03 and its destroy returns at 19:39:04.
END = datetime.fromisoformat("2026-10-19T19:39:04+00:00")
CASES = {
    "blaxel": ("blaxel", "Blaxel account metrics API", "hourly_cost"),
    "daytona": ("daytona", "Daytona GET /organization/{organizationId}/usage/sandbox", "total"),
}


def _text(at: datetime) -> str:
    return at.isoformat().replace("+00:00", "Z")


def _priced(provider: str, *periods: tuple[datetime, datetime], **changes: Any) -> dict[str, Any]:
    evidence = json.loads(
        (ROOT / provider / "fixtures" / "core-cost-report" / "evidence.json").read_text()
    )
    _, source, meter = CASES[provider]
    evidence["provider_reports"]["cost"]["readings"] = [
        {
            "amount": "0.001",
            "currency": "USD",
            "meter": meter,
            "interval_start": _text(begun) if begun else None,
            "interval_end": _text(stopped) if stopped else None,
            "scope": "sandbox",
            "source": source,
        }
        for begun, stopped in periods
    ]
    evidence.update(deepcopy(changes))
    return price(evidence)


@pytest.mark.parametrize("provider", sorted(CASES))
def test_periods_that_cover_the_sandbox_are_reported_in_any_order(provider: str) -> None:
    middle = START + timedelta(minutes=20)
    for periods in (((START, middle), (middle, END)), ((middle, END), (START, middle))):
        assert _priced(provider, *periods)["label"] == "reported"


@pytest.mark.parametrize("provider", sorted(CASES))
def test_a_minute_of_slack_at_each_edge_and_between_periods_is_allowed(provider: str) -> None:
    slack = timedelta(seconds=60)
    middle = START + timedelta(minutes=20)
    assert _priced(provider, (START + slack, middle), (middle + slack, END - slack))["label"] == (
        "reported"
    )
    late = timedelta(seconds=61)
    assert _priced(provider, (START + late, END))["label"] == "unknown"
    assert _priced(provider, (START, END - late))["label"] == "unknown"
    assert _priced(provider, (START, middle), (middle + late, END))["label"] == "unknown"


@pytest.mark.parametrize("provider", sorted(CASES))
def test_periods_that_leave_out_part_of_the_sandbox_stay_unknown(provider: str) -> None:
    middle = START + timedelta(minutes=20)
    for periods in (
        ((START, middle),),  # the end has not arrived
        ((middle, END),),  # the start has not arrived
        ((START, START + timedelta(minutes=5)), (middle, END)),  # a stretch is missing
    ):
        result = _priced(provider, *periods)
        assert (result["label"], result["total"]) == ("unknown", None)
        assert result["held_back_by"]


@pytest.mark.parametrize("provider", sorted(CASES))
def test_a_period_without_both_times_cannot_show_coverage(provider: str) -> None:
    result = _priced(provider, (START, END), (None, None))  # type: ignore[arg-type]
    assert result["label"] == "unknown"


def test_nothing_is_held_back_when_the_sandbox_has_no_known_times() -> None:
    """Daytona asks no end of the sandbox; Blaxel waits for one before it reports at all."""
    result = _priced("daytona", (START, START + timedelta(minutes=5)), calls=[])
    assert result["label"] == "reported"
