# SPDX-FileCopyrightText: BoxRouter, Inc.
# SPDX-License-Identifier: Apache-2.0
"""The daily price watch: one issue per changed or unreadable provider, closed when confirmed."""

import importlib.util
import json
import subprocess
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

from sandbox_provider_pricing.versions import seed_versions
from sandbox_provider_pricing.watch.check import FetchError, PageText, page_text

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "watch_prices.py"
spec = importlib.util.spec_from_file_location("watch_prices", SCRIPT)
assert spec is not None and spec.loader is not None
watch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(watch)

URL = "https://example.test/pricing"


def version(provider: str, name: str, quotes: list[str], **extra: Any) -> dict[str, Any]:
    return {
        "provider": provider,
        "version": f"{provider}@{name}",
        "effective_from": "2026-10-01T00:00:00Z",
        "retrieved_at": f"2026-10-0{name}T00:00:00Z",
        "sources": [{"url": f"{URL}/{provider}", "quote": quote} for quote in quotes],
        **extra,
    }


class FakeGitHub:
    """A `gh` that keeps issues in memory."""

    def __init__(self) -> None:
        self.issues: list[dict[str, Any]] = []
        self.calls: list[list[str]] = []

    def __call__(self, command: list[str], **_: Any) -> subprocess.CompletedProcess[str]:
        self.calls.append(command)
        verb, out = command[2], ""
        if verb == "list":
            out = json.dumps([item for item in self.issues if item["state"] == "open"])
        elif verb == "create":
            self.issues.append(
                {"number": len(self.issues) + 1, "state": "open",
                 "title": command[command.index("--title") + 1],
                 "body": command[command.index("--body") + 1]}
            )  # fmt: skip
        else:
            issue = next(item for item in self.issues if str(item["number"]) == command[3])
            if verb == "edit":
                issue["body"] = command[command.index("--body") + 1]
            else:
                issue["state"] = "closed"
        return subprocess.CompletedProcess(command, 0, out, "")


def pages(world: Mapping[str, str | None]) -> Any:
    """A fetcher: a provider's page says `world[provider]`; None is an unreachable page."""

    def fetch(url: str) -> PageText:
        text = world[url.rsplit("/", 1)[1]]
        if text is None:
            raise FetchError(f"{url}: HTTP 503")
        return page_text(text, html=False)

    return fetch


POOL = [
    version("zzz", "1", ["old rate"]),
    version("zzz", "2", ["rate is $1", "memory is $2"], supersedes=["zzz@1"]),
    version("yyy", "1", ["yyy is $5"]),
    version("xxx", "1", ["xxx is $7"]),
]


def test_each_provider_is_checked_by_its_current_version_without_a_list_to_edit() -> None:
    assert watch.providers(POOL) == ["xxx", "yyy", "zzz"]
    assert [item["version"] for item in watch.current_versions(POOL)] == [
        "xxx@1",
        "yyy@1",
        "zzz@2",
    ]
    assert set(watch.providers()) == {item["provider"] for item in seed_versions()}


def test_a_changed_quote_opens_one_issue_per_provider_and_repeats_do_not_duplicate() -> None:
    github = FakeGitHub()
    world = {"zzz": "rate is $1 memory is $3", "yyy": "yyy is $5", "xxx": None}
    for run in (1, 2):
        watch.run(f"https://runs/{run}", fetch=pages(world), gh=github, versions=POOL)
    titles = sorted(item["title"] for item in github.issues)
    assert titles == ["Price check: xxx", "Price check: zzz"]  # yyy is confirmed: no issue
    zzz = next(item for item in github.issues if item["title"] == "Price check: zzz")
    assert "**changed**" in zzz["body"] and "memory is $2" in zzz["body"]
    xxx = next(item for item in github.issues if item["title"] == "Price check: xxx")
    assert "**unreadable**" in xxx["body"] and "HTTP 503" in xxx["body"]
    # The second run's only difference is its run URL: that is not an update.
    assert [call[2] for call in github.calls if call[2] != "list"] == ["create", "create"]


def test_a_confirmed_quote_closes_the_issue() -> None:
    github = FakeGitHub()
    world: dict[str, str | None] = {
        "zzz": "rate is $1 memory is $3",
        "yyy": "yyy is $5",
        "xxx": "xxx is $7",
    }
    watch.run("https://runs/1", fetch=pages(world), gh=github, versions=POOL)
    assert [item["title"] for item in github.issues] == ["Price check: zzz"]
    world["zzz"] = "rate is $1 memory is $2"
    watch.run("https://runs/2", fetch=pages(world), gh=github, versions=POOL)
    assert github.issues[0]["state"] == "closed"
    assert len(github.issues) == 1


def test_an_unchanged_result_rewrites_nothing() -> None:
    github = FakeGitHub()
    world = {"zzz": "nope", "yyy": "yyy is $5", "xxx": "xxx is $7"}
    watch.run("https://runs/1", fetch=pages(world), gh=github, versions=POOL)
    before = [call for call in github.calls if call[2] != "list"]
    watch.run("https://runs/1", fetch=pages(world), gh=github, versions=POOL)
    assert [call for call in github.calls if call[2] != "list"] == before


def test_the_watch_imports_no_drafting_agent_and_writes_no_price() -> None:
    source = SCRIPT.read_text()
    assert "watch.draft" not in source and "watch.agent" not in source
    assert "ANTHROPIC" not in source and "write_text" not in source and "open(" not in source


def test_an_unknown_provider_is_refused() -> None:
    with pytest.raises(SystemExit):
        watch.run("https://runs/1", fetch=pages({}), gh=FakeGitHub(), versions=POOL, only="nope")
