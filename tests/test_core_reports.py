# SPDX-FileCopyrightText: BoxRouter, Inc.
# SPDX-License-Identifier: Apache-2.0
"""Core's frozen report transport is interpreted inside pricing, including partial groups."""

import json
from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from sandbox_provider_pricing import price, reproduce
from sandbox_provider_pricing.evidence import normalize_evidence


# Field names match Core provider_reports. No Core/SDK runtime dependency is needed.
@dataclass(frozen=True)
class Reading:
    meter: str
    value: Decimal
    unit: str
    interval_start: datetime | None = None
    interval_end: datetime | None = None
    scope: str = "session"
    source: str = "test provider record"


@dataclass(frozen=True)
class Time:
    kind: str
    at: datetime
    source: str = "provider timestamp"


@dataclass(frozen=True)
class Record:
    id: str
    scope: str
    source: str
    readings: tuple[Reading, ...] = ()
    times: tuple[Time, ...] = ()
    related_id: str | None = None
    final: bool = True


@dataclass(frozen=True)
class Report:
    status: str
    readings: tuple[Reading, ...] = ()
    reason: str | None = None
    records: tuple[Record, ...] = ()
    observed_at: datetime | None = None
    retention_seconds: int | None = None


START = datetime(2026, 10, 20, 12, tzinfo=UTC)


def at(seconds: int) -> datetime:
    return START + timedelta(seconds=seconds)


def test_frozen_e2b_grouped_events_use_execution_sizes_and_event_times() -> None:
    records = []
    for kind, seconds in (("created", 0), ("paused", 12), ("resumed", 22), ("killed", 31)):
        end = kind in ("paused", "killed")
        cpu, memory = (1, 512) if kind == "paused" else (4, 2048)
        rows = (
            (
                Reading("cpu", Decimal(cpu), "vCPU"),
                Reading("memory", Decimal(memory), "MiB"),
                Reading("execution_time", Decimal(1), "ms"),
            )
            if end
            else ()
        )
        records.append(
            Record(
                kind,
                "session",
                f"E2B event sandbox.lifecycle.{kind}",
                rows,
                (Time("ended" if kind == "killed" else kind, at(seconds)),),
                "exec-test",
            )
        )
    report = Report(
        "available", records=tuple(records), observed_at=at(60), retention_seconds=604800
    )
    evidence = {
        "provider": "e2b",
        "sandbox_id": "e2b-test",
        "provider_reports": {"read_times": {"usage": at(60)}, "read_at": at(900), "usage": report},
    }
    original = deepcopy(evidence)
    result = price(evidence)
    assert result["total"] == {"low": "0.00078", "high": "0.00078"}
    assert result["label"] == "calculated"
    assert reproduce(result) == result
    assert evidence == original
    assert result["as_of"] == "2026-10-20T12:01:00Z"
    assert all(
        record["read_at"] == "2026-10-20T12:01:00Z"
        for record in result["steps"]["evidence"]["provider_records"]
        if record["source"] in {"core.usage", "E2B lifecycle API"}
    )
    partial = Report(
        "unknown", reason="events_partial", records=tuple(records[:-1]), observed_at=at(60)
    )
    assert (
        price(evidence | {"provider_reports": {"read_at": at(900), "usage": partial}})["total"]
        is None
    )


@pytest.mark.parametrize("missing", [0, 1])
def test_e2b_every_running_interval_needs_its_own_execution_size(missing: int) -> None:
    records = []
    for kind, seconds in (("created", 0), ("paused", 12), ("resumed", 22), ("killed", 31)):
        terminal = kind in ("paused", "killed")
        allocation = terminal and (kind == "killed") != bool(missing)
        records.append(
            Record(
                kind,
                "session",
                f"E2B event sandbox.lifecycle.{kind}",
                (Reading("cpu", Decimal(2), "vCPU"), Reading("memory", Decimal(1024), "MiB"))
                if allocation
                else (),
                (Time("ended" if kind == "killed" else kind, at(seconds)),),
            )
        )
    result = price(
        {
            "provider": "e2b",
            "sandbox_id": "test",
            "provider_reports": {
                "read_at": at(900),
                "usage": Report("available", records=tuple(records), observed_at=at(60)),
            },
        }
    )
    assert (result["label"], result["total"]) == ("unknown", None)
    assert reproduce(result) == result


def test_e2b_core_size_cannot_fill_events_without_allocation() -> None:
    records = tuple(
        Record(
            kind,
            "session",
            f"E2B event sandbox.lifecycle.{kind}",
            (),
            (Time(event_kind, at(seconds)),),
        )
        for kind, event_kind, seconds in (
            ("created", "created", 0),
            ("killed", "ended", 60),
        )
    )
    evidence = {
        "provider": "e2b",
        "sandbox_id": "e2b-size-fallback",
        "provider_reports": {
            "read_at": at(900),
            "usage": Report("available", records=records, observed_at=at(120)),
            "size": {
                "status": "available",
                "readings": [
                    {
                        "resource": "cpu",
                        "value": Decimal(2),
                        "unit": "vCPU",
                        "source": "size report",
                    },
                    {
                        "resource": "memory",
                        "value": Decimal(1024),
                        "unit": "MiB",
                        "source": "size report",
                    },
                ],
            },
        },
    }

    result = price(evidence)
    assert (result["label"], result["total"]) == ("unknown", None)
    assert any("size" in item["text"] for item in result["held_back_by"])
    assert reproduce(result) == result

    without_size = {
        **evidence,
        "provider_reports": {
            "read_at": at(900),
            "usage": Report("available", records=records, observed_at=at(120)),
        },
    }
    unknown = price(without_size)
    assert (unknown["label"], unknown["total"]) == ("unknown", None)


def session(identity: str, start: int, stop: int, *, memory: int = 4096) -> Record:
    return Record(
        identity,
        "session",
        "vercel.Session",
        (
            Reading("cpu", Decimal(2), "vCPU"),
            Reading("memory", Decimal(memory), "MiB"),
            Reading("active_cpu", Decimal(11040), "ms"),
            Reading("egress", Decimal(0), "byte"),
        ),
        (Time("started", at(start)), Time("stopped", at(stop))),
    )


def test_frozen_vercel_sessions_bind_snapshot_to_its_source_session() -> None:
    snapshot = Record(
        "snap-test",
        "snapshot",
        "vercel.Snapshot",
        (Reading("snapshot_size", Decimal(1_000_000_000), "byte", scope="snapshot"),),
        (Time("created", at(120)), Time("deadline", at(999999))),
        "session-1",
    )
    report = Report(
        "available",
        records=(session("session-1", 0, 120), snapshot, session("session-2", 600, 720)),
        observed_at=at(900),
    )
    evidence: dict[str, Any] = {
        "provider": "vercel",
        "sandbox_id": "vercel-test",
        "provider_reports": {"read_at": at(900), "usage": report},
    }
    result = price(evidence)
    assert result["label"] == "calculated"
    assert result["total"]["low"] == result["total"]["high"]
    lines = {line["what"]: line for line in result["lines"]}
    assert lines["cpu"]["quantity"].startswith("0.006133333333333333333333333333333")
    assert lines["memory"]["quantity"].startswith("0.266666666666666666666666666666666")
    assert lines["snapshot_storage"]["quantity"].startswith("0.000182648401826484018264840182648")
    assert reproduce(result) == result
    missing = Report(
        "available", records=(report.records[0], report.records[2]), observed_at=at(900)
    )
    assert (
        price(evidence | {"provider_reports": {"read_at": at(900), "usage": missing}})["total"]
        is None
    )


def test_vercel_session_allocation_controls_its_priced_size() -> None:
    report = Report(
        "available",
        records=(session("vercel-session-size", 0, 61, memory=4096),),
        observed_at=at(900),
    )
    evidence = {
        "provider": "vercel",
        "sandbox_id": "vercel-session-size",
        "provider_reports": {
            "read_at": at(900),
            "usage": report,
            "size": {
                "status": "available",
                "readings": [
                    {
                        "resource": "cpu",
                        "value": Decimal(8),
                        "unit": "vCPU",
                        "source": "test size report",
                    },
                    {
                        "resource": "memory",
                        "value": Decimal(16384),
                        "unit": "MiB",
                        "source": "test size report",
                    },
                ],
            },
        },
    }

    result = price(evidence)
    assert result["label"] == "calculated"
    memory = next(line for line in result["lines"] if line["what"] == "memory")
    assert memory["quantity"].startswith("0.133333333333333333333333333333333")
    assert result["steps"]["usage"]["low"]["intervals"][0]["size"]["memory_mib"] == 4096
    assert reproduce(result) == result


def test_legacy_usage_readings_do_not_invent_grouped_session_records() -> None:
    report = Report(
        "available",
        readings=(Reading("active_cpu", Decimal(10), "ms", at(0), at(60)),),
        observed_at=at(900),
    )
    result = price(
        {
            "provider": "vercel",
            "sandbox_id": "test",
            "provider_reports": {"read_at": at(900), "usage": report},
        }
    )
    assert (result["label"], result["total"]) == ("unknown", None)


def _utc(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


@pytest.mark.parametrize(
    ("provider", "source", "meter"),
    [
        ("blaxel", "Blaxel account metrics API", "hourly_cost"),
        ("daytona", "Daytona GET /organization/{organizationId}/usage/sandbox", "total"),
    ],
)
def test_selected_core_cost_reports_require_sandbox_scope(
    provider: str, source: str, meter: str
) -> None:
    row = {
        "amount": Decimal("0.1234"),
        "currency": "USD",
        "meter": meter,
        "scope": "sandbox",
        "source": source,
        "interval_start": at(0),
        "interval_end": at(60),
    }
    evidence: dict[str, Any] = {
        "provider": provider,
        "sandbox_id": "test",
        "provider_times": [
            {
                "kind": "ended",
                "field": "provider ended",
                "at": {"value": at(0), "source": "provider", "how": "Fixture end."},
            }
        ],
        "provider_reports": {
            "read_at": at(900),
            "cost": {"status": "available", "readings": [row], "reason": None},
        },
    }
    result = price(evidence)
    assert (result["label"], result["total"]) == ("reported", {"low": "0.1234", "high": "0.1234"})
    assert result["revisit"] is not None
    assert reproduce(result) == result
    assert result["steps"]["times"]["start"]["value"] == _utc(at(0))
    assert result["steps"]["sandbox_start"]["value"] is None
    assert result["steps"]["sandbox_start"]["source"] == "unknown"
    assert result["steps"]["times"]["end"]["value"] == _utc(at(60))
    assert result["steps"]["sandbox_end"]["value"] == _utc(at(0))
    assert result["steps"]["sandbox_end"]["source"] == "provider"
    for usage in result["steps"]["usage"].values():
        assert usage["started"]["at"] is None
        assert usage["started"]["source"] == "unknown"
    created = deepcopy(evidence)
    created["calls"] = [
        {
            "name": "create",
            "outcome": "returned",
            "sent_at": {"value": at(-2), "source": "recorded", "how": "Fixture create sent."},
            "returned_at": {"value": at(-1), "source": "recorded", "how": "Fixture create return."},
        }
    ]
    with_create = price(created)
    assert with_create["steps"]["sandbox_start"]["value"] == _utc(at(-1))
    for usage in with_create["steps"]["usage"].values():
        assert usage["started"]["at"] == _utc(at(-1))
        assert usage["started"]["source"] == "recorded"
    row["interval_start"] = row["interval_end"] = None
    timeless = price(evidence)
    assert timeless["versions"]["prices"] is None
    assert reproduce(timeless) == timeless
    row["scope"] = "account"
    assert price(evidence)["total"] is None


def test_blaxel_core_cost_report_waits_for_revisit_delay() -> None:
    reading = {
        "meter": "hourly_cost",
        "amount": Decimal("0.1234"),
        "currency": "USD",
        "interval_start": at(0),
        "interval_end": at(60),
        "scope": "sandbox",
        "source": "Blaxel account metrics API",
    }
    ended = {
        "kind": "ended",
        "field": "provider ended",
        "at": {"value": at(0), "source": "provider", "how": "Fixture end."},
    }
    report = {"status": "available", "readings": [reading], "reason": None}

    def bill(read_seconds: int) -> dict[str, Any]:
        return price(
            {
                "provider": "blaxel",
                "sandbox_id": "test",
                "provider_times": [ended],
                "provider_reports": {
                    "read_at": at(read_seconds),
                    "cost": report,
                },
            }
        )

    assert (bill(599)["label"], bill(599)["total"]) == ("unknown", None)
    assert (bill(600)["label"], bill(600)["total"]) == (
        "reported",
        {"low": "0.1234", "high": "0.1234"},
    )


def _fixture(provider: str, name: str) -> tuple[dict[str, Any], dict[str, Any]]:
    root = Path(__file__).parents[1] / "providers" / provider / "fixtures" / name
    return json.loads((root / "evidence.json").read_text()), json.loads(
        (root / "result.json").read_text()
    )


def _via_core_records(evidence: dict[str, Any], records: list[dict[str, Any]]) -> dict[str, Any]:
    """The same evidence, with its provider records arriving as a Core CostReport.to_dict()."""
    collected = {key: value for key, value in evidence.items() if key != "provider_records"}
    sources = {record["source"] for record in records}
    collected["provider_records"] = [
        record for record in evidence["provider_records"] if record["source"] not in sources
    ]
    collected["provider_reports"] = {
        "read_at": max((record["read_at"] for record in records), default="2026-10-24T06:00:00Z"),
        "cost": {"status": "available", "reason": None, "readings": [], "records": records},
    }
    return collected


@pytest.mark.parametrize(
    ("provider", "source"),
    [("modal", "Modal Workspace.billing.report"), ("blaxel", "Blaxel metrics API")],
)
def test_core_cost_report_records_reach_the_provider_rule(provider: str, source: str) -> None:
    evidence, expected = _fixture(provider, "best")
    records = [item for item in evidence["provider_records"] if item["source"] == source]
    assert records
    via_core = _via_core_records(evidence, records)
    normalized = normalize_evidence(via_core)
    assert [item for item in normalized["provider_records"] if item["source"] == source] == records
    result = price(via_core)
    assert (result["label"], result["total"], result["final"]) == (
        expected["label"],
        expected["total"],
        expected["final"],
    )
    assert result["total"] is not None
    unreported = {"read_at": "2026-10-24T06:00:00Z", "cost": {"status": "unknown", "readings": []}}
    assert price(via_core | {"provider_reports": unreported})["total"] is None


def test_modal_report_target_arrives_in_provider_reports() -> None:
    evidence, expected = _fixture("modal", "best")
    source = "Modal Workspace.billing.report"
    records = [item for item in evidence["provider_records"] if item["source"] == source]
    target = evidence.pop("report_target")
    via_core = _via_core_records(evidence, records)
    via_core["provider_reports"]["target"] = target
    assert normalize_evidence(via_core)["report_target"] == target
    assert price(via_core)["total"] == expected["total"]
    del via_core["provider_reports"]["target"]
    assert price(via_core)["total"] is None


def test_core_provider_record_object_form_is_accepted() -> None:
    evidence, expected = _fixture("modal", "best")
    source = "Modal Workspace.billing.report"
    records = [item for item in evidence["provider_records"] if item["source"] == source]
    via_core = _via_core_records(evidence, records)
    via_core["provider_reports"]["cost"]["records"] = [
        {
            "source": item["source"],
            "read_at": datetime.fromisoformat(item["read_at"]),
            "body_json": json.dumps(item["body"]),
        }
        for item in records
    ]
    assert price(via_core)["total"] == expected["total"]


def test_partial_core_provider_records_stay_unknown() -> None:
    evidence, _ = _fixture("modal", "best")
    source = "Modal Workspace.billing.report"
    records = deepcopy([item for item in evidence["provider_records"] if item["source"] == source])
    assert records
    for item in records:
        item["body"] = {key: value for key, value in item["body"].items() if key != "rows"}
    result = price(_via_core_records(evidence, records))
    assert (result["label"], result["total"]) == ("unknown", None)
    evidence["provider_records"] = [
        item for item in evidence["provider_records"] if item["source"] != source
    ]
    result = price(_via_core_records(evidence, []))
    assert (result["label"], result["total"]) == ("unknown", None)


@pytest.mark.parametrize(
    "bad",
    [
        {"source": "x", "read_at": "2026-10-24T00:00:00Z"},
        {"source": "", "read_at": "2026-10-24T00:00:00Z", "body": {}},
        {"source": "x", "read_at": "2026-10-24T00:00:00Z", "body": []},
        "text",
    ],
)
def test_malformed_core_provider_records_are_refused(bad: Any) -> None:
    with pytest.raises(ValueError, match="provider record"):
        normalize_evidence(
            {
                "provider": "modal",
                "provider_reports": {
                    "read_at": "2026-10-24T00:00:00Z",
                    "cost": {"status": "available", "readings": [], "records": [bad]},
                },
            }
        )
