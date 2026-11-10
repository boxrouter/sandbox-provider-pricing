# SPDX-FileCopyrightText: BoxRouter, Inc.
# SPDX-License-Identifier: Apache-2.0
"""Guards a pull request would otherwise need: released prices stay put, new versions chain on."""

import subprocess
from copy import deepcopy
from importlib import util
from pathlib import Path
from typing import Any

import pytest
import yaml  # type: ignore[import-untyped]

from sandbox_provider_pricing.versions import _version_order

_spec = util.spec_from_file_location(
    "release_digests", Path(__file__).resolve().parents[1] / "scripts" / "release_digests.py"
)
assert _spec is not None and _spec.loader is not None
release_digests = util.module_from_spec(_spec)
_spec.loader.exec_module(release_digests)

ROOT = release_digests.ROOT
SCHEMA_HEADER = (
    "# yaml-language-server: $schema="
    "../../../../../schemas/price-version.schema.json"  # sibling-paths: allow
)
RELEASED = release_digests.listed()


def version_problems(versions: list[dict[str, Any]], released: set[str]) -> list[str]:
    """Why a provider's price versions cannot be published, one message each.

    `versions` are one provider's documents; `released` holds the ids of those already shipped.
    A released version is only checked for a consistent id. A new one must also name versions that
    exist and start after the version it replaces.
    """
    problems: list[str] = []
    ids = {version["version"] for version in versions}
    ordered = sorted(versions, key=_version_order)
    for index, version in enumerate(ordered):
        name = version["version"]
        if name in released:
            continue
        for later in ordered[index + 1 :]:
            if later["version"] in released:
                problems.append(f"{name} starts before the released {later['version']}")
        supersedes = version.get("supersedes", [])
        problems += [
            f"{name} supersedes {other}, which does not exist"
            for other in supersedes
            if other not in ids
        ]
        if name in supersedes:
            problems.append(f"{name} supersedes itself")
        if index == 0:
            continue
        previous = ordered[index - 1]
        if _version_order(previous) == _version_order(version):
            problems.append(
                f"{name} has the same effective_from and retrieved_at as {previous['version']}"
            )
        if previous["version"] not in supersedes:
            problems.append(
                f"{name} does not supersede {previous['version']}, the version before it"
            )
    return problems


def _documents() -> dict[Path, dict[str, Any]]:
    return {
        path: yaml.safe_load((ROOT / path).read_text(encoding="utf-8"))
        for path in release_digests.price_files()
    }


def test_released_price_files_are_unchanged() -> None:
    problems = []
    for path, sha in RELEASED.items():
        if not (ROOT / path).is_file():
            problems.append(f"{path} was released and is now missing")
        elif release_digests.digest(Path(path)) != sha:
            problems.append(f"{path} was released and has changed")
    assert not problems, (
        "A released price version never changes. Restore the file and add a new version that "
        "supersedes it instead:\n" + "\n".join(problems)
    )


def test_every_release_lists_its_price_files() -> None:
    tags = subprocess.run(
        ["git", "tag", "--list", "v*", "--sort=-v:refname"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    ).stdout.split()
    if not tags:
        pytest.skip("no release tags in this checkout")
    shipped = subprocess.run(
        ["git", "ls-tree", "-r", "--name-only", tags[0], "--", "providers", "src"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    ).stdout.split()
    # Releases before the provider packages moved name their price files under `providers/`.
    shipped = [
        path if path.startswith("src/") else f"src/sandbox_provider_pricing/{path}"
        for path in shipped
    ]
    missing = [
        path
        for path in shipped
        if "/prices/" in path and path.endswith(".yaml") and path not in RELEASED
    ]
    assert not missing, (
        f"{tags[0]} shipped price files that tests/released-digests.txt does not list. "
        f"Run `make release-digests` and commit it:\n" + "\n".join(missing)
    )


def test_price_versions_are_named_after_their_files() -> None:
    for path, document in _documents().items():
        assert document["provider"] == path.parts[3], path
        assert document["version"] == f"{path.parts[3]}@{path.stem}", path


def test_new_price_versions_chain_onto_the_previous_one() -> None:
    released = {
        document["version"]
        for path, document in _documents().items()
        if path.as_posix() in RELEASED
    }
    by_provider: dict[str, list[dict[str, Any]]] = {}
    for document in _documents().values():
        by_provider.setdefault(document["provider"], []).append(document)
    for provider, versions in by_provider.items():
        assert version_problems(versions, released) == [], provider


def test_new_price_files_carry_the_editor_schema_header() -> None:
    missing = [
        path.as_posix()
        for path in release_digests.price_files()
        if path.as_posix() not in RELEASED
        and not (ROOT / path).read_text(encoding="utf-8").startswith(SCHEMA_HEADER)
    ]
    assert not missing, f"Start these files with `{SCHEMA_HEADER}`: {missing}"


def test_every_billing_record_carries_the_editor_schema_header() -> None:
    header = (
        "# yaml-language-server: $schema="
        "../../../../schemas/billing.schema.json"  # sibling-paths: allow
    )
    for path in sorted((ROOT / "src/sandbox_provider_pricing/providers").glob("*/billing.yaml")):
        assert path.read_text(encoding="utf-8").startswith(header), path


def _version(name: str, effective: str, retrieved: str, supersedes: list[str]) -> dict[str, Any]:
    return {
        "provider": "p",
        "version": f"p@{name}",
        "effective_from": effective,
        "retrieved_at": retrieved,
        "supersedes": [f"p@{item}" for item in supersedes],
    }


CHAIN = [
    _version("a", "2026-01-01T00:00:00Z", "2026-01-02T00:00:00Z", []),
    _version("b", "2026-01-01T00:00:00Z", "2026-01-03T00:00:00Z", ["a"]),
]


def test_a_new_version_that_chains_on_passes() -> None:
    new = _version("c", "2026-02-01T00:00:00Z", "2026-02-02T00:00:00Z", ["b", "a"])
    assert version_problems([*CHAIN, new], {"p@a", "p@b"}) == []


@pytest.mark.parametrize(
    ("new", "expected"),
    [
        (
            _version("c", "2026-02-01T00:00:00Z", "2026-02-02T00:00:00Z", []),
            "does not supersede p@b",
        ),
        (
            _version("c", "2026-02-01T00:00:00Z", "2026-02-02T00:00:00Z", ["b", "zz"]),
            "supersedes p@zz, which does not exist",
        ),
        (
            _version("c", "2026-02-01T00:00:00Z", "2026-02-02T00:00:00Z", ["b", "c"]),
            "supersedes itself",
        ),
        (
            _version("c", "2026-01-01T00:00:00Z", "2026-01-03T00:00:00Z", ["b"]),
            "has the same effective_from and retrieved_at as p@b",
        ),
        (
            _version("c", "2025-12-01T00:00:00Z", "2026-02-02T00:00:00Z", ["b"]),
            "starts before the released p@a",
        ),
    ],
)
def test_a_new_version_that_breaks_the_chain_is_named(new: dict[str, Any], expected: str) -> None:
    problems = version_problems([*deepcopy(CHAIN), new], {"p@a", "p@b"})
    assert any(expected in problem for problem in problems), problems


def test_no_spec_class_is_covered_by_two_classes_of_one_version() -> None:
    for path, document in _documents().items():
        covered = [
            name
            for price_class in document["classes"]
            for name in price_class.get("covers") or [price_class["name"]]
        ]
        assert len(covered) == len(set(covered)), path
