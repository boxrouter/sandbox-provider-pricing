# SPDX-FileCopyrightText: BoxRouter, Inc.
# SPDX-License-Identifier: Apache-2.0
"""E2B's plan quotes follow the pricing page as it was reworded on 2026-10-29 and 2026-10-31."""

from pathlib import Path
from typing import Any

import pytest
import yaml  # type: ignore[import-untyped]

from sandbox_provider_pricing.versions import latest_version
from sandbox_provider_pricing.watch import check

ROOT = Path(__file__).resolve().parents[1]
PAGES = Path(__file__).parent / "fixtures" / "pages"
PRICES = ROOT / "src" / "sandbox_provider_pricing" / "providers" / "e2b" / "prices"
LATEST = "2026-10-31-015028Z.yaml"
# page excerpt, the markers of the quotes it holds, the version before and the version after
REWORDINGS = [
    (
        "e2b-plans-reworded.html",
        ("Hobby FREE", "one-time usage credit", "pro $150"),
        "2026-10-20-061802Z.yaml",
        "2026-10-29-203000Z.yaml",
    ),
    (
        "e2b-enterprise-commit.html",
        ("Pro++", "Enterprise"),
        "2026-10-29-203000Z.yaml",
        LATEST,
    ),
]


def _version(version_file: str) -> dict[str, Any]:
    version: dict[str, Any] = yaml.safe_load((PRICES / version_file).read_text())
    return version


def _quotes(version_file: str, markers: tuple[str, ...]) -> list[str]:
    return [
        str(item["quote"])
        for item in _version(version_file)["sources"]
        if any(marker in str(item["quote"]) for marker in markers)
    ]


@pytest.mark.parametrize(("page", "markers", "before", "after"), REWORDINGS)
def test_the_new_quotes_are_on_the_reworded_page_and_the_old_ones_are_not(
    page: str, markers: tuple[str, ...], before: str, after: str
) -> None:
    text = check.page_text((PAGES / page).read_text(encoding="utf-8"))
    current = _quotes(after, markers)
    assert current and all(text.contains(quote) for quote in current)
    assert not any(text.contains(quote) for quote in _quotes(before, markers))


@pytest.mark.parametrize(("before", "after"), [(item[2], item[3]) for item in REWORDINGS])
def test_each_refresh_changes_no_rate(before: str, after: str) -> None:
    previous, refreshed = _version(before), _version(after)
    assert refreshed["effective_from"] == previous["effective_from"]
    for key in ("provider", "classes"):
        assert refreshed[key] == previous[key], key


def test_the_enterprise_commit_refresh_is_the_latest() -> None:
    latest = latest_version("e2b")
    assert latest["version"] == "e2b@2026-10-31-015029Z"
    assert latest["classes"] == _version(LATEST)["classes"]
    assert any("$2,000/month commit" in item for item in _version(LATEST)["exclusions"])
