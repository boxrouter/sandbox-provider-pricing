# SPDX-FileCopyrightText: BoxRouter, Inc.
# SPDX-License-Identifier: Apache-2.0
"""`cost-method.json` is generated from METHOD.md, billing.yaml and the price versions only."""

import copy
import json
import re
import subprocess
import sys
from importlib import util
from pathlib import Path
from typing import cast

import pytest
import yaml  # type: ignore[import-untyped]
from jsonschema import Draft202012Validator

from sandbox_provider_pricing import cost_method, seed_versions
from sandbox_provider_pricing.billing_text import fill_answer
from sandbox_provider_pricing.cost_method import build_cost_method, validate_cost_method
from sandbox_provider_pricing.providers import (
    FIRST_KEPT_RULES_VERSION,
    billing,
    billing_history,
)
from sandbox_provider_pricing.versions import latest_version

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
_spec = util.spec_from_file_location("pricing_docs", ROOT / "scripts" / "docs.py")
assert _spec is not None and _spec.loader is not None
docs = util.module_from_spec(_spec)
_spec.loader.exec_module(docs)


def _squash(text: str) -> str:
    return " ".join(text.split())


def test_the_document_matches_its_schema_and_holds_every_price_version() -> None:
    document = cost_method()
    validate_cost_method(document)
    published = {name for entry in document["providers"].values() for name in entry["versions"]}
    assert published == {version["version"] for version in seed_versions()}


def test_a_document_missing_its_method_or_a_providers_formula_fails_the_schema() -> None:
    document = cost_method()
    del document["method"]["labels"]["unknown"]
    with pytest.raises(ValueError, match="method/labels"):
        validate_cost_method(document)
    document = cost_method()
    del document["providers"]["e2b"]["formula"]
    with pytest.raises(ValueError, match="formula"):
        validate_cost_method(document)


@pytest.mark.parametrize("provider", sorted(cost_method()["providers"]))
def test_each_providers_readme_formula_is_its_latest_versions_formula(provider: str) -> None:
    entry = cost_method(provider)
    latest = cost_method(provider, entry["latest_version"])
    page = (ROOT / "providers" / provider / "README.md").read_text(encoding="utf-8")
    heading = "## How the cost is worked out\n\n"
    assert page.count(heading) == 1
    section = page.split(heading, 1)[1].split("\n\n", 1)[0]
    assert section == latest["formula"]


def test_the_readme_status_table_is_built_from_the_same_document() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    table = readme.split(docs.STATUS_START, 1)[1].split(docs.STATUS_END, 1)[0]
    for provider, entry in cost_method()["providers"].items():
        row = f"| [{entry['name']}](providers/{provider}/README.md) | `{entry['best_label']}` | "
        assert f"{row}{docs._cell(entry['formula'])} |" in table


def test_a_price_version_selects_the_version_that_priced_a_cost() -> None:
    entry = cost_method("vercel")
    older = next(name for name in entry["versions"] if name != entry["latest_version"])
    narrowed = cost_method("vercel", older)
    assert list(narrowed["versions"]) == [older]
    assert narrowed["versions"][older] == entry["versions"][older]
    assert narrowed["formula"] == entry["formula"]
    assert narrowed["versions"][older]["state"] == "replaced"
    assert entry["versions"][entry["latest_version"]]["state"] == "in_effect"


def test_unknown_providers_and_versions_are_refused() -> None:
    with pytest.raises(ValueError, match="no cost method for provider 'nope'"):
        cost_method("nope")
    with pytest.raises(ValueError, match="no price version 'e2b@x' for provider 'e2b'"):
        cost_method("e2b", "e2b@x")
    with pytest.raises(ValueError, match="needs its provider"):
        cost_method(version="e2b@x")


def test_a_returned_document_is_a_copy() -> None:
    cost_method("e2b")["formula"] = "changed"
    assert cost_method("e2b")["formula"] != "changed"


def test_every_method_sentence_is_in_method_md() -> None:
    method = _squash((ROOT / "METHOD.md").read_text(encoding="utf-8"))
    slots = cost_method()["method"]
    paragraphs = [
        *slots["what_a_cost_is"],
        *slots["list_price_vs_bill"],
        *slots["never_a_cost"],
        *(
            text
            for label in slots["labels"].values()
            for text in (label["meaning"], *label["method"])
        ),
    ]
    assert len(paragraphs) == 12
    for paragraph in paragraphs:
        assert paragraph in method


def test_every_provider_sentence_is_in_its_billing_record_or_price_version() -> None:
    for provider, entry in cost_method()["providers"].items():
        path = ROOT / "src/sandbox_provider_pricing/providers" / provider / "billing.yaml"
        source = _squash(path.read_text(encoding="utf-8"))
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        for field in ("summary", "formula", "why_not_higher", "would_raise"):
            assert entry[field] in source
        for rule in entry["rules"]:
            # An answer's price fields are filled from the price version in effect.
            written = cast(str, raw["rules"][rule["key"]]["answer"])
            assert _squash(written) in source
            assert rule["answer"] == _squash(fill_answer(written, latest_version(provider)))
        for version in entry["versions"].values():
            text = _squash((ROOT / version["file"]).read_text(encoding="utf-8"))
            assert version["classes"][0]["name"] in text
            assert version["sources"]


def test_the_release_asset_is_the_built_document(tmp_path: Path) -> None:
    out = tmp_path / "cost-method.json"
    subprocess.run(
        [sys.executable, "-m", "sandbox_provider_pricing.cost_method", "--out", str(out)],
        check=True,
        cwd=ROOT,
    )
    document = json.loads(out.read_text(encoding="utf-8"))
    schema = json.loads((ROOT / "schemas/cost-method.schema.json").read_text(encoding="utf-8"))
    Draft202012Validator(schema).validate(document)
    assert document == build_cost_method()
    assert re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", document["pricing_release_version"])


def test_the_release_builds_and_lists_the_asset() -> None:
    assert "`cost-method.json`" in (ROOT / "RELEASE.md").read_text(encoding="utf-8")
    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
    assert "spp-cost-method --out dist/cost-method.json" in makefile
    assert "cp schemas/cost-method.schema.json dist/cost-method.schema.json" in makefile


def test_a_version_without_a_state_breaks_the_schema() -> None:
    document = cost_method()
    broken = copy.deepcopy(document)
    version = next(iter(broken["providers"]["e2b"]["versions"].values()))
    version["state"] = "current"
    with pytest.raises(ValueError, match="state"):
        validate_cost_method(broken)


def _fixture_versions() -> list[tuple[str, dict[str, object]]]:
    return [
        (path.parents[2].name, json.loads(path.read_text(encoding="utf-8"))["versions"])
        for path in sorted(ROOT.glob("providers/*/fixtures/*/result.json"))
    ]


@pytest.mark.parametrize(("provider", "versions"), _fixture_versions())
def test_the_recorded_versions_of_every_fixture_select_the_method_that_priced_it(
    provider: str, versions: dict[str, object]
) -> None:
    entry = cost_method(provider, str(versions["prices"]), int(str(versions["rules"])))
    assert entry["rules_version"] == versions["rules"]
    assert list(entry["versions"]) == [versions["prices"]]


def test_an_old_fixtures_rules_version_returns_that_versions_formula_not_the_newest() -> None:
    fixture = ROOT / "providers/modal/fixtures/best/result.json"
    recorded = json.loads(fixture.read_text(encoding="utf-8"))["versions"]
    newest = cost_method("modal", recorded["prices"], recorded["rules"])
    assert newest["rules_version"] == 4
    for old in (2, 3):
        # A result priced under an earlier rules version records that version.
        entry = cost_method("modal", recorded["prices"], old)
        history = billing_history("modal")[old]
        assert entry["rules_version"] == old
        assert entry["formula"] == _squash(history["formula"])
        assert entry["formula"] != newest["formula"]
        assert entry["rules"] != newest["rules"]
        assert entry["rules_history"] == {}
        assert list(entry["versions"]) == [recorded["prices"]]


def test_a_rules_version_that_was_not_kept_is_refused() -> None:
    with pytest.raises(ValueError, match="no rules version 1 kept for provider 'modal'"):
        cost_method("modal", rules=1)
    with pytest.raises(ValueError, match="needs its provider"):
        cost_method(rules=2)


@pytest.mark.parametrize("provider", sorted(cost_method()["providers"]))
def test_every_rules_version_back_to_the_first_kept_has_its_document(provider: str) -> None:
    current = billing(provider)["rules_version"]
    history = billing_history(provider)
    assert sorted(history) == list(range(FIRST_KEPT_RULES_VERSION, current))
    for version, document in history.items():
        assert document["rules_version"] == version
    entry = cost_method(provider)
    assert list(entry["rules_history"]) == [
        str(version) for version in sorted(history, reverse=True)
    ]


def test_every_earlier_rules_sentence_is_in_its_billing_history_file() -> None:
    for provider, entry in cost_method()["providers"].items():
        for version, earlier in entry["rules_history"].items():
            source = _squash(
                (
                    ROOT
                    / "src/sandbox_provider_pricing/providers"
                    / provider
                    / "billing-history"
                    / f"{version}.yaml"
                ).read_text(encoding="utf-8")
            )
            for field in ("summary", "formula", "why_not_higher", "would_raise"):
                assert earlier[field] in source
            for rule in earlier["rules"]:
                assert rule["answer"] in source


def test_labels_carry_the_words_a_consumer_shows_and_unknown_shows_none() -> None:
    labels = cost_method()["method"]["labels"]
    assert {label: item["title"] for label, item in labels.items()} == {
        "reported": "Reported By Provider",
        "calculated": "Calculated",
        "unknown": None,
    }
    method = _squash((ROOT / "METHOD.md").read_text(encoding="utf-8"))
    assert "- `reported`: Reported By Provider - `calculated`: Calculated" in method


def test_state_titles_come_from_method_md_and_stay_separate_from_the_labels() -> None:
    method = cost_method()["method"]
    assert method["state_titles"] == {"pending": "Pending", "unknown": "Unknown"}
    # `unknown` names a settlement state and a provenance label: only the state gets a title.
    assert method["labels"]["unknown"]["title"] is None
    text = _squash((ROOT / "METHOD.md").read_text(encoding="utf-8"))
    assert "- `pending`: Pending - `unknown`: Unknown" in text


def test_a_document_missing_a_state_title_or_holding_an_extra_one_fails_the_schema() -> None:
    document = cost_method()
    del document["method"]["state_titles"]["pending"]
    with pytest.raises(ValueError, match="state_titles"):
        validate_cost_method(document)
    document = cost_method()
    document["method"]["state_titles"]["exact"] = "Exact"
    with pytest.raises(ValueError, match="state_titles"):
        validate_cost_method(document)
