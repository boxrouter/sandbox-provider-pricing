# SPDX-FileCopyrightText: BoxRouter, Inc.
# SPDX-License-Identifier: Apache-2.0
"""Only complete provider lifecycle timestamps can produce billable time."""

from copy import deepcopy
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from sandbox_provider_pricing.usage import default_billable

START = datetime(2026, 10, 11, 12, 0, tzinfo=UTC)
OBSERVED = "2026-10-11T12:01:42Z"


def time_fact(seconds: int, source: str = "recorded") -> dict[str, Any]:
    return {
        "value": (START + timedelta(seconds=seconds)).isoformat().replace("+00:00", "Z"),
        "source": source,
        "how": "test observation",
    }


def sample() -> dict[str, Any]:
    return {
        "provider": "example",
        "sandbox_made": {"value": True, "source": "recorded", "how": "created"},
        "requested": {"cpu": 2, "memory_mib": 4096, "region": "iad", "options": {}},
        "calls": [
            {
                "name": name,
                "sent_at": time_fact(sent),
                "returned_at": time_fact(back),
                "outcome": "returned",
                **({"keeps": "files"} if name == "pause" else {}),
            }
            for name, sent, back in (
                ("create", 0, 2),
                ("pause", 20, 22),
                ("resume", 50, 52),
                ("destroy", 100, 102),
            )
        ],
        "provider_times": [],
        "last_seen_alive": time_fact(90),
        "noticed_gone": time_fact(102),
        "deadline": time_fact(99),
        "measured": {},
        "provider_records": [],
    }


def points(*events: tuple[str, int]) -> list[dict[str, Any]]:
    return [
        {"kind": kind, "at": time_fact(seconds, "provider"), "field": f"provider {kind}"}
        for kind, seconds in events
    ]


def test_call_edges_observations_and_deadlines_never_become_billed_time() -> None:
    result = default_billable(sample())
    assert result["low"] == result["high"]
    assert result["low"]["intervals"][0]["seconds"] is None
    assert result["times"]["start"].value is None
    assert result["times"]["end"].value is None


def test_provider_events_split_running_and_paused_time() -> None:
    evidence = sample()
    evidence["provider_times"] = points(
        ("created", 2), ("paused", 20), ("resumed", 50), ("ended", 99)
    )
    result = default_billable(evidence)
    assert result["low"] == result["high"]
    assert [(item["state"], item["seconds"]) for item in result["low"]["intervals"]] == [
        ("running", 18),
        ("paused", 30),
        ("running", 49),
    ]
    assert all(item["source"] == "provider" for item in result["low"]["intervals"])


def test_call_pause_edges_do_not_split_provider_time() -> None:
    evidence = sample()
    evidence["provider_times"] = points(("created", 2), ("ended", 99))
    result = default_billable(evidence)
    assert [(item["state"], item["seconds"]) for item in result["low"]["intervals"]] == [
        ("running", 97)
    ]


def test_changing_call_clocks_cannot_change_provider_intervals() -> None:
    evidence = sample()
    evidence["provider_times"] = points(("created", 2), ("ended", 99))
    baseline = default_billable(evidence, as_of=OBSERVED)
    changed = deepcopy(evidence)
    for call in changed["calls"]:
        call["sent_at"] = time_fact(-10000)
        call["returned_at"] = time_fact(10000)
    assert default_billable(changed, as_of=OBSERVED) == baseline


@pytest.mark.parametrize(
    "events",
    [(), (("created", 0),), (("ended", 100),), (("created", 0), ("paused", 20), ("resumed", 30))],
)
def test_incomplete_provider_events_leave_time_unknown(events: tuple[tuple[str, int], ...]) -> None:
    evidence = sample()
    evidence["provider_times"] = points(*events)
    result = default_billable(evidence)
    assert result["low"]["intervals"][0]["seconds"] is None


def test_a_terminal_pause_can_close_a_provider_segment() -> None:
    evidence = sample()
    evidence["provider_times"] = points(("created", 0), ("paused", 20))
    result = default_billable(evidence)
    assert result["low"]["intervals"][0]["seconds"] == 20


def test_times_marked_recorded_are_not_provider_times() -> None:
    evidence = sample()
    evidence["provider_times"] = points(("created", 0), ("ended", 100))
    for point in evidence["provider_times"]:
        point["at"]["source"] = "recorded"
    assert default_billable(evidence)["low"]["intervals"][0]["seconds"] is None


def test_refused_create_without_provider_usage_does_not_invent_zero_cost() -> None:
    evidence = sample()
    evidence["sandbox_made"]["value"] = False
    assert default_billable(evidence)["low"]["intervals"][0]["seconds"] is None


def test_the_recorded_class_becomes_the_usage_class() -> None:
    evidence = sample()
    evidence["requested"]["class"] = "vm"
    usage = default_billable(evidence, as_of=OBSERVED)["high"]
    assert usage["class"] == {
        "name": "vm",
        "source": "recorded",
        "observed_at": OBSERVED,
        "how": "The class the sandbox was created in.",
    }


@pytest.mark.parametrize("recorded", [False, True])
def test_no_recorded_class_leaves_the_default_class(recorded: bool) -> None:
    evidence = sample()
    if recorded:
        evidence["requested"]["class"] = None
    assert "class" not in default_billable(evidence)["high"]
