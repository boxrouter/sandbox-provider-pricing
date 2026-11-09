# SPDX-FileCopyrightText: BoxRouter, Inc.
# SPDX-License-Identifier: Apache-2.0
"""The scraper's agent fallback: an agent drafts a new price version, and code checks its work.

When the daily check finds that a page no longer says what a price version quotes, an agent reads
the page and writes the version again, with fresh quotes. The agent is trusted with nothing:
`verify` rejects a draft unless every quote it took from the page is on the page, every unit rate
is a number in one of its quotes, each rate is in the unit its quote prints, and the draft
validates against the price-version schema. A rejected draft is retried once with the failures
listed, then reported `unreadable`. A verified draft is `reworded` when its rates, meter rules and
exclusions equal the current version's, otherwise `price changed`, with each change named.

The agent only writes what the page can show: the quotes from this page, the classes, the
exclusions and the open questions. The quotes from other pages are kept as they are, and the
version id, `retrieved_at` and `effective_from` are set here, from the clock.

`watch.prompt` writes the message and reads the answer; `watch.verify` checks the draft.
"""

import os
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import yaml  # type: ignore[import-untyped]

from sandbox_provider_pricing.types import JsonObject
from sandbox_provider_pricing.watch.check import PageText, page_text
from sandbox_provider_pricing.watch.errors import DraftError
from sandbox_provider_pricing.watch.prompt import build_prompt, read_reply, yaml_text
from sandbox_provider_pricing.watch.verify import classify, verify

__all__ = [
    "ATTEMPTS",
    "MAX_PAGE_CHARS",
    "PRICE_FILE_HEADER",
    "DraftError",
    "Drafter",
    "Outcome",
    "assemble",
    "build_prompt",
    "classify",
    "draft_version",
    "infer_url",
    "read_reply",
    "run",
    "verify",
]

Drafter = Callable[[str], str]
ATTEMPTS = 2  # one draft, and one retry with the failures listed
MAX_PAGE_CHARS = 400_000
# Lets an editor check the file against the schema once it sits in the provider's `prices/` folder.
PRICE_FILE_HEADER = (
    "# yaml-language-server: $schema=../../../../../schemas/price-version.schema.json\n"
)


@dataclass
class Outcome:
    """What came of drafting a page: a verified draft, or why none could be had."""

    status: str  # `reworded`, `price changed` or `unreadable`
    draft: JsonObject | None = None
    changes: list[str] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)

    def result_line(self) -> str:
        if self.status == "price changed":
            return f"price changed: {'; '.join(self.changes)}"
        return self.status


def infer_url(current: JsonObject, page: PageText) -> str:
    """The page's address: the source URL of the current version most of whose quotes it holds."""
    found: dict[str, int] = {}
    for source in current["sources"]:
        found[source["url"]] = found.get(source["url"], 0) + page.contains(source["quote"])
    best = max(found.values(), default=0)
    urls = [url for url, count in found.items() if count == best]
    if best == 0 or len(urls) != 1:
        raise DraftError("Cannot tell which of the version's pages this is; say so with --url.")
    return urls[0]


def assemble(reply: JsonObject, current: JsonObject, url: str, now: datetime) -> JsonObject:
    """The draft: the agent's four parts, the other pages' quotes kept, the rest from the clock."""
    stamp = now.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    fresh = [{"url": url, "quote": quote} for quote in reply["sources"]]
    sources: list[JsonObject] = []
    placed = False
    for source in current["sources"]:
        if source["url"] != url:
            sources.append(source)
        elif not placed:
            sources.extend(fresh)
            placed = True
    if not placed:
        sources.extend(fresh)
    day = now.astimezone(UTC).strftime("%Y-%m-%d")
    # Keep an existing same-day record immutable; the UTC time makes the next capture unique.
    current_version = current.get("version", "")
    same_day = current_version == f"{current['provider']}@{day}" or current_version.startswith(
        f"{current['provider']}@{day}-"
    )
    version = f"{current['provider']}@{day}"
    if same_day:
        version += f"-{now.astimezone(UTC):%H%M%SZ}"
    return {
        "provider": current["provider"],
        "version": version,
        "effective_from": stamp,
        "retrieved_at": stamp,
        "sources": sources,
        "classes": reply["classes"],
        "exclusions": reply["exclusions"],
        "open_questions": reply["open_questions"],
    }


def draft_version(
    current: JsonObject,
    page: PageText,
    url: str,
    drafter: Drafter,
    *,
    now: datetime | None = None,
) -> Outcome:
    """Draft the new version of a changed page; one retry, then `unreadable`.

    `drafter` sends a prompt to the agent and returns its answer; it raises DraftError when the
    agent cannot be asked at all. A page too long to send is `unreadable` without asking.
    """
    if len(page.visible) > MAX_PAGE_CHARS:
        return Outcome("unreadable", failures=[f"The page is over {MAX_PAGE_CHARS} characters."])
    moment = now or datetime.now(UTC)
    failures: list[str] = []
    rejected: list[str] = []
    for attempt in range(1, ATTEMPTS + 1):
        answer = drafter(build_prompt(current, url, page, rejected or None))
        reply, rejected = read_reply(answer)
        draft = None
        if reply is not None:
            draft = assemble(reply, current, url, moment)
            rejected = verify(draft, page, url, current)
        failures += [f"attempt {attempt}: {failure}" for failure in rejected]
        if draft is not None and not rejected:
            changes = classify(current, draft)
            return Outcome("price changed" if changes else "reworded", draft, changes)
    return Outcome("unreadable", failures=failures)


def run(
    version_file: str,
    page_file: str,
    drafter: Drafter,
    *,
    url: str | None = None,
    out: str | None = None,
) -> int:
    """Draft the new version of one changed page and print the result on the last line.

    Exit status 0 for `reworded` and `price changed`, 1 for `unreadable` (the failures are
    printed above it), 2 when drafting could not be done at all. The verified draft is written
    to `out` as YAML, when given; nothing else is written.
    """
    try:
        current: JsonObject = yaml.safe_load(Path(version_file).read_text(encoding="utf-8"))
        path = Path(page_file)
        body = path.read_text(encoding="utf-8", errors="replace")
        page = page_text(body, html=path.suffix.lower() not in (".md", ".txt"))
        outcome = draft_version(current, page, url or infer_url(current, page), drafter)
    except (OSError, DraftError) as error:
        sys.stderr.write(f"{_redacted(str(error))}\n")
        return 2
    for failure in outcome.failures:
        sys.stdout.write(f"  {failure}\n")
    if out is not None and outcome.draft is not None:
        Path(out).write_text(PRICE_FILE_HEADER + yaml_text(outcome.draft), encoding="utf-8")
    sys.stdout.write(f"{outcome.result_line()}\n")
    return 1 if outcome.status == "unreadable" else 0


def _redacted(message: str) -> str:
    """The message without the API key, should anything have echoed it."""
    key = os.environ.get("ANTHROPIC_API_KEY")
    return message.replace(key, "[redacted]") if key else message
