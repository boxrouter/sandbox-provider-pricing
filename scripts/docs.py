# SPDX-FileCopyrightText: BoxRouter, Inc.
# SPDX-License-Identifier: Apache-2.0
"""Generate provider pages and the README and COMPARING.md tables from billing records."""

import posixpath
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any, cast

from sandbox_provider_pricing.billing_text import unit_name
from sandbox_provider_pricing.calculator import per_hour
from sandbox_provider_pricing.cost_method import cost_method
from sandbox_provider_pricing.versions import latest_version

ROOT = Path(__file__).resolve().parents[1]
# Each provider's shipped files; its README, evidence and fixtures stay in `providers/<id>/`.
PACKAGES = Path("src/sandbox_provider_pricing/providers")
STATUS_START = "<!-- generated:provider-status -->"
STATUS_END = "<!-- /generated:provider-status -->"
HOURLY_START = "<!-- generated:hourly -->"
HOURLY_END = "<!-- /generated:hourly -->"
# The size COMPARING.md quotes for every provider.
HOURLY_SIZE = {"cpu": 2, "memory_mib": 4096}
BASIS = {
    "allocated": "size requested",
    "active": "only while in use",
    "larger_of_request_and_use": "larger of requested and used",
}
METERS = {
    "cpu": "CPU",
    "memory": "Memory",
    "disk": "Disk",
    "egress": "Network egress",
    "creation": "Creation",
    "snapshot_storage": "Snapshot storage",
    "gpu": "GPU",
    "machine": "Machine",
}


def load_documents() -> list[tuple[str, dict[str, Any]]]:
    """Each provider's entry in the cost method, sorted by provider folder."""
    providers = cast(dict[str, dict[str, Any]], cost_method()["providers"])
    return sorted(providers.items())


def _cell(value: str) -> str:
    """Escape text for a Markdown table cell."""
    return value.strip().replace("|", "\\|").replace("\n", " ").replace("\r", "")


def _link(source: str, provider: str) -> str:
    """Render one source as a short Markdown link relative to the provider page."""
    if source.startswith("https://"):
        label = source.removeprefix("https://").removeprefix("www.").split("#", 1)[0]
        return f"[{label.rstrip('/')}]({source})"
    target = posixpath.relpath(source, f"providers/{provider}")
    label = source.split("#", 1)[0].rsplit("/", 1)[-1]
    return f"[{label}]({target})"


class _Notes:
    """Footnotes for one page: each distinct source gets one number, in order of first use."""

    def __init__(self, provider: str) -> None:
        self.provider = provider
        self.sources: list[str] = []

    def cite(self, sources: list[str]) -> str:
        """Footnote references for the given sources."""
        for source in sources:
            if source not in self.sources:
                self.sources.append(source)
        numbers = sorted({self.sources.index(source) + 1 for source in sources})
        return "".join(f"[^{number}]" for number in numbers)

    def lines(self) -> list[str]:
        return [
            f"[^{number}]: {_link(source, self.provider)}"
            for number, source in enumerate(self.sources, 1)
        ]


def _answer(answer: dict[str, Any], notes: _Notes) -> str:
    """One rule's answer with its source footnotes, or the check that would settle it."""
    text = _cell(answer["answer"])
    if "sources" in answer:
        return f"{text} {notes.cite(answer['sources'])}"
    return f"{text} To find out: {_cell(answer['unknown_how'])}"


def _rate(rate: dict[str, Any]) -> str:
    if "usd" not in rate:
        return f"per GPU model ({len(rate)} models in the price version)"
    return f"${rate['usd']} per {unit_name(rate['per'])}"


def _package_link(provider: str, name: str) -> str:
    """A link from a provider's page, which stays in `providers/<id>/`, to a file in its package."""
    return f"../../{PACKAGES.as_posix()}/{provider}/{name}"


def _price_link(version: dict[str, Any]) -> str:
    return f"../../{version['file']}"


def _rates(version: dict[str, Any]) -> list[str]:
    price_class = next(item for item in version["classes"] if item.get("default"))
    meter = price_class.get("meter", {})
    lines = [
        f"From [`{version['version']}`]({_price_link(version)}), in effect from "
        f"{version['effective_from'][:10]}, default class `{price_class['name']}`.",
        "",
        "| Meter | Rate | Billed on | Billed while |",
        "| --- | --- | --- | --- |",
    ]
    for name, rate in price_class["rates"].items():
        rule = meter.get(name, {})
        basis = BASIS.get(rule.get("basis", ""), "")
        if "increment_seconds" in rule:
            basis = f"{basis}, in {rule['increment_seconds']} s increments".lstrip(", ")
        states = ", ".join(rule.get("billed_states", []))
        if name == "machine":
            for size_name, size_rate in rate.items():
                lines.append(f"| Machine ({size_name}) | {_rate(size_rate)} | {basis} | {states} |")
            continue
        lines.append(f"| {METERS.get(name, name)} | {_rate(rate)} | {basis} | {states} |")
    multipliers = price_class.get("region_multipliers")
    if multipliers:
        pairs = ", ".join(f"{region} x{value}" for region, value in multipliers.items())
        lines += ["", f"Region multipliers when a region is chosen: {pairs}."]
    return lines


def _version_list(document: dict[str, Any]) -> list[str]:
    """One line per price version file: the one in effect, then what replaced each other one."""
    lines = []
    for version in document["versions"].values():
        if version["state"] == "in_effect":
            state = "in effect now"
        elif version["replaced_by"] is None:
            state = "still in force for earlier sandboxes"
        else:
            state = f"replaced by `{version['replaced_by']}`"
        lines.append(
            f"- [`{version['version']}`]({_price_link(version)}): from "
            f"{version['effective_from'][:10]}, read {version['retrieved_at'][:10]}, {state}."
        )
    return lines


def render_provider_page(provider: str, document: dict[str, Any]) -> str:
    """Render one provider's page in template order."""
    label = document["best_label"]
    meaning = cost_method()["method"]["labels"][label]["meaning"]
    notes = _Notes(provider)
    lines = [
        f"# {document['name']}",
        "",
        f"{document['name']} costs are `{label}`. {meaning}",
        "",
        document["summary"],
        "",
        "## How the cost is worked out",
        "",
        document["formula"],
        "",
        f"What holds it back: {document['why_not_higher']}",
        "",
        f"What would improve it: {document['would_raise']}",
        "",
        "## Rates",
        "",
        *_rates(document["versions"][document["latest_version"]]),
        "",
        "## Billing rules",
        "",
        "| Rule | Answer |",
        "| --- | --- |",
    ]
    lines += [f"| {rule['title']} | {_answer(rule, notes)} |" for rule in document["rules"]]
    lines += ["", "## Not known yet", ""]
    questions = cast(list[dict[str, str]], document["open_questions"])
    for item in questions:
        lines += [f"- {item['question']}", f"  - To find out: {item['how']}"]
    if not questions:
        lines.append("Nothing open.")
    lines += ["", "## Our measurements", ""]
    checks = cast(list[dict[str, str]], document["measurements"])
    lines += [
        f"- {check['date']}: [{check['title']}]({check['file']}). {check['result']}"
        for check in checks
    ]
    if not checks:
        lines.append("None yet.")
    lines += [
        "",
        "## Price versions",
        "",
        *_version_list(document),
        "",
        "This page is generated from "
        f"[billing.yaml]({_package_link(provider, 'billing.yaml')}) and the price versions by "
        "`make docs`. Edit those, not this file.",
        "",
        *notes.lines(),
    ]
    return "\n".join(lines) + "\n"


def render_status_table(documents: list[tuple[str, dict[str, Any]]]) -> str:
    """Render the root-level table of how each provider's cost is worked out."""
    lines = [
        "| Provider | Best cost available | How it is worked out |",
        "| --- | --- | --- |",
    ]
    for provider, document in documents:
        lines.append(
            f"| [{document['name']}](providers/{provider}/README.md) | "
            f"`{document['best_label']}` | {_cell(document['formula'])} |"
        )
    return "\n".join(lines)


HOURLY_BASIS = {
    "allocated": "as requested",
    "active": "only while in use",
    "larger_of_request_and_use": "at the larger of request and use",
}


def _billed_on(meter: dict[str, Any]) -> str:
    """How CPU and memory are billed, from the default class's meter rules."""
    parts: dict[str, list[str]] = {}
    for name, label in (("cpu", "CPU"), ("memory", "memory")):
        if name in meter:
            parts.setdefault(HOURLY_BASIS[meter[name]["basis"]], []).append(label)
    if not parts:
        return "Flat per-size rate, not per vCPU or GiB"
    phrases = [f"{' and '.join(names)} {basis}" for basis, names in parts.items()]
    text = ", ".join(phrases)
    return text[0].upper() + text[1:]


def _hour_amount(text: str) -> str:
    """A quote as the calculator gives it, or, where its decimal does not end (an hour of a
    monthly rate), rounded to a millionth of a dollar and marked "about"."""
    exact = Decimal(text)
    rounded = exact.quantize(Decimal("0.000001"))
    return text if rounded == exact else f"about {rounded.normalize():f}"


def render_hourly_table(documents: list[tuple[str, dict[str, Any]]]) -> str:
    """Render COMPARING.md's one-hour quote for HOURLY_SIZE on each newest price version."""
    lines = [
        "| Provider | One hour (USD) | Billed on | Price version |",
        "| --- | ---: | --- | --- |",
    ]
    for provider, document in documents:
        version = latest_version(provider)
        price_class = next(item for item in version["classes"] if item.get("default"))
        meter = price_class.get("meter", {})
        quote = per_hour(version, HOURLY_SIZE)
        if quote is None:
            amount = "not priced"
        elif quote["low"] != quote["high"]:
            amount = f"{_hour_amount(quote['low'])} to {_hour_amount(quote['high'])}"
        elif any(rule.get("basis") == "larger_of_request_and_use" for rule in meter.values()):
            amount = f"at least {_hour_amount(quote['low'])}"
        else:
            amount = _hour_amount(quote["low"])
        link = f"[`{version['version']}`]({document['versions'][version['version']]['file']})"
        lines.append(f"| {document['name']} | {amount} | {_billed_on(meter)} | {link} |")
    return "\n".join(lines)


def replace_block(path: Path, start: str, end: str, generated: str) -> None:
    """Replace exactly one generated block while preserving its surrounding prose."""
    text = path.read_text(encoding="utf-8")
    if text.count(start) != 1 or text.count(end) != 1:
        raise ValueError(f"{path} must contain exactly one {start} and {end} marker")
    start_at = text.index(start) + len(start)
    end_at = text.index(end)
    if end_at < start_at:
        raise ValueError(f"{path} has its generated markers out of order")
    updated = f"{text[:start_at]}\n{generated.rstrip()}\n{text[end_at:]}"
    path.write_text(updated, encoding="utf-8")


def generate(root: Path = ROOT) -> None:
    """Write every provider page, the README status table and the COMPARING.md hourly table."""
    documents = load_documents()
    for provider, document in documents:
        page = root / "providers" / provider / "README.md"
        page.write_text(render_provider_page(provider, document), encoding="utf-8")
    replace_block(root / "README.md", STATUS_START, STATUS_END, render_status_table(documents))
    replace_block(root / "COMPARING.md", HOURLY_START, HOURLY_END, render_hourly_table(documents))


def main() -> int:
    generate(Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
