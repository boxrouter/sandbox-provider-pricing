# SPDX-FileCopyrightText: BoxRouter, Inc.
# SPDX-License-Identifier: Apache-2.0
"""Billing rules for every provider validate against the public billing schema."""

import copy
import json
from pathlib import Path
from typing import Any, cast

import pytest
import yaml  # type: ignore[import-untyped]
from jsonschema import Draft202012Validator

from sandbox_provider_pricing.billing_text import fill_rules
from sandbox_provider_pricing.providers import bundled_billing, provider_ids, validate_billing
from sandbox_provider_pricing.types import json_copy
from sandbox_provider_pricing.versions import bundled_pool, latest_version

ROOT = Path(__file__).resolve().parents[1]
PACKAGES = ROOT / "src" / "sandbox_provider_pricing" / "providers"


def load_schema() -> dict[str, Any]:
    return cast(dict[str, Any], json.loads((ROOT / "schemas" / "billing.schema.json").read_text()))


def load_billing(provider: str) -> dict[str, Any]:
    return load_billing_path(PACKAGES / provider / "billing.yaml")


def load_billing_path(path: Path) -> dict[str, Any]:
    return cast(dict[str, Any], yaml.safe_load(path.read_text()))


def billing_errors(document: dict[str, Any]) -> list[str]:
    return sorted(
        "/".join(map(str, error.absolute_path)) + ": " + error.message
        for error in Draft202012Validator(load_schema()).iter_errors(document)
    )


def test_billing_schema_is_valid_json_schema_2020_12() -> None:
    schema = load_schema()
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    Draft202012Validator.check_schema(schema)


@pytest.mark.parametrize(
    "path", sorted(PACKAGES.glob("*/billing.yaml")), ids=lambda path: path.parent.name
)
def test_every_provider_billing_file_validates(path: Path) -> None:
    """Each file validates as a reader gets it: with its price fields filled."""
    document = load_billing_path(path)
    fill_rules(document, lambda: latest_version(path.parent.name))
    assert billing_errors(document) == []


def test_every_template_section_is_required() -> None:
    document = copy.deepcopy(load_billing("vercel"))
    del document["rules"]["image_pull"]
    del document["formula"]

    errors = billing_errors(document)
    assert any("image_pull" in error for error in errors)
    assert any("formula" in error for error in errors)


def test_answers_are_kept_short() -> None:
    document = copy.deepcopy(load_billing("vercel"))
    document["rules"]["rounding"]["answer"] = "x" * 351

    assert any("rules/rounding/answer" in error for error in billing_errors(document))


def test_runtime_billing_validator_rejects_call_boundary_fallbacks() -> None:
    document = load_billing("modal")
    document["boundary"] = {"start": "create_returned", "end": "destroy_sent", "checked": True}
    with pytest.raises(ValueError, match="boundary"):
        validate_billing(document)


def test_blaxel_metrics_support_reported_label() -> None:
    document = load_billing("blaxel")

    assert document["reported_at_list_price"]["value"] is True
    assert document["status"]["best_label"] == "reported"


def test_answer_requires_exactly_one_provenance_field() -> None:
    document = copy.deepcopy(load_billing("modal"))
    document["rules"]["billed_on"]["unknown_how"] = "Both forms must not be present."

    assert any("billed_on" in error for error in billing_errors(document))


def _answers(node: Any) -> list[dict[str, Any]]:
    if isinstance(node, dict):
        if "answer" in node:
            return [node]
        return [answer for value in node.values() for answer in _answers(value)]
    return []


@pytest.mark.parametrize(
    "path", sorted(PACKAGES.glob("*/billing.yaml")), ids=lambda path: path.parent.name
)
def test_provider_record_is_complete_and_its_sources_exist(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    assert "TODO" not in text
    assert "planning/" not in text
    document = load_billing_path(path)
    for answer in _answers(document["rules"]):
        for source in answer.get("sources", []):
            if not source.startswith("https://"):
                assert (ROOT / source.split("#", 1)[0]).is_file(), source
    for check in document["checks"]:
        assert (ROOT / "providers" / path.parent.name / check["file"]).is_file(), check["file"]


def _containers(node: object, seen: dict[int, object]) -> None:
    if isinstance(node, (dict, list)):
        assert id(node) not in seen, "a bundled document shares a part between two places"
        seen[id(node)] = node
        for item in node.values() if isinstance(node, dict) else node:
            _containers(item, seen)
    else:
        assert isinstance(node, (str, int, float, bool)) or node is None, type(node)


def test_bundled_documents_are_plain_unshared_trees_so_json_copy_is_a_deep_copy() -> None:
    providers = sorted(path.parent.name for path in PACKAGES.glob("*/billing.yaml"))
    assert providers
    documents: list[object] = [bundled_billing(name) for name in providers]
    documents += bundled_pool()
    seen: dict[int, object] = {}
    for document in documents:
        _containers(document, seen)
        copied = json_copy(document)
        assert copied == copy.deepcopy(document)
        mine: dict[int, object] = {}
        _containers(copied, mine)
        assert not set(mine) & set(seen)


@pytest.mark.parametrize(
    "path", sorted(PACKAGES.glob("*/billing.yaml")), ids=lambda path: path.parent.name
)
def test_every_provider_states_what_its_report_is_under_an_account_rate(path: Path) -> None:
    fact = load_billing(path.parent.name)["reported_under_account_rate"]
    assert fact["value"] in (True, False, None)
    assert ("unknown_how" in fact) == (fact["value"] is None)


def test_a_provider_that_reports_no_cost_is_not_account_rate_dependent() -> None:
    calculated = [
        provider
        for provider in provider_ids()
        if load_billing(provider)["status"]["best_label"] != "reported"
    ]
    assert calculated
    for provider in calculated:
        assert load_billing(provider)["reported_under_account_rate"]["value"] is False
