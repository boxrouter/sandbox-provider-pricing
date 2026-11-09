# SPDX-FileCopyrightText: BoxRouter, Inc.
# SPDX-License-Identifier: Apache-2.0
"""The cost method as data: METHOD.md, each provider's billing rules and every price version.

This is the one generator behind `cost-method.json`, the provider pages and the README table. It
writes no sentence of its own: the text comes from METHOD.md, each provider's `billing.yaml` and its
price versions.
"""

import argparse
import re
from functools import cache
from importlib import resources
from pathlib import Path

from jsonschema import Draft202012Validator

from sandbox_provider_pricing._util import (
    bundled_schema,
    package_version,
    write_json,
)
from sandbox_provider_pricing.providers import billing, billing_history, provider_ids
from sandbox_provider_pricing.types import JsonObject, bundled_copy
from sandbox_provider_pricing.versions import latest_version, seed_versions

SCHEMA_VERSION = "1.2.0"
#: The billing rules, in the order a provider's page lists them, with their headings.
RULES = (
    ("billed_on", "Billed on"),
    ("starts", "Billing starts"),
    ("ends", "Billing ends"),
    ("rounding", "Rounding"),
    ("idle_and_paused", "Idle and paused"),
    ("image_pull", "Image pull"),
    ("extra_charges", "Billed separately"),
    ("left_out", "Left out"),
    ("per_sandbox_data", "Per-sandbox data"),
)
_PACKAGE_PRICES = "src/sandbox_provider_pricing/providers"
_STORAGE = ("snapshot_storage", "image_storage", "volume_storage", "month_hours")
_SLOT = re.compile(
    r"<!-- cost-method: (?P<slot>\w+) -->\n(?P<body>.*?)(?=\n<!-- |\n#|\Z)", re.DOTALL
)
_TITLE = re.compile(r"^- `(?P<label>\w+)`: (?P<title>.+)$", re.MULTILINE)
_TERM = re.compile(r"^\| `(?P<term>\w+)` \| (?P<meaning>.+) \|$", re.MULTILINE)


def _method_text() -> str:
    bundled = resources.files("sandbox_provider_pricing").joinpath("METHOD.md")
    path = bundled if bundled.is_file() else Path(__file__).resolve().parents[2] / "METHOD.md"
    return path.read_text(encoding="utf-8")


def _paragraphs(body: str) -> list[str]:
    """The paragraphs of a block, each joined onto one line."""
    return [" ".join(part.split()) for part in body.strip().split("\n\n") if part.strip()]


def _slot_text(text: str, slot: str) -> str:
    match = next(match for match in _SLOT.finditer(text) if match["slot"] == slot)
    return match["body"]


def _method() -> JsonObject:
    """METHOD.md's rules: the slots it marks, and each label's meaning from its glossary."""
    text = _method_text()
    slots = {match["slot"]: _paragraphs(match["body"]) for match in _SLOT.finditer(text)}
    meanings = {match["term"]: match["meaning"] for match in _TERM.finditer(text)}
    titles = {
        match["label"]: match["title"] for match in _TITLE.finditer(_slot_text(text, "titles"))
    }
    slots.pop("titles")
    state_titles = {
        match["label"]: match["title"]
        for match in _TITLE.finditer(_slot_text(text, "state_titles"))
    }
    slots.pop("state_titles")
    labels = {
        label: {
            "title": titles.get(label),
            "meaning": meanings[label],
            "method": slots.pop(label),
        }
        for label in ("reported", "calculated", "unknown")
    }
    return {**slots, "labels": labels, "state_titles": state_titles}


def _version_entries(provider: str) -> JsonObject:
    """Every price version of a provider, newest first, keyed by the id a result records."""
    versions = [version for version in seed_versions() if version["provider"] == provider]
    newest = latest_version(provider, versions)["version"]
    ordered = sorted(
        versions, key=lambda item: (item["effective_from"], item["retrieved_at"]), reverse=True
    )
    entries: JsonObject = {}
    for version in ordered:
        name = version["version"]
        # The oldest version that supersedes this one replaced it directly.
        replaced_by = next(
            (
                other["version"]
                for other in reversed(ordered)
                if name in other.get("supersedes", [])
            ),
            None,
        )
        if name == newest:
            state = "in_effect"
        else:
            state = "earlier" if replaced_by is None else "replaced"
        storage = {key: version[key] for key in _STORAGE if version.get(key) is not None}
        entries[name] = {
            "version": name,
            "effective_from": version["effective_from"],
            "retrieved_at": version["retrieved_at"],
            "supersedes": version["supersedes"],
            "state": state,
            "replaced_by": replaced_by,
            "file": f"{_PACKAGE_PRICES}/{provider}/prices/{name.split('@', 1)[1]}.yaml",
            "classes": version["classes"],
            "sources": version["sources"],
            **({"storage": storage} if storage else {}),
            "left_out": version["exclusions"],
            "open_questions": version["open_questions"],
        }
    return entries


def _rules_entry(document: JsonObject) -> JsonObject:
    """What one `rules_version` of a provider's `billing.yaml` says: label, formula and rules."""
    rules = document["rules"]
    return {
        "rules_version": document["rules_version"],
        "best_label": document["status"]["best_label"],
        "summary": " ".join(document["summary"].split()),
        "formula": " ".join(document["formula"].split()),
        "why_not_higher": " ".join(document["status"]["why_not_higher"].split()),
        "would_raise": " ".join(document["status"]["would_raise"].split()),
        "rules": [
            {
                "key": key,
                "title": title,
                "answer": " ".join(rules[key]["answer"].split()),
                **{
                    field: rules[key][field]
                    for field in ("sources", "unknown_how")
                    if field in rules[key]
                },
            }
            for key, title in RULES
        ],
        "open_questions": [
            {"question": " ".join(item["question"].split()), "how": " ".join(item["how"].split())}
            for item in document["open_questions"]
        ],
        "measurements": [
            {**check, "result": " ".join(check["result"].split())} for check in document["checks"]
        ],
    }


def _provider(provider: str) -> JsonObject:
    """The provider's newest rules and every earlier `rules_version` kept in `billing-history/`."""
    document = billing(provider)
    versions = _version_entries(provider)
    return {
        "name": document["name"],
        "website": document["website"],
        **_rules_entry(document),
        "rules_history": {
            str(version): _rules_entry(old)
            for version, old in sorted(billing_history(provider).items(), reverse=True)
        },
        "latest_version": next(
            name for name, item in versions.items() if item["state"] == "in_effect"
        ),
        "versions": versions,
    }


def build_cost_method() -> JsonObject:
    """The whole document: the shared method and every provider with every price version."""
    return {
        "schema_version": SCHEMA_VERSION,
        "pricing_release_version": package_version(),
        "method": _method(),
        "providers": {provider: _provider(provider) for provider in provider_ids()},
    }


@cache
def _document() -> JsonObject:
    return build_cost_method()


def cost_method(
    provider: str | None = None, version: str | None = None, rules: int | None = None
) -> JsonObject:
    """The cost method as plain data (the content of `cost-method.json`).

    With no argument, the whole document. With a provider, that provider's entry: its label,
    formula, billing rules, open questions and every price version, for its newest `rules_version`,
    with the earlier ones under `rules_history`. With a provider and the price version a result
    recorded as `versions.prices`, the same entry holding only that version. With the
    `rules_version` a result recorded as `versions.rules`, the label, formula and billing rules
    are that version's own, so a consumer renders exactly the method that priced the cost. A fresh
    copy is returned each time.
    """
    document = bundled_copy(_document())
    if (version is not None or rules is not None) and provider is None:
        raise ValueError("a price version or rules version needs its provider")
    if provider is None:
        return document
    entry: JsonObject | None = document["providers"].get(provider)
    if entry is None:
        raise ValueError(f"no cost method for provider {provider!r}")
    if version is not None:
        if version not in entry["versions"]:
            raise ValueError(f"no price version {version!r} for provider {provider!r}")
        entry["versions"] = {version: entry["versions"][version]}
    if rules is not None and rules != entry["rules_version"]:
        earlier = entry["rules_history"].get(str(rules))
        if earlier is None:
            raise ValueError(f"no rules version {rules!r} kept for provider {provider!r}")
        entry.update(earlier)
        entry["rules_history"] = {}
    return entry


def validate_cost_method(document: JsonObject) -> None:
    """Fail when a cost-method document does not match its schema."""
    error = next(Draft202012Validator(bundled_schema("cost-method")).iter_errors(document), None)
    if error is not None:
        path = "/".join(map(str, error.absolute_path)) or "<root>"
        raise ValueError(f"{path}: {error.message}")


def main() -> int:
    """Write the cost method as JSON to a file or stdout, after checking it against its schema."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, help="write JSON to this file; default is stdout")
    arguments = parser.parse_args()
    document = build_cost_method()
    validate_cost_method(document)
    write_json(document, arguments.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
