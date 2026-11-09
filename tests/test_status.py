# SPDX-FileCopyrightText: BoxRouter, Inc.
# SPDX-License-Identifier: Apache-2.0
"""Each provider's best fixture demonstrates its published billing status."""

import json
from pathlib import Path
from typing import Any, cast

import yaml  # type: ignore[import-untyped]

from sandbox_provider_pricing import price
from sandbox_provider_pricing.providers import provider_ids

ROOT = Path(__file__).resolve().parents[1]
PACKAGES = ROOT / "src" / "sandbox_provider_pricing" / "providers"


def _best_evidence(provider: str) -> dict[str, Any]:
    path = ROOT / "providers" / provider / "fixtures" / "best" / "evidence.json"
    return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))


def test_best_fixture_label_matches_each_provider_status() -> None:
    for provider in provider_ids():
        billing = cast(
            dict[str, Any],
            yaml.safe_load((PACKAGES / provider / "billing.yaml").read_text(encoding="utf-8")),
        )
        result = price(_best_evidence(provider))
        expected = json.loads(
            (ROOT / "providers" / provider / "fixtures" / "best" / "result.json").read_text(
                encoding="utf-8"
            )
        )
        # This historical E2B fixture has event times but lacks execution allocations.
        label = "unknown" if provider == "e2b" else billing["status"]["best_label"]
        assert result["label"] == label
        assert {"label": result["label"], "total": result["total"]} == {
            key: expected[key] for key in ("label", "total")
        }
        assert result["final"] is False
        assert result["revisit"]["next_read_at"] is not None


def test_daytona_retains_the_sum_of_its_reported_period_prices() -> None:
    result = price(_best_evidence("daytona"))

    assert result["reported"]["usd"] == "0.11754000"
    assert result["reported"]["source"] == "provider"
    assert result["label"] == "reported"


def test_blaxel_early_metrics_read_stays_unknown() -> None:
    evidence = _best_evidence("blaxel")
    evidence["provider_records"][0]["read_at"] = "2026-10-19T20:09:00Z"

    result = price(evidence)

    assert result["reported"] is None
    assert result["label"] == "unknown"
    assert result["total"] is None
    assert result["revisit"]["after"] == "2026-10-19T20:10:00Z"


def test_daytona_missing_record_stays_unknown() -> None:
    evidence = _best_evidence("daytona")
    evidence["provider_records"] = []

    result = price(evidence)

    assert result["reported"] is None
    assert result["label"] == "unknown"
    assert result["total"] is None


def test_e2b_webhook_events_split_running_and_paused_time() -> None:
    result = price(_best_evidence("e2b"))
    intervals = result["steps"]["usage"]["low"]["intervals"]

    assert [(item["state"], item["seconds"]) for item in intervals] == [
        ("running", 12.0),
        ("paused", 10.0),
        ("running", 9.0),
    ]


def test_modal_single_app_report_is_the_sandbox_cost() -> None:
    result = price(_best_evidence("modal"))

    assert (result["label"], result["total"]) == (
        "reported",
        {"low": "0.01431635", "high": "0.01431635"},
    )
    assert result["revisit"]["interval_s"] == 3600
    assert result["reported"]["source"] == "provider"
    assert "boxrouter-internal/main" in result["reported"]["how"]
