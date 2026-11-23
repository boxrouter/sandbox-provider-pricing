# SPDX-FileCopyrightText: BoxRouter, Inc.
# SPDX-License-Identifier: Apache-2.0
"""Pricing records the shapes each provider class sells; a size is priced by the cheapest fit."""

import json
import re
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator

from sandbox_provider_pricing import build_price_sheet, class_shapes, covered_classes, is_priced
from sandbox_provider_pricing import price_sheet as sheet_module
from sandbox_provider_pricing._util import providers_root
from sandbox_provider_pricing.calculator import per_hour
from sandbox_provider_pricing.providers import billing
from sandbox_provider_pricing.versions import latest_version

ROOT = Path(__file__).parents[1]
SCHEMA = json.loads((ROOT / "schemas" / "price-sheet.schema.json").read_text(encoding="utf-8"))
PROVIDERS = sorted(
    folder.name for folder in providers_root().iterdir() if (folder / "billing.yaml").is_file()
)
RECORDED = [
    (provider, spec_class, entry)
    for provider in PROVIDERS
    for spec_class, entries in (billing(provider).get("shapes") or {}).items()
    for entry in entries
]


def _cell(provider: str, spec_class: str, vcpu: int, memory_gib: int) -> Any:
    sheet = build_price_sheet()
    entry = next(
        item for item in sheet["providers"] if (item["id"], item["class"]) == (provider, spec_class)
    )
    return next(
        config
        for config in entry["configs"]
        if config["size"] == {"vcpu": vcpu, "memory_gib": memory_gib}
    )


def _page_text(provider: str, checked: str) -> str:
    return (ROOT / "providers" / provider / "evidence" / f"{checked}-shapes.txt").read_text(
        encoding="utf-8"
    )


@pytest.mark.parametrize(("provider", "spec_class", "entry"), RECORDED)
def test_every_recorded_shape_quotes_its_saved_page(
    provider: str, spec_class: str, entry: dict[str, Any]
) -> None:
    """A shape names its page, the date it was read and a line of the page saved in evidence."""
    saved = _page_text(provider, entry["checked"])
    assert f"Source: {entry['source']}\n" in saved, f"{provider}/{spec_class}"
    assert entry["quote"] in saved, f"{provider}/{spec_class}: {entry['quote']}"


def test_every_class_the_sheet_prices_records_its_shapes() -> None:
    sheet = build_price_sheet()
    assert {(item["id"], item["class"]) for item in sheet["providers"]} <= {
        (provider, spec_class)
        for provider in PROVIDERS
        for spec_class in (billing(provider).get("shapes") or {})
    }


@pytest.mark.parametrize(("provider", "spec_class", "entry"), RECORDED)
def test_the_price_version_prices_every_recorded_shape(
    provider: str, spec_class: str, entry: dict[str, Any]
) -> None:
    """A recorded shape that its price version cannot price would show as a missing price."""
    low_cpu = entry["cpu"][0] if isinstance(entry["cpu"], list) else entry["cpu"]
    low_memory = (
        entry["memory_mib"][0] if isinstance(entry["memory_mib"], list) else entry["memory_mib"]
    )
    version = latest_version(provider)
    assert per_hour(version, {"cpu": low_cpu, "memory_mib": low_memory}, class_name=spec_class)


def test_a_flat_per_size_price_lists_the_same_shapes_as_the_shapes_record() -> None:
    """Boat publishes one price per named size; its shapes are those sizes, no more or fewer."""
    default = next(c for c in latest_version("boat")["classes"] if c.get("default"))
    machines = {
        (float(rate["cpu"]), float(rate["memory_gib"]) * 1024)
        for rate in default["rates"]["machine"].values()
    }
    assert {(cpu[0], memory[0]) for cpu, memory in class_shapes("boat", "default")} == machines


def test_boat_prices_every_size_it_sells_including_the_plan_gated_one() -> None:
    assert [
        _cell("boat", "default", vcpu, memory_gib)["running_per_hour_usd"]["high"]
        for vcpu, memory_gib in ((2, 4), (4, 8), (8, 16))
    ] == [0.018, 0.036, 0.072]
    xlarge = next(entry for entry in billing("boat")["shapes"]["default"] if entry["cpu"] == 16)
    assert xlarge["note"] == "Needs the $100 plan or higher."


def test_boxd_prices_the_shape_it_sells_that_fits() -> None:
    """boxd sells 1/4, 2/8, 4/16 and 8/32, so its 2 vCPU, 4 GiB cell is its 2/8 machine."""
    assert [
        _cell("boxd", "default", vcpu, memory_gib)["shape"]
        for vcpu, memory_gib in ((1, 2), (2, 4), (4, 8), (8, 16))
    ] == [
        {"vcpu": 1, "memory_gib": 4},
        {"vcpu": 2, "memory_gib": 8},
        {"vcpu": 4, "memory_gib": 16},
        {"vcpu": 8, "memory_gib": 32},
    ]


def test_a_size_no_shape_fits_is_not_offered_and_has_no_price() -> None:
    cell = _cell("blaxel", "default", 8, 16)
    assert cell["status"] == "not_offered"
    assert cell["shape"] is None
    assert cell["reason"] == "No size the provider offers is large enough for this configuration."
    assert not [key for key, value in cell.items() if key.endswith("_usd") and value is not None]


def test_a_range_prices_the_exact_size_inside_it() -> None:
    cell = _cell("e2b", "default", 4, 8)
    assert (cell["status"], cell["shape"]) == ("priced", {"vcpu": 4, "memory_gib": 8})
    assert _cell("e2b", "default", 8, 16)["status"] == "not_offered"


def test_a_range_with_no_published_maximum_prices_any_size_above_its_minimum() -> None:
    assert class_shapes("modal", "default") == [((0.125, float("inf")), (128, float("inf")))]
    assert _cell("modal", "default", 8, 16)["status"] == "priced"


def test_equal_prices_go_to_fewer_vcpus_then_less_memory(monkeypatch: pytest.MonkeyPatch) -> None:
    """Blaxel bills memory only, so two shapes of one memory cost the same at any vCPU count."""
    monkeypatch.setattr(
        sheet_module,
        "class_shapes",
        lambda provider, spec_class: [
            ((4, 4), (4096, 4096)),
            ((2, 2), (4096, 4096)),
            ((2, 2), (8192, 8192)),
        ],
    )
    sheet = build_price_sheet()
    entry = next(item for item in sheet["providers"] if item["id"] == "blaxel")
    cell = next(c for c in entry["configs"] if c["size"] == {"vcpu": 1, "memory_gib": 2})
    assert cell["shape"] == {"vcpu": 2, "memory_gib": 4}


def test_a_class_with_no_recorded_shapes_fails_the_build_naming_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real = billing("daytona")
    without_vm = {**real, "shapes": {"container": real["shapes"]["container"]}}
    monkeypatch.setattr(
        "sandbox_provider_pricing.shapes.provider_billing",
        lambda provider: without_vm if provider == "daytona" else billing(provider),
    )
    with pytest.raises(ValueError, match="daytona/vm: pricing records no shapes"):
        build_price_sheet()


def test_exact_sizes_prices_each_requested_size_as_asked() -> None:
    for provider in build_price_sheet(exact_sizes=True)["providers"]:
        for config in provider["configs"]:
            if config["status"] == "priced":
                assert config["shape"] == config["size"]


def test_the_sheet_validates_with_shapes_and_unoffered_cells() -> None:
    Draft202012Validator(SCHEMA).validate(build_price_sheet())


def test_is_priced_needs_a_recorded_shape_and_a_price() -> None:
    assert is_priced("boxd", "default", 2, 8192)
    assert not is_priced("boxd", "default", 2, 4096)  # boxd sells 2/8, not 2/4
    assert not is_priced("acme", "default", 2, 4096)
    assert is_priced("e2b", "default", [1, 8], [1024, 8192])
    assert not is_priced("e2b", "default", [1, 8], [128, 8192])
    assert not is_priced("e2b", "default", [1, 16], [1024, 8192])


def test_every_covered_class_has_a_recorded_shape_list() -> None:
    """A class a price version covers and the sheet shows has shapes in its billing record."""
    for provider in PROVIDERS:
        default = next(c for c in latest_version(provider)["classes"] if c.get("default"))
        recorded = billing(provider).get("shapes") or {}
        for spec_class in covered_classes(default):
            assert spec_class in recorded, f"{provider}/{spec_class}"


def test_recorded_dates_are_dates() -> None:
    for _, _, entry in RECORDED:
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", entry["checked"])


def test_vercel_bills_provisioned_memory_while_idle_and_no_active_cpu() -> None:
    """Idle at 2 vCPU, 4 GiB is the 4 GiB of provisioned memory at its rate, with no CPU part."""
    version = latest_version("vercel")
    default = next(c for c in version["classes"] if c.get("default"))
    memory_rate = Decimal(default["rates"]["memory"]["usd"])
    entry = next(item for item in build_price_sheet()["providers"] if item["id"] == "vercel")
    cell = next(c for c in entry["configs"] if c["size"] == {"vcpu": 2, "memory_gib": 4})
    assert Decimal(str(cell["idle_per_hour_usd"]["high"])) == 4 * memory_rate
    assert cell["idle_cpu_per_hour_usd"]["high"] == 0
    assert cell["idle_per_hour_usd"]["high"] > 0
    assert cell["idle_per_hour_usd"]["high"] < cell["running_per_hour_usd"]["high"]


def test_boxd_paused_is_the_standby_memory_at_its_rate() -> None:
    """Standby bills resident RAM: at the upper end, 2 vCPU / 8 GiB pays for 8 GiB at its rate."""
    default = next(c for c in latest_version("boxd")["classes"] if c.get("default"))
    memory_rate = Decimal(default["rates"]["memory"]["usd"])
    entry = next(item for item in build_price_sheet()["providers"] if item["id"] == "boxd")
    cell = next(c for c in entry["configs"] if c["size"] == {"vcpu": 2, "memory_gib": 4})
    assert cell["shape"] == {"vcpu": 2, "memory_gib": 8}
    assert Decimal(str(cell["paused_per_hour_usd"]["high"])) == 8 * memory_rate
    assert cell["paused_per_hour_usd"]["low"] == 0
    # The idle parts stay those of the running machine: the paused rule does not overwrite them.
    assert cell["idle_cpu_per_hour_usd"]["high"] == cell["cpu_per_hour_usd"]["high"]
    assert cell["idle_memory_per_hour_usd"]["high"] == cell["memory_per_hour_usd"]["high"]
