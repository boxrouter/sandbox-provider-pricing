# SPDX-FileCopyrightText: BoxRouter, Inc.
# SPDX-License-Identifier: Apache-2.0
"""The exported source builds with no private release artifact.

`uv sync --locked` and `make check` must work where no BoxRouter App token, no
private `boxrouter` repository and no fetched `.artifacts` directory exists:
every locked package resolves from a public index or a wheel committed beside
the lock.
"""

import hashlib
import re
import subprocess
import tomllib
from pathlib import Path
from zipfile import ZipFile

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
PINS = ROOT / "artifacts.lock"
PYPROJECT = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
LOCK = tomllib.loads((ROOT / "uv.lock").read_text(encoding="utf-8"))
PUBLIC_INDEX = "https://pypi.org/simple"
VERIFIER_REPOSITORY = "boxrouter/sandbox-provider-benchmarks"
LOCK_ROW = re.compile(
    r"^(?P<repo>boxrouter/[A-Za-z0-9._-]+) "
    r"(?P<tree>[0-9a-f]{40}) "
    r"(?P<asset>[A-Za-z0-9][A-Za-z0-9._+-]*\.whl) "
    r"(?P<sha256>[0-9a-f]{64})$"
)


def _tracked() -> list[str]:
    result = subprocess.run(
        ["git", "ls-files"], cwd=ROOT, check=True, capture_output=True, text=True
    )
    return result.stdout.splitlines()


def _pins() -> list[list[str]]:
    return [
        line.split()
        for line in PINS.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    ]


def _verifier_wheel() -> Path:
    package = next(item for item in LOCK["package"] if item["name"] == "sandbox-benchmark-verifier")
    (wheel,) = package["wheels"]
    return ROOT / str(package["source"]["registry"]) / str(wheel["path"])


def test_find_links_names_only_tracked_source_directories() -> None:
    find_links = PYPROJECT["tool"]["uv"].get("find-links", [])
    assert ".artifacts" not in find_links
    tracked = _tracked()
    for entry in find_links:
        directory = entry.rstrip("/")
        assert (ROOT / directory).is_dir(), entry
        assert any(name.startswith(f"{directory}/") for name in tracked), entry


def test_locked_packages_come_from_public_or_committed_sources() -> None:
    for package in LOCK["package"]:
        source = package["source"]
        if "registry" in source:
            assert source["registry"] in {PUBLIC_INDEX, "wheels"}, (package["name"], source)
        else:
            assert source == {"editable": "."}, (package["name"], source)
    text = (ROOT / "uv.lock").read_text(encoding="utf-8")
    assert ".artifacts" not in text
    assert "boxrouter/" not in text


def test_the_locked_verifier_wheel_is_committed() -> None:
    path = _verifier_wheel()
    assert path.is_file()
    assert str(path.relative_to(ROOT)) in _tracked()


@pytest.mark.skipif(
    not PINS.is_file(), reason="the release-pin registry is not in the public snapshot"
)
def test_artifacts_lock_rows_are_exact_provenance_fields() -> None:
    """Every lock row is `<repo> <release source tree SHA> <wheel> <sha256>`."""
    assert _pins()
    for row in _pins():
        assert LOCK_ROW.fullmatch(" ".join(row)), row


@pytest.mark.skipif(
    not PINS.is_file(), reason="the release-pin registry is not in the public snapshot"
)
def test_the_committed_verifier_wheel_matches_its_lock_pin() -> None:
    path = _verifier_wheel()
    (pin,) = [line for line in _pins() if line[2] == path.name]
    assert hashlib.sha256(path.read_bytes()).hexdigest() == pin[3]


@pytest.mark.skipif(
    not PINS.is_file(), reason="the release-pin registry is not in the public snapshot"
)
def test_artifacts_lock_pins_only_the_public_verifier_repository() -> None:
    assert all(line[0] == VERIFIER_REPOSITORY for line in _pins())


def test_the_committed_verifier_wheel_has_a_valid_record() -> None:
    """The committed release wheel is a readable archive with a complete RECORD."""
    path = _verifier_wheel()
    with ZipFile(path) as archive:
        assert archive.testzip() is None
        names = archive.namelist()
        record = next(name for name in names if name.endswith(".dist-info/RECORD"))
        recorded = {
            line.rsplit(",", 2)[0]
            for line in archive.read(record).decode().splitlines()
            if line.strip()
        }
        assert recorded | {record} == set(names)


def test_make_check_fetches_no_pinned_artifact() -> None:
    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
    assert ".artifacts" not in makefile
    assert "pinned-artifacts" not in makefile
    assert "gh pins" not in makefile


def test_no_workflow_fetches_a_pinned_release() -> None:
    # release.yml downloads this repository's own release SHA256SUMS; nothing
    # else may fetch a release asset (the pinned artifacts are committed).
    for path in (ROOT / ".github").rglob("*.yml"):
        if path.name == "release.yml":
            continue
        assert "gh release download" not in path.read_text(encoding="utf-8"), path


def test_no_repack_machinery_remains() -> None:
    assert not (ROOT / "scripts/repack_verifier_wheel.py").exists()
    scanned = list((ROOT / "scripts").glob("*.py")) + list((ROOT / ".github").rglob("*.yml"))
    mentions = [
        str(path.relative_to(ROOT))
        for path in scanned
        if "repack" in path.read_text(encoding="utf-8")
    ]
    assert not mentions
    assert "repack" not in PINS.read_text(encoding="utf-8")
