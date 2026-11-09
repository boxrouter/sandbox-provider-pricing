# SPDX-FileCopyrightText: BoxRouter, Inc.
# SPDX-License-Identifier: Apache-2.0
"""Modal's quotes follow its pricing page (reworded 2026-10-29) and docs page (2026-10-30)."""

from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]

from sandbox_provider_pricing.versions import latest_version
from sandbox_provider_pricing.watch import check

ROOT = Path(__file__).resolve().parents[1]
PAGE = Path(__file__).parent / "fixtures" / "pages" / "modal-sandbox-pricing.html"
RESOURCES_PAGE = Path(__file__).parent / "fixtures" / "pages" / "modal-sandbox-resources.html"
PRICING_URL = "https://modal.com/pricing"
RESOURCES_URL = "https://modal.com/docs/guide/sandbox-resources"


def _version(version_file: str) -> dict[str, Any]:
    version: dict[str, Any] = yaml.safe_load(
        (ROOT / "src/sandbox_provider_pricing/providers/modal/prices" / version_file).read_text()
    )
    return version


def _quotes(version_file: str, url: str) -> list[str]:
    return [str(item["quote"]) for item in _version(version_file)["sources"] if item["url"] == url]


def _first_pricing_quote(version_file: str) -> str:
    return _quotes(version_file, PRICING_URL)[0]


def test_the_sandbox_rate_quote_is_on_the_reworded_page_and_the_old_one_is_not() -> None:
    page = check.page_text(PAGE.read_text(encoding="utf-8"))
    assert page.contains(_first_pricing_quote("2026-10-29-163500Z.yaml"))
    assert not page.contains(_first_pricing_quote("2026-10-24-065000Z.yaml"))


def test_the_new_resources_page_quotes_are_on_the_rewritten_page_and_the_old_one_is_not() -> None:
    page = check.page_text(RESOURCES_PAGE.read_text(encoding="utf-8"))
    old = _quotes("2026-10-29-163500Z.yaml", RESOURCES_URL)
    current = _quotes("2026-10-30-103442Z.yaml", RESOURCES_URL)
    added = [quote for quote in current if quote not in old]
    dropped = [quote for quote in old if quote not in current]
    assert len(added) == 2
    assert any("max(request, actual)" in quote for quote in added)
    assert all(page.contains(quote) for quote in added)
    assert len(dropped) == 1 and "billed by the second" in dropped[0]
    assert not page.contains(dropped[0])


def test_the_corrected_version_and_its_successors_change_no_rate() -> None:
    corrected = _version("2026-10-30-103442Z.yaml")
    assert corrected["supersedes"] == ["modal@2026-10-29-163500Z"]
    assert corrected["classes"] == _version("2026-10-29-163500Z.yaml")["classes"]
    assert latest_version("modal")["classes"] == corrected["classes"]
