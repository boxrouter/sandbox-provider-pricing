# SPDX-FileCopyrightText: BoxRouter, Inc.
# SPDX-License-Identifier: Apache-2.0
"""`spp from-discovery` writes a valid price version from a discovery price block and refuses the
cases that should not become a version."""

import copy
import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
import yaml  # type: ignore[import-untyped]
from jsonschema import Draft202012Validator, FormatChecker

from sandbox_provider_pricing.discovery import Refused, canonical_json, digest, generate
from sandbox_provider_pricing.providers import validate_billing
from sandbox_provider_pricing.watch.cli import main

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "tests" / "data" / "discovery"
SOURCE = "https://example.test/.well-known/sandbox-provider-spec.json"
NOW = datetime(2026, 11, 13, 12, 0, 0, tzinfo=UTC)
SCHEMA = json.loads((ROOT / "schemas" / "price-version.schema.json").read_text())


def load(name: str) -> dict[str, Any]:
    document: dict[str, Any] = json.loads((DATA / f"{name}.json").read_text())
    return document


def make(prices: list[dict[str, Any]], **fields: Any) -> dict[str, Any]:
    document = load("example")
    document["classes"][0]["prices"] = prices
    document["classes"][0] |= fields
    return document


def build(document: dict[str, Any], previous: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return generate(document, provider="zzexample", source=SOURCE, previous=previous, now=NOW)


def schema_failures(version: dict[str, Any]) -> list[str]:
    validator = Draft202012Validator(SCHEMA, format_checker=FormatChecker())
    return [error.message for error in validator.iter_errors(version)]


def refusal(document: dict[str, Any], previous: list[dict[str, Any]] | None = None) -> str:
    with pytest.raises(Refused) as caught:
        build(document, previous)
    return str(caught.value)


def test_example_becomes_a_valid_version_that_cites_each_item() -> None:
    version = build(load("example"))
    assert schema_failures(version) == []
    assert version["version"] == "zzexample@2026-11-13"
    assert version["discovery_digest"] == digest(load("example"))
    items = load("example")["classes"][0]["prices"]
    assert [source["quote"] for source in version["sources"]] == [canonical_json(i) for i in items]
    assert {source["url"] for source in version["sources"]} == {SOURCE}
    rates = version["classes"][0]["rates"]
    assert rates["cpu"] == {"usd": "0.000014", "per": "vcpu-second"}
    assert rates["memory"] == {"usd": "0.0000045", "per": "gib-second"}
    assert rates["disk"] == {"usd": "0.09", "per": "gib-month"}
    assert rates["egress"] == {"usd": "0", "per": "gb"}
    assert version["classes"][0]["meter"]["disk"]["billed_states"] == [
        "running",
        "paused",
        "stopped",
    ]
    assert version["month_hours"] == "730"


def test_quote_is_the_canonical_json_of_the_item() -> None:
    item = {"unit": "gb", "item": "egress", "price_usd": "0", "basis": "used", "included": True}
    assert canonical_json(item) == (
        '{"basis":"used","included":true,"item":"egress","price_usd":"0","unit":"gb"}'
    )


def test_digest_covers_the_price_block_only() -> None:
    document = load("example")
    other = copy.deepcopy(document)
    other["provider"]["name"] = "Renamed"
    other["classes"][0]["ready"] = False
    assert digest(other) == digest(document)
    other["classes"][0]["prices"][0]["price_usd"] = "0.000015"
    assert digest(other) != digest(document)


def test_a_missing_item_is_unknown_and_never_zero() -> None:
    prices = [load("example")["classes"][0]["prices"][0]]
    version = build(make(prices))
    assert list(version["classes"][0]["rates"]) == ["cpu"]
    assert list(version["classes"][0]["meter"]) == ["cpu"]


@pytest.mark.parametrize(
    ("name", "reason"),
    [
        ("unmarked-zero", "refused: zero amount on an item not marked included"),
        ("negative", "refused: negative amount"),
    ],
)
def test_fixture_refusals(name: str, reason: str) -> None:
    assert refusal(load(name)) == reason


def test_included_zero_is_accepted() -> None:
    version = build(load("included-zero"))
    assert schema_failures(version) == []
    assert version["classes"][0]["rates"]["creation"] == {"usd": "0", "per": "creation"}


def test_included_item_with_an_amount_is_refused() -> None:
    items = load("example")["classes"][0]["prices"]
    items[0]["included"] = True
    assert refusal(make(items)) == "refused: an included item must have amount 0"


@pytest.mark.parametrize("amount", ["1e-5", "0,5", "", ".5"])
def test_amount_must_be_a_decimal_string(amount: str) -> None:
    items = load("example")["classes"][0]["prices"]
    items[0]["price_usd"] = amount
    assert refusal(make(items)) == "refused: price_usd must be a decimal string"
    items[0]["price_usd"] = 0.5
    assert refusal(make(items)) == "refused: price_usd must be a decimal string"


def test_rate_that_moves_more_than_tenfold_is_refused_and_exactly_tenfold_is_not() -> None:
    previous = [build(load("example"))]
    assert refusal(load("tenfold"), previous).splitlines()[0] == (
        "refused: rate moved more than 10x"
    )
    exact = load("example")
    exact["classes"][0]["prices"][0]["price_usd"] = "0.00014"
    assert build(exact, previous)["classes"][0]["rates"]["cpu"]["usd"] == "0.00014"
    down = load("example")
    down["classes"][0]["prices"][0]["price_usd"] = "0.0000013"
    assert refusal(down, previous).splitlines()[0] == "refused: rate moved more than 10x"


def test_item_that_became_zero_is_refused() -> None:
    previous = [build(load("example"))]
    message = refusal(load("became-zero"), previous)
    assert message.splitlines()[0] == "refused: item priced in the previous version became zero"


def test_a_zero_that_was_zero_before_is_accepted() -> None:
    previous = [build(load("example"))]
    assert build(load("example"), previous)["version"] == "zzexample@2026-11-13-120000Z"


def test_comparison_ignores_how_the_unit_is_spelled() -> None:
    previous = [build(load("example"))]
    hourly = load("example")
    hourly["classes"][0]["prices"][0] |= {"unit": "vcpu_hour", "price_usd": "0.0504"}
    assert build(hourly, previous)["classes"][0]["rates"]["cpu"]["per"] == "vcpu-hour"
    wrong = load("example")
    wrong["classes"][0]["prices"][0] |= {"unit": "vcpu_hour", "price_usd": "0.000014"}
    assert refusal(wrong, previous).startswith("refused: rate moved more than 10x")


def test_item_that_is_no_longer_priced_is_noted_not_zeroed() -> None:
    previous = [build(load("example"))]
    prices = load("example")["classes"][0]["prices"][:2]
    version = build(make(prices), previous)
    assert "disk" not in version["classes"][0]["rates"]
    assert any("default:disk" in text for text in version["open_questions"])


def test_the_newest_previous_version_is_the_one_compared() -> None:
    old = build(load("example"))
    old["effective_from"] = old["retrieved_at"] = "2026-01-01T00:00:00Z"
    old["version"] = "zzexample@2026-01-01"
    old["classes"][0]["rates"]["cpu"]["usd"] = "0.1"
    new = build(load("example"))
    assert build(load("example"), [old, new])["version"] == "zzexample@2026-11-13-120000Z"


def test_a_version_that_already_exists_twice_is_refused() -> None:
    first = build(load("example"))
    second = build(load("example"), [first])
    assert refusal(load("example"), [first, second]).startswith("refused: version zzexample@")


@pytest.mark.parametrize(
    ("item", "rate"),
    [
        (
            {"item": "memory", "price_usd": "0.02", "unit": "gb_hour", "basis": "allocated"},
            {"usd": "0.02", "per": "gb-hour", "size_per_unit": "0.931322574615478515625"},
        ),
        (
            {"item": "cpu", "price_usd": "0.04", "unit": "core_second", "basis": "allocated"},
            {"usd": "0.04", "per": "core-second", "size_per_unit": "2"},
        ),
        (
            {"item": "cpu", "price_usd": "0.7", "unit": "vcpu_month", "basis": "allocated"},
            {"usd": "0.7", "per": "vcpu-month"},
        ),
        (
            {"item": "create", "price_usd": "0.00003", "unit": "each", "basis": "count"},
            {"usd": "0.00003", "per": "creation"},
        ),
        (
            {"item": "egress", "price_usd": "0.05", "unit": "gib", "basis": "used"},
            {"usd": "0.05", "per": "gib"},
        ),
    ],
)
def test_units_keep_the_providers_spelling(item: dict[str, Any], rate: dict[str, Any]) -> None:
    version = build(make([item]))
    assert schema_failures(version) == []
    key = "creation" if item["item"] == "create" else item["item"]
    assert version["classes"][0]["rates"][key] == rate


def test_gpu_and_machine_items_are_keyed() -> None:
    prices: list[dict[str, Any]] = [
        {
            "item": "gpu",
            "price_usd": "4",
            "unit": "gpu_hour",
            "basis": "allocated",
            "gpu_model": "nvidia:h100",
        },
        {
            "item": "machine",
            "price_usd": "0.05",
            "unit": "machine_hour",
            "basis": "fixed",
            "size": {"cpu": 2, "memory_mib": 2048},
        },
    ]
    version = build(make(prices))
    assert schema_failures(version) == []
    rates = version["classes"][0]["rates"]
    assert rates["gpu"] == {"nvidia:h100": {"usd": "4", "per": "gpu-hour"}}
    assert rates["machine"] == {
        "2vcpu-2048mib": {"usd": "0.05", "per": "machine-hour", "cpu": "2", "memory_gib": "2"}
    }
    assert version["classes"][0]["meter"]["machine"]["basis"] == "allocated"


def test_gpu_without_a_model_is_refused() -> None:
    item = {"item": "gpu", "price_usd": "4", "unit": "gpu_hour", "basis": "allocated"}
    assert refusal(make([item])).startswith("refused: a gpu item needs a gpu_model")


def test_meter_rules_come_from_the_item() -> None:
    item = {
        "item": "memory",
        "price_usd": "0.0000045",
        "unit": "gib_second",
        "basis": "max_allocated_used",
        "states": ["paused", "running"],
        "increment_seconds": 60,
        "minimum_seconds": 60,
        "allowance": {"quantity": "0.5", "period": "sandbox", "scope": "sandbox"},
    }
    meter = build(make([item]))["classes"][0]["meter"]["memory"]
    assert meter == {
        "basis": "larger_of_request_and_use",
        "billed_states": ["running", "paused"],
        "minimum_seconds": 60,
        "increment_seconds": 60,
        "free_quantity": "0.5",
    }


def test_allowance_beyond_one_sandbox_is_an_exclusion() -> None:
    item = {
        "item": "egress",
        "price_usd": "0.05",
        "unit": "gb",
        "basis": "used",
        "allowance": {"quantity": "100", "period": "month", "scope": "account"},
    }
    version = build(make([item]))
    assert len(version["exclusions"]) == 1
    assert "100 gb per month for each account" in version["exclusions"][0]


def test_region_and_variant_items_are_unknown_and_noted() -> None:
    prices = load("example")["classes"][0]["prices"]
    prices.append(
        {
            "item": "cpu",
            "price_usd": "0.00002",
            "unit": "vcpu_second",
            "basis": "allocated",
            "region": "example:eu-west",
        }  # fmt: skip
    )
    prices.append(
        {
            "item": "memory",
            "price_usd": "0.000001",
            "unit": "gib_second",
            "basis": "allocated",
            "variant": "preemptible",
        }  # fmt: skip
    )
    version = build(make(prices))
    assert version["classes"][0]["rates"]["cpu"]["usd"] == "0.000014"
    assert sum("applies only to" in text for text in version["open_questions"]) == 2
    assert len(version["sources"]) == 4


def test_minimum_quantity_is_noted_and_not_applied() -> None:
    item = {
        "item": "cpu",
        "price_usd": "0.00004",
        "unit": "core_second",
        "basis": "allocated",
        "minimum_quantity": "0.125",
    }
    version = build(make([item]))
    assert any("minimum quantity of 0.125" in text for text in version["open_questions"])
    assert any("2 vCPUs" in text for text in version["open_questions"])


@pytest.mark.parametrize(
    ("item", "reason"),
    [
        (
            {"item": "cpu", "price_usd": "1", "unit": "gib_second", "basis": "allocated"},
            "refused: unit 'gib_second' does not fit item cpu",
        ),
        (
            {"item": "bandwidth", "price_usd": "1", "unit": "gib", "basis": "used"},
            "refused: unknown item 'bandwidth'",
        ),
        (
            {"item": "cpu", "price_usd": "1", "unit": "vcpu_second", "basis": "guessed"},
            "refused: unknown basis 'guessed'",
        ),
    ],
)
def test_malformed_items_are_refused(item: dict[str, Any], reason: str) -> None:
    assert refusal(make([item])) == reason


def test_one_item_priced_twice_is_refused() -> None:
    prices = load("example")["classes"][0]["prices"]
    assert refusal(make(prices + [prices[0]])).startswith("refused: item cpu is priced twice")


def test_a_document_without_prices_for_the_default_class_is_refused() -> None:
    document = make([])
    assert refusal(document) == "refused: no prices for the default class"
    del document["classes"][0]["prices"]
    assert refusal(document) == "refused: no prices for the default class"
    assert refusal({"classes": []}) == "refused: discovery has no classes"


def test_other_classes_get_their_own_rates() -> None:
    document = load("example")
    vm = copy.deepcopy(document["classes"][0]) | {"id": "vm"}
    vm["prices"][0]["price_usd"] = "0.00003"
    document["classes"].append(vm)
    version = build(document)
    assert schema_failures(version) == []
    assert [c["name"] for c in version["classes"]] == ["default", "vm"]
    assert "default" not in version["classes"][1]


def test_the_document_must_name_this_provider() -> None:
    document = load("example")
    document["provider"]["id"] = "other"
    assert refusal(document) == "refused: discovery names another provider"


def test_generated_amounts_are_exact_decimals() -> None:
    item = {"item": "cpu", "price_usd": "0.000000014", "unit": "vcpu_second", "basis": "used"}
    rate = build(make([item]))["classes"][0]["rates"]["cpu"]
    assert Decimal(rate["usd"]) == Decimal("0.000000014")


def run_cli(
    capsys: pytest.CaptureFixture[str], name: str, out: Path, *extra: str
) -> tuple[int, str]:
    code = main(
        [
            "from-discovery",
            "--provider",
            "zzexample",
            "--discovery",
            str(DATA / f"{name}.json"),
            "--source",
            SOURCE,
            "--out",
            str(out),
            "--root",
            str(ROOT),
            *extra,
        ]
    )
    return code, capsys.readouterr().out


def test_cli_writes_one_valid_file(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code, printed = run_cli(capsys, "example", tmp_path)
    files = list(tmp_path.glob("*.yaml"))
    assert code == 0
    assert files == [Path(printed.strip())]
    assert schema_failures(yaml.safe_load(files[0].read_text())) == []


def test_cli_refuses_with_exit_2_and_writes_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    run_cli(capsys, "example", tmp_path)
    before = sorted(tmp_path.iterdir())
    code, printed = run_cli(capsys, "tenfold", tmp_path)
    assert (code, printed.splitlines()[0]) == (2, "refused: rate moved more than 10x")
    code, printed = run_cli(capsys, "unmarked-zero", tmp_path)
    assert (code, printed.strip()) == (
        2,
        "refused: zero amount on an item not marked included",
    )
    assert sorted(tmp_path.iterdir()) == before


def test_cli_accepts_included_zero(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    run_cli(capsys, "example", tmp_path)
    code, _ = run_cli(capsys, "included-zero", tmp_path)
    assert code == 0
    assert len(list(tmp_path.glob("*.yaml"))) == 2


def test_cli_refuses_a_file_that_is_not_json(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text("{")
    code = main(
        [
            "from-discovery",
            "--provider",
            "zzexample",
            "--discovery",
            str(bad),
            "--source",
            SOURCE,
            "--out",
            str(tmp_path / "out"),
        ]  # fmt: skip
    )
    assert code == 2
    assert capsys.readouterr().out.startswith("refused: ")


def test_cli_refuses_a_source_that_is_not_an_address(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = main(
        [
            "from-discovery",
            "--provider",
            "zzexample",
            "--discovery",
            str(DATA / "example.json"),
            "--source",
            "somewhere",
            "--out",
            str(tmp_path),
        ]  # fmt: skip
    )
    assert code == 2
    assert "--source" in capsys.readouterr().out


def provider_root(tmp_path: Path, prices: str | None) -> Path:
    folder = tmp_path / "src/sandbox_provider_pricing/providers/zzexample"
    folder.mkdir(parents=True)
    billing = {"name": "ZZ", "website": "https://example.test"}
    if prices:
        billing["prices"] = prices
    (folder / "billing.yaml").write_text(yaml.safe_dump(billing))
    return tmp_path


def test_a_hand_priced_provider_cannot_use_discovery(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = provider_root(tmp_path / "checkout", None)
    code = main(
        [
            "from-discovery",
            "--provider",
            "zzexample",
            "--discovery",
            str(DATA / "example.json"),
            "--source",
            SOURCE,
            "--out",
            str(tmp_path / "out"),
            "--root",
            str(root),
        ]  # fmt: skip
    )
    assert code == 2
    assert "does not say prices: discovery" in capsys.readouterr().out
    root = provider_root(tmp_path / "other", "discovery")
    code = main(
        [
            "from-discovery",
            "--provider",
            "zzexample",
            "--discovery",
            str(DATA / "example.json"),
            "--source",
            SOURCE,
            "--out",
            str(tmp_path / "out"),
            "--root",
            str(root),
        ]  # fmt: skip
    )
    assert code == 0


def test_a_billing_record_may_say_prices_discovery() -> None:
    sample = yaml.safe_load(
        (ROOT / "src/sandbox_provider_pricing/providers/superserve/billing.yaml").read_text()
    )
    validate_billing(sample | {"prices": "discovery"})
    with pytest.raises(ValueError, match="prices"):
        validate_billing(sample | {"prices": "hand"})
