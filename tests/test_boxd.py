# SPDX-FileCopyrightText: BoxRouter, Inc.
# SPDX-License-Identifier: Apache-2.0
"""boxd accepts only complete, attributed USD list-cost records."""

import json
from decimal import Decimal
from fractions import Fraction
from pathlib import Path
from typing import Any, cast

import pytest

from sandbox_provider_pricing import billing, build_price_sheet, price, reservation_quote
from sandbox_provider_pricing.versions import latest_version

ROOT = Path(__file__).resolve().parents[1]


def evidence() -> dict[str, Any]:
    return cast(
        dict[str, Any],
        json.loads((ROOT / "providers/boxd/fixtures/best/evidence.json").read_text()),
    )


def test_usage_based_sheet_never_presents_a_fixed_per_size_price() -> None:
    provider = next(item for item in build_price_sheet()["providers"] if item["id"] == "boxd")
    assert provider["basis"] == "active CPU and memory"
    region = billing("boxd")["price_sheet"]["benchmark_region"]
    assert (provider["region"], provider["region_source_url"]) == (
        region["value"],
        region["source_url"],
    )
    assert provider["region_multiplier"] is None
    for config in provider["configs"]:
        hourly = config["running_per_hour_usd"]
        assert hourly["low"] == 0
        assert hourly["high"] > hourly["low"]
        assert config["paused_per_hour_usd"] is None
    disk = next(item for item in provider["storage"] if item["kind"] == "disk")
    assert disk["status"] == "priced"


def test_cost_is_reported_when_the_provider_gives_no_lifecycle_times() -> None:
    """Cloud keeps only its own create and destroy calls for boxd, and no provider times."""
    item = evidence()
    item["provider_times"] = []
    item["calls"] = [
        {
            "name": "create",
            "sent_at": {"value": "2026-11-02T00:00:00Z", "source": "recorded", "how": "Create."},
            "returned_at": {
                "value": "2026-11-02T00:00:02Z",
                "source": "recorded",
                "how": "Create returned.",
            },
            "outcome": "returned",
        },
        *item["calls"],
    ]
    result = price(item)
    assert result["label"] == "reported"
    assert result["total"] == {"low": "0.03932", "high": "0.03932"}
    assert result["basis"] == "provider_reported"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("complete", False),
        ("complete", 1),
        ("currency", "eur"),
        ("currency", "USD"),
        ("machine_id", "another_machine"),
        ("cost_micro", -1),
        ("cost_micro", True),
        ("cost_micro", "39320"),
        ("cost_micro", 39320.0),
        (
            "rates",
            {"vcpu_hour_micro": 47001, "ram_gib_hour_micro": 14000, "disk_gib_hour_micro": 96},
        ),
        ("rates", {}),
        ("period", {"start": "2026-11-02T00:30:00Z", "end": "2026-11-02T01:15:00Z"}),
    ],
)
def test_unusable_machine_records_remain_unknown(field: str, value: Any) -> None:
    item = evidence()
    item["provider_records"][0]["body"][field] = value
    result = price(item)
    assert result["label"] == "unknown"
    assert result["total"] is None


def test_reservation_ceiling_is_the_full_allocation_times_the_sourced_rates() -> None:
    # The managed hold is a ceiling, never a sandbox cost: every declared size
    # bounds a reservation once the fixed 100 GiB platform disk is in the size.
    version = latest_version("boxd")
    for cpu, memory_mib in ((1, 4096), (2, 8192), (4, 16384), (8, 32768)):
        size = {"cpu": cpu, "memory_mib": memory_mib, "disk_mib": 102400}
        quote = reservation_quote(version, size, 300, class_name="default")
        assert quote["status"] == "bounded"
        assert quote["held_back_by"] == []
        expected_fraction = Fraction(300, 3600) * (
            Fraction(47, 1000) * cpu
            + Fraction(14, 1000) * Fraction(memory_mib, 1024)
            + Fraction(96, 1_000_000) * 100
        )
        expected = Decimal(expected_fraction.numerator) / Decimal(expected_fraction.denominator)
        ceiling = quote["ceiling_usd"]
        assert ceiling is not None
        assert abs(Decimal(ceiling) - expected) < Decimal("1e-9")


def test_reservation_without_the_platform_disk_stays_unknown() -> None:
    quote = reservation_quote(
        latest_version("boxd"), {"cpu": 1, "memory_mib": 4096}, 300, class_name="default"
    )
    assert (quote["status"], quote["ceiling_usd"]) == ("unknown", None)
    assert any("disk" in reason for reason in quote["held_back_by"])


def test_no_record_never_uses_allocation_to_estimate_cost() -> None:
    item = evidence()
    item["provider_records"] = []
    result = price(item)
    assert result["label"] == "unknown"
    assert result["total"] is None


def test_rate_mismatch_is_recorded() -> None:
    item = evidence()
    item["provider_records"][0]["body"]["rates"]["disk_gib_hour_micro"] = 80
    result = price(item)
    assert result["steps"]["usage"]["low"]["intervals"][0]["how"] == (
        "boxd usage rates do not match the stored USD list rates."
    )


def discounted_card() -> dict[str, Any]:
    """An account rate card: the stored list version at half of each resource rate."""
    document = cast(dict[str, Any], json.loads(json.dumps(latest_version("boxd"))))
    rates = document["classes"][0]["rates"]
    for resource in ("cpu", "memory", "disk"):
        rates[resource]["usd"] = str(Decimal(rates[resource]["usd"]) / 2)
    return document


def test_reported_rates_are_checked_against_the_version_in_use() -> None:
    card = discounted_card()
    # The list-rate record is not a card-rate record.
    assert price(evidence(), versions=[card])["label"] == "unknown"
    # The same record priced at the card's rates is accepted.
    item = evidence()
    item["provider_records"][0]["body"]["rates"] = {
        "vcpu_hour_micro": 23500,
        "ram_gib_hour_micro": 7000,
        "disk_gib_hour_micro": 48,
    }
    result = price(item, versions=[card])
    assert result["label"] == "reported"
    assert result["basis"] == "provider_reported"
