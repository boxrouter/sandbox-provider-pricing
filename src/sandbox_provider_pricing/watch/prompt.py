# SPDX-FileCopyrightText: BoxRouter, Inc.
# SPDX-License-Identifier: Apache-2.0
"""The message that asks an agent to draft a price version, and reading its answer."""

import json
import re

import yaml  # type: ignore[import-untyped]

from sandbox_provider_pricing.types import JsonObject
from sandbox_provider_pricing.watch.check import PageText
from sandbox_provider_pricing.watch.verify import price_version_schema

PARTS = ("sources", "classes", "exclusions", "open_questions")
MAX_EMBEDDED_CHARS = 100_000
SCRIPT_WINDOW = 3000  # characters of script text sent each side of where a quote sits
PREFIX_CHARS = 30


def build_prompt(
    current: JsonObject, url: str, page: PageText, failures: list[str] | None = None
) -> str:
    """The message that asks for a new version, with the failures of a rejected draft if any."""
    text = page.visible
    sections = [f"The page, as text (visible text only):\n<page>\n{text}\n</page>"]
    excerpts = _script_excerpts(current, url, page)
    if excerpts:
        sections.append(
            "This page keeps some of its text only inside scripts. These are the parts of that "
            "text where the current version's quotes from this page sit:\n"
            f"<script-text>\n{excerpts}\n</script-text>"
        )
    schema = json.dumps(price_version_schema(), indent=1)
    asked = (
        f"The price page {url} for {current['provider']} has changed, so the quotes of its "
        "current price version no longer match it. Write the new version's four parts from "
        "the page.\n\n"
        "Answer with one JSON object, with no code fence and no other text before or after it:\n"
        '{"sources": [<string>, ...], "classes": [...], "exclusions": [...], '
        '"open_questions": [...]}\n\n'
        "- `sources`: verbatim quotes from the page above, as strings. Copy them character for "
        "character; only spacing may differ, and you may join excerpts that are apart on the "
        " page with ` | `. Quote every passage a rate or a meter rule was read from, and "
        "every other passage the current version quotes from this page that the page still says. "
        "Do not add the URL; it is this page's.\n"
        "- `classes`, `exclusions`, `open_questions`: as the current version has them, changed "
        "only where the page says something different. Read each rate as the page prints it, "
        "in the unit it prints it in; never convert a price to another unit. Every `usd` is a "
        "number printed in one of your quotes, or in a quote the current version takes from "
        "another page (those are kept as they are).\n"
        "- Read each rate from the same place on the page that the current version's quote for "
        "it was read. If that place now prints a different number, that is the new rate, even "
        "where other places on the page disagree with it (say so in `open_questions`). Leave a "
        "rate or a rule out only if the page no longer prints it anywhere. Never guess a "
        "number the page does not show.\n"
        "- Do not write `provider`, `version`, `effective_from`, `retrieved_at` or the URLs; "
        "they are set for you."
    )
    context = (
        "The current version (YAML), which shows the format:\n<current>\n"
        f"{yaml_text(current)}</current>\n\n"
        f"It must validate against this JSON Schema:\n<schema>\n{schema}\n</schema>"
    )
    parts = [asked, context, *sections]
    if failures:
        listed = "\n".join(f"- {failure}" for failure in failures)
        parts.append(
            f"Your previous answer was rejected:\n{listed}\n"
            "Fix these and answer again with the whole JSON object."
        )
    return "\n\n".join(parts)


def yaml_text(document: JsonObject) -> str:
    dumped: str = yaml.safe_dump(document, sort_keys=False, allow_unicode=True, width=100)
    return dumped


def _script_excerpts(current: JsonObject, url: str, page: PageText) -> str:
    """The script text around each quote of this page that only scripts hold, or nothing.

    A page that ships its text as JSON in a script (Vercel's API reference) has too much of it to
    send whole, and what the version quotes is near what it quoted. A quote is found by its
    first excerpt, or, if that has changed, by its first words.
    """
    visible = PageText(visible=page.visible)
    spans: list[tuple[int, int]] = []
    for source in current["sources"]:
        if source["url"] != url or visible.contains(source["quote"]):
            continue
        first = re.sub(r"\s+", " ", source["quote"].split("|")[0]).strip()
        at = page.embedded.find(first)
        if at < 0:
            at = page.embedded.find(first[:PREFIX_CHARS])
        if at >= 0:
            spans.append((max(0, at - SCRIPT_WINDOW), at + len(first) + SCRIPT_WINDOW))
    merged: list[tuple[int, int]] = []
    for start, end in sorted(spans):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return "\n...\n".join(page.embedded[start:end] for start, end in merged)[:MAX_EMBEDDED_CHARS]


def read_reply(text: str) -> tuple[JsonObject | None, list[str]]:
    """The JSON object in the agent's answer, or why there is none.

    An answer may have more than one object (a draft and then a correction, or a code fence
    around it); the last one that reads is the answer.
    """
    reply: JsonObject | None = None
    decoder = json.JSONDecoder()
    at = text.find("{")
    while at >= 0:
        try:
            found, end = decoder.raw_decode(text, at)
        except ValueError:
            at = text.find("{", at + 1)
            continue
        reply = found if isinstance(found, dict) else reply
        at = text.find("{", end)
    if reply is None:
        return None, ["The answer has no JSON object."]
    problems = [f"The answer has no `{name}`." for name in PARTS if name not in reply]
    problems += [
        f"The answer has `{name}`, which is not asked for." for name in reply if name not in PARTS
    ]
    sources = reply.get("sources")
    if "sources" in reply and not (
        isinstance(sources, list) and all(isinstance(quote, str) for quote in sources)
    ):
        problems.append("`sources` must be a list of quote strings.")
    return (None, problems) if problems else (reply, [])
