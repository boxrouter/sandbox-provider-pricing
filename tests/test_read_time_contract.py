# SPDX-FileCopyrightText: BoxRouter, Inc.
# SPDX-License-Identifier: Apache-2.0
"""A bounded use scan and behavioral samples; deliberately not a data-flow proof."""

import ast
import json
from collections.abc import Iterator, Sequence
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from sandbox_provider_pricing import READ_TIME_CONTRACT, READ_TIME_PATHS, price, settles_after
from sandbox_provider_pricing.providers import provider_ids
from sandbox_provider_pricing.read_time import _valid_declaration
from sandbox_provider_pricing.revisit import RevisitPolicy, revisit

ROOT = Path(__file__).resolve().parents[1]
PACKAGES = ROOT / "src" / "sandbox_provider_pricing" / "providers"
FIXTURES = sorted((ROOT / "providers").glob("*/fixtures/*/evidence.json"))
KINDS = {"copied verbatim", "compared with input", "bounded comparison"}


def scan(path: Path) -> dict[str, list[str]]:
    """Track direct names, keys, attributes, parameters and keywords, including read aliases."""
    tree = ast.parse(path.read_text())
    found: dict[str, list[str]] = {}

    def walk(node: ast.AST, function: str) -> None:
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            function = function + "." + node.name if function else node.name
        name = None
        if isinstance(node, ast.Name):
            name = node.id
        elif isinstance(node, ast.Attribute):
            name = node.attr
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            if node.value in {"as_of", "observed_at", "read_at", "last_read_at", "next_read_at"}:
                name = node.value
        elif isinstance(node, ast.arg):
            name = node.arg
        elif isinstance(node, ast.keyword):
            name = node.arg
        if name and (name in {"as_of", "observed_at"} or "read_at" in name):
            found.setdefault(function or "<module>", []).append(f"{type(node).__name__}:{name}")
        for child in ast.iter_child_nodes(node):
            walk(child, function)

    walk(tree, "")
    return {key: sorted(value) for key, value in found.items()}


def test_reviewed_uses() -> None:
    shared = json.loads((ROOT / "tests/read-time-uses.json").read_text())
    for declaration in sorted(PACKAGES.glob("*/read-time.json")):
        data = json.loads(declaration.read_text())
        assert data["settles"] == "never" or _valid_declaration(data)
        shared.extend(data["uses"])
    expected = {}
    for entry in shared:
        assert entry["kind"] in KINDS
        assert entry["offset"]
        key = (entry["file"], entry["function"])
        assert key not in expected
        expected[key] = entry["uses"]
    actual = {}
    files = [*(ROOT / "src").rglob("*.py")]
    for path in files:
        actual.update({(str(path.relative_to(ROOT)), fn): uses for fn, uses in scan(path).items()})
    assert actual == expected


def test_no_ambient_clocks() -> None:
    for path in (ROOT / "src").rglob("*.py"):
        if "watch" in path.parts:
            continue
        tree = ast.parse(path.read_text())
        aliases = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                aliases.update({a.asname or a.name: a.name for a in node.names})
            elif isinstance(node, ast.ImportFrom):
                aliases.update({a.asname or a.name: f"{node.module}.{a.name}" for a in node.names})
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            called = ast.unparse(node.func)
            head, *tail = called.split(".")
            called = ".".join([aliases.get(head, head), *tail])
            assert called not in {
                "datetime.datetime.now",
                "datetime.datetime.utcnow",
                "datetime.date.today",
                "datetime.datetime.today",
                "time.time",
                "time.time_ns",
            }, (path, node.lineno, called)


def timestamps(value: Any) -> Iterator[datetime]:
    if isinstance(value, dict):
        for child in value.values():
            yield from timestamps(child)
    elif isinstance(value, list):
        for child in value:
            yield from timestamps(child)
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return
        # A date/naive timestamp can end almost 24h later in a negative UTC offset.
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC) + timedelta(days=2)
        yield parsed.astimezone(UTC)


def swapped(value: Any, old: str, new: str) -> Any:
    result = deepcopy(value)

    def visit(node: Any, parts: Sequence[str]) -> None:
        if not parts or not isinstance(node, dict | list):
            return
        keys = list(node) if isinstance(node, dict) else list(range(len(node)))
        for key in keys:
            if parts[0] != "*" and key != parts[0]:
                continue
            if len(parts) == 1:
                if node[key] == old:
                    node[key] = new
            else:
                visit(node[key], parts[1:])

    for path in READ_TIME_PATHS:
        visit(result, path.split("."))
    return result


@pytest.mark.parametrize("fixture", FIXTURES, ids=lambda p: str(p.relative_to(ROOT / "providers")))
@pytest.mark.parametrize(
    "variant", ["original", "no-records", "no-end", "fraction-offset", "date-only", "per-kind"]
)
def test_settled_samples(fixture: Path, variant: str) -> None:
    evidence = json.loads(fixture.read_text())
    if variant == "no-records":
        evidence["provider_records"] = []
        evidence.pop("provider_reports", None)
    elif variant == "no-end":
        evidence["provider_times"] = [
            item for item in evidence["provider_times"] if item["kind"] not in {"ended", "stopped"}
        ]
    elif variant in {"fraction-offset", "date-only"}:
        # Uninterpreted record body input still participates in the latest-input bound.
        evidence["provider_records"].append(
            {
                "source": "contract.sample",
                "read_at": "2027-01-01T00:00:00Z",
                "body": {
                    "time": "2027-01-01"
                    if variant == "date-only"
                    else "2027-01-01T23:59:59.999999-23:59"
                },
            }
        )
    if variant == "per-kind":
        records = evidence["provider_records"]
        reports = {
            record["source"][5:]: record["body"]
            for record in records
            if record["source"] in {"core.cost", "core.size", "core.usage"}
        }
        times = {
            record["source"][5:]: record["read_at"]
            for record in records
            if record["source"] in {"core.cost", "core.size", "core.usage"}
        }
        for kind in ("cost", "size", "usage"):
            if kind not in reports:
                reports[kind] = {"status": "unavailable"}
                times[kind] = "2027-01-01T00:00:00Z"
        evidence["provider_records"] = [
            record for record in records if not record["source"].startswith("core.")
        ]
        evidence["provider_reports"] = {**reports, "read_times": times}
    bound = settles_after(evidence["provider"])
    if bound is None:
        pytest.skip("Provider does not promise settlement.")
    latest = max(timestamps(evidence), default=datetime(2027, 1, 1, tzinfo=UTC))
    settled = latest + timedelta(seconds=bound)
    reads = [settled + timedelta(seconds=n) for n in (0, 1, 86400, 30 * 86400)]
    reads.append(datetime(9000, 1, 1, tzinfo=UTC))
    first = reads[0].isoformat()
    baseline = price(evidence, as_of=first)
    # Just-before-bound is sampled, but deliberately has no equality requirement.
    price(evidence, as_of=(settled - timedelta(microseconds=1)).isoformat())
    for at in reads[1:]:
        stamp = at.isoformat()
        assert swapped(baseline, first, stamp) == price(evidence, as_of=stamp)


def test_unknown_and_malformed(mocker: Any, tmp_path: Path) -> None:
    mocker.patch("sandbox_provider_pricing.read_time.providers_root", return_value=tmp_path)
    assert settles_after("unknown") is None
    assert settles_after("../modal") is None
    folder = tmp_path / "custom"
    folder.mkdir()
    declaration = folder / "read-time.json"
    for data in [
        "{",
        "null",
        "{}",
        '{"contract":1,"settles":"never","uses":[]}',
        '{"contract":true,"settles":"bounded","uses":[]}',
        '{"contract":1,"settles":"bounded","uses":[{}]}',
    ]:
        declaration.write_text(data)
        assert settles_after("custom") is None


def test_bounds() -> None:
    assert READ_TIME_CONTRACT == 1
    for provider in provider_ids():
        policy = revisit(provider)
        assert (
            settles_after(provider) == policy.after_s + policy.until_s + policy.interval_s + 259202
        )


@pytest.mark.parametrize("provider", provider_ids())
def test_revisit_and_finality_boundaries(provider: str) -> None:
    evidence = json.loads(
        (ROOT / "providers" / provider / "fixtures/best/evidence.json").read_text()
    )
    ended = max(timestamps(evidence))
    policy = revisit(provider)
    until = ended + timedelta(seconds=policy.until_s)
    before = price(evidence, ended_at=ended, as_of=(until - timedelta(microseconds=1)).isoformat())
    exact = price(evidence, ended_at=ended, as_of=until.isoformat())
    after = price(evidence, ended_at=ended, as_of=(until + timedelta(microseconds=1)).isoformat())
    assert before["final"] is False
    assert before["revisit"] is not None
    assert exact["final"] is True
    assert exact["revisit"] is None
    assert after["final"] is True
    assert after["revisit"] is None
    for seconds in (policy.after_s - 1, policy.after_s, policy.after_s + policy.interval_s):
        read = ended + timedelta(seconds=seconds)
        result = price(evidence, ended_at=ended, as_of=read.isoformat())
        assert result["final"] is False
        assert result["revisit"] is not None


def test_custom_provider_opt_in(mocker: Any, tmp_path: Path) -> None:
    mocker.patch("sandbox_provider_pricing.read_time.providers_root", return_value=tmp_path)
    folder = tmp_path / "new-provider"
    folder.mkdir()
    (folder / "rules.py").write_text("# New rules do not opt in implicitly.\n")
    mocker.patch("sandbox_provider_pricing.read_time.revisit", return_value=RevisitPolicy(5, 10, 2))
    assert settles_after("new-provider") is None
    declaration = folder / "read-time.json"
    data: dict[str, Any] = {"contract": 1, "settles": "bounded", "uses": []}
    declaration.write_text(json.dumps(data))
    assert settles_after("new-provider") == 259219
    data["contract"] = 2
    declaration.write_text(json.dumps(data))
    assert settles_after("new-provider") is None
    data["contract"] = 1
    data["settles"] = "never"
    declaration.write_text(json.dumps(data))
    assert settles_after("new-provider") is None


def test_broken_provider_billing_declines(mocker: Any, tmp_path: Path) -> None:
    mocker.patch("sandbox_provider_pricing.read_time.providers_root", return_value=tmp_path)
    folder = tmp_path / "new-provider"
    folder.mkdir()
    (folder / "read-time.json").write_text(
        json.dumps({"contract": 1, "settles": "bounded", "uses": []})
    )
    mocker.patch("sandbox_provider_pricing.read_time.revisit", side_effect=ValueError("bad policy"))
    assert settles_after("new-provider") is None
