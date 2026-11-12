# SPDX-FileCopyrightText: BoxRouter, Inc.
# SPDX-License-Identifier: Apache-2.0
"""The imported price versions preserve the source rates and quotes."""

import fnmatch
import hashlib
import json
import re
import tomllib
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]
from jsonschema import Draft202012Validator, FormatChecker

from sandbox_provider_pricing.providers import billing, provider_ids
from sandbox_provider_pricing.versions import (
    latest_version,
    price_version,
    priced_provider_ids,
    seed_versions,
)

ROOT = Path(__file__).resolve().parents[1]
PACKAGES = ROOT / "src" / "sandbox_provider_pricing" / "providers"
PRICE_SCHEMA = json.loads((ROOT / "schemas" / "price-version.schema.json").read_text())
PRICE_FILES = sorted(PACKAGES.glob("*/prices/*.yaml"))


def load_price(path: Path) -> dict[str, Any]:
    """Load a price version with its quoted decimal strings intact."""
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(document, dict)
    return document


def _reuse_patterns() -> list[str]:
    reuse = tomllib.loads((ROOT / "REUSE.toml").read_text(encoding="utf-8"))
    return [path for annotation in reuse["annotations"] for path in annotation["path"]]


def test_every_price_file_has_reuse_license_information() -> None:
    # Price files carry no SPDX header; REUSE.toml must cover each one, or CI's REUSE lint fails.
    patterns = _reuse_patterns()
    uncovered = [
        str(path.relative_to(ROOT))
        for path in PRICE_FILES
        if not any(fnmatch.fnmatch(str(path.relative_to(ROOT)), p) for p in patterns)
    ]
    assert uncovered == []


def test_reuse_annotations_cover_any_provider_folder() -> None:
    """A new provider's billing, fixtures and README are licensed without editing REUSE.toml."""
    patterns = _reuse_patterns()
    named = [path for path in patterns if re.search(r"providers/[a-z0-9-]+/", path)]
    assert named == []
    samples = (
        "providers/acme/README.md",
        "src/sandbox_provider_pricing/providers/acme/billing.yaml",
        "src/sandbox_provider_pricing/providers/acme/read-time.json",
        "src/sandbox_provider_pricing/providers/acme/record-rules.json",
        "src/sandbox_provider_pricing/providers/acme/prices/2026-01-31.yaml",
        "providers/acme/fixtures/best/evidence.json",
        "providers/acme/fixtures/best/result.json",
        "providers/acme/evidence/check.md",
    )
    uncovered = [
        sample for sample in samples if not any(fnmatch.fnmatch(sample, path) for path in patterns)
    ]
    assert uncovered == []


def test_every_price_file_validates_against_the_schema() -> None:
    validator = Draft202012Validator(PRICE_SCHEMA, format_checker=FormatChecker())
    assert sorted({path.parts[-3] for path in PRICE_FILES}) == priced_provider_ids()
    for path in PRICE_FILES:
        messages = sorted(error.message for error in validator.iter_errors(load_price(path)))
        assert messages == [], f"{path.relative_to(ROOT)}: {messages}"


# sha256 of each version's canonical JSON as published in 0.1.9. Consumers store price versions by
# this content hash, so a published version must never change.
PUBLISHED_HASHES = {
    "blaxel@2026-10-20-061947Z": "cc9a01b22aec62e31c8ea15fd55c9519e956a7e23230a401a428016a49c02ee1",
    "blaxel@2026-10-20": "fb25f6d321c9e45946f243f800ce6a4bab5348275d6f44660107eec78dd3ed7a",
    "daytona@2026-10-20-061942Z": "2c9ff9d73876ff24f4236be6a658622e37b7998c9a48794b80766b8d2315e3f6",  # noqa: E501
    "daytona@2026-10-20": "e96c9df4bd7ee2ed994776a27a7de2720cf973324f36a6b94e40532625f389a3",
    "e2b@2026-10-20-061802Z": "8aa7513a296cd0fa68084fb1d8913579947264204b7af77fbe2afec22663487c",
    "e2b@2026-10-20": "4374e22a00b752d5cd8b14f3a5d662213d7d39633655fe701b6ca316a1624343",
    "modal@2026-10-20-061900Z": "6b263772b527fe50a6cb99da0aeb704ec8606101b194d13982cbce6b4f653d70",
    "modal@2026-10-20": "27b7854fc205a5c818824e20f018e6daeeaf0ab0858aa18c8485fd0a70175fef",
    "vercel@2026-10-20-055630Z": "97d107fb4913180cb597e8059891840fcc625ebc57f463652539405a17b0523d",
    "vercel@2026-10-20": "5c8f7cb8894708423d1e3eb582af15bad82d70d828b18b1f316fa618f44a2167",
}


def test_published_price_versions_are_unchanged() -> None:
    hashes = {}
    for document in seed_versions():
        canonical = json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        hashes[document["version"]] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    assert {version: hashes.get(version) for version in PUBLISHED_HASHES} == PUBLISHED_HASHES


def test_vercel_egress_correction_applies_from_the_first_version() -> None:
    versions = seed_versions()
    earlier = price_version("vercel", "2026-10-06T00:00:00Z", versions)
    current = price_version("vercel", "2026-10-20T00:00:00Z", versions)
    assert earlier is not None and current is not None
    assert earlier["version"] == current["version"] == "vercel@2026-10-20-055631Z"
    assert current["classes"][0]["rates"]["egress"]["usd"] == "0.15"
    assert "vercel@2026-10-20" in current["supersedes"]


def test_billing_rules_do_not_expose_call_clock_boundaries() -> None:
    # Each provider's rules version, and whether it keeps evidence: boat has no measurement yet
    # (its `checks` is empty and its rules cite only Boat's pages).
    expected = {
        "agent37": (1, True),
        "blaxel": (2, True),
        "boat": (1, False),
        "boxd": (1, True),
        "daytona": (2, True),
        "e2b": (2, True),
        "modal": (4, True),
        "vercel": (2, True),
    }
    for provider in provider_ids():
        # A provider scaffolded before its first measurement is rules_version 1, no evidence.
        rules_version, has_evidence = expected.get(provider, (1, False))
        assert "boundary" not in billing(provider)
        assert billing(provider)["rules_version"] == rules_version
        evidence = ROOT / "providers" / provider / "evidence"
        assert (evidence.is_dir() and any(evidence.iterdir())) == has_evidence


def test_every_unit_rate_appears_in_a_quote() -> None:
    for path in PRICE_FILES:
        document = load_price(path)
        quotes = [source["quote"] for source in document["sources"]]
        for price_class in document["classes"]:
            derived = price_class.get("derived_from", {}).get("rates", ())
            for resource, rate in price_class["rates"].items():
                if resource in derived:
                    continue  # watch.verify's `_derived_failures` checks it (test_draft)
                rates = rate.items() if resource in ("gpu", "machine") else [(None, rate)]
                for model, model_rate in rates:
                    amount = model_rate["usd"]
                    matches = [quote for quote in quotes if amount in quote]
                    assert matches, (
                        f"{path.relative_to(ROOT)} {resource} rate {amount} has no source quote"
                    )
                    if model is not None and resource == "gpu":
                        token = "".join(
                            character for character in model.split(":", 1)[1] if character.isalnum()
                        )
                        assert any(
                            "gpu" in quote.lower()
                            and token.lower()
                            in "".join(
                                character for character in quote if character.isalnum()
                            ).lower()
                            for quote in matches
                        ), (
                            f"{path.relative_to(ROOT)} GPU {model} rate {amount} "
                            "has no model-specific quote"
                        )


def test_modal_t0_correction_uses_modal_cores_per_vcpu() -> None:
    path = PACKAGES / "modal" / "prices" / "2026-10-20-061900Z.yaml"
    document = load_price(path)
    default_class = next(item for item in document["classes"] if item.get("default") is True)
    assert default_class["rates"]["cpu"] == {
        "usd": "0.00003942",
        "per": "core-second",
        "size_per_unit": "2",
    }


def test_daytona_t0_b300_correction_stays_model_specific() -> None:
    path = PACKAGES / "daytona" / "prices" / "2026-10-20-061942Z.yaml"
    document = load_price(path)
    default_class = next(item for item in document["classes"] if item.get("default") is True)
    assert default_class["rates"]["gpu"]["nvidia:b300"]["usd"] == "6.25"
    assert default_class["rates"]["gpu"]["nvidia:b300"]["per"] == "gpu-hour"
    assert any(
        "B300" in source["quote"] and "$6.25" in source["quote"] for source in document["sources"]
    )


def test_modal_gpu_rates_are_from_the_pricing_page() -> None:
    matches = list((PACKAGES / "modal/prices").glob("2026-10-20-*.yaml"))
    assert len(matches) == 1
    document = load_price(matches[0])
    gpu = document["classes"][0]["rates"]["gpu"]
    assert len(gpu) == 11
    assert gpu["nvidia:h100"] == {"usd": "0.001097", "per": "gpu-second"}


def test_daytona_has_both_gpu_schedules_and_model_specific_b300_prices() -> None:
    matches = list((PACKAGES / "daytona/prices").glob("2026-10-20-*.yaml"))
    assert len(matches) == 1
    document = load_price(matches[0])
    classes = {price_class["name"]: price_class for price_class in document["classes"]}
    assert classes["preemptible"]["rates"]["gpu"]["nvidia:b300"]["usd"] == "4.08"
    assert classes["on-demand"]["rates"]["gpu"]["nvidia:b300"]["usd"] == "6.25"


INTERNAL_NOTES = (
    "planning/",
    "andre",
    "found" + "er",
    "tc-l",
    "evidence.md",
    "rate-cards.md",
    "our account",
    "benchmark",
    "boxrouter version",
)


def test_current_price_versions_carry_no_internal_notes() -> None:
    for provider in sorted({version["provider"] for version in seed_versions()}):
        text = json.dumps(latest_version(provider)).lower()
        assert [note for note in INTERNAL_NOTES if note in text] == [], provider
