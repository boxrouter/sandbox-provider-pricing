# SPDX-FileCopyrightText: BoxRouter, Inc.
# SPDX-License-Identifier: Apache-2.0
"""A provider that deletes its record with the sandbox is priced from its last read before."""

import json
from copy import deepcopy
from pathlib import Path
from typing import Any, cast

import pytest

from sandbox_provider_pricing import price
from sandbox_provider_pricing.record import merge_reports
from sandbox_provider_pricing.usage import read_before_end

ROOT = Path(__file__).resolve().parents[1]
BEST = ROOT / "providers/boat/fixtures/best/evidence.json"


def _evidence() -> dict[str, Any]:
    """The best fixture, with its stopped record replaced by a read taken just before the delete."""
    evidence = cast(dict[str, Any], json.loads(BEST.read_text(encoding="utf-8")))
    record = evidence["provider_records"][0]
    record["read_at"] = "2026-11-01T04:04:59Z"
    record["body"].update(until="2026-11-01T04:04:59Z", seconds=289, dollars=0.00289, running=True)
    return evidence


def test_last_read_before_the_delete_is_reported_taken_at_the_read() -> None:
    result = price(_evidence())
    assert result["label"] == "reported"
    assert result["total"] == {"low": "0.00289", "high": "0.00289"}
    assert result["reported"]["taken_at"] == "2026-11-01T04:04:59Z"
    assert "before Boat deleted the sandbox" in result["reported"]["how"]


def test_a_final_record_carries_no_taken_at() -> None:
    best = json.loads(BEST.read_text("utf-8"))
    assert "taken_at" not in price(best)["reported"]


def test_a_running_read_with_no_known_end_is_not_a_cost() -> None:
    evidence = _evidence()
    evidence["calls"] = [call for call in evidence["calls"] if call["name"] != "destroy"]
    result = price(evidence)
    assert (result["label"], result["total"]) == ("unknown", None)


def test_a_destroy_that_did_not_return_is_not_an_end() -> None:
    evidence = _evidence()
    for call in evidence["calls"]:
        if call["name"] == "destroy":
            call["outcome"] = "unknown"
            call["returned_at"] = None
    assert price(evidence)["total"] is None


def test_a_sandbox_noticed_gone_ends_the_last_read() -> None:
    evidence = _evidence()
    evidence["calls"] = [call for call in evidence["calls"] if call["name"] != "destroy"]
    evidence["noticed_gone"] = {
        "value": "2026-11-01T04:06:00Z",
        "source": "recorded",
        "how": "first listing without it",
    }
    assert price(evidence)["total"] == {"low": "0.00289", "high": "0.00289"}


def test_a_read_after_the_end_is_not_a_read_before_it() -> None:
    evidence = _evidence()
    evidence["provider_records"][0]["read_at"] = "2026-11-01T04:05:30Z"
    assert price(evidence)["total"] is None


def test_the_latest_read_wins_and_a_missing_record_never_becomes_zero() -> None:
    evidence = _evidence()
    earlier = deepcopy(evidence["provider_records"][0])
    earlier["read_at"] = "2026-11-01T04:04:00Z"
    earlier["body"].update(seconds=240, dollars=0.0024)
    evidence["provider_records"].insert(0, earlier)
    assert price(evidence)["total"]["low"] == "0.00289"
    evidence["provider_records"] = []
    result = price(evidence)
    assert (result["label"], result["total"]) == ("unknown", None)


def test_another_sandbox_record_is_not_this_ones_cost() -> None:
    evidence = _evidence()
    evidence["provider_records"][0]["body"]["sandboxId"] = "bx_other"
    assert price(evidence)["total"] is None


@pytest.mark.parametrize("running", [None, "yes"])
def test_only_a_boolean_running_flag_counts(running: object) -> None:
    evidence = _evidence()
    evidence["provider_records"][0]["body"]["running"] = running
    assert price(evidence)["total"] is None


def test_the_shared_helper_places_any_providers_read_without_naming_it() -> None:
    evidence = _evidence()
    record = evidence["provider_records"][0]
    assert read_before_end(evidence, record) == record["read_at"]
    evidence["provider"] = "acme"
    assert read_before_end(evidence, record) == record["read_at"]
    record["read_at"] = "2026-11-01T05:00:00Z"
    assert read_before_end(evidence, record) is None


# The in-process adapter (`sps_provider_boat`) reports Core cost lines, not the old usage record.
# Its read of a live sandbox is `accruing` (`final: false`, a line with no end). Cloud takes one
# just before Boat's own timer ends a sandbox (`ended_pass.PRE_END_LEAD`), and Boat then deletes
# the record, so that read is the last figure there is (production 11-21: 46 sandboxes ended by
# Boat's timer and 27 deleted just after it were released unpaid without it).


def _accruing(read_at: str = "2026-11-01T04:04:59Z", amount: str = "0.00289") -> dict[str, Any]:
    return {
        "status": "available",
        "reason": None,
        "final": False,
        "readings": [
            {
                "amount": amount,
                "currency": "USD",
                "meter": "machine",
                "interval_start": "2026-11-01T04:00:10Z",
                "interval_end": None,
                "scope": "sandbox",
                "source": "reported",
            }
        ],
    }


def _spec_evidence(*, ended_by: str = "timer") -> dict[str, Any]:
    """The best fixture with only an accruing spec report read before the end.

    `timer`: Boat's own timer ended the sandbox (no destroy call; Cloud recorded it gone).
    `destroy`: a destroy returned after the read.
    """
    evidence = cast(dict[str, Any], json.loads(BEST.read_text(encoding="utf-8")))
    evidence["provider_records"] = []
    evidence["provider_reports"] = {"read_at": "2026-11-01T04:04:59Z", "cost": _accruing()}
    if ended_by == "timer":
        evidence["calls"] = [call for call in evidence["calls"] if call["name"] != "destroy"]
        evidence["noticed_gone"] = {
            "value": "2026-11-01T04:05:10Z",
            "source": "recorded",
            "how": "Cloud recorded the sandbox gone from the provider",
        }
    return evidence


@pytest.mark.parametrize("ended_by", ["timer", "destroy"])
def test_an_accruing_spec_report_read_before_the_end_is_reported_as_of_that_read(
    ended_by: str,
) -> None:
    result = price(_spec_evidence(ended_by=ended_by))
    assert result["label"] == "reported"
    assert result["total"] == {"low": "0.00289", "high": "0.00289"}
    assert result["reported"]["taken_at"] == "2026-11-01T04:04:59Z"
    assert "before Boat deleted the sandbox" in result["reported"]["how"]


def test_an_accruing_spec_report_with_no_known_end_is_not_a_cost() -> None:
    evidence = _spec_evidence()
    evidence["noticed_gone"] = None
    result = price(evidence)
    assert (result["label"], result["total"]) == ("unknown", None)


def test_an_accruing_spec_report_read_after_the_end_is_not_a_cost() -> None:
    evidence = _spec_evidence()
    evidence["provider_reports"]["read_at"] = "2026-11-01T04:05:30Z"
    assert price(evidence)["total"] is None


def test_a_final_capture_still_carries_no_taken_at() -> None:
    evidence = _spec_evidence(ended_by="destroy")
    cost = evidence["provider_reports"]["cost"]
    del cost["final"]
    cost["readings"][0]["interval_end"] = "2026-11-01T04:04:59Z"
    result = price(evidence)
    assert result["label"] == "reported"
    assert "taken_at" not in result["reported"]


def test_a_later_unavailable_read_does_not_hide_the_read_before_the_end() -> None:
    """Cloud keeps every read; pricing merges them, and `sandbox_not_found` after the delete
    never replaces the figure read before it."""
    evidence = _spec_evidence()
    reads = [
        {"read_at": "2026-11-01T04:04:59Z", "cost": _accruing()},
        {
            "read_at": "2026-11-01T04:06:10Z",
            "cost": {"status": "unavailable", "reason": "sandbox_not_found", "readings": []},
        },
    ]
    evidence["provider_reports"] = merge_reports(reads)
    result = price(evidence)
    assert result["total"] == {"low": "0.00289", "high": "0.00289"}
    assert result["reported"]["taken_at"] == "2026-11-01T04:04:59Z"
