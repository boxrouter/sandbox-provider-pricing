# SPDX-FileCopyrightText: BoxRouter, Inc.
# SPDX-License-Identifier: Apache-2.0
"""Public provider revisit policy and schedule boundary tests."""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from sandbox_provider_pricing import RevisitPolicy, price, revisit, scheduled_revisit
from sandbox_provider_pricing.providers import provider_ids

ENDED = datetime(2026, 1, 1, tzinfo=UTC)


def test_every_provider_has_a_complete_policy() -> None:
    expected = {
        "agent37": (60, 604800, 1800),
        "blaxel": (600, 604800, 3600),
        "boat": (15, 900, 300),
        "boxd": (1500, 604800, 900),
        "daytona": (120, 259200, 3600),
        "e2b": (15, 604800, 3600),
        "modal": (600, 604800, 3600),
        "vercel": (120, 604800, 3600),
    }
    for provider in provider_ids():
        # A provider scaffolded before its schedule is verified has no policy to re-read by.
        policy = scheduled_revisit(provider)
        times = expected.get(provider)
        if times is None:
            assert policy is None
        else:
            assert policy is not None
            assert (policy.after_s, policy.until_s, policy.interval_s) == times


def test_first_read_is_anchored_at_end() -> None:
    policy = RevisitPolicy(after_s=15, until_s=20000, interval_s=3600)
    assert policy.next_read(ENDED) == ENDED + timedelta(seconds=15)


def test_pre_first_read_keeps_first_scheduled_time() -> None:
    policy = RevisitPolicy(after_s=600, until_s=20000, interval_s=3600)
    last = ENDED + timedelta(seconds=5)
    assert policy.next_read(ENDED, last_read_at=last) == ENDED + timedelta(seconds=600)


def test_second_arithmetic_normalizes_across_dst_transition() -> None:
    policy = RevisitPolicy(after_s=600, until_s=7200, interval_s=3600)
    before_spring_forward = datetime(2026, 3, 8, 1, 55, tzinfo=ZoneInfo("America/Toronto"))
    assert policy.next_read(before_spring_forward) == datetime(2026, 3, 8, 7, 5, tzinfo=UTC)


def test_repeat_read_uses_interval_from_last_read() -> None:
    policy = RevisitPolicy(after_s=15, until_s=20000, interval_s=3600)
    last = ENDED + timedelta(seconds=7200)
    assert policy.next_read(ENDED, last_read_at=last) == last + timedelta(seconds=3600)


def test_repeat_read_is_clamped_to_final_boundary() -> None:
    policy = RevisitPolicy(after_s=0, until_s=10000, interval_s=3600)
    last = ENDED + timedelta(seconds=8000)
    assert policy.next_read(ENDED, last_read_at=last) == ENDED + timedelta(seconds=10000)


def test_read_at_or_after_boundary_stops() -> None:
    policy = RevisitPolicy(after_s=0, until_s=10000, interval_s=3600)
    assert policy.next_read(ENDED, last_read_at=ENDED + timedelta(seconds=10000)) is None
    assert policy.next_read(ENDED, last_read_at=ENDED + timedelta(seconds=10001)) is None


def test_single_report_does_not_change_schedule_or_window() -> None:
    policy = revisit("daytona")
    first = policy.next_read(ENDED)
    assert first is not None
    later = policy.next_read(ENDED, last_read_at=first)
    assert later is not None
    assert first == ENDED + timedelta(seconds=120)
    assert later == ENDED + timedelta(seconds=120 + 3600)
    assert policy.may_change(ENDED, as_of=later)


def test_may_change_stops_exactly_at_boundary() -> None:
    policy = RevisitPolicy(after_s=0, until_s=100, interval_s=10)
    assert policy.may_change(ENDED, as_of=ENDED + timedelta(seconds=99))
    assert not policy.may_change(ENDED, as_of=ENDED + timedelta(seconds=100))


@pytest.mark.parametrize(
    "arguments",
    [
        {"after_s": -1, "until_s": 1, "interval_s": 1},
        {"after_s": 2, "until_s": 1, "interval_s": 1},
        {"after_s": 0, "until_s": 1, "interval_s": 0},
        {"after_s": True, "until_s": 1, "interval_s": 1},
    ],
)
def test_malformed_policy_is_rejected(arguments: dict[str, int]) -> None:
    with pytest.raises((TypeError, ValueError)):
        RevisitPolicy(**arguments)


def test_naive_datetime_is_rejected() -> None:
    policy = RevisitPolicy(after_s=0, until_s=1, interval_s=1)
    with pytest.raises(ValueError, match="timezone-aware"):
        policy.next_read(datetime(2026, 1, 1))


def test_reported_amount_stays_nonfinal_and_has_next_read() -> None:
    root = Path(__file__).resolve().parents[1]
    evidence = json.loads(
        (root / "providers/daytona/fixtures/best/evidence.json").read_text(encoding="utf-8")
    )
    evidence["provider_records"][0]["read_at"] = "2026-10-20T12:00:01Z"
    result = price(evidence, as_of="2026-10-20T12:00:01Z")
    assert result["label"] == "reported"
    assert result["final"] is False
    assert result["revisit"]["next_read_at"] is not None


def test_price_early_raw_read_keeps_provider_first_read_time() -> None:
    evidence = json.loads(
        (
            Path(__file__).resolve().parents[1] / "providers/blaxel/fixtures/best/evidence.json"
        ).read_text(encoding="utf-8")
    )
    initial = price(evidence)
    assert initial["revisit"] is not None
    first = datetime.fromisoformat(initial["revisit"]["after"].replace("Z", "+00:00"))
    ended = first - timedelta(seconds=revisit("blaxel").after_s)
    early_read = ended + timedelta(seconds=5)
    evidence["provider_records"][0]["read_at"] = early_read.isoformat()
    result = price(evidence, as_of=early_read.isoformat())
    assert result["revisit"]["next_read_at"] == first.isoformat().replace("+00:00", "Z")


def test_window_boundary_is_final_and_does_not_invent_a_cost() -> None:
    evidence = json.loads(
        (
            Path(__file__).resolve().parents[1] / "providers/blaxel/fixtures/best/evidence.json"
        ).read_text(encoding="utf-8")
    )
    evidence["provider_records"] = []
    pending = price(evidence)
    assert pending["revisit"] is not None
    boundary = datetime.fromisoformat(pending["revisit"]["until"].replace("Z", "+00:00"))
    result = price(evidence, as_of=boundary.isoformat())
    assert result["label"] == "unknown"
    assert result["total"] is None
    assert result["final"] is True
    assert result["revisit"] is None


def test_no_known_end_is_nonfinal_without_scheduled_read() -> None:
    root = Path(__file__).resolve().parents[1]
    evidence = json.loads(
        (root / "providers/modal/fixtures/primitives/evidence.json").read_text(encoding="utf-8")
    )
    evidence["provider_times"] = []
    evidence["calls"] = [call for call in evidence["calls"] if call["name"] != "destroy"]
    evidence["noticed_gone"] = None
    evidence["deadline"] = None
    result = price(evidence, as_of="2026-10-20T12:00:00Z")
    assert result["final"] is False
    assert result["revisit"] is None


def test_never_created_is_final_without_cost() -> None:
    root = Path(__file__).resolve().parents[1]
    evidence = json.loads(
        (root / "providers/modal/fixtures/primitives/evidence.json").read_text(encoding="utf-8")
    )
    evidence["sandbox_made"]["value"] = False
    result = price(
        evidence,
        as_of="2026-10-20T12:00:00Z",
        ended_at=datetime(2026, 10, 20, 11, tzinfo=UTC),
    )
    assert result["label"] == "unknown"
    assert result["total"] is None
    assert result["final"] is True
    assert result["revisit"] is None


def test_explicit_ended_at_overrides_billing_end_only_for_scheduling() -> None:
    root = Path(__file__).resolve().parents[1]
    evidence = json.loads(
        (root / "providers/modal/fixtures/primitives/evidence.json").read_text(encoding="utf-8")
    )
    ended = datetime(2026, 10, 11, 15, tzinfo=UTC)
    baseline = price(evidence)
    result = price(evidence, ended_at=ended)
    assert result["revisit"]["after"] == "2026-10-11T15:10:00Z"
    assert result["steps"]["usage"] == baseline["steps"]["usage"]


def test_without_terminal_anchor_billed_end_and_pause_do_not_schedule() -> None:
    root = Path(__file__).resolve().parents[1]
    evidence = json.loads(
        (root / "providers/vercel/fixtures/deep-swe/evidence.json").read_text(encoding="utf-8")
    )
    evidence["calls"] = [call for call in evidence["calls"] if call["name"] != "destroy"]
    evidence["noticed_gone"] = None
    evidence["provider_times"] = [
        time for time in evidence["provider_times"] if time["kind"] in ("paused", "billed_end")
    ]
    result = price(evidence)
    assert result["final"] is False
    assert result["revisit"] is None
