# SPDX-FileCopyrightText: BoxRouter, Inc.
# SPDX-License-Identifier: Apache-2.0
"""The three formats: a price version, a usage record and a cost."""

import copy
import json
from functools import cache
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator

from sandbox_provider_pricing.types import JsonObject

ROOT = Path(__file__).resolve().parents[1]
KINDS = ["price-version", "usage", "cost"]
SOURCES = ["provider", "published", "measured", "recorded", "calculated", "unknown"]
FIGURE_OBSERVED_AT = "2026-10-02T14:03:00Z"


def load_schema(kind: str) -> JsonObject:
    schema: JsonObject = json.loads((ROOT / "schemas" / f"{kind}.schema.json").read_text())
    return schema


def load_example(kind: str) -> JsonObject:
    example: JsonObject = json.loads((ROOT / "examples" / f"{kind}.json").read_text())
    return example


@cache
def validator(kind: str) -> Draft202012Validator:
    return Draft202012Validator(load_schema(kind))


def errors(kind: str, document: JsonObject) -> list[str]:
    """Every reason the document is rejected, as `<path>: <message>`, sorted."""
    return sorted(
        f"{'/'.join(map(str, error.absolute_path)) or '<root>'}: {error.message}"
        for error in validator(kind).iter_errors(document)
    )


def price_version(**class_parts: Any) -> JsonObject:
    """A price version with one default class built from `rates`, `meter` and the like."""
    document = load_example("price-version")
    document["classes"] = [{"name": "default", "default": True, **class_parts}]
    return document


@pytest.mark.parametrize("kind", KINDS)
def test_schema_is_valid_json_schema_2020_12(kind: str) -> None:
    schema = load_schema(kind)
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    Draft202012Validator.check_schema(schema)


@pytest.mark.parametrize("kind", KINDS)
def test_example_validates(kind: str) -> None:
    assert errors(kind, load_example(kind)) == []


def _rate_units(node: Any, path: str = "") -> list[tuple[str, JsonObject]]:
    """Every `per` enum in a schema, by path, outside the `if` conditions that only test it."""
    found: list[tuple[str, JsonObject]] = []
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "if":
                continue
            here = f"{path}/{key}"
            if key == "per" and isinstance(value, dict) and "enum" in value:
                found.append((here, value))
            found += _rate_units(value, here)
    return found


def test_every_rate_unit_enum_is_open() -> None:
    """Units grow with the provider roster (Agent37 added months), so clients read `per` as the
    known units plus any string: OpenAPI's `x-boxrouter-open-enum`."""
    units = _rate_units(load_schema("price-version"))
    assert len(units) >= 9
    assert [path for path, unit in units if unit.get("x-boxrouter-open-enum") is not True] == []


def test_source_is_the_same_six_values_in_usage_and_cost() -> None:
    assert load_schema("usage")["$defs"]["source"]["enum"] == SOURCES
    assert load_schema("cost")["$defs"]["source"]["enum"] == SOURCES


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        (["started"], ["started: 'source' is a required property"]),
        # Without its source the already-unknown region is no longer unknown, so its null name
        # is rejected as well.
        (
            ["region"],
            [
                "region/name: None is not of type 'string'",
                "region: 'source' is a required property",
            ],
        ),
        (["size"], ["size: 'source' is a required property"]),
        (["intervals", 0], ["intervals/0: 'source' is a required property"]),
        (["creations"], ["creations: 'source' is a required property"]),
    ],
)
def test_usage_fact_without_a_source_is_rejected(
    path: list[str | int], expected: list[str]
) -> None:
    usage = load_example("usage")
    fact: Any = usage
    for step in path:
        fact = fact[step]
    del fact["source"]
    assert errors("usage", usage) == expected


def test_usage_source_outside_the_six_is_rejected() -> None:
    usage = load_example("usage")
    usage["size"]["source"] = "guessed"
    assert errors("usage", usage) == [
        "size/source: 'guessed' is not one of "
        "['provider', 'published', 'measured', 'recorded', 'calculated', 'unknown']"
    ]


def test_usage_fact_without_when_or_how_is_rejected() -> None:
    usage = load_example("usage")
    del usage["size"]["observed_at"]
    del usage["size"]["how"]
    assert errors("usage", usage) == [
        "size: 'how' is a required property",
        "size: 'observed_at' is a required property",
    ]


def test_usage_time_that_is_not_utc_is_rejected() -> None:
    usage = load_example("usage")
    usage["size"]["observed_at"] = "2026-09-29T18:39:04+02:00"
    assert errors("usage", usage) == [
        "size/observed_at: '2026-09-29T18:39:04+02:00' does not match "
        "'^[0-9]{4}-(0[1-9]|1[0-2])-(0[1-9]|[12][0-9]|3[01])T([01][0-9]|2[0-3]):[0-5][0-9]:"
        "[0-5][0-9](\\\\.[0-9]+)?Z$'"
    ]


def test_usage_unknown_fact_with_a_value_is_rejected() -> None:
    usage = load_example("usage")
    usage["region"]["name"] = "us-east-1"
    assert errors("usage", usage) == ["region/name: 'us-east-1' is not of type 'null'"]


def test_usage_known_fact_with_a_null_value_is_rejected() -> None:
    usage = load_example("usage")
    usage["creations"]["count"] = None
    assert errors("usage", usage) == ["creations/count: None is not of type 'integer'"]


def test_usage_unknown_size_may_not_carry_values() -> None:
    usage = load_example("usage")
    usage["size"]["source"] = "unknown"
    [message] = errors("usage", usage)
    assert message.startswith("size: {'cpu': 2, 'memory_mib': 1024, 'source': 'unknown'")
    assert message.endswith(
        "should not be valid under {'anyOf': [{'required': ['cpu']}, "
        "{'required': ['memory_mib']}, {'required': ['disk_mib']}, "
        "{'required': ['gpu']}, {'required': ['gpu_model']}]}"
    )


def test_usage_known_size_needs_at_least_one_value() -> None:
    usage = load_example("usage")
    del usage["size"]["cpu"]
    del usage["size"]["memory_mib"]
    [message] = errors("usage", usage)
    assert message.startswith("size: {'source': 'provider'")
    assert message.endswith("is not valid under any of the given schemas")


def test_usage_unknown_size_without_values_is_valid() -> None:
    usage = load_example("usage")
    usage["size"] = {
        "source": "unknown",
        "observed_at": "2026-09-29T18:39:04Z",
        "how": "the sandbox was gone before its size was read",
    }
    assert errors("usage", usage) == []


def test_usage_gpu_count_and_model_are_a_pair() -> None:
    usage = load_example("usage")
    usage["size"]["gpu"] = 1
    assert any(
        message.startswith("size: 'gpu_model' is a required property")
        for message in errors("usage", usage)
    )

    usage["size"]["gpu_model"] = "nvidia:h100"
    assert errors("usage", usage) == []

    del usage["size"]["gpu"]
    assert any(
        message.startswith("size: 'gpu' is a required property")
        for message in errors("usage", usage)
    )


def test_usage_interval_seconds_may_be_a_range_when_a_change_was_noticed_late() -> None:
    usage = load_example("usage")
    usage["intervals"][0].update(
        seconds={"low": 1740, "high": 1800},
        source="recorded",
        how="the list check at 19:08 saw it running, the one at 19:09 saw it gone",
    )
    assert errors("usage", usage) == []


def test_usage_interval_seconds_as_a_string_is_rejected() -> None:
    usage = load_example("usage")
    usage["intervals"][0]["seconds"] = "1800"
    assert errors("usage", usage) == [
        "intervals/0/seconds: '1800' is not of type 'number', 'object'",
        "intervals/0/seconds: '1800' is not valid under any of the given schemas",
    ]


def test_usage_interval_in_a_state_outside_the_three_is_rejected() -> None:
    usage = load_example("usage")
    usage["intervals"][0]["state"] = "starting"
    assert errors("usage", usage) == [
        "intervals/0/state: 'starting' is not one of ['running', 'paused', 'stopped']"
    ]


def test_usage_may_carry_the_class_and_provider_reported_usage() -> None:
    usage = load_example("usage")
    usage["class"] = {
        "name": "vm",
        "source": "recorded",
        "observed_at": "2026-09-29T18:39:03Z",
        "how": "the create request Cloud sent",
    }
    usage["active_cpu"] = {
        "seconds": 12.5,
        "source": "provider",
        "observed_at": "2026-09-29T19:09:05Z",
        "how": "Vercel session activeCpuDurationMs",
    }
    usage["egress"] = {
        "bytes": None,
        "source": "unknown",
        "observed_at": "2026-09-29T19:09:05Z",
        "how": "the sandbox did not stop cleanly",
    }
    assert errors("usage", usage) == []


def test_cost_total_as_a_json_number_is_rejected() -> None:
    cost = load_example("cost")
    cost["total"] = 0.0585
    assert errors("cost", cost) == [
        "total: 0.0585 is not of type 'object'",
        "total: 0.0585 is not valid under any of the given schemas",
    ]


def test_cost_total_ends_as_json_numbers_are_rejected() -> None:
    cost = load_example("cost")
    cost["total"] = {"low": 0.0585, "high": 0.0585}
    assert errors("cost", cost) == [
        "total: {'low': 0.0585, 'high': 0.0585} is not valid under any of the given schemas"
    ]


def test_cost_total_with_no_upper_bound_is_rejected() -> None:
    cost = load_example("cost")
    cost["total"] = {"low": "0.04", "high": None}
    assert errors("cost", cost) == [
        "total: {'low': '0.04', 'high': None} is not valid under any of the given schemas"
    ]


def test_cost_total_with_no_lower_bound_is_rejected() -> None:
    cost = load_example("cost")
    cost["label"] = "calculated"
    cost["total"] = {"low": None, "high": None}
    assert errors("cost", cost) == [
        "total: {'low': None, 'high': None} is not valid under any of the given schemas"
    ]


def test_cost_per_hour_with_no_upper_bound_is_rejected() -> None:
    cost = load_example("cost")
    cost["per_hour"] = {"low": "0.04", "high": None}
    assert errors("cost", cost) == ["per_hour/high: None is not of type 'string'"]


def test_cost_amount_in_exponent_notation_is_rejected() -> None:
    cost = load_example("cost")
    cost["lines"][0]["rate"] = "1.4e-05"
    assert errors("cost", cost) == [
        "lines/0/rate: '1.4e-05' does not match '^(0|[1-9][0-9]*)(\\\\.[0-9]+)?$'"
    ]


def test_cost_label_outside_the_three_is_rejected() -> None:
    cost = load_example("cost")
    cost["label"] = "billed"
    assert errors("cost", cost) == [
        "label: 'billed' is not one of ['reported', 'calculated', 'unknown']"
    ]


def test_cost_unknown_label_with_a_total_is_rejected() -> None:
    cost = load_example("cost")
    cost["label"] = "unknown"
    assert errors("cost", cost) == [
        "total: {'low': '0.0585', 'high': '0.0585'} is not of type 'null'"
    ]


def test_cost_label_other_than_unknown_without_a_total_is_rejected() -> None:
    cost = load_example("cost")
    cost["label"] = "calculated"
    cost["total"] = None
    assert errors("cost", cost) == ["total: None is not of type 'object'"]


def test_cost_unknown_has_a_null_total_and_no_price_version() -> None:
    cost = load_example("cost")
    cost.update(
        label="unknown",
        total=None,
        lines=[],
        held_back_by=[
            {
                "code": "no_rate",
                "resource": "usage",
                "text": "We do not have Blaxel's prices for this region yet",
            }
        ],
        price_version=None,
    )
    assert errors("cost", cost) == []


def test_cost_accepts_a_same_day_time_suffixed_price_version() -> None:
    cost = load_example("cost")
    cost["price_version"] = "modal@2026-10-20-061900Z"
    assert errors("cost", cost) == []


def test_cost_reported_needs_the_figures_source() -> None:
    cost = load_example("cost")
    cost.update(label="reported", lines=[])
    assert errors("cost", cost) == ["<root>: 'reported_figure' is a required property"]


def test_cost_reported_figure_must_come_from_the_provider() -> None:
    cost = load_example("cost")
    cost.update(
        label="reported",
        lines=[],
        reported_figure={"source": "published", "observed_at": FIGURE_OBSERVED_AT, "how": "x"},
    )
    assert errors("cost", cost) == ["reported_figure/source: 'provider' was expected"]


def test_cost_reported_with_the_provider_figures_source_is_valid() -> None:
    cost = load_example("cost")
    cost.update(
        label="reported",
        total={"low": "0.0612", "high": "0.0612"},
        lines=[],
        reported_figure={
            "source": "provider",
            "observed_at": FIGURE_OBSERVED_AT,
            "how": "Daytona GET /organization/{org}/usage/sandbox",
        },
    )
    assert errors("cost", cost) == []


def test_cost_figure_source_on_a_calculated_cost_is_rejected() -> None:
    cost = load_example("cost")
    cost["reported_figure"] = {"source": "provider", "observed_at": FIGURE_OBSERVED_AT, "how": "x"}
    [message] = errors("cost", cost)
    assert message.startswith("<root>: {'label': 'calculated'")
    assert message.endswith("should not be valid under {'required': ['reported_figure']}")


def test_unknown_sandbox_cost_can_retain_an_hourly_rate_range() -> None:
    cost = load_example("cost")
    cost.update(label="unknown", total=None, lines=[], per_hour={"low": "0.0162", "high": "0.1170"})
    assert errors("cost", cost) == []
    cost["label"] = "estimated"
    assert any("label" in error for error in errors("cost", cost))


def test_price_version_rate_as_a_json_number_is_rejected() -> None:
    version = load_example("price-version")
    version["classes"][0]["rates"]["cpu"]["usd"] = 0.000014
    assert errors("price-version", version) == [
        "classes/0/rates/cpu/usd: 1.4e-05 is not of type 'string'"
    ]


def test_price_version_rate_in_exponent_notation_is_rejected() -> None:
    version = load_example("price-version")
    version["classes"][0]["rates"]["cpu"]["usd"] = "1.4e-05"
    assert errors("price-version", version) == [
        "classes/0/rates/cpu/usd: '1.4e-05' does not match '^(0|[1-9][0-9]*)(\\\\.[0-9]+)?$'"
    ]


def test_price_version_rate_outside_the_six_is_rejected() -> None:
    version = load_example("price-version")
    version["classes"][0]["rates"]["network"] = {"usd": "0.01", "per": "gib"}
    assert errors("price-version", version) == [
        "classes/0/rates: Additional properties are not allowed ('network' was unexpected)"
    ]


@pytest.mark.parametrize(
    "field", ["status", "effective_to", "first_seen_at", "last_confirmed_at", "content_hash"]
)
def test_price_version_database_only_field_is_rejected(field: str) -> None:
    version = load_example("price-version")
    version[field] = "live"
    assert errors("price-version", version) == [
        f"<root>: Additional properties are not allowed ('{field}' was unexpected)"
    ]


def test_price_version_date_without_a_time_is_rejected() -> None:
    version = load_example("price-version")
    version["effective_from"] = "2026-09-29"
    [message] = errors("price-version", version)
    assert message.startswith("effective_from: '2026-09-29' does not match")


def test_price_version_date_can_have_a_utc_time_suffix() -> None:
    version = load_example("price-version")
    version["version"] = "e2b@2026-10-21-120000Z"
    assert errors("price-version", version) == []


def test_price_version_without_a_default_class_is_rejected() -> None:
    version = load_example("price-version")
    del version["classes"][0]["default"]
    [message] = errors("price-version", version)
    assert message.startswith("classes: [{'name': 'default'")
    assert message.endswith("does not contain items matching the given schema")


def test_price_version_with_two_default_classes_is_rejected() -> None:
    version = load_example("price-version")
    second = copy.deepcopy(version["classes"][0])
    second["name"] = "vm"
    version["classes"].append(second)
    assert errors("price-version", version) == [
        "classes: Too many items match the given schema (expected at most 1)"
    ]


def test_price_version_core_rate_needs_the_vcpus_one_core_covers() -> None:
    version = load_example("price-version")
    version["classes"][0]["rates"]["cpu"] = {"usd": "0.00003942", "per": "core-second"}
    assert errors("price-version", version) == [
        "classes/0/rates/cpu: 'size_per_unit' is a required property"
    ]


def test_price_version_gb_rate_needs_the_gib_one_gb_covers() -> None:
    version = load_example("price-version")
    version["classes"][0]["rates"]["memory"] = {"usd": "0.0000115", "per": "gb-second"}
    assert errors("price-version", version) == [
        "classes/0/rates/memory: 'size_per_unit' is a required property"
    ]


def test_price_version_vcpu_rate_may_not_carry_a_unit_size() -> None:
    version = load_example("price-version")
    version["classes"][0]["rates"]["cpu"]["size_per_unit"] = "2"
    [message] = errors("price-version", version)
    assert message.startswith("classes/0/rates/cpu: {'usd': '0.000014'")
    assert message.endswith("should not be valid under {'required': ['size_per_unit']}")


def test_price_version_meter_for_a_resource_that_is_not_time_billed_is_rejected() -> None:
    version = load_example("price-version")
    version["classes"][0]["meter"]["egress"] = {"basis": "allocated", "billed_states": ["running"]}
    assert errors("price-version", version) == [
        "classes/0/meter: 'egress' does not match any of the regexes: "
        "'^(cpu|gpu|machine)$', '^disk$', '^memory$', '^snapshot_storage$'"
    ]


def test_price_version_gpu_rates_are_keyed_by_registry_model() -> None:
    version = price_version(
        rates={
            "gpu": {
                "nvidia:h100": {"usd": "0.001097", "per": "gpu-second"},
                "amd:mi355x": {"usd": "3.44", "per": "gpu-hour"},
            }
        },
        meter={"gpu": {"basis": "allocated", "billed_states": ["running"]}},
    )
    assert errors("price-version", version) == []
    version["classes"][0]["rates"]["gpu"]["NVIDIA H100"] = {"usd": "1", "per": "gpu-hour"}
    assert any(
        "NVIDIA H100" in message and "does not match" in message
        for message in errors("price-version", version)
    )


def test_price_version_memory_tiers_are_positive_mib_values() -> None:
    version = price_version(
        rates={"memory": {"usd": "0.0000115", "per": "gb-second", "size_per_unit": "1"}},
        meter={
            "memory": {
                "basis": "active",
                "billed_states": ["running"],
                "memory_steps_mib": [2048, 4096, 8192, 16384, 32768],
            }
        },
    )
    assert errors("price-version", version) == []
    version["classes"][0]["meter"]["memory"]["memory_steps_mib"] = [0, 4096]
    assert any("minimum" in message for message in errors("price-version", version))


def test_price_version_meter_without_billed_states_is_rejected() -> None:
    version = load_example("price-version")
    version["classes"][0]["meter"]["cpu"]["billed_states"] = []
    assert errors("price-version", version) == [
        "classes/0/meter/cpu/billed_states: [] should be non-empty"
    ]


def test_price_version_disk_as_memory_ratio_belongs_to_the_disk_meter_only() -> None:
    version = load_example("price-version")
    version["classes"][0]["meter"]["cpu"]["disk_gib_per_memory_gib"] = "20"
    assert errors("price-version", version) == [
        "classes/0/meter/cpu: Additional properties are not allowed "
        "('disk_gib_per_memory_gib' was unexpected)"
    ]


# The providers' published shapes. These check that the format can hold each one; the digits
# are the 2026-10-01 benchmark readings and are not an authoritative price list.
PROVIDER_SHAPES: dict[str, JsonObject] = {
    "modal": {
        "rates": {
            "cpu": {"usd": "0.00003942", "per": "core-second", "size_per_unit": "2"},
            "memory": {"usd": "0.00000667", "per": "gib-second"},
            "egress": {"usd": "0.04", "per": "gib"},
        },
        "meter": {
            "cpu": {"basis": "larger_of_request_and_use", "billed_states": ["running"]},
            "memory": {"basis": "larger_of_request_and_use", "billed_states": ["running"]},
            "disk": {
                "basis": "larger_of_request_and_use",
                "billed_states": ["running"],
                "disk_gib_per_memory_gib": "20",
            },
        },
        "region_multipliers": {"us": "1.15", "us-west": "1.75"},
    },
    "vercel": {
        "rates": {
            "cpu": {"usd": "0.128", "per": "vcpu-hour"},
            "memory": {"usd": "0.0212", "per": "gb-hour", "size_per_unit": "1"},
            "creation": {"usd": "0.60", "per": "million-creations"},
            "egress": {"usd": "0.15", "per": "gb"},
        },
        "meter": {
            "cpu": {"basis": "active", "billed_states": ["running"]},
            "memory": {
                "basis": "allocated",
                "billed_states": ["running"],
                "increment_seconds": 60,
            },
        },
    },
    "daytona": {
        "rates": {
            "cpu": {"usd": "0.0504", "per": "vcpu-hour"},
            "memory": {"usd": "0.0162", "per": "gib-hour"},
            "disk": {"usd": "0.000108", "per": "gib-hour"},
        },
        "meter": {
            "cpu": {"basis": "allocated", "billed_states": ["running"]},
            "memory": {"basis": "allocated", "billed_states": ["running"]},
            "disk": {
                "basis": "allocated",
                "billed_states": ["running", "paused", "stopped"],
                "free_quantity": "5",
            },
        },
    },
    "blaxel": {
        "rates": {"memory": {"usd": "0.0000115", "per": "gb-second", "size_per_unit": "1"}},
        "meter": {"memory": {"basis": "allocated", "billed_states": ["running"]}},
    },
}


@pytest.mark.parametrize("provider", PROVIDER_SHAPES)
def test_price_version_holds_the_providers_published_shape(provider: str) -> None:
    version = price_version(**PROVIDER_SHAPES[provider])
    version["provider"] = provider
    version["version"] = f"{provider}@2026-10-20-120000Z"
    assert errors("price-version", version) == []


def test_price_version_holds_a_second_class_with_its_own_rates() -> None:
    version = price_version(**PROVIDER_SHAPES["modal"])
    vm = {"name": "vm", **copy.deepcopy(PROVIDER_SHAPES["modal"])}
    version["classes"].append(vm)
    assert errors("price-version", version) == []


def test_price_version_accepts_a_published_free_rate_of_zero() -> None:
    version = price_version(
        rates={
            "cpu": {"usd": "0.000014", "per": "vcpu-second"},
            "disk": {"usd": "0", "per": "gib-hour"},
        },
        meter={"cpu": {"basis": "allocated", "billed_states": ["running"]}},
    )
    assert errors("price-version", version) == []


def test_unknown_cost_example_has_no_total() -> None:
    cost = json.loads((ROOT / "examples" / "cost-unknown.json").read_text())
    assert errors("cost", cost) == []
    assert (cost["label"], cost["total"], cost["lines"]) == ("unknown", None, [])
