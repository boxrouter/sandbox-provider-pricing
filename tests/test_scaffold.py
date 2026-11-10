# SPDX-FileCopyrightText: BoxRouter, Inc.
# SPDX-License-Identifier: Apache-2.0
"""CI generates records and exercises the same validators used for real records."""

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml  # type: ignore[import-untyped]

from sandbox_provider_pricing import next_read, price, record_evidence
from sandbox_provider_pricing.providers import validate_billing
from sandbox_provider_pricing.scaffold import add
from sandbox_provider_pricing.testing import use_providers
from sandbox_provider_pricing.versions import load_price_versions
from sandbox_provider_pricing.watch.cli import main

ROOT = Path(__file__).resolve().parents[1]
PACKAGES = ROOT / "src" / "sandbox_provider_pricing" / "providers"


def test_generated_provider_is_valid_unknown_and_additive(tmp_path: Path) -> None:
    before = {
        p: p.read_bytes()
        for folder in (ROOT / "providers", PACKAGES)
        for p in folder.rglob("*")
        if p.is_file() and "__pycache__" not in p.parts
    }
    paths = add(tmp_path, "fixture", name="Fixture", website="https://example.invalid")
    document = yaml.safe_load((tmp_path / paths[1]).read_text())
    validate_billing(document)
    assert document["status"]["best_label"] == "unknown"
    assert document["revisit"] is None
    assert document["reported_at_list_price"]["value"] is None
    assert "TODO" not in (tmp_path / paths[1]).read_text()
    assert not (tmp_path / PACKAGES.relative_to(ROOT) / "fixture/prices").exists()
    assert all(p.read_bytes() == value for p, value in before.items())
    with pytest.raises(ValueError, match="already exists"):
        add(tmp_path, "fixture", name="Replacement", website="https://example.invalid")


def test_cli_dry_run_writes_nothing(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert (
        main(
            [
                "scaffold",
                "fixture",
                "--root",
                str(tmp_path),
                "--name",
                "Fixture",
                "--website",
                "https://example.invalid",
                "--dry-run",
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["writes"] == [
        "src/sandbox_provider_pricing/providers/fixture/__init__.py",
        "src/sandbox_provider_pricing/providers/fixture/billing.yaml",
    ]
    assert not list(tmp_path.iterdir())


def test_sourced_price_uses_existing_validation_before_writing(tmp_path: Path) -> None:
    # This is a real existing schema/quote fixture, never a claim about another provider.
    price = yaml.safe_load((PACKAGES / "e2b/prices/2026-10-20.yaml").read_text())
    # Synthetic saved pages exercise admission; they are not new pricing evidence.
    combined = tmp_path / "source.txt"
    combined.write_text("\n".join(s["quote"] for s in price["sources"]))
    pages = {source["url"]: combined for source in price["sources"]}
    paths = add(tmp_path, "e2b", name="E2B", website="https://e2b.dev", price=price, pages=pages)
    assert len(paths) == 3
    assert load_price_versions(tmp_path / PACKAGES.relative_to(ROOT) / "e2b") == [price]
    with pytest.raises(ValueError, match="already exists"):
        add(tmp_path, "e2b", price=price, pages=pages)
    price["classes"][0]["rates"]["cpu"]["usd"] = "0.123456789"
    empty = tmp_path / "rejected"
    with pytest.raises(ValueError):
        add(empty, "e2b", name="E2B", website="https://e2b.dev", price=price, pages=pages)
    assert not empty.exists()


def test_missing_source_page_fails_before_creating_provider(tmp_path: Path) -> None:
    price = yaml.safe_load((PACKAGES / "e2b/prices/2026-10-20.yaml").read_text())
    with pytest.raises(ValueError, match="saved provider source required"):
        add(tmp_path, "e2b", name="E2B", website="https://e2b.dev", price=price)
    assert not list(tmp_path.iterdir())


def test_a_scaffolded_provider_prices_unknown_with_no_read_scheduled(tmp_path: Path) -> None:
    """`revisit: null` is the scaffold's unknown state: a trial still prices, as unknown and never
    final, and no consumer is told to read its records again."""
    add(tmp_path, "fixture", name="Fixture", website="https://example.invalid")
    ended = datetime(2026, 10, 31, 12, tzinfo=UTC)
    with use_providers(tmp_path / PACKAGES.relative_to(ROOT)):
        result = price(
            record_evidence({"provider": "fixture", "sandbox_id": "native"}),
            as_of="2026-10-31T12:05:00Z",
            ended_at=ended,
        )
        assert (result["label"], result["total"]) == ("unknown", None)
        assert result["revisit"] is None
        assert result["final"] is False
        assert next_read(result, ended, datetime(2026, 10, 31, 13, tzinfo=UTC)) is None
