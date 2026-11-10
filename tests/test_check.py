# SPDX-FileCopyrightText: BoxRouter, Inc.
# SPDX-License-Identifier: Apache-2.0
"""The daily quote check: confirmed, changed and unreadable, and how a page becomes text."""

import json
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest
import yaml  # type: ignore[import-untyped]

from sandbox_provider_pricing.watch import check, cli

ROOT = Path(__file__).resolve().parents[1]
PACKAGES = ROOT / "src" / "sandbox_provider_pricing" / "providers"
PAGES = Path(__file__).parent / "fixtures" / "pages"
E2B_VERSION = PACKAGES / "e2b" / "prices" / "2026-10-20-061802Z.yaml"
CPU_QUOTE = (
    "vCPUs Plan Costs 1 Hobby / Pro $0.000014/s 2 [Default] Hobby / Pro $0.000028/s 4 Hobby / Pro "
    "$0.000056/s 6 Hobby / Pro $0.000084/s 8 Hobby / Pro $0.000112/s"
)


class _Site:
    """A local web server: each path serves a status, a body and a content type."""

    def __init__(self) -> None:
        self.routes: dict[str, tuple[int, bytes, str]] = {}
        self.requests: list[str] = []
        site = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802
                site.requests.append(self.path)
                status, body, content_type = site.routes.get(
                    self.path, (404, b"not found", "text/plain")
                )
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def url(self, path: str) -> str:
        return f"http://127.0.0.1:{self.server.server_address[1]}{path}"

    def serve(
        self, path: str, body: str | bytes, status: int = 200, kind: str = "text/html"
    ) -> str:
        data = body.encode() if isinstance(body, str) else body
        self.routes[path] = (status, data, kind)
        return self.url(path)


@pytest.fixture(name="site")
def site_fixture() -> Iterator[_Site]:
    site = _Site()
    site.thread.start()
    yield site
    site.server.shutdown()
    site.server.server_close()


def _e2b_pricing_version(url: str) -> dict[str, Any]:
    """The real E2B version, cut down to the quotes taken from the pricing page, served at `url`."""
    document: dict[str, Any] = yaml.safe_load(E2B_VERSION.read_text(encoding="utf-8"))
    document["sources"] = [
        {"url": url, "quote": source["quote"]}
        for source in document["sources"]
        if source["url"] == "https://e2b.dev/pricing"
    ]
    assert len(document["sources"]) == 10
    return document


def _single(document: dict[str, Any]) -> check.VersionCheck:
    return check.check_version(document)


def test_todays_e2b_page_is_confirmed(site: _Site) -> None:
    url = site.serve("/pricing", (PAGES / "e2b-pricing.html").read_text(encoding="utf-8"))
    result = _single(_e2b_pricing_version(url))
    assert (result.status, result.missing, result.unreadable) == ("confirmed", [], [])
    assert result.provider == "e2b"
    assert result.version == "e2b@2026-10-20-061802Z"


def test_a_changed_rate_names_the_quote_that_is_gone(site: _Site) -> None:
    url = site.serve("/pricing", (PAGES / "e2b-cpu-changed.html").read_text(encoding="utf-8"))
    result = _single(_e2b_pricing_version(url))
    assert result.status == "changed"
    assert result.missing == [{"url": url, "quote": CPU_QUOTE}]
    assert result.unreadable == []


def test_an_http_500_is_unreadable(site: _Site) -> None:
    url = site.serve("/pricing", "<html>Internal Server Error</html>", status=500)
    result = _single(_e2b_pricing_version(url))
    assert result.status == "unreadable"
    assert result.missing == []
    assert len(result.unreadable) == 1
    assert result.unreadable[0]["url"] == url
    assert "500" in result.unreadable[0]["error"]


def test_a_server_that_is_not_there_is_unreadable() -> None:
    document = _e2b_pricing_version("http://127.0.0.1:9/pricing")
    result = _single(document)
    assert result.status == "unreadable"
    assert [item["url"] for item in result.unreadable] == ["http://127.0.0.1:9/pricing"]


def test_a_missing_quote_beats_an_unreadable_page(site: _Site) -> None:
    good = site.serve("/good", "<p>We charge per second of a running sandbox.</p>")
    bad = site.serve("/bad", "boom", status=503)
    document = {
        "provider": "x",
        "version": "x@1",
        "sources": [
            {"url": good, "quote": "We charge per hour."},
            {"url": bad, "quote": "anything"},
        ],
    }
    result = _single(document)
    assert result.status == "changed"
    assert [item["quote"] for item in result.missing] == ["We charge per hour."]
    assert [item["url"] for item in result.unreadable] == [bad]


def test_the_command_prints_one_json_line_and_writes_nothing(
    site: _Site, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    url = site.serve("/pricing", (PAGES / "e2b-cpu-changed.html").read_text(encoding="utf-8"))
    version_file = tmp_path / "e2b.yaml"
    version_file.write_text(yaml.safe_dump(_e2b_pricing_version(url), sort_keys=False))
    before = version_file.read_bytes()
    status = cli.main(["check", str(version_file)])
    lines = capsys.readouterr().out.splitlines()
    assert status == 1
    assert len(lines) == 1
    line = json.loads(lines[0])
    assert list(line) == ["provider", "version", "status", "missing", "unreadable", "fetched_at"]
    assert line["status"] == "changed"
    assert line["missing"] == [{"url": url, "quote": CPU_QUOTE}]
    assert line["fetched_at"].endswith("Z")
    assert version_file.read_bytes() == before
    assert sorted(path.name for path in tmp_path.iterdir()) == ["e2b.yaml"]


def test_the_command_exits_0_when_every_version_is_confirmed(
    site: _Site, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    url = site.serve("/pricing", (PAGES / "e2b-pricing.html").read_text(encoding="utf-8"))
    paths = []
    for name in ("a.yaml", "b.yaml"):
        path = tmp_path / name
        path.write_text(yaml.safe_dump(_e2b_pricing_version(url), sort_keys=False))
        paths.append(str(path))
    assert cli.main(["check", *paths]) == 0
    statuses = [json.loads(line)["status"] for line in capsys.readouterr().out.splitlines()]
    assert statuses == ["confirmed", "confirmed"]
    assert site.requests == ["/pricing"], "a page shared by two versions is fetched once"


def test_markdown_pages_are_used_as_they_are(site: _Site) -> None:
    url = site.serve(
        "/api.md", "memory: 8192, // Memory in MB <default: 4096>\n", kind="text/markdown"
    )
    document = {
        "provider": "x",
        "version": "x@1",
        "sources": [{"url": url, "quote": "memory: 8192, // Memory in MB <default: 4096>"}],
    }
    assert _single(document).status == "confirmed"


@pytest.mark.parametrize(
    ("html", "visible", "contained"),
    [
        pytest.param(
            '<span>CPU</span> <span>$<span class="sr-only">0.0000131</span> '
            '<span aria-hidden="true"><span>0</span><span>.</span><span>0</span></span></span> '
            "/ core / sec",
            "CPU $0.0000131 / core / sec",
            "CPU $0.0000131 / core / sec",
            id="modal-draws-each-digit-twice-and-only-the-real-number-counts",
        ),
        pytest.param(
            '<script>self.push("{\\"description\\":\\"Must equal vcpus * 2048.\\\\n'
            'See \\\\u003ccode\\\\u003e\\"}")'
            "</script><p>Pricing</p>",
            "Pricing",
            "Must equal vcpus * 2048.",
            id="text-a-site-ships-inside-a-script-is-found",
        ),
    ],
)
def test_page_text_reads_what_a_reader_sees(html: str, visible: str, contained: str) -> None:
    page = check.page_text(html)
    assert page.visible == visible
    assert page.contains(contained)


def test_a_hidden_tab_panel_is_still_page_text() -> None:
    html = (
        '<div aria-hidden="false">Plan CPU</div>'
        '<div aria-hidden="true" class="invisible">Memory (GiB) 1 Hobby</div>'
    )
    assert check.page_text(html).contains("Memory (GiB) 1 Hobby")


def test_scripts_styles_and_head_are_not_page_text() -> None:
    html = (
        "<html><head><title>Pricing</title></head><body><style>.a{}</style>"
        "<script>var price = '$9';</script><p>$1 / hour</p><noscript>$7</noscript></body></html>"
    )
    page = check.page_text(html)
    assert page.visible == "$1 / hour"
    assert page.embedded == "var price = '$9';", "a script's data is kept apart from page text"
    assert not page.contains("$7")
    assert not page.contains(".a{}")
    assert not page.contains("Pricing")


def test_spacing_and_cell_joins_do_not_matter() -> None:
    page = check.page_text("<table><tr><td>Active CPU</td><td>$0.128/hour</td></tr></table>")
    assert page.contains("Active CPU | $0.128/hour")
    assert page.contains("Active   CPU $0.128/hour")
    assert not page.contains("Active CPU | $0.129/hour")


def test_excerpts_joined_by_a_pipe_may_be_apart_on_the_page() -> None:
    page = check.page_text(
        "<p>$200 in free compute included.</p><p>x</p><p>All billing is per second.</p>"
    )
    assert page.contains("All billing is per second. | $200 in free compute included.")
    assert not page.contains("$200 in free compute included. | All billing is per hour.")


def test_one_changed_digit_is_not_found() -> None:
    page = check.page_text("<p>CPU $0.000016/s</p>")
    assert not page.contains("CPU $0.000014/s")


def test_an_empty_quote_is_never_found() -> None:
    assert not check.page_text("<p>anything</p>").contains(" | ")
