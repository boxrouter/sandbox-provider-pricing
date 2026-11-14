# SPDX-FileCopyrightText: BoxRouter, Inc.
# SPDX-License-Identifier: Apache-2.0
"""The daily price watch notices Superserve's storage turning billable, and names billing.yaml."""

import importlib.util
import json
import subprocess
from pathlib import Path
from typing import Any

from sandbox_provider_pricing.versions import seed_versions
from sandbox_provider_pricing.watch.check import PageText, check_version, page_text

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("watch_prices", ROOT / "scripts" / "watch_prices.py")
assert spec is not None and spec.loader is not None
watch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(watch)

PRICING_JSON = "https://api.superserve.ai/billing/pricing/public"
# The answer of PRICING_JSON on 2026-11-13: storage_gib has "billable":false.
TODAY = (ROOT / "tests/data/superserve-pricing-public.json").read_text(encoding="utf-8")
PLANTED = TODAY.replace('"tracked":true,"billable":false', '"tracked":true,"billable":true')


def superserve() -> dict[str, Any]:
    version: dict[str, Any] = watch.current_versions(
        [v for v in seed_versions() if v["provider"] == "superserve"]
    )[0]
    return version


def fetch_with(pricing_json: str) -> Any:
    """Serve the JSON for the pricing data, and each other page as exactly its stored quotes."""
    quotes: dict[str, list[str]] = {}
    for source in superserve()["sources"]:
        quotes.setdefault(source["url"], []).append(source["quote"])

    def fetch(url: str) -> PageText:
        if url == PRICING_JSON:
            return page_text(pricing_json, html=False)
        return page_text(" ".join(quotes[url]), html=False)

    return fetch


def test_the_planted_copy_differs_from_today_only_in_storage() -> None:
    assert PLANTED != TODAY
    assert TODAY.count('"billable":false') == 1 and PLANTED.count('"billable":true') == 3


def test_todays_answer_is_confirmed() -> None:
    assert check_version(superserve(), fetch_with(TODAY)).status == "confirmed"


def test_storage_turning_billable_is_changed_and_names_the_storage_quote() -> None:
    result = check_version(superserve(), fetch_with(PLANTED))
    assert result.status == "changed"
    assert [item["url"] for item in result.missing] == [PRICING_JSON]
    assert '"resource_key":"storage_gib"' in result.missing[0]["quote"]
    assert result.missing[0]["quote"].endswith('"billable":false')


def test_the_issue_for_it_names_billing_yaml() -> None:
    issues: list[str] = []

    def gh(command: list[str], **_: Any) -> Any:
        if command[2] == "create":
            issues.append(command[command.index("--body") + 1])
        return subprocess.CompletedProcess(command, 0, json.dumps([]), "")

    watch.run("https://runs/1", fetch=fetch_with(PLANTED), gh=gh, versions=[superserve()])
    assert len(issues) == 1
    assert "providers/superserve/billing.yaml" in issues[0]
    assert (ROOT / "src/sandbox_provider_pricing/providers/superserve/billing.yaml").is_file()
