# SPDX-FileCopyrightText: BoxRouter, Inc.
# SPDX-License-Identifier: Apache-2.0
"""The daily price watch: `spp check` over every provider's current price version, then issues.

For each provider it checks the current (newest, not superseded) price version's quotes against
the provider's pages, exactly as `spp check` does, and keeps ONE issue per provider:

- `changed` or `unreadable`: open it, or rewrite its body when the result differs;
- `confirmed`: close it with a comment.

It reads pages and writes issues. It never drafts a version, never calls an AI and never writes a
price file: a person (or a reviewed `spp draft`) turns a `changed` issue into a pull request.
Providers come from the bundled price versions, so a new provider is watched without an edit.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections.abc import Callable, Sequence

from sandbox_provider_pricing.types import JsonObject
from sandbox_provider_pricing.versions import latest_version, seed_versions
from sandbox_provider_pricing.watch.check import Fetcher, VersionCheck, check_documents, fetch_page

Gh = Callable[..., "subprocess.CompletedProcess[str]"]
MAX_LISTED = 10


def providers(versions: list[JsonObject] | None = None) -> list[str]:
    pool = seed_versions() if versions is None else versions
    return sorted({str(version["provider"]) for version in pool})


def current_versions(versions: list[JsonObject] | None = None) -> list[JsonObject]:
    pool = seed_versions() if versions is None else versions
    return [latest_version(provider, pool) for provider in providers(pool)]


def without_run(text: str) -> str:
    """The issue text minus its `Run:` line, which differs every day and is not a change."""
    return "\n".join(line for line in text.splitlines() if not line.startswith("Run: "))


def title(provider: str) -> str:
    return f"Price check: {provider}"


def body(result: VersionCheck, run_url: str) -> str:
    """The issue text for one `changed` or `unreadable` version."""
    lines = [
        f"Run: {run_url}",
        "",
        f"`spp check` of `{result.version}` is **{result.status}**.",
        "",
    ]
    if result.missing:
        lines.append("Stored quotes no longer on the page:")
        lines += [f"- {item['url']}: `{item['quote']}`" for item in result.missing[:MAX_LISTED]]
        if len(result.missing) > MAX_LISTED:
            lines.append(f"- and {len(result.missing) - MAX_LISTED} more")
        lines.append("")
    if result.unreadable:
        lines.append("Pages that could not be read:")
        lines += [f"- {item['url']}: {item['error']}" for item in result.unreadable[:MAX_LISTED]]
        lines.append("")
    lines += [
        "Nothing was changed. To fix it, re-read the page, write a new price version and open a"
        " pull request (docs/watching-prices.md, `spp draft` helps). The issue updates daily and"
        " closes when the quotes are confirmed again.",
    ]
    return "\n".join(lines)


def sync_issue(provider: str, result: VersionCheck, run_url: str, gh: Gh = subprocess.run) -> str:
    """Open, update or close the provider's one issue; return what was done."""
    name = title(provider)
    listing = gh(
        ["gh", "issue", "list", "--state", "open", "--search", f'in:title "{name}"',
         "--json", "number,title,body", "--limit", "20"],
        capture_output=True, text=True, check=True,
    )  # fmt: skip
    found = next((item for item in json.loads(listing.stdout) if item["title"] == name), None)
    if result.status == "confirmed":
        if found is None:
            return "confirmed"
        gh(["gh", "issue", "close", str(found["number"]), "--comment",
            f"Confirmed again: {run_url}"], check=True)  # fmt: skip
        return "closed"
    text = body(result, run_url)
    if found is None:
        gh(["gh", "issue", "create", "--title", name, "--body", text], check=True)
        return "opened"
    if without_run(found["body"]) != without_run(text):
        gh(["gh", "issue", "edit", str(found["number"]), "--body", text], check=True)
        return "updated"
    return "unchanged"


def run(
    run_url: str,
    *,
    fetch: Fetcher = fetch_page,
    gh: Gh = subprocess.run,
    versions: list[JsonObject] | None = None,
    only: str = "",
) -> int:
    documents = [
        document
        for document in current_versions(versions)
        if not only or document["provider"] == only
    ]
    if not documents:
        raise SystemExit(f"no price version for provider {only!r}")
    for document, result in zip(documents, check_documents(documents, fetch), strict=True):
        action = sync_issue(str(document["provider"]), result, run_url, gh)
        sys.stdout.write(result.as_json() + f"  # issue {action}\n")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="watch_prices", description=__doc__)
    parser.add_argument("--run-url", required=True)
    parser.add_argument("--provider", default="", help="one provider (default: every provider)")
    arguments = parser.parse_args(argv)
    return run(arguments.run_url, only=arguments.provider)


if __name__ == "__main__":
    raise SystemExit(main())
