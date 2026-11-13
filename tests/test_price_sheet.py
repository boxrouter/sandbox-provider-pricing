# SPDX-FileCopyrightText: BoxRouter, Inc.
# SPDX-License-Identifier: Apache-2.0
"""Price sheet contract."""

import copy
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml  # type: ignore[import-untyped]
from jsonschema import Draft202012Validator
from sandbox_benchmark_verifier.content import (
    content_criteria,
    reader_literal_errors,
    slot_errors,
    slot_rule,
)

from sandbox_provider_pricing import billing as load_billing
from sandbox_provider_pricing import build_price_sheet, seed_versions
from sandbox_provider_pricing import price_sheet as sheet_module
from sandbox_provider_pricing.calculator import SECONDS_PER_HOUR
from sandbox_provider_pricing.testing import use_providers
from sandbox_provider_pricing.versions import latest_version, priced_provider_ids

ROOT = Path(__file__).parents[1]
SCHEMA = json.loads((ROOT / "schemas" / "price-sheet.schema.json").read_text(encoding="utf-8"))
EXPECTED_PROVIDERS = set(priced_provider_ids())
EXPECTED_SIZES = [(vcpu, memory_gib) for vcpu in (1, 2, 4, 8) for memory_gib in (2, 4, 8, 16)]
LEGACY_BENCHMARK_SIZES = [(1, 2), (2, 4), (4, 8), (8, 16)]


def test_a_schema_ref_has_no_sibling_keywords() -> None:
    """A `$ref` beside other keywords compiles to a numbered copy of its definition in a
    consumer's generated types; a narrower bound goes beside an `allOf` of the reference."""
    found = []
    stack: list[tuple[str, Any]] = [("", SCHEMA)]
    while stack:
        path, node = stack.pop()
        if isinstance(node, dict):
            if "$ref" in node and set(node) - {"$ref", "description"}:
                found.append(path)
            stack.extend((f"{path}/{key}", value) for key, value in node.items())
        elif isinstance(node, list):
            stack.extend((f"{path}/{index}", value) for index, value in enumerate(node))
    assert found == []


def test_price_sheet_schema_and_provider_size_coverage() -> None:
    sheet = build_price_sheet()
    Draft202012Validator(SCHEMA).validate(sheet)
    assert sheet["pages"]["pricing"]["summary"]
    assert sheet["pages"]["pricing"] == SCHEMA["x-text"]["pages"]["pricing"]
    for key in ("title", "sections", "machine_size"):
        missing = copy.deepcopy(sheet)
        del missing["pages"]["pricing"][key]
        assert not Draft202012Validator(SCHEMA).is_valid(missing)
    assert sheet["hourly"] == {"seconds_per_hour": int(SECONDS_PER_HOUR)}
    assert sheet["excludes"] == SCHEMA["properties"]["excludes"]["items"]["enum"]
    assert sheet["default_size"]["label"] == "2 vCPU, 4 GiB"
    assert [item["label"] for item in sheet["sizes"]] == [
        f"{vcpu} vCPU, {memory_gib} GiB" for vcpu, memory_gib in EXPECTED_SIZES
    ]
    assert set(sheet["panels"]) == {
        "active-use",
        "inactive-use",
        "image-storage",
        "disk-storage",
    }
    for panel in sheet["panels"].values():
        assert panel["title"]
        assert panel["summary"]
        assert panel["caption"].endswith(".")
        assert panel["axis_measure"].startswith("Price")
    assert {provider["id"] for provider in sheet["providers"]} == EXPECTED_PROVIDERS
    for provider in sheet["providers"]:
        assert [
            (item["size"]["vcpu"], item["size"]["memory_gib"]) for item in provider["configs"]
        ] == EXPECTED_SIZES
        assert provider["billing_rules"]["best_cost_label"] in {"reported", "calculated", "unknown"}
        assert {item["kind"] for item in provider["storage"]} == {
            "image",
            "disk",
            "snapshot",
            "volume",
        }
        for storage in provider["storage"]:
            assert storage["source_url"]
            assert storage["checked_at"]
            assert storage["status_text"]["word"] == storage["status"].title()
            status_text = SCHEMA["x-text"]["storage_statuses"][storage["status"]]
            assert storage["status_text"]["word"] == status_text["word"]
            template = SCHEMA["$defs"]["content_criteria"]["const"]["hover_slots"]["price-status"][
                "template"
            ]
            assert template.format(reason=storage["status_text"]["hover"]) == status_text[
                "hover_template"
            ].format(kind=storage["kind"])


def test_storage_status_templates_cover_statuses_and_declare_kind() -> None:
    storage_status_schema = SCHEMA["$defs"]["provider"]["properties"]["storage"]["items"][
        "properties"
    ]["status"]
    statuses = SCHEMA["x-text"]["storage_statuses"]
    assert set(statuses) == set(storage_status_schema["enum"])
    for entry in statuses.values():
        assert entry["runtime_fields"] == ["kind"]
        assert "{kind}" in entry["hover_template"]


def test_price_sheet_accepts_consumer_size_set_without_changing_prices() -> None:
    """A consumer can request its own size set and retain the published figures."""
    default = build_price_sheet()
    selected = build_price_sheet(LEGACY_BENCHMARK_SIZES)
    for provider_id in EXPECTED_PROVIDERS:
        default_provider = next(item for item in default["providers"] if item["id"] == provider_id)
        selected_provider = next(
            item for item in selected["providers"] if item["id"] == provider_id
        )
        default_rows = {
            (row["size"]["vcpu"], row["size"]["memory_gib"]): row
            for row in default_provider["configs"]
        }
        assert selected_provider["configs"] == [
            default_rows[size] for size in LEGACY_BENCHMARK_SIZES
        ]


def test_price_sheet_rejects_invalid_size_sets() -> None:
    for invalid in ([], [(1, 2), (1, 2)], [(1, 0)], [(True, 2)], [(1, 2, 3)]):
        try:
            build_price_sheet(invalid)  # type: ignore[arg-type]
        except ValueError:
            continue
        raise AssertionError(f"accepted invalid price configuration set: {invalid!r}")


def test_size_without_a_price_is_marked_in_development(monkeypatch: Any) -> None:
    """A missing rate stays explicit and does not become a zero price."""
    module: Any = sheet_module
    actual = module.per_hour

    def missing_largest_size(version: dict[str, Any], size: dict[str, Any], **kwargs: Any) -> Any:
        if size == {"cpu": 8, "memory_mib": 16 * 1024}:
            return None
        return actual(version, size, **kwargs)

    monkeypatch.setattr(module, "per_hour", missing_largest_size)
    document = latest_version("e2b", seed_versions())
    billing = load_billing("e2b")
    package_version = build_price_sheet()["pricing_release_version"]
    result = sheet_module._provider_sheet(
        "e2b",
        "default",
        document,
        billing,
        package_version,
        storage_statuses=SCHEMA["x-text"]["storage_statuses"],
    )
    largest = result["configs"][-1]
    assert largest["status"] == "in_development"
    assert largest["reason"]
    assert largest["running_per_hour_usd"] is None


def test_a_storage_row_must_name_its_price_version_rates_unit() -> None:
    """Agent37's disk rate is per GB-month, so a row that reads it as per GiB-hour would be
    multiplied by the month's hours again; the sheet refuses it."""
    billing = copy.deepcopy(load_billing("agent37"))
    disk = next(row for row in billing["price_sheet"]["storage"] if row["kind"] == "disk")
    disk["price_version_rate"] |= {"per": "gib-hour", "multiply_by_month_hours": True}
    with pytest.raises(ValueError, match="disk storage names a gib-hour rate"):
        sheet_module._provider_sheet(
            "agent37",
            "default",
            latest_version("agent37", seed_versions()),
            billing,
            "0",
            storage_statuses=SCHEMA["x-text"]["storage_statuses"],
        )


def test_modal_region_multiplier_is_part_of_displayed_prices() -> None:
    modal = next(item for item in build_price_sheet()["providers"] if item["id"] == "modal")
    assert modal["region"] == "us"
    assert modal["region_multiplier"] == 1.15
    assert modal["configs"][0]["running_per_hour_usd"]["low"] == 0.136827


def test_price_sheet_uses_display_names_and_one_storage_unit() -> None:
    sheet = build_price_sheet()
    assert {provider["id"]: provider["name"] for provider in sheet["providers"]} == {
        "agent37": "Agent37",
        "blaxel": "Blaxel",
        "boat": "Boat",
        "boxd": "boxd",
        "daytona": "Daytona",
        "e2b": "E2B",
        "modal": "Modal",
        "superserve": "Superserve",
        "vercel": "Vercel",
    }
    assert all(provider["display_name"] == provider["name"] for provider in sheet["providers"])
    storage = {
        (provider["id"], entry["kind"]): entry
        for provider in sheet["providers"]
        for entry in provider["storage"]
    }
    priced = [entry for entry in storage.values() if entry["status"] == "priced"]
    assert priced
    assert {entry["per"] for entry in priced} == {"gib-month"}
    vercel = storage[("vercel", "snapshot")]
    assert (vercel["source_usd"], vercel["source_per"]) == (0.08, "gb-month")
    assert vercel["usd"] == pytest.approx(0.08 * 1.073741824, rel=1e-12)
    blaxel = storage[("blaxel", "image")]
    assert (blaxel["usd"], blaxel["source_usd"], blaxel["source_per"]) == (
        0.045,
        0.045,
        "gib-month",
    )
    blaxel_volume = storage[("blaxel", "volume")]
    assert (blaxel_volume["status"], blaxel_volume["usd"], blaxel_volume["source_per"]) == (
        "priced",
        0.12,
        "gib-month",
    )
    daytona = storage[("daytona", "disk")]
    assert (daytona["source_usd"], daytona["source_per"]) == (0.000108, "gib-hour")


def test_price_sheet_has_one_entry_per_provider_and_spec_class() -> None:
    """Each entry is keyed by provider and class, with a readable class label."""
    entries = {(item["id"], item["class"]): item for item in build_price_sheet()["providers"]}
    assert set(entries) == {
        ("agent37", "default"),
        ("blaxel", "default"),
        ("boat", "default"),
        ("boxd", "default"),
        ("daytona", "container"),
        ("daytona", "vm"),
        ("e2b", "default"),
        ("modal", "default"),
        ("modal", "vm"),
        ("superserve", "default"),
        ("vercel", "default"),
    }
    for (provider_id, spec_class), entry in entries.items():
        overrides = (load_billing(provider_id).get("price_sheet") or {}).get(
            "class_overrides"
        ) or {}
        expected = (overrides.get(spec_class) or {}).get("label") or spec_class
        assert entry["label"] == expected

    def running(key: tuple[str, str]) -> list[Any]:
        return [c["running_per_hour_usd"] for c in entries[key]["configs"]]

    assert running(("modal", "vm")) == running(("modal", "default"))
    assert running(("daytona", "vm")) == running(("daytona", "container"))


def test_class_labels_follow_owner_data_without_inventing_missing_labels() -> None:
    """A spec class's sheet label is its billing `class_overrides` label, else the class id."""
    document = latest_version("e2b", seed_versions())
    billing = load_billing("e2b")
    release_version = build_price_sheet()["pricing_release_version"]
    sheet = sheet_module._provider_sheet(
        "e2b",
        "default",
        document,
        billing,
        release_version,
        storage_statuses=SCHEMA["x-text"]["storage_statuses"],
    )
    assert sheet["label"] == "default"
    billing["price_sheet"]["class_overrides"] = {"default": {"label": "Updated owner label"}}
    sheet = sheet_module._provider_sheet(
        "e2b",
        "default",
        document,
        billing,
        release_version,
        storage_statuses=SCHEMA["x-text"]["storage_statuses"],
    )
    assert sheet["label"] == "Updated owner label"


def test_flat_per_size_provider_prices_published_sizes_only() -> None:
    """Boat's bundle gives a running hourly price on its three on-grid sizes and nothing else."""
    entries = {(item["id"], item["class"]): item for item in build_price_sheet()["providers"]}
    boat = entries[("boat", "default")]
    priced = {
        (config["size"]["vcpu"], config["size"]["memory_gib"]): config for config in boat["configs"]
    }
    for size, usd in {(2, 4): 0.018, (4, 8): 0.036, (8, 16): 0.072}.items():
        config = priced[size]
        assert config["status"] == "priced"
        assert (config["running_per_hour_usd"]["low"], config["running_per_hour_usd"]["high"]) == (
            usd,
            usd,
        )
        assert config["cpu_per_hour_usd"] is None
        assert config["memory_per_hour_usd"] is None
    unpriced = [
        config for (size, config) in priced.items() if size not in {(2, 4), (4, 8), (8, 16)}
    ]
    assert {config["status"] for config in unpriced} == {"in_development"}
    assert all(config["running_per_hour_usd"] is None for config in unpriced)


def test_class_billing_rules() -> None:
    entries = {(item["id"], item["class"]): item for item in build_price_sheet()["providers"]}
    daytona_vm = entries[("daytona", "vm")]
    assert daytona_vm["class_rules"]["archive"].startswith("Not supported")
    assert {c["paused_per_hour_usd"] is not None for c in daytona_vm["configs"]} == {True}
    assert "memory is kept" in daytona_vm["configs"][0]["paused_note"]
    assert "512 GiB" in entries[("modal", "vm")]["class_rules"]["disk"]
    assert entries[("modal", "default")]["class_rules"] == {}
    assert entries[("daytona", "container")]["class_rules"]["archive"] == "Archived: not billed."


def test_discovered_provider_without_price_sheet_facts_keeps_unknown_cells(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """A billing folder needs no central entry; missing display facts remain unknown."""
    folder = tmp_path / "acme"
    folder.mkdir()
    billing = load_billing("e2b")
    billing["name"] = "Acme"
    billing.pop("price_sheet", None)
    (folder / "billing.yaml").write_text(yaml.safe_dump(billing), encoding="utf-8")

    version = copy.deepcopy(latest_version("e2b", seed_versions()))
    version.update(provider="acme", version="acme@2026-10-20", supersedes=[])
    monkeypatch.setattr(sheet_module, "seed_versions", lambda: [version])

    with use_providers(tmp_path):
        document = build_price_sheet(price_configs=[(1, 2)])
    Draft202012Validator(SCHEMA).validate(document)

    assert [item["id"] for item in document["providers"]] == ["acme"]
    provider = document["providers"][0]
    assert provider["region"] is None
    assert provider["region_source_url"] is None
    assert provider["region_checked_at"] is None
    assert provider["configs"][0]["idle_per_hour_usd"] is None
    assert provider["configs"][0]["paused_per_hour_usd"] is None
    assert provider["configs"][0]["idle_note"].startswith("No idle billing fact")
    assert provider["storage"] == []


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("summary", "Hourly sandbox cost."),
        ("caption", "lower is better"),
        ("limits", []),
    ],
)
def test_price_text_rejects_fragments_and_missing_required_slots(field: str, value: Any) -> None:
    sheet = build_price_sheet()
    sheet["panels"]["active-use"][field] = value
    with pytest.raises(ValueError):
        sheet_module.validate_price_text(sheet)


def test_price_text_rejects_duplicate_description_and_details() -> None:
    sheet = build_price_sheet()
    panel = sheet["panels"]["active-use"]
    panel["how_it_is_measured"] = panel["summary"]
    with pytest.raises(ValueError, match="duplicates summary"):
        sheet_module.validate_price_text(sheet)


@pytest.mark.parametrize(
    "template",
    [
        "The test ran in Virginia.",
        "The test ran in us-east-1.",
        "Measured 2026-10-27.",
        "The test used 4 vCPU and 8 GiB.",
    ],
)
def test_authored_page_fact_scan_rejects_literal_region_date_and_size(template: str) -> None:
    assert reader_literal_errors(template, content_criteria())


def test_authored_page_fact_scan_allows_two_declared_dynamic_regions() -> None:
    errors = reader_literal_errors(
        "Compare {region_a} and {region_b}.",
        content_criteria(),
        ["region_a", "region_b"],
    )
    assert errors == []


def test_price_hover_templates_export_stable_owner_slots() -> None:
    hover_slots = SCHEMA["$defs"]["content_criteria"]["const"]["hover_slots"]
    criteria = content_criteria()
    expected = criteria["hover_slots"]["price-info"]["criteria_slot"]
    for binding in hover_slots.values():
        assert binding["criteria_slot"] == expected
        assert binding["criteria_slot"] in criteria["slots"]


def test_descriptions_and_storage_statuses_match_shared_rendered_conventions() -> None:
    criteria = content_criteria()
    sheet = build_price_sheet()
    for panel in sheet["panels"].values():
        assert slot_errors(panel["summary"], slot_rule(criteria, "description")) == []
    binding = sheet["content_criteria"]["hover_slots"]["price-status"]
    for provider in sheet["providers"]:
        for storage in provider["storage"]:
            reason = storage["status_text"]["hover"]
            tooltip = binding["template"].format(reason=reason)
            assert slot_errors(tooltip, slot_rule(criteria, binding["criteria_slot"])) == []


def test_price_page_fact_scan_covers_reader_text_and_declared_hover_templates() -> None:
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "check_price_text.py")],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(result.stdout)
    templates = [slot["template"] for slot in payload["authored_slots"]]
    assert templates
    slot_ids = {slot["id"] for slot in payload["authored_slots"]}
    expected_hover_slots = {
        "$defs.content_criteria.const.hover_slots.billing-rule.template",
        "$defs.content_criteria.const.hover_slots.price-bar.template",
        "$defs.content_criteria.const.hover_slots.price-info.template",
        "$defs.content_criteria.const.hover_slots.price-status.template",
        "$defs.content_criteria.const.hover_slots.source.template",
    }
    assert expected_hover_slots <= slot_ids
    expected_storage_status_templates = {
        f"x-text.storage_statuses.{status}.hover_template"
        for status in SCHEMA["x-text"]["storage_statuses"]
    }
    assert expected_storage_status_templates <= slot_ids
    criteria = content_criteria()
    for slot in payload["authored_slots"]:
        if slot["id"] in expected_storage_status_templates:
            assert slot["runtime_fields"] == ["kind"]
        assert reader_literal_errors(slot["template"], criteria, slot["runtime_fields"]) == []
    assert all("Virginia" not in template and "us-east-1" not in template for template in templates)
    assert all("4 vCPU" not in template and "8 GiB" not in template for template in templates)


@pytest.mark.parametrize("panel_id", SCHEMA["x-text"]["panels"])
def test_price_caption_requires_the_plotted_metric(panel_id: str) -> None:
    sheet = build_price_sheet()
    panel = sheet["panels"][panel_id]
    panel["caption"] = sheet["content_criteria"]["directions"][panel["metric"]["direction"]]
    with pytest.raises(ValueError, match="missing metric"):
        sheet_module.validate_price_text(sheet)


def test_price_text_change_preserves_all_provider_price_facts() -> None:
    """Content changes cannot silently change the independent numerical price data."""
    sheet = build_price_sheet()
    assert sheet["content_criteria"]["details_order"][-1] == "details.sources"
    for panel in sheet["panels"].values():
        assert panel["metric"]["direction"] == "lower_is_better"


def test_reader_reasons_are_complete_sentences_before_joining() -> None:
    sheet = build_price_sheet()
    for provider in sheet["providers"]:
        for config in provider["configs"]:
            for key in ("reason", "idle_note", "paused_note"):
                if reason := config.get(key):
                    assert reason.endswith((".", "!", "?")), (provider["id"], key, reason)
        reasons = [item["status_text"]["hover"] for item in provider["storage"]]
        assert all(reason.endswith((".", "!", "?")) for reason in reasons), reasons
        assert not re.search(r"[a-z] [A-Z][a-z]+ (?:storage|price)", " ".join(reasons))
    assert (
        SCHEMA["$defs"]["content_criteria"]["const"]["hover_slots"]["price-status"]["template"]
        == "{reason}"
    )


def test_content_criteria_is_typed_by_its_one_definition() -> None:
    """The sheet's `content_criteria` is the schema's `$defs.content_criteria` constant, so a
    consumer's generated types carry each criterion; an open object compiled to `{}`."""
    assert SCHEMA["properties"]["content_criteria"] == {"$ref": "#/$defs/content_criteria"}
    sheet = build_price_sheet()
    assert sheet["content_criteria"] == SCHEMA["$defs"]["content_criteria"]["const"]
    sheet["content_criteria"]["hover_slots"]["price-bar"]["template"] = "{value}"
    assert not Draft202012Validator(SCHEMA).is_valid(sheet)


@pytest.mark.parametrize(
    "reason", ["The disk storage item is listed as included", "listed as included."]
)
def test_reader_reason_fragments_are_rejected(reason: str) -> None:
    sheet = build_price_sheet()
    sheet["providers"][0]["storage"][0]["status_text"]["hover"] = reason
    with pytest.raises(ValueError, match="reader reason must be a complete sentence"):
        sheet_module.validate_price_text(sheet)


def test_axes_use_compact_quantity_and_rate_units_without_losing_billing_basis() -> None:
    panels = build_price_sheet()["panels"]
    assert {key: panel["axis_measure"] for key, panel in panels.items()} == {
        "active-use": "Price (USD/hour)",
        "inactive-use": "Price (USD/hour)",
        "image-storage": "Price (USD/GiB-month)",
        "disk-storage": "Price (USD/GiB-month)",
    }
    assert panels["active-use"]["metric"]["per"] == "active hour"
    assert "per active hour" in panels["active-use"]["caption"]


def test_every_sheet_provider_carries_typed_billing_mode_and_compute_rate_units() -> None:
    """The sheet projects the typed price-version and billing facts; no consumer infers them."""
    sheet = build_price_sheet()
    assert sheet["schema_version"] == "2.4.0"
    assert SCHEMA["properties"]["schema_version"] == {"const": "2.4.0"}
    Draft202012Validator(SCHEMA).validate(sheet)
    facts = {
        provider["id"]: (
            provider["billing_mode"],
            provider["active_time_priced"],
            [rate["resource"] for rate in provider["compute_rates"]],
        )
        for provider in sheet["providers"]
    }
    assert facts == {
        "agent37": ("allocated", False, ["cpu", "memory"]),
        "blaxel": ("active", True, ["memory"]),
        "boat": ("allocated", False, ["machine"]),
        "boxd": ("active", False, ["cpu", "memory"]),
        "daytona": ("allocated", False, ["cpu", "memory"]),
        "e2b": ("allocated", False, ["cpu", "memory"]),
        "modal": ("larger_of_request_and_use", False, ["cpu", "memory"]),
        "superserve": ("allocated", False, ["cpu", "memory"]),
        "vercel": ("mixed", True, ["cpu", "memory"]),
    }
    # Each compute rate carries its price version's meter and the rate's own unit and amount.
    for provider in sheet["providers"]:
        version = latest_version(provider["id"])
        default = next(
            (item for item in version["classes"] if item.get("default")), version["classes"][0]
        )
        for rate in provider["compute_rates"]:
            meter, owner = default["meter"][rate["resource"]], default["rates"][rate["resource"]]
            assert (rate["basis"], rate["billed_states"]) == (
                meter["basis"],
                meter["billed_states"],
            )
            if rate["resource"] == "machine":
                assert (rate["usd"], {entry["per"] for entry in owner.values()}) == (
                    None,
                    {rate["per"]},
                )
            else:
                assert (rate["per"], rate["usd"], rate["size_per_unit"]) == (
                    owner["per"],
                    float(owner["usd"]),
                    float(owner["size_per_unit"]) if "size_per_unit" in owner else None,
                )


def test_sheet_ranges_follow_the_typed_billing_mode() -> None:
    """A zero-use floor appears exactly when every compute meter is active and not collapsed."""
    for provider in build_price_sheet()["providers"]:
        zero_floor = provider["billing_mode"] == "active" and not provider["active_time_priced"]
        for config in provider["configs"]:
            running = config["running_per_hour_usd"]
            if running is None:
                continue
            assert (running["low"] == 0 and running["high"] > 0) == zero_floor, provider["id"]


@pytest.mark.parametrize(
    "mutation",
    [
        lambda provider: provider.pop("billing_mode"),
        lambda provider: provider.update(billing_mode="metered"),
        lambda provider: provider.pop("active_time_priced"),
        lambda provider: provider.pop("compute_rates"),
        lambda provider: provider["compute_rates"][0].update(per="parsec"),
        lambda provider: provider["compute_rates"][0].update(basis="prose"),
        lambda provider: provider.pop("unit_rates"),
        lambda provider: provider.update(unit_rates={"cpu_per_vcpu_hour": 0.05}),
    ],
)
def test_sheet_schema_rejects_untyped_or_invalid_billing_fields(mutation: Any) -> None:
    sheet = build_price_sheet()
    mutation(sheet["providers"][0])
    assert not Draft202012Validator(SCHEMA).is_valid(sheet)


def test_unit_rates_add_up_to_every_sized_running_price() -> None:
    """vCPUs times the CPU rate plus GiB times the memory rate is each size's running price."""
    sheet = build_price_sheet()
    with_rates = set()
    for provider in sheet["providers"]:
        rates = provider["unit_rates"]
        resources = {rate["resource"] for rate in provider["compute_rates"]}
        assert (rates is None) == ("memory" not in resources), provider["id"]
        if rates is None:
            continue
        assert (rates["cpu_per_vcpu_hour"] is None) == ("cpu" not in resources), provider["id"]
        with_rates.add(provider["id"])
        for config in provider["configs"]:
            running = config["running_per_hour_usd"]
            if running is None:
                continue
            size = config["size"]
            total = (
                size["vcpu"] * (rates["cpu_per_vcpu_hour"] or 0)
                + size["memory_gib"] * rates["memory_per_gib_hour"]
            )
            assert total == pytest.approx(running["high"], abs=1e-9), (provider["id"], size)
    assert with_rates == EXPECTED_PROVIDERS - {"boat"}
