# SPDX-FileCopyrightText: BoxRouter, Inc.
# SPDX-License-Identifier: Apache-2.0
"""Funding and benchmark budgets share a distinct rate-card quote contract."""

from copy import deepcopy
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from sandbox_provider_pricing import reservation_quote
from sandbox_provider_pricing.reservation import COVERAGE_KINDS
from sandbox_provider_pricing.versions import latest_version, seed_versions

ROOT = Path(__file__).resolve().parents[1]


def _entry(treatment: str) -> dict[str, str]:
    return {"treatment": treatment, "source": "https://example.test", "note": "Stated."}


def _covered(**treatments: str) -> dict[str, Any]:
    """Every kind stated: time kinds and creation in the quote, the rest unbounded."""
    kinds = {
        kind: "in_quote" if kind in ("cpu", "memory", "disk", "creation") else "unbounded"
        for kind in COVERAGE_KINDS
    }
    kinds.update(treatments)
    return {kind: _entry(treatment) for kind, treatment in kinds.items()}


def test_vercel_reservation_assumes_full_active_cpu_use() -> None:
    version = latest_version("vercel")
    original = deepcopy(version)
    result = reservation_quote(version, {"cpu": 2, "memory_mib": 4096}, 3600)
    assert result["kind"] == "reservation_quote"
    assert result["status"] == "bounded"
    assert result["ceiling_usd"] == "0.3408006"
    assert result["price_version"] == version["version"]
    assert "Network egress and retained storage" in result["excluded"]
    assert version == original
    assert "label" not in result


def test_meter_rounding_creation_and_region_are_applied_to_the_reservation() -> None:
    version: dict[str, Any] = {
        "version": "example@2026-10-20",
        "coverage": _covered(),
        "classes": [
            {
                "name": "vm",
                "default": True,
                "rates": {
                    "cpu": {"usd": "0.001", "per": "vcpu-second"},
                    "memory": {"usd": "0.0002", "per": "gib-second"},
                    "creation": {"usd": "0.02", "per": "creation"},
                },
                "meter": {
                    "cpu": {
                        "basis": "active",
                        "billed_states": ["running"],
                        "minimum_seconds": 60,
                        "increment_seconds": 30,
                    },
                    "memory": {
                        "basis": "allocated",
                        "billed_states": ["running"],
                        "increment_seconds": 10,
                    },
                },
                "region_multipliers": {"region-test": "1.5"},
            }
        ],
    }
    size = {"cpu": 2, "memory_mib": 5120}
    quote = reservation_quote(version, size, 10, region="region-test", class_name="vm")
    assert (quote["status"], quote["ceiling_usd"]) == ("bounded", "0.225")
    assert (
        reservation_quote(version, size, 10, region="region-test", creation=False)["ceiling_usd"]
        == "0.195"
    )
    assert reservation_quote(version, size, 0, region="region-test")["ceiling_usd"] == "0.03"


def test_modal_rate_card_cannot_bound_a_reservation() -> None:
    quote = reservation_quote(latest_version("modal"), {"cpu": 2, "memory_mib": 4096}, 3600)
    assert (quote["status"], quote["ceiling_usd"]) == ("unbounded", None)
    assert any("cannot bound use above the request" in reason for reason in quote["held_back_by"])


def test_missing_size_class_or_gpu_rate_cannot_produce_a_ceiling() -> None:
    quote = reservation_quote(latest_version("vercel"), {"cpu": 2}, 3600)
    assert (quote["status"], quote["ceiling_usd"]) == ("unknown", None)
    assert (
        reservation_quote(latest_version("e2b"), {"cpu": 2}, 1, class_name="missing")["ceiling_usd"]
        is None
    )


def test_flat_per_size_machine_rate_bounds_a_reservation() -> None:
    version = latest_version("boat")
    quote = reservation_quote(version, {"cpu": 2, "memory_mib": 4096}, 3600)
    assert (quote["status"], quote["ceiling_usd"]) == ("bounded", "0.018")
    assert (
        reservation_quote(version, {"cpu": 8, "memory_mib": 16384}, 1800)["ceiling_usd"] == "0.036"
    )
    unmatched = reservation_quote(version, {"cpu": 1, "memory_mib": 2048}, 3600)
    assert (unmatched["status"], unmatched["ceiling_usd"]) == ("unknown", None)
    assert any("machine" in reason for reason in unmatched["held_back_by"])
    partial = reservation_quote(version, {"memory_mib": 4096}, 3600)
    assert (partial["status"], partial["ceiling_usd"]) == ("unknown", None)


@pytest.mark.parametrize("seconds", [-1, True, float("nan"), Decimal("Infinity")])
def test_invalid_reservation_duration_is_rejected(seconds: Any) -> None:
    with pytest.raises(ValueError, match="duration_seconds must be finite and non-negative"):
        reservation_quote(latest_version("e2b"), {"cpu": 2, "memory_mib": 1024}, seconds)


SIZE = {"cpu": 2, "memory_mib": 4096, "disk_mib": 10240}
# What each provider's current coverage implies for a 2 vCPU, 4 GiB, 10 GiB sandbox.
EXPECTED_STATUS = {
    "agent37": "bounded",
    "blaxel": "bounded",  # the writable filesystem is in billed RAM
    "boat": "bounded",
    "boxd": "bounded",
    "daytona": "bounded",
    "e2b": "bounded",
    "modal": "unbounded",  # CPU, memory and disk are charged on request or use
    "vercel": "bounded",
}


@pytest.mark.parametrize("provider", sorted(EXPECTED_STATUS))
def test_each_providers_current_coverage_gives_its_status(provider: str) -> None:
    quote = reservation_quote(latest_version(provider), SIZE, 3600)
    assert quote["status"] == EXPECTED_STATUS[provider], quote["held_back_by"]
    assert (quote["ceiling_usd"] is not None) == (quote["status"] == "bounded")


def test_every_provider_is_expected() -> None:
    assert {version["provider"] for version in seed_versions()} == set(EXPECTED_STATUS)


def test_an_uncovered_charge_makes_the_quote_unknown() -> None:
    version = latest_version("vercel")
    assert reservation_quote(version, SIZE, 3600)["status"] == "bounded"
    for kind in COVERAGE_KINDS:
        stated = deepcopy(version)
        del stated["coverage"][kind]
        quote = reservation_quote(stated, SIZE, 3600)
        assert (quote["status"], quote["ceiling_usd"]) == ("unknown", None), kind
        assert [reason for reason in quote["held_back_by"] if reason.startswith(f"{kind}:")]


def test_a_version_without_coverage_is_unknown() -> None:
    version = deepcopy(latest_version("e2b"))
    del version["coverage"]
    quote = reservation_quote(version, SIZE, 3600)
    assert (quote["status"], quote["ceiling_usd"]) == ("unknown", None)
    assert quote["held_back_by"] == [
        "The price version states no coverage of its billable charges."
    ]


def test_an_uncovered_charge_beats_an_unbounded_meter() -> None:
    version = deepcopy(latest_version("modal"))
    del version["coverage"]["egress"]
    assert reservation_quote(version, SIZE, 3600)["status"] == "unknown"


def test_coverage_that_contradicts_the_rate_card_is_unknown() -> None:
    free = deepcopy(latest_version("vercel"))
    free["coverage"]["egress"] = _entry("not_billed")  # the class prices egress
    assert reservation_quote(free, SIZE, 3600)["status"] == "unknown"
    priced = deepcopy(latest_version("vercel"))
    priced["coverage"]["egress"] = _entry("in_quote")  # a quote does not price egress
    assert reservation_quote(priced, SIZE, 3600)["status"] == "unknown"
    hidden = deepcopy(latest_version("vercel"))
    hidden["coverage"]["creation"] = _entry("unbounded")  # the quote would price creation
    assert reservation_quote(hidden, SIZE, 3600)["status"] == "unknown"
    invented = deepcopy(latest_version("boat"))
    invented["coverage"]["creation"] = _entry("in_quote")  # the class has no creation rate
    assert reservation_quote(invented, SIZE, 3600)["status"] == "unknown"


def test_unbounded_charges_are_listed_as_excluded_and_do_not_block_a_quote() -> None:
    quote = reservation_quote(latest_version("vercel"), SIZE, 3600)
    assert quote["status"] == "bounded"
    assert any(line.startswith("egress: ") for line in quote["excluded"])
    assert not any(line.startswith("cpu: ") for line in quote["excluded"])


def test_an_unbounded_running_charge_makes_the_quote_unbounded() -> None:
    version = deepcopy(latest_version("e2b"))
    version["coverage"]["memory"] = _entry("unbounded")
    quote = reservation_quote(version, SIZE, 3600)
    assert (quote["status"], quote["ceiling_usd"]) == ("unbounded", None)


def test_every_provider_latest_version_states_all_its_charges_with_a_source() -> None:
    for provider in EXPECTED_STATUS:
        version = latest_version(provider)
        coverage = version["coverage"]
        assert set(coverage) == set(COVERAGE_KINDS), provider
        urls = {source["url"] for source in version["sources"]}
        for kind, entry in coverage.items():
            where = f"{provider} {kind}"
            assert entry["source"] in urls or (ROOT / entry["source"]).is_file(), where
