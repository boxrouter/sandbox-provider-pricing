# SPDX-FileCopyrightText: BoxRouter, Inc.
# SPDX-License-Identifier: Apache-2.0
"""The wheel carries the schemas and every price version, and `seed_versions()` reads them."""

import json
import re
import subprocess
import sys
import zipfile
from collections.abc import Iterator
from pathlib import Path

import pytest

from sandbox_provider_pricing import seed_versions

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
PACKAGES = ROOT / "src" / "sandbox_provider_pricing" / "providers"
PRICE_FILES = sorted(PACKAGES.glob("*/prices/*.yaml"))


@pytest.fixture(scope="module")
def wheel(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Path]:
    out_dir = tmp_path_factory.mktemp("wheel")
    uv = Path(sys.executable).parent / "uv"
    subprocess.run(
        [str(uv), "build", "--wheel", "--out-dir", str(out_dir)],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    (built,) = out_dir.glob("*.whl")
    yield built


def test_wheel_holds_every_price_file(wheel: Path) -> None:
    with zipfile.ZipFile(wheel) as archive:
        packed = sorted(
            name
            for name in archive.namelist()
            if name.startswith("sandbox_provider_pricing/providers/")
            and "/prices/" in name
            and name.endswith(".yaml")
        )
    assert PRICE_FILES
    assert packed == [str(path.relative_to(ROOT / "src")) for path in PRICE_FILES]
    with zipfile.ZipFile(wheel) as archive:
        packed_rules = sorted(
            name
            for name in archive.namelist()
            if name.startswith("sandbox_provider_pricing/providers/") and name.endswith("/rules.py")
        )
    assert packed_rules == [
        str(path.relative_to(ROOT / "src")) for path in sorted(PACKAGES.glob("*/rules.py"))
    ]


def test_wheel_holds_what_the_cost_method_reads(wheel: Path) -> None:
    with zipfile.ZipFile(wheel) as archive:
        names = set(archive.namelist())
    assert {
        "sandbox_provider_pricing/METHOD.md",
        "sandbox_provider_pricing/schemas/cost-method.schema.json",
    } <= names


# The package's only name is sandbox-provider-pricing; the old name has no alias anywhere.
OLD_NAME = re.compile(rb"(?<![A-Za-z0-9_/.-])provider[-_]pricing")


def test_every_schema_is_identified_by_the_package_name() -> None:
    schemas = sorted((ROOT / "schemas").glob("*.schema.json"))
    assert schemas
    for schema in schemas:
        identifier = json.loads(schema.read_text())["$id"]
        assert identifier == f"urn:boxrouter:sandbox-provider-pricing:{schema.name.split('.')[0]}"


def test_the_wheel_never_names_the_package_by_its_old_name(wheel: Path) -> None:
    with zipfile.ZipFile(wheel) as archive:
        named = [name for name in archive.namelist() if OLD_NAME.search(archive.read(name))]
        assert not [name for name in archive.namelist() if OLD_NAME.search(name.encode())]
    assert named == []


def test_seed_versions_returns_one_entry_per_file() -> None:
    versions = seed_versions()
    assert len(versions) == len(PRICE_FILES)
    assert [(item["provider"], item["version"]) for item in versions] == [
        (path.parent.parent.name, f"{path.parent.parent.name}@{path.stem}") for path in PRICE_FILES
    ]


def test_seed_versions_from_the_unpacked_wheel(wheel: Path, tmp_path: Path) -> None:
    with zipfile.ZipFile(wheel) as archive:
        assert "sandbox_provider_pricing/class-registry.json" not in archive.namelist()
        archive.extractall(tmp_path)
    script = (
        "import sandbox_provider_pricing as p; from sandbox_provider_pricing.providers import "
        "billing, rules; print(p.__file__); print(len(p.seed_versions())); "
        "print(billing('vercel')['rules_version']); print(rules('e2b').__file__); "
        "p.build_price_sheet()"
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=tmp_path,
        env={"PYTHONPATH": str(tmp_path)},
        check=True,
        capture_output=True,
        text=True,
    )
    location, count, rules_version, rules_file = result.stdout.split()
    assert Path(location).is_relative_to(tmp_path)
    assert int(count) == len(PRICE_FILES)
    assert rules_version == "2"
    assert Path(rules_file).is_relative_to(tmp_path / "sandbox_provider_pricing" / "providers")
