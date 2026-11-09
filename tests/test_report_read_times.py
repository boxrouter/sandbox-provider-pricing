# SPDX-FileCopyrightText: BoxRouter, Inc.
# SPDX-License-Identifier: Apache-2.0
"""Report input times, including causal evidence captured from Cloud 3182 / pricing 039."""

import json
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator

from sandbox_provider_pricing import price
from sandbox_provider_pricing.evidence import normalize_evidence

STAMP = "2026-10-20T12:00:00.123456+00:00"
LATER = "2026-10-20T12:15:00Z"
KINDS = ("cost", "size", "usage")
CAPTURES = json.loads((Path(__file__).parent / "data/cloud-report-read-times.json").read_text())


def test_each_kind_and_mixed_fallback() -> None:
    reports: dict[str, Any] = {kind: {"status": "unavailable"} for kind in KINDS}
    reports["read_times"] = dict(zip(KINDS, (STAMP, LATER, "2026-10-21T00:00:00Z"), strict=True))
    schema = json.loads((Path(__file__).parents[1] / "schemas/evidence.schema.json").read_text())
    validator = Draft202012Validator({"$defs": schema["$defs"], "$ref": "#/$defs/provider_reports"})
    assert validator.is_valid(reports)
    result = normalize_evidence({"provider": "e2b", "provider_reports": reports})
    assert [r["read_at"] for r in result["provider_records"]] == list(
        reports["read_times"].values()
    )
    reports["read_at"] = LATER
    del reports["read_times"]["size"]
    assert validator.is_valid(reports)
    result = normalize_evidence({"provider": "e2b", "provider_reports": reports})
    assert [r["read_at"] for r in result["provider_records"]] == [
        STAMP,
        LATER,
        "2026-10-21T00:00:00Z",
    ]


def test_target_only_preserves_target_and_raw_records() -> None:
    target = {"sandbox_id": "sandbox", "identities": [{"scope": "app", "id": "app-test"}]}
    raw = [{"source": "raw", "read_at": STAMP, "body": {}}]
    result = normalize_evidence(
        {"provider": "modal", "provider_records": raw, "provider_reports": {"target": target}}
    )
    assert result["report_target"] == target
    assert result["provider_records"] == raw
    assert (
        normalize_evidence({"provider": "modal", "provider_reports": {}})["provider_records"] == []
    )


@pytest.mark.parametrize(
    "reports",
    [
        {"cost": {"status": "available"}, "read_times": {}},
        {"usage": {"status": "available"}},
        {"usage": {"status": "available", "observed_at": "bad"}},
        {"cost": {"status": "available"}, "usage": {"status": "available", "observed_at": None}},
        {"cost": {"status": "available"}, "read_times": {"cost": "bad"}, "read_at": STAMP},
        {"cost": {"status": "available"}, "read_times": {"cost": None}},
        {"cost": {"status": "available"}, "read_at": "bad"},
        {"cost": {"status": "available"}, "read_times": {"other": STAMP}, "read_at": STAMP},
        {"read_times": {"usage": STAMP}},
        {"read_times": []},
    ],
)
def test_missing_malformed_and_unmatched_times_refused(reports: Any) -> None:
    with pytest.raises(ValueError):
        normalize_evidence({"provider": "e2b", "provider_reports": reports})
    schema = json.loads((Path(__file__).parents[1] / "schemas/evidence.schema.json").read_text())
    validator = Draft202012Validator({"$defs": schema["$defs"], "$ref": "#/$defs/provider_reports"})
    assert not validator.is_valid(reports)


@pytest.mark.parametrize("name", list(CAPTURES))
def test_cloud_captures_legacy_bundle_matches_per_kind(name: str) -> None:
    for row in CAPTURES[name]:
        legacy = row["evidence"]
        updated = deepcopy(legacy)
        reports = updated["provider_reports"]
        stamp = reports.pop("read_at")
        reports["read_times"] = {kind: stamp for kind in KINDS if kind in reports}
        assert json.dumps(price(legacy, as_of=row["as_of"])) == json.dumps(
            price(updated, as_of=row["as_of"])
        )


def test_blaxel_early_report_never_matures_with_read_clock() -> None:
    for row in CAPTURES["blaxel-early-report-falsely-matures-039"]:
        evidence = deepcopy(row["evidence"])
        reports = evidence["provider_reports"]
        reports.pop("read_at")
        early = row["actual_report_observed_at"]
        reports["read_times"] = {"cost": early}
        result = price(evidence, as_of=row["as_of"])
        assert (result["label"], result["total"]) == ("unknown", None)
        assert result["steps"]["evidence"]["provider_records"][0]["read_at"] == early
        reports["read_times"]["cost"] = "2026-09-29T19:49:03+00:00"
        result = price(evidence, as_of="9000-01-01T00:00:00Z")
        assert (result["label"], result["total"]) == ("reported", {"low": "0.25", "high": "0.25"})


def _schema_valid(reports: Any) -> bool:
    schema = json.loads((Path(__file__).parents[1] / "schemas/evidence.schema.json").read_text())
    validator = Draft202012Validator({"$defs": schema["$defs"], "$ref": "#/$defs/provider_reports"})
    return validator.is_valid(reports)


def test_legacy_usage_observed_at_is_the_bundle_read_time() -> None:
    """Pricing 0.4.39 documented it: without `read_at`, the usage report's `observed_at` is the
    read time for every report that has no time of its own."""
    reports: dict[str, Any] = {
        "usage": {"status": "available", "observed_at": STAMP},
        "cost": {"status": "unavailable"},
    }
    assert _schema_valid(reports)
    result = normalize_evidence({"provider": "e2b", "provider_reports": reports})
    assert {r["source"]: r["read_at"] for r in result["provider_records"]} == {
        "core.cost": STAMP,
        "core.usage": STAMP,
    }


def test_read_time_precedence_is_own_then_bundle_then_usage_observed_at() -> None:
    usage = {"status": "available", "observed_at": "2026-10-19T00:00:00Z"}
    reports: dict[str, Any] = {
        "usage": usage,
        "cost": {"status": "unavailable"},
        "size": {"status": "unavailable"},
        "read_at": LATER,
        "read_times": {"cost": STAMP},
    }
    assert _schema_valid(reports)
    result = normalize_evidence({"provider": "e2b", "provider_reports": reports})
    assert {r["source"]: r["read_at"] for r in result["provider_records"]} == {
        "core.cost": STAMP,
        "core.size": LATER,
        "core.usage": LATER,
    }
    del reports["read_at"]
    result = normalize_evidence({"provider": "e2b", "provider_reports": reports})
    assert {r["source"]: r["read_at"] for r in result["provider_records"]} == {
        "core.cost": STAMP,
        "core.size": usage["observed_at"],
        "core.usage": usage["observed_at"],
    }


def test_price_accepts_the_legacy_usage_only_form() -> None:
    """The form root found refused by 0.4.40 (usage report with observed_at, no read_at)."""
    evidence = {
        "provider": "e2b",
        "sandbox_id": "sandbox",
        "provider_reports": {"usage": {"status": "unavailable", "observed_at": STAMP}},
    }
    result = price(evidence, as_of=LATER)
    assert result["label"] == "unknown"
    assert result["steps"]["evidence"]["provider_records"][0]["read_at"] == STAMP


def test_unused_null_usage_observed_at_is_not_checked() -> None:
    """Core's pending-events usage report has `observed_at: null`. With its own `read_times`
    entry nothing falls back to it, so it is not a read time and is not refused (0.4.41 was)."""
    usage: dict[str, Any] = {
        "status": "unknown",
        "reason": "provider_events_pending_or_expired",
        "readings": [],
        "records": [],
        "observed_at": None,
        "retention_seconds": None,
    }
    reports: dict[str, Any] = {"usage": usage, "read_times": {"usage": "2026-10-24T12:00:00Z"}}
    assert _schema_valid(reports)
    evidence = {"provider": "e2b", "sandbox_id": "synthetic-owned", "provider_reports": reports}
    ended = datetime(2026, 10, 24, 11, 59, 45, tzinfo=UTC)
    result = price(evidence, as_of="2026-10-24T12:00:00Z", ended_at=ended)
    assert result["label"] == "unknown"
    assert result["steps"]["evidence"]["provider_records"][0]["read_at"] == "2026-10-24T12:00:00Z"


@pytest.mark.parametrize(
    "reports",
    [
        {"usage": {"status": "unknown", "observed_at": "bad"}, "read_times": {"usage": STAMP}},
        {"usage": {"status": "unknown", "observed_at": None}, "read_at": STAMP},
        {
            "usage": {"status": "unknown", "observed_at": None},
            "cost": {"status": "unavailable"},
            "read_times": {"usage": STAMP, "cost": LATER},
        },
    ],
)
def test_usage_observed_at_is_only_checked_when_used(reports: Any) -> None:
    assert _schema_valid(reports)
    result = normalize_evidence({"provider": "e2b", "provider_reports": reports})
    assert all(record["read_at"] in (STAMP, LATER) for record in result["provider_records"])
