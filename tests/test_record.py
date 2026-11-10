# SPDX-FileCopyrightText: BoxRouter, Inc.
# SPDX-License-Identifier: Apache-2.0
"""One builder from a stored sandbox record to evidence, and one merge of its report reads."""

from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator

from sandbox_provider_pricing import merge_reports, price, record_evidence, region_name, reproduce

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = sorted((ROOT / "tests" / "fixtures" / "records").glob("*.json"))
RECORD_SCHEMA = json.loads((ROOT / "schemas" / "record.schema.json").read_text())
RESULT_SCHEMA = json.loads((ROOT / "schemas" / "result.schema.json").read_text())
Reads = list[dict[str, Any]]
T0, T1, T2, T3 = (f"2026-10-20T1{hour}:00:00Z" for hour in range(4))


def _fixture(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())  # type: ignore[no-any-return]


def _cloud_record(case: dict[str, Any]) -> dict[str, Any]:
    """Cloud keeps each read of a report as a fact: the record is built from the merged reads."""
    cloud = case["cloud"]
    return {**cloud["record"], "reports": merge_reports(cloud["reads"])}


def _priced(case: dict[str, Any], record: dict[str, Any]) -> dict[str, Any]:
    result = price(
        record_evidence(record),
        as_of=case["as_of"],
        ended_at=datetime.fromisoformat(case["ended_at"].replace("Z", "+00:00")),
    )
    Draft202012Validator(RESULT_SCHEMA).validate(result)
    return result


@pytest.mark.parametrize("path", FIXTURES, ids=lambda path: path.stem)
def test_one_sandbox_stored_cloud_style_and_runner_style_prices_the_same(path: Path) -> None:
    """Cloud's facts (two reads, edges, its own region) and the runner's trial (one envelope,
    prefixed region, a time index) are the same sandbox, so they give the same result. Only
    Cloud's recorded call edges, which stand in for provider times and never price, differ."""
    case = _fixture(path)
    cloud = _priced(case, _cloud_record(case))
    runner = _priced(case, case["runner"]["record"])
    for result in (cloud, runner):
        assert (result["label"], result["total"]) == (
            case["expect"]["label"],
            case["expect"]["total"],
        )
    assert cloud["steps"]["evidence"].pop("calls")
    assert runner["steps"]["evidence"].pop("calls") == []
    assert cloud == runner


@pytest.mark.parametrize("path", FIXTURES, ids=lambda path: path.stem)
def test_fixture_records_follow_the_record_schema(path: Path) -> None:
    case = _fixture(path)
    validator = Draft202012Validator(RECORD_SCHEMA)
    validator.validate(case["runner"]["record"])
    validator.validate(_cloud_record(case))
    Draft202012Validator.check_schema(RECORD_SCHEMA)


def test_record_evidence_does_not_change_the_record() -> None:
    case = _fixture(FIXTURES[0])
    record = _cloud_record(case)
    before = deepcopy(record)
    record_evidence(record)
    assert record == before


def test_a_record_needs_its_provider() -> None:
    with pytest.raises(ValueError, match="provider"):
        record_evidence({"sandbox_id": "x"})


def test_a_record_with_no_reports_is_unknown_and_has_no_report_envelope() -> None:
    evidence = record_evidence({"provider": "e2b", "sandbox_id": "native"})
    assert "provider_reports" not in evidence
    result = price(evidence, as_of="2026-10-20T12:00:00Z")
    assert (result["label"], result["total"], result["lines"]) == ("unknown", None, [])


def test_the_region_loses_our_provider_prefix_and_the_class_stays() -> None:
    requested = record_evidence(
        {
            "provider": "modal",
            "requested": {"cpu": 2, "region": "modal:us-east", "class": "vm", "disk_mib": None},
        }
    )["requested"]
    assert requested == {"options": {}, "cpu": 2, "region": "us-east", "class": "vm"}
    other = record_evidence({"provider": "e2b", "requested": {"region": "modal:us"}})
    assert other["requested"]["region"] == "modal:us"  # only this provider's own prefix goes


def test_only_the_providers_own_times_of_a_kind_pricing_takes_are_kept() -> None:
    def time(kind: str, source: str = "provider", **extra: Any) -> dict[str, Any]:
        at = {"value": "2026-10-21T00:00:00Z", "source": source, "how": "field"}
        return {"kind": kind, "at": at, "field": "Sandbox.field", "read": "after_destroy", **extra}

    kept = record_evidence(
        {
            "provider": "vercel",
            "provider_times": [
                time("started", sandbox=2),
                time("requested"),  # Core's kind, not pricing's
                time("create_sent"),  # a call edge, never a provider time
                time("ended", source="recorded"),  # our clock
            ],
        }
    )["provider_times"]
    assert kept == [time("started")]


def test_calls_keep_the_first_create_and_last_destroy_each_with_its_send() -> None:
    def edge(name: str, which: str, at: str) -> dict[str, str]:
        return {"name": name, "edge": which, "at": at}

    calls = record_evidence(
        {
            "provider": "daytona",
            "calls": [
                edge("create", "sent", "2026-10-20T12:00:00Z"),
                edge("create", "returned", "2026-10-20T12:00:02Z"),
                edge("create", "sent", "2026-10-20T12:10:00Z"),  # a second create's send
                edge("create", "returned", "2026-10-20T12:10:02Z"),
                edge("destroy", "sent", "2026-10-20T12:05:00+00:00"),
                edge("destroy", "returned", "2026-10-20T12:05:01+00:00"),
                edge("destroy", "sent", "2026-10-20T12:20:00Z"),
                edge("destroy", "returned", "2026-10-20T12:20:03Z"),
                edge("pause", "returned", "2026-10-20T12:06:00Z"),  # pricing needs what it kept
                edge("destroy", "sent", "2026-10-20T12:30:00Z"),  # sent but never answered
            ],
        }
    )["calls"]
    assert [
        (call["name"], call["sent_at"]["value"], call["returned_at"]["value"]) for call in calls
    ] == [
        ("create", "2026-10-20T12:00:00Z", "2026-10-20T12:00:02Z"),
        ("destroy", "2026-10-20T12:20:00Z", "2026-10-20T12:20:03Z"),
    ]
    assert {call["outcome"] for call in calls} == {"returned"}
    assert all(call["sent_at"]["source"] == "recorded" for call in calls)
    unsent = record_evidence(
        {"provider": "daytona", "calls": [edge("create", "returned", "2026-10-20T12:00:02Z")]}
    )["calls"]
    assert unsent[0]["sent_at"] is None


def test_the_recorded_call_edges_do_not_change_a_complete_price() -> None:
    case = _fixture(next(path for path in FIXTURES if path.stem == "e2b-usage"))
    with_calls = _priced(case, _cloud_record(case))
    without = _priced(case, {**_cloud_record(case), "calls": []})
    for key in ("label", "total", "lines"):
        assert with_calls[key] == without[key]
    assert with_calls["steps"]["sandbox_start"] == without["steps"]["sandbox_start"]
    assert with_calls["steps"]["sandbox_end"] == without["steps"]["sandbox_end"]


def test_a_report_without_a_time_takes_the_newest_read_compared_as_times_not_text() -> None:
    """In the same second, a whole-second read is earlier than a fractional one, though its
    text sorts after it; Modal's billing record is read just after the report."""
    reports = {
        "read_at": "2026-10-24T16:07:10Z",
        "cost": {"status": "available", "records": [{"read_at": "2026-10-24T16:07:10.298668Z"}]},
    }
    found = record_evidence({"provider": "modal", "reports": reports})["provider_reports"]
    assert found["read_at"] == "2026-10-24T16:07:10.298668Z"


def test_read_times_are_offset_free_utc_and_need_a_zone() -> None:
    reports = {"read_at": "2026-10-23T12:00:00+00:00", "usage": {"status": "unknown"}}
    found = record_evidence({"provider": "e2b", "reports": reports})["provider_reports"]
    assert found["read_at"] == "2026-10-23T12:00:00Z"
    naive = {"read_at": "2026-10-23T12:00:00", "usage": {"status": "unknown"}}
    with pytest.raises(ValueError, match="timezone"):
        record_evidence({"provider": "e2b", "reports": naive})


def test_the_read_time_falls_back_to_the_usage_report_and_then_the_record() -> None:
    usage = {"status": "available", "observed_at": "2026-10-23T12:00:00+02:00", "records": []}
    found = record_evidence({"provider": "e2b", "reports": {"usage": usage}})
    assert found["provider_reports"]["read_at"] == "2026-10-23T10:00:00Z"
    bare = record_evidence(
        {
            "provider": "e2b",
            "reports": {"size": {"status": "unknown"}},
            "read_at": "2026-10-23T12:00:00Z",
        }
    )
    assert bare["provider_reports"]["read_at"] == "2026-10-23T12:00:00Z"


def test_a_report_target_alone_keeps_the_identity_and_no_clock() -> None:
    target = {"sandbox_id": "native", "identities": []}
    evidence = record_evidence({"provider": "e2b", "reports": {"target": target}})
    assert evidence["provider_reports"] == {"target": target}


def test_an_image_preparation_that_ran_leaves_the_cost_unknown() -> None:
    case = _fixture(next(path for path in FIXTURES if path.stem == "e2b-usage"))
    record = _cloud_record(case)
    ran = _priced(case, {**record, "operations": [{"name": "image.prepare", "outcome": "success"}]})
    assert (ran["label"], ran["total"], ran["lines"], ran["reported"], ran["final"]) == (
        "unknown",
        None,
        [],
        None,
        False,
    )
    assert ran["held_back_by"][-1]["code"] == "preparation_cost_unavailable"
    skipped = _priced(
        case, {**record, "operations": [{"name": "image.prepare", "outcome": "not_reached"}]}
    )
    assert skipped["label"] == "calculated"
    assert skipped["steps"]["evidence"]["operations"] == [
        {"name": "image.prepare", "outcome": "not_reached"}
    ]


def test_an_image_preparation_stays_unknown_when_the_result_is_replayed() -> None:
    case = _fixture(next(path for path in FIXTURES if path.stem == "e2b-usage"))
    record = {
        **_cloud_record(case),
        "operations": [{"name": "image.prepare", "outcome": "failure"}],
    }
    replay = reproduce(_priced(case, record))
    assert (replay["label"], replay["total"]) == ("unknown", None)
    assert replay["held_back_by"][-1]["code"] == "preparation_cost_unavailable"


# --- merge_reports -------------------------------------------------------------------------------


def _read(at: str, **reports: Any) -> dict[str, Any]:
    return {"read_at": at, **reports}


def _usage(*ids: str, status: str = "available") -> dict[str, Any]:
    records = [{"id": item, "scope": "session", "source": "event"} for item in ids]
    return {"status": status, "readings": [], "records": records}


def test_a_later_empty_read_never_hides_what_an_earlier_one_found() -> None:
    cost = {"status": "available", "readings": [{"amount": "1"}]}
    empty = {"status": "unknown", "reason": "no_report", "readings": []}
    merged = merge_reports([_read(T1, cost=cost), _read(T2, cost=empty)])
    assert merged["cost"] == cost
    assert merged["read_times"] == {"cost": T1}
    assert merged["read_at"] == T2  # the newest read, which prices anything without its own


def test_an_empty_first_read_is_kept_so_its_status_stays_visible() -> None:
    """Cloud kept only `available` cost reports and so lost why a cost was unknown; the runner
    kept the first report whatever it said. The report stays, and a later one replaces it."""
    empty = {"status": "unavailable", "reason": "no_report_source", "readings": []}
    cost = {"status": "available", "readings": [{"amount": "1"}]}
    assert merge_reports([_read(T1, cost=empty)])["cost"] == empty
    assert merge_reports([_read(T1, cost=empty), _read(T2, cost=cost)])["cost"] == cost


def test_a_cost_report_that_is_not_available_never_replaces_one_that_is() -> None:
    cost = {"status": "available", "readings": [{"amount": "1"}]}
    partial = {"status": "unknown", "readings": [{"amount": "2"}], "records": []}
    assert merge_reports([_read(T1, cost=cost), _read(T2, cost=partial)])["cost"] == cost
    size = {"status": "available", "readings": [{"value": "2"}]}
    later = {"status": "unknown", "readings": [{"value": "4"}]}
    assert merge_reports([_read(T1, size=size), _read(T2, size=later)])["size"] == later


def test_usage_records_join_by_identity_and_a_later_read_replaces_the_same_record() -> None:
    older = {"id": "a", "scope": "session", "source": "event", "final": False}
    newer = {**older, "final": True}
    merged = merge_reports(
        [
            _read(T1, usage={"status": "available", "records": [older, _usage("b")["records"][0]]}),
            _read(T2, usage={"status": "available", "records": [newer], "retention_seconds": 7}),
        ]
    )
    assert [(item["id"], item.get("final")) for item in merged["usage"]["records"]] == [
        ("a", True),
        ("b", None),
    ]
    assert merged["usage"]["retention_seconds"] == 7
    assert merged["read_times"] == {"usage": T2}


def test_each_kind_keeps_the_time_of_the_read_that_supplied_it() -> None:
    cost = {"status": "available", "readings": [1]}
    merged = merge_reports(
        [
            _read("2026-10-20T10:00:00Z", cost=cost, size={"status": "available", "readings": [1]}),
            _read("2026-10-20T11:00:00Z", size={"status": "available", "readings": [2]}),
            _read("2026-10-20T12:00:00Z", usage=_usage("a")),
        ]
    )
    assert merged["read_times"] == {
        "cost": "2026-10-20T10:00:00Z",
        "size": "2026-10-20T11:00:00Z",
        "usage": "2026-10-20T12:00:00Z",
    }
    assert merged["read_at"] == "2026-10-20T12:00:00Z"


def test_reads_are_taken_oldest_first_whatever_order_they_come_in() -> None:
    old = {"status": "available", "readings": [1]}
    new = {"status": "available", "readings": [2]}
    merged = merge_reports(
        [_read("2026-10-20T12:00:00.5Z", cost=new), _read("2026-10-20T12:00:00Z", cost=old)]
    )
    assert merged["cost"] == new


def test_the_target_of_the_newest_read_that_has_one_stays() -> None:
    first, second = {"sandbox_id": "a", "identities": []}, {"sandbox_id": "b", "identities": []}
    merged = merge_reports(
        [_read(T1, target=first), _read(T2, target=second), _read(T3, usage=_usage("a"))]
    )
    assert merged["target"] == second


def test_a_read_with_its_own_read_times_keeps_them_and_unknown_fields_stay_out() -> None:
    merged = merge_reports(
        [
            {
                "read_times": {"cost": T0},
                "cost": {"status": "available", "readings": [1]},
                "read_errors": ["x"],
            }
        ]
    )
    assert merged == {"cost": {"status": "available", "readings": [1]}, "read_times": {"cost": T0}}


def test_merging_nothing_gives_an_empty_envelope() -> None:
    assert merge_reports([]) == {}


def test_region_name_drops_only_the_providers_own_prefix() -> None:
    assert region_name("modal:us-east", "modal") == "us-east"
    assert region_name("modal:us", "e2b") == "modal:us"
    assert region_name("modal:", "modal") is None
    assert region_name(None, "modal") is None
