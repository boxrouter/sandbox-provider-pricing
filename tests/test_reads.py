# SPDX-FileCopyrightText: BoxRouter, Inc.
# SPDX-License-Identifier: Apache-2.0
"""One schedule for reading a sandbox's provider records again."""

from __future__ import annotations

import sys
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from sandbox_provider_pricing import (
    RevisitPolicy,
    compose,
    next_read,
    price,
    record_evidence,
    revisit,
    scheduled_revisit,
)
from sandbox_provider_pricing.providers import bundled_billing, provider_ids, validate_billing

ENDED = datetime(2026, 10, 20, 12, tzinfo=UTC)


def _unpriced(provider: str, now: datetime) -> dict[str, Any]:
    """A sandbox that ended at ENDED whose provider records have not arrived, read at `now`."""
    result = price(
        record_evidence({"provider": provider, "sandbox_id": "native"}),
        as_of=now.isoformat().replace("+00:00", "Z"),
        ended_at=ENDED,
    )
    assert result["label"] == "unknown"
    return result


def _cloud_next_read(result: dict[str, Any], now: datetime, ended_at: datetime) -> datetime | None:
    """Cloud's rule as it stood in `ProviderRevisit.next_read` before this function replaced it."""
    window, first = timedelta(minutes=30), timedelta(seconds=15)
    next_text = None if result["revisit"] is None else result["revisit"]["next_read_at"]
    planned = (
        None if next_text is None else datetime.fromisoformat(next_text.replace("Z", "+00:00"))
    )
    if result["final"] or planned is None:
        return None
    if result["label"] != "unknown" or now - ended_at >= window:
        return planned
    return min(planned, now + max(first, (now - ended_at) / 2))


@pytest.mark.parametrize(
    ("minutes", "wait"),
    [(1, timedelta(seconds=30)), (10, timedelta(minutes=5)), (40, timedelta(minutes=60))],
)
def test_an_unpriced_sandbox_is_read_again_as_cloud_reads_it_today(
    minutes: int, wait: timedelta
) -> None:
    """Soon after the end, half the time since the end; after 30 minutes, the policy's hourly
    cadence (the first read at one minute is the e2b policy's 15 s after the end)."""
    now = ENDED + timedelta(minutes=minutes)
    result = _unpriced("e2b", now)
    expected = _cloud_next_read(result, now, ENDED)
    assert next_read(result, ENDED, now) == expected == now + wait


def test_every_provider_follows_cloud_for_a_young_unpriced_sandbox() -> None:
    for provider in provider_ids():
        for seconds in (0, 15, 60, 600, 1799, 1800, 2400, 7200):
            now = ENDED + timedelta(seconds=seconds)
            result = _unpriced(provider, now)
            assert next_read(result, ENDED, now) == _cloud_next_read(result, now, ENDED)


def test_the_soonest_read_is_never_closer_than_the_shortest_wait() -> None:
    now = ENDED + timedelta(seconds=2)
    result = _unpriced("e2b", now)
    assert next_read(result, ENDED, now) == ENDED + timedelta(seconds=15)  # the policy's first read
    late = ENDED + timedelta(seconds=20)
    assert next_read(_unpriced("e2b", late), ENDED, late) == late + timedelta(seconds=15)


def test_a_priced_sandbox_follows_the_policy_alone() -> None:
    now = ENDED + timedelta(minutes=5)
    result = _unpriced("e2b", now) | {"label": "calculated"}
    assert next_read(result, ENDED, now) == ENDED + timedelta(minutes=5, hours=1)


def test_a_final_result_or_one_without_a_schedule_is_not_read_again() -> None:
    now = ENDED + timedelta(minutes=5)
    result = _unpriced("e2b", now)
    assert next_read(result | {"final": True}, ENDED, now) is None
    assert next_read(result | {"revisit": None}, ENDED, now) is None
    long_after = ENDED + timedelta(days=8)
    closed = _unpriced("e2b", long_after)
    assert closed["final"] and next_read(closed, ENDED, long_after) is None


def test_a_composed_result_is_due_when_its_earliest_part_is() -> None:
    now = ENDED + timedelta(minutes=10)
    young = _unpriced("e2b", now)
    done = _unpriced("e2b", ENDED + timedelta(days=8))
    assert next_read(compose([young, done]), ENDED, now) == now + timedelta(minutes=5)
    assert next_read(compose([done]), ENDED, now) is None


def test_times_need_a_zone() -> None:
    result = _unpriced("e2b", ENDED)
    with pytest.raises(ValueError, match="ended_at"):
        next_read(result, ENDED.replace(tzinfo=None), ENDED)
    with pytest.raises(ValueError, match="now"):
        next_read(result, ENDED, ENDED.replace(tzinfo=None))


def test_the_sooner_reads_default_to_cloud_s_constants_and_billing_can_set_them() -> None:
    assert all(
        (policy.unpriced_window_s, policy.unpriced_first_s) == (1800, 15)
        for policy in map(scheduled_revisit, provider_ids())
        if policy is not None
    )
    document = bundled_billing("e2b")["revisit"]
    assert "unpriced_window_s" not in document  # the defaults stand until a provider sets them
    tuned = RevisitPolicy(15, 604800, 3600, unpriced_window_s=60, unpriced_first_s=5)
    assert (tuned.unpriced_window_s, tuned.unpriced_first_s) == (60, 5)
    with pytest.raises(ValueError, match="unpriced"):
        RevisitPolicy(15, 604800, 3600, unpriced_first_s=0)


def test_a_providers_billing_document_sets_its_own_sooner_reads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document = deepcopy(dict(bundled_billing("e2b")))
    document["revisit"] |= {"unpriced_window_s": 60, "unpriced_first_s": 5}
    validate_billing(document)
    now = ENDED + timedelta(seconds=40)
    result = _unpriced("e2b", now)
    module = sys.modules["sandbox_provider_pricing.revisit"]  # the package name holds the function
    monkeypatch.setattr(module, "bundled_billing", lambda _: document)
    assert revisit("e2b").unpriced_window_s == 60
    assert next_read(result, ENDED, now) == now + timedelta(seconds=20)  # half of 40 s
    later = ENDED + timedelta(seconds=90)  # past this provider's 60 s window
    assert next_read(_unpriced("e2b", later), ENDED, later) == later + timedelta(hours=1)
    document["revisit"]["unpriced_first_s"] = 0
    with pytest.raises(ValueError, match="unpriced_first_s"):
        validate_billing(document)
