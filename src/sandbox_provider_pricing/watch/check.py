# SPDX-FileCopyrightText: BoxRouter, Inc.
# SPDX-License-Identifier: Apache-2.0
"""The daily quote check: does every provider page still say what its price version quotes?

For each price version, fetch every source URL, turn the page into text and look for every
stored quote. All found means `confirmed`; a quote missing from a page that was read means
`changed`; a page that could not be fetched means `unreadable`. The check reads prices; it never
writes one.
"""

import json
import re
import sys
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from html.parser import HTMLParser
from pathlib import Path
from urllib.request import Request, urlopen

import yaml  # type: ignore[import-untyped]

from sandbox_provider_pricing.types import JsonObject

FETCH_TIMEOUT_SECONDS = 30
MAX_PAGE_BYTES = 16 * 1024 * 1024
USER_AGENT = "sandbox-provider-pricing-check/0.1 (+https://boxrouter.ai)"

# Never shown: scripts and styles are code, `head` is metadata, `svg` is drawing.
_NOT_TEXT = frozenset({"script", "style", "noscript", "template", "svg", "head"})
# Tags with no end tag; they open no element.
_VOID = frozenset({"br", "hr", "img", "input", "meta", "link", "wbr", "area", "col", "source"})
# A browser starts a new line or cell at these, so text on either side is not joined.
_BLOCK = frozenset(
    {
        "address", "article", "aside", "blockquote", "body", "br", "button", "dd", "details",
        "div", "dl", "dt", "fieldset", "figcaption", "figure", "footer", "form", "h1", "h2",
        "h3", "h4", "h5", "h6", "header", "hr", "label", "li", "main", "nav", "ol", "option",
        "p", "pre", "section", "select", "summary", "table", "tbody", "td", "tfoot", "th",
        "thead", "tr", "ul",
    }
)  # fmt: skip
# `aria-hidden` on these marks decoration. Modal's price page draws each digit a second time
# in an `aria-hidden` span beside the real number. `aria-hidden` on a block is a tab panel or
# a collapsed section (E2B keeps its inactive tabs' tables that way), which is page content.
_DECORATIVE_INLINE = frozenset({"span", "i", "b", "em", "strong", "sup", "sub", "small", "abbr"})
_SEPARATOR = re.compile(r"[\s|]+")
_JSON_ESCAPE = re.compile(r"\\(u[0-9a-fA-F]{4}|.)")
_JSON_SIMPLE = {"n": " ", "r": " ", "t": " ", "b": " ", "f": " "}


class _TextParser(HTMLParser):
    """Collects the text a reader sees, and separately the text of inline scripts."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.visible: list[str] = []
        self.embedded: list[str] = []
        self._open: list[tuple[str, bool]] = []
        self._hidden = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _BLOCK:
            self.visible.append(" ")
        if tag in _VOID:
            return
        hidden = tag in _NOT_TEXT or (
            tag in _DECORATIVE_INLINE and dict(attrs).get("aria-hidden") == "true"
        )
        self._open.append((tag, hidden))
        self._hidden += hidden

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _BLOCK:
            self.visible.append(" ")

    def handle_endtag(self, tag: str) -> None:
        if tag in _BLOCK:
            self.visible.append(" ")
        for index in range(len(self._open) - 1, -1, -1):
            if self._open[index][0] == tag:
                self._hidden -= sum(hidden for _, hidden in self._open[index:])
                del self._open[index:]
                return

    def handle_data(self, data: str) -> None:
        if self._open and self._open[-1][0] == "script":
            self.embedded.append(data)
        elif not self._hidden:
            self.visible.append(data)


@dataclass(frozen=True)
class PageText:
    """What a page says: the text a reader sees, and data embedded in its scripts.

    Some sites (Vercel's API reference) ship their text only as JSON inside a script and draw
    it in the browser, so a quote taken from the drawn page is found there.
    """

    visible: str
    embedded: str = ""

    def contains(self, quote: str) -> bool:
        """Whether every part of the quote is on the page, verbatim up to spacing."""
        wanted = _compact(quote)
        if not wanted:
            return False
        pages = [_compact(self.visible), _compact(self.embedded)]
        if any(wanted in page for page in pages):
            return True
        # A quote may join separate excerpts with ` | `; each one must be on the page.
        parts = [_compact(part) for part in quote.split("|")]
        parts = [part for part in parts if part]
        return len(parts) > 1 and all(any(part in page for page in pages) for part in parts)


def _compact(text: str) -> str:
    """The text without whitespace or `|`, so that how a page spaces or joins it does not matter."""
    return _SEPARATOR.sub("", text)


def _unescape_json(text: str) -> str:
    def replace(match: re.Match[str]) -> str:
        escape = match.group(1)
        if escape[0] == "u" and len(escape) == 5:
            return chr(int(escape[1:], 16))
        return _JSON_SIMPLE.get(escape, escape)

    return _JSON_ESCAPE.sub(replace, text)


def page_text(body: str, *, html: bool = True) -> PageText:
    """Turn a fetched page into the text its quotes were taken from.

    HTML has its tags stripped; text that a browser would not show is left out. Markdown and
    other plain text is used as it is.
    """
    if not html:
        return PageText(visible=_SEPARATOR.sub(" ", body).strip())
    parser = _TextParser()
    parser.feed(body)
    parser.close()
    return PageText(
        visible=re.sub(r"\s+", " ", "".join(parser.visible)).strip(),
        embedded=re.sub(r"\s+", " ", _unescape_json(" ".join(parser.embedded))).strip(),
    )


class FetchError(Exception):
    """A page could not be read: no connection, a timeout or an HTTP error."""


Fetcher = Callable[[str], PageText]


def fetch_page(url: str) -> PageText:
    """Fetch one page and return its text."""
    request = Request(url, headers={"User-Agent": USER_AGENT})  # noqa: S310
    try:
        with urlopen(request, timeout=FETCH_TIMEOUT_SECONDS) as response:  # noqa: S310
            charset = response.headers.get_content_charset() or "utf-8"
            content_type = response.headers.get_content_type()
            body = response.read(MAX_PAGE_BYTES).decode(charset, errors="replace")
    except Exception as error:
        raise FetchError(f"{type(error).__name__}: {error}") from error
    return page_text(body, html="html" in content_type or "xml" in content_type)


@dataclass
class VersionCheck:
    """The result for one price version."""

    provider: str
    version: str
    status: str
    fetched_at: str
    missing: list[dict[str, str]] = field(default_factory=list)
    unreadable: list[dict[str, str]] = field(default_factory=list)

    def as_json(self) -> str:
        return json.dumps(
            {
                "provider": self.provider,
                "version": self.version,
                "status": self.status,
                "missing": self.missing,
                "unreadable": self.unreadable,
                "fetched_at": self.fetched_at,
            },
            ensure_ascii=False,
        )


def check_version(document: JsonObject, fetch: Fetcher = fetch_page) -> VersionCheck:
    """Check one price version's quotes against its pages. Never changes the version."""
    pages: dict[str, PageText | str] = {}
    result = VersionCheck(
        provider=str(document["provider"]),
        version=str(document["version"]),
        status="confirmed",
        fetched_at=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    )
    for source in document["sources"]:
        url, quote = source["url"], source["quote"]
        if url not in pages:
            try:
                pages[url] = fetch(url)
            except FetchError as error:
                pages[url] = str(error)
        page = pages[url]
        if isinstance(page, str):
            entry = {"url": url, "error": page}
            if entry not in result.unreadable:
                result.unreadable.append(entry)
        elif not page.contains(quote):
            result.missing.append({"url": url, "quote": quote})
    if result.missing:
        result.status = "changed"
    elif result.unreadable:
        result.status = "unreadable"
    return result


def check_files(paths: Iterable[Path], fetch: Fetcher = fetch_page) -> list[VersionCheck]:
    """Check each price version file; a page shared by several versions is fetched once."""
    return check_documents(
        [yaml.safe_load(path.read_text(encoding="utf-8")) for path in paths], fetch
    )


def check_documents(
    documents: Iterable[JsonObject], fetch: Fetcher = fetch_page
) -> list[VersionCheck]:
    """Check each price version document; a page shared by several versions is fetched once."""
    cache: dict[str, PageText | FetchError] = {}

    def cached_fetch(url: str) -> PageText:
        if url not in cache:
            try:
                cache[url] = fetch(url)
            except FetchError as error:
                cache[url] = error
        outcome = cache[url]
        if isinstance(outcome, FetchError):
            raise outcome
        return outcome

    return [check_version(document, cached_fetch) for document in documents]


def run(paths: Sequence[str], fetch: Fetcher = fetch_page) -> int:
    """Print one JSON line per version file. Exit status 0 only when all are confirmed."""
    results = check_files([Path(path) for path in paths], fetch)
    for result in results:
        sys.stdout.write(result.as_json() + "\n")
    return 0 if all(result.status == "confirmed" for result in results) else 1
