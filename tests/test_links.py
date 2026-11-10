# SPDX-FileCopyrightText: BoxRouter, Inc.
# SPDX-License-Identifier: Apache-2.0
"""Every link to a file in this repository, and every heading anchor, must resolve."""

import re
import subprocess
from pathlib import Path

import yaml  # type: ignore[import-untyped]

ROOT = Path(__file__).resolve().parents[1]
PACKAGES = ROOT / "src" / "sandbox_provider_pricing" / "providers"
LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")
FENCE = re.compile(r"^(```|~~~).*?^\1", re.MULTILINE | re.DOTALL)


def _tracked(pattern: str) -> list[Path]:
    listed = subprocess.run(
        ["git", "ls-files", pattern], cwd=ROOT, check=True, capture_output=True, text=True
    )
    return [ROOT / name for name in listed.stdout.split()]


def _anchors(path: Path) -> set[str]:
    """GitHub's heading anchors: lower case, punctuation dropped, spaces as hyphens."""
    text = FENCE.sub("", path.read_text(encoding="utf-8"))
    headings = re.findall(r"^#{1,6} +(.+?) *#*$", text, re.MULTILINE)
    return {re.sub(r"[^\w\- ]", "", heading.lower()).replace(" ", "-") for heading in headings}


def _problem(origin: Path, target: str, base: Path) -> str | None:
    location, _, anchor = target.partition("#")
    path = origin if not location else (base / location).resolve()
    if not path.exists():
        return f"{origin.relative_to(ROOT)} links to {target}, which does not exist"
    if anchor and path.suffix == ".md" and anchor not in _anchors(path):
        return f"{origin.relative_to(ROOT)} links to {target}, which has no such heading"
    return None


def test_markdown_links_resolve() -> None:
    problems = []
    for path in _tracked("*.md"):
        text = FENCE.sub("", path.read_text(encoding="utf-8"))
        for target in LINK.findall(text):
            if re.match(r"[a-z]+:", target):
                continue
            problem = _problem(path, target, path.parent)
            if problem:
                problems.append(problem)
    assert problems == []


def test_billing_sources_in_this_repository_resolve() -> None:
    problems = []
    for path in sorted(PACKAGES.glob("*/billing.yaml")):
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        for rule in document["rules"].values():
            for source in rule.get("sources", []):
                if not re.match(r"[a-z]+:", source):
                    problem = _problem(path, source.split(" ")[0], ROOT)
                    if problem:
                        problems.append(problem)
    assert problems == []
