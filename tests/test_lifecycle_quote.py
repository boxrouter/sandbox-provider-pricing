# SPDX-FileCopyrightText: BoxRouter, Inc.
# SPDX-License-Identifier: Apache-2.0
"""A lifecycle quote prices only the demand its caller supplies."""

from __future__ import annotations

import json
import subprocess
from copy import deepcopy
from decimal import Decimal
from pathlib import Path
from typing import Any, cast

import pytest

from sandbox_provider_pricing import LifecyclePeriod, lifecycle_quote, price
from sandbox_provider_pricing.calculator import cost
from sandbox_provider_pricing.types import Document
from sandbox_provider_pricing.versions import seed_versions

ROOT = Path(__file__).resolve().parents[1]
QUOTE_DOC = ROOT / "docs" / "reservation-quote.md"


def _version(
    rates: dict[str, Any],
    meter: dict[str, Any],
    *,
    region_multipliers: dict[str, str] | None = None,
    month_hours: str | None = None,
) -> dict[str, Any]:
    price_class: dict[str, Any] = {
        "name": "default",
        "default": True,
        "rates": rates,
        "meter": meter,
    }
    if region_multipliers is not None:
        price_class["region_multipliers"] = region_multipliers
    version: dict[str, Any] = {
        "version": "fixture@2026-11-06",
        "exclusions": ["Credits and discounts"],
        "classes": [price_class],
    }
    if month_hours is not None:
        version["month_hours"] = month_hours
    return version


def _cpu_version(meter: dict[str, Any] | None = None) -> dict[str, Any]:
    return _version(
        {"cpu": {"usd": "0.001", "per": "vcpu-second"}},
        {"cpu": meter or {"basis": "allocated", "billed_states": ["running"]}},
    )


def test_each_period_is_rounded_before_amounts_are_summed() -> None:
    version = _cpu_version(
        {
            "basis": "allocated",
            "billed_states": ["running"],
            "minimum_seconds": 60,
            "increment_seconds": 60,
        }
    )
    size = {"cpu": 1}
    two_short_periods = lifecycle_quote(
        version, size, [LifecyclePeriod("running", 1), LifecyclePeriod("running", 1)]
    )
    assert (two_short_periods["status"], two_short_periods["amount_usd"]) == (
        "known",
        "0.12",
    )

    first = lifecycle_quote(version, size, [LifecyclePeriod("running", 1)])
    second = lifecycle_quote(version, size, [LifecyclePeriod("running", 61)])
    mean_duration = lifecycle_quote(version, size, [LifecyclePeriod("running", 31)])
    assert first["amount_usd"] == "0.06"
    assert second["amount_usd"] == "0.12"
    assert first["amount_usd"] is not None
    assert second["amount_usd"] is not None
    mean_amount = (Decimal(first["amount_usd"]) + Decimal(second["amount_usd"])) / Decimal(2)
    assert mean_amount == Decimal("0.09")
    assert mean_duration["amount_usd"] == "0.06"


def test_lifecycle_duration_changes_the_conditional_amount() -> None:
    three_hour = _version(
        {"cpu": {"usd": "0.10", "per": "vcpu-hour"}},
        {"cpu": {"basis": "allocated", "billed_states": ["running"]}},
    )
    one_hour = _version(
        {"cpu": {"usd": "0.20", "per": "vcpu-hour"}},
        {"cpu": {"basis": "allocated", "billed_states": ["running"]}},
    )
    low_rate = lifecycle_quote(three_hour, {"cpu": 1}, [LifecyclePeriod("running", 10800)])
    high_rate = lifecycle_quote(one_hour, {"cpu": 1}, [LifecyclePeriod("running", 3600)])
    assert low_rate["amount_usd"] == "0.3"
    assert high_rate["amount_usd"] == "0.2"


def test_only_periods_in_a_meter_billed_state_are_charged() -> None:
    version = _version(
        {
            "cpu": {"usd": "0.001", "per": "vcpu-second"},
            "disk": {"usd": "0.0001", "per": "gib-second"},
        },
        {
            "cpu": {"basis": "allocated", "billed_states": ["running"]},
            "disk": {"basis": "allocated", "billed_states": ["running", "paused"]},
        },
    )
    quote = lifecycle_quote(
        version,
        {"cpu": 1, "disk_mib": 1024},
        [
            LifecyclePeriod("running", 60),
            LifecyclePeriod("paused", 120),
            LifecyclePeriod("stopped", 300),
        ],
    )
    assert (quote["status"], quote["amount_usd"]) == ("known", "0.078")


def test_creation_conversion_and_region_multiplier_defaults() -> None:
    version = _version(
        {"creation": {"usd": "0.60", "per": "million-creations"}},
        {},
        region_multipliers={"region-test": "1.5"},
    )
    periods = [LifecyclePeriod("running", 0)]
    no_region = lifecycle_quote(version, {"cpu": 1}, periods, creations=3)
    selected_region = lifecycle_quote(
        version, {"cpu": 1}, periods, region="region-test", creations=3
    )
    default_region = lifecycle_quote(version, {"cpu": 1}, periods, region="unlisted", creations=3)
    assert (no_region["status"], no_region["amount_usd"]) == ("unknown", None)
    assert selected_region["amount_usd"] == "0.0000027"
    assert default_region["amount_usd"] == "0.0000018"


def test_memory_tiers_free_quantity_and_disk_coupling_use_shared_size_rules() -> None:
    version = _version(
        {"memory": {"usd": "0.01", "per": "gib-hour"}},
        {
            "memory": {
                "basis": "allocated",
                "billed_states": ["running"],
                "memory_steps_mib": [2048],
                "free_quantity": "0.5",
            },
            "disk": {
                "basis": "allocated",
                "billed_states": ["stopped"],
                "disk_gib_per_memory_gib": "2",
            },
        },
    )
    quote = lifecycle_quote(
        version,
        {"memory_mib": 1024, "disk_mib": 4096},
        [LifecyclePeriod("running", 3600)],
    )
    assert (quote["status"], quote["amount_usd"]) == ("known", "0.015")


def test_disk_billed_as_memory_has_no_required_separate_disk_rate() -> None:
    version = _version(
        {"memory": {"usd": "0.01", "per": "gib-second"}},
        {
            "memory": {"basis": "allocated", "billed_states": ["running"]},
            "disk": {
                "basis": "allocated",
                "billed_states": ["running"],
                "disk_gib_per_memory_gib": "20",
            },
        },
    )
    quote = lifecycle_quote(
        version,
        {"memory_mib": 1024, "disk_mib": 40 * 1024},
        [LifecyclePeriod("running", 10)],
    )
    assert (quote["status"], quote["amount_usd"]) == ("known", "0.2")


def test_gpu_model_and_flat_machine_size_select_their_published_rates() -> None:
    gpu_version = _version(
        {"gpu": {"nvidia:h100": {"usd": "2", "per": "gpu-hour"}}},
        {"gpu": {"basis": "allocated", "billed_states": ["running"]}},
    )
    gpu_quote = lifecycle_quote(
        gpu_version,
        {"gpu": 1, "gpu_model": "nvidia:h100"},
        [LifecyclePeriod("running", 3600)],
    )
    machine_version = _version(
        {
            "machine": {
                "small": {
                    "usd": "0.018",
                    "per": "machine-hour",
                    "cpu": 2,
                    "memory_gib": 4,
                }
            }
        },
        {"machine": {"billed_states": ["running"]}},
    )
    machine_quote = lifecycle_quote(
        machine_version,
        {"cpu": 2, "memory_mib": 4096},
        [LifecyclePeriod("running", 10800)],
    )
    unmatched = lifecycle_quote(
        machine_version,
        {"cpu": 1, "memory_mib": 2048},
        [LifecyclePeriod("running", 3600)],
    )
    assert gpu_quote["amount_usd"] == "2"
    assert machine_quote["amount_usd"] == "0.054"
    assert (unmatched["status"], unmatched["amount_usd"]) == ("unknown", None)


def test_active_cpu_demand_is_required_and_other_active_bases_stay_unknown() -> None:
    active_cpu = _cpu_version({"basis": "active", "billed_states": ["running"]})
    missing = lifecycle_quote(active_cpu, {"cpu": 1}, [LifecyclePeriod("running", 60)])
    supplied = lifecycle_quote(
        active_cpu,
        {"cpu": 1},
        [LifecyclePeriod("running", 60, active_cpu_seconds=8)],
    )
    active_memory = _version(
        {"memory": {"usd": "0.001", "per": "gib-second"}},
        {"memory": {"basis": "active", "billed_states": ["running"]}},
    )
    unsupported = lifecycle_quote(
        active_memory,
        {"memory_mib": 1024},
        [LifecyclePeriod("running", 60, active_cpu_seconds=8)],
    )
    larger = _cpu_version({"basis": "larger_of_request_and_use", "billed_states": ["running"]})
    unbounded_use = lifecycle_quote(larger, {"cpu": 1}, [LifecyclePeriod("running", 60)])
    assert (missing["status"], missing["amount_usd"]) == ("unknown", None)
    assert supplied["amount_usd"] == "0.008"
    assert (unsupported["status"], unsupported["amount_usd"]) == ("unknown", None)
    assert (unbounded_use["status"], unbounded_use["amount_usd"]) == ("unknown", None)


def test_egress_and_snapshot_storage_require_explicit_material_demand() -> None:
    egress_version = _version({"egress": {"usd": "0.15", "per": "gb"}}, {})
    missing_egress = lifecycle_quote(egress_version, {}, [LifecyclePeriod("running", 0)])
    zero_egress = lifecycle_quote(
        egress_version, {}, [LifecyclePeriod("running", 0)], egress_bytes=0
    )
    sent_egress = lifecycle_quote(
        egress_version, {}, [LifecyclePeriod("running", 0)], egress_bytes=2_000_000_000
    )
    snapshot_version = _version(
        {"snapshot_storage": {"usd": "0.08", "per": "gb-month"}},
        {"snapshot_storage": {"billed_states": ["stopped"]}},
        month_hours="730",
    )
    missing_snapshot = lifecycle_quote(snapshot_version, {}, [LifecyclePeriod("stopped", 3600)])
    stored = lifecycle_quote(
        snapshot_version,
        {},
        [LifecyclePeriod("stopped", 3600, snapshot_bytes=1_000_000_000)],
    )
    unbilled_snapshot = lifecycle_quote(
        _version(
            {"snapshot_storage": {"usd": "0.08", "per": "gb-month"}},
            {"snapshot_storage": {"billed_states": ["stopped"]}},
        ),
        {},
        [LifecyclePeriod("running", 3600)],
    )
    missing_month = lifecycle_quote(
        _version(
            {"snapshot_storage": {"usd": "0.08", "per": "gb-month"}},
            {"snapshot_storage": {"billed_states": ["stopped"]}},
        ),
        {},
        [LifecyclePeriod("stopped", 3600, snapshot_bytes=0)],
    )
    assert (missing_egress["status"], missing_egress["amount_usd"]) == ("unknown", None)
    assert zero_egress["amount_usd"] == "0"
    assert sent_egress["amount_usd"] == "0.3"
    assert (missing_snapshot["status"], missing_snapshot["amount_usd"]) == ("unknown", None)
    assert (
        stored["amount_usd"] == "0.000109589041095890410958904109589041095890410958904109589041096"
    )
    assert unbilled_snapshot["amount_usd"] == "0"
    assert (missing_month["status"], missing_month["amount_usd"]) == ("unknown", None)


@pytest.mark.parametrize(
    "month_hours",
    [
        True,
        "soon",
        "0",
        0,
        -730,
        "NaN",
        "Infinity",
        float("nan"),
        float("inf"),
        Decimal("NaN"),
        Decimal("Infinity"),
        ["730"],
    ],
)
def test_an_invalid_month_length_holds_the_snapshot_quote_back(month_hours: Any) -> None:
    version = _version(
        {"snapshot_storage": {"usd": "0.08", "per": "gb-month"}},
        {"snapshot_storage": {"billed_states": ["stopped"]}},
    )
    version["month_hours"] = month_hours
    quote = lifecycle_quote(
        version, {}, [LifecyclePeriod("stopped", 3600, snapshot_bytes=1_000_000_000)]
    )
    assert (quote["status"], quote["amount_usd"]) == ("unknown", None)
    assert quote["held_back_by"] == ["snapshot_storage: a positive month_hours value is required."]


@pytest.mark.parametrize("month_hours", [730, 730.0, Decimal("730"), "730"])
def test_accepted_month_length_forms_price_the_same_snapshot(month_hours: Any) -> None:
    version = _version(
        {"snapshot_storage": {"usd": "0.08", "per": "gb-month"}},
        {"snapshot_storage": {"billed_states": ["stopped"]}},
    )
    version["month_hours"] = month_hours
    quote = lifecycle_quote(
        version, {}, [LifecyclePeriod("stopped", 3600, snapshot_bytes=1_000_000_000)]
    )
    assert (quote["status"], quote["held_back_by"]) == ("known", [])
    assert (
        quote["amount_usd"] == "0.000109589041095890410958904109589041095890410958904109589041096"
    )


def test_unknown_class_size_rate_and_meter_basis_do_not_become_zero() -> None:
    version = _cpu_version()
    period = [LifecyclePeriod("running", 60)]
    unknown_class = lifecycle_quote(version, {"cpu": 1}, period, class_name="missing")
    missing_size = lifecycle_quote(version, {}, period)
    missing_rate = lifecycle_quote(
        _version({}, {"cpu": {"basis": "allocated", "billed_states": ["running"]}}),
        {"cpu": 1},
        period,
    )
    unknown_basis = lifecycle_quote(
        _cpu_version({"basis": "mystery", "billed_states": ["running"]}),
        {"cpu": 1},
        period,
    )
    for quote in (unknown_class, missing_size, missing_rate, unknown_basis):
        assert (quote["status"], quote["amount_usd"]) == ("unknown", None)


@pytest.mark.parametrize(
    "period",
    [
        LifecyclePeriod("running", -1),
        LifecyclePeriod("running", float("nan")),
        LifecyclePeriod("running", Decimal("Infinity")),
        LifecyclePeriod("running", cast(Any, True)),
        LifecyclePeriod("running", cast(Any, "1")),
        LifecyclePeriod("running", 1, active_cpu_seconds=-1),
        LifecyclePeriod("running", 1, active_cpu_seconds=float("inf")),
        LifecyclePeriod("running", 1, snapshot_bytes=-1),
        LifecyclePeriod("running", 1, snapshot_bytes=cast(Any, False)),
        LifecyclePeriod(cast(Any, "starting"), 1),
    ],
)
def test_invalid_period_demand_is_rejected(period: LifecyclePeriod) -> None:
    with pytest.raises(ValueError):
        lifecycle_quote(_cpu_version(), {"cpu": 1}, [period])


@pytest.mark.parametrize(
    "creations",
    [-1, 1.5, True, float("nan"), Decimal("Infinity"), cast(Any, "1")],
)
def test_invalid_creation_count_is_rejected(creations: Any) -> None:
    with pytest.raises(ValueError):
        lifecycle_quote(
            _cpu_version(), {"cpu": 1}, [LifecyclePeriod("running", 1)], creations=creations
        )


def test_invalid_quote_containers_quantities_and_empty_periods_are_rejected() -> None:
    version = _cpu_version()
    period = LifecyclePeriod("running", 1)
    invalid_calls: tuple[dict[str, Any], ...] = (
        {"periods": []},
        {"periods": ["running"]},
        {"egress_bytes": -1},
        {"egress_bytes": float("inf")},
        {"egress_bytes": True},
        {"size": {"cpu": -1}},
        {"size": {"cpu": float("nan")}},
        {"size": {"cpu": True}},
        {"region": 1},
        {"class_name": 1},
    )
    for override in invalid_calls:
        kwargs: dict[str, Any] = {
            "version": version,
            "size": {"cpu": 1},
            "periods": [period],
        }
        kwargs.update(override)
        with pytest.raises(ValueError):
            lifecycle_quote(**cast(Any, kwargs))


def test_quote_does_not_mutate_caller_owned_objects() -> None:
    version = _cpu_version()
    size = {"cpu": 1}
    periods = [LifecyclePeriod("running", 60)]
    original = deepcopy((version, size, periods))
    lifecycle_quote(version, size, periods)
    assert (version, size, periods) == original


def test_documented_lifecycle_quote_example_runs_unchanged() -> None:
    text = QUOTE_DOC.read_text(encoding="utf-8")
    section = text.split("## Prospective lifecycle quote", 1)[1]
    fence = chr(96) * 3
    example = section.split(fence + "python\n", 1)[1].split(fence, 1)[0]
    result = subprocess.run(
        ["uv", "run", "--locked", "python", "-c", example],
        cwd=ROOT,
        capture_output=True,
        check=True,
        text=True,
    )
    assert result.stdout.strip() == "known 0.0276"


@pytest.mark.parametrize("source", ["recorded", "unknown"])
def test_provider_fixture_quotes_exact_demand_without_relaxing_actual_cost(
    source: str,
) -> None:
    fixture = ROOT / "providers" / "vercel" / "fixtures" / "best" / "evidence.json"
    priced = price(json.loads(fixture.read_text(encoding="utf-8")))
    assert priced["label"] == "calculated"
    usage: Document = priced["steps"]["usage"]["high"]
    version = next(
        item for item in seed_versions() if item["version"] == priced["versions"]["prices"]
    )
    active = usage["active_cpu"]["seconds"]
    intervals = usage["intervals"]
    assert len(intervals) == 1
    assert intervals[0]["state"] == "running"
    quote = lifecycle_quote(
        version,
        usage["size"],
        [
            LifecyclePeriod(
                interval["state"],
                interval["seconds"],
                active_cpu_seconds=active,
            )
            for interval in intervals
        ],
        region=usage["region"]["name"],
        creations=usage["creations"]["count"],
        egress_bytes=usage["egress"]["bytes"],
    )
    actual = cost(usage, version, as_of=priced["as_of"])
    assert actual["total"] is not None
    assert quote["status"] == "known"
    assert quote["amount_usd"] == actual["total"]["low"] == priced["total"]["low"]
    assert not {"label", "final", "source"}.intersection(quote)

    untrusted = deepcopy(usage)
    untrusted["intervals"][0]["source"] = source
    refused = cost(untrusted, version, as_of=priced["as_of"])
    assert (refused["label"], refused["total"]) == ("unknown", None)
