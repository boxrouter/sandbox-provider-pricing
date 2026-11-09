# SPDX-FileCopyrightText: BoxRouter, Inc.
# SPDX-License-Identifier: Apache-2.0
"""`spp check-imports` names every use of a package name its public API does not promise."""

from __future__ import annotations

from pathlib import Path

import pytest

import sandbox_provider_pricing
from sandbox_provider_pricing.check_imports import private_imports
from sandbox_provider_pricing.watch.cli import main

ROOT = Path(__file__).resolve().parents[1]


def _write(directory: Path, name: str, text: str) -> Path:
    path = directory / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


def test_public_names_are_not_listed(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "ok.py",
        "import sandbox_provider_pricing as pricing\n"
        "from sandbox_provider_pricing import price, record_evidence, next_read, find_class\n"
        "from sandbox_provider_pricing import latest_version as latest\n"
        "pricing.price({}); pricing.ReservationQuote; pricing.merge_reports([])\n",
    )
    assert private_imports(tmp_path) == []


def test_every_kind_of_private_use_is_listed_with_its_line(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        "pkg/bad.py",
        "import sandbox_provider_pricing as pricing\n"  # 1: fine
        "import sandbox_provider_pricing.versions\n"  # 2
        "from sandbox_provider_pricing import versions, price\n"  # 3
        "from sandbox_provider_pricing.calculator.documents import covered_classes\n"  # 4
        "from sandbox_provider_pricing.watch.check import PageText as Page\n"  # 5
        "pricing.versions.seed_versions()\n"  # 6
        "sandbox_provider_pricing.calculator.cost\n"  # 7
        "pricing.price\n",  # 8: fine
    )
    found = [(item.path, item.line, item.name) for item in private_imports(tmp_path)]
    assert sorted(found, key=lambda item: item[1]) == [
        (path, 2, "sandbox_provider_pricing.versions"),
        (path, 3, "sandbox_provider_pricing.versions"),
        (path, 4, "sandbox_provider_pricing.calculator.documents.covered_classes"),
        (path, 5, "sandbox_provider_pricing.watch.check.PageText"),
        (path, 6, "sandbox_provider_pricing.versions"),
        (path, 7, "sandbox_provider_pricing.calculator"),
    ]


def test_names_in_a_public_submodules_all_are_not_listed(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        "mod.py",
        "from sandbox_provider_pricing.watch import check_version, draft_version\n"  # 1: fine
        "from sandbox_provider_pricing.conformance import load_cases, run_cases\n"  # 2: fine
        "from sandbox_provider_pricing.testing import use_providers\n"  # 3: fine
        "from sandbox_provider_pricing.conformance import _fixture\n"  # 4
        "from sandbox_provider_pricing.watch import cli\n"  # 5
        "from sandbox_provider_pricing.usage import observation\n",  # 6
    )
    found = [(item.line, item.name) for item in private_imports(path)]
    assert found == [
        (4, "sandbox_provider_pricing.conformance._fixture"),
        (5, "sandbox_provider_pricing.watch.cli"),
        (6, "sandbox_provider_pricing.usage.observation"),
    ]


def test_a_file_can_be_named_and_vendored_or_cache_folders_are_skipped(tmp_path: Path) -> None:
    bad = "from sandbox_provider_pricing import versions\n"
    one = _write(tmp_path, "one.py", bad)
    _write(tmp_path, ".venv/lib/two.py", bad)
    _write(tmp_path, "node_modules/three.py", bad)
    assert [item.path for item in private_imports(one)] == [one]
    assert [item.path for item in private_imports(tmp_path)] == [one]


def test_the_package_s_own_modules_are_not_checked(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "src/sandbox_provider_pricing/inner.py",
        "from sandbox_provider_pricing.usage import x\n",
    )
    assert private_imports(tmp_path) == []
    assert private_imports(ROOT / "src") == []


def test_the_command_prints_each_use_and_exits_one(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = _write(tmp_path, "bad.py", "from sandbox_provider_pricing import versions\n")
    assert main(["check-imports", str(tmp_path)]) == 1
    assert capsys.readouterr().out == f"{path}:1: sandbox_provider_pricing.versions\n"


def test_the_command_prints_nothing_and_exits_zero_when_clean(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _write(tmp_path, "ok.py", "from sandbox_provider_pricing import price\n")
    assert main(["check-imports", str(tmp_path)]) == 0
    assert capsys.readouterr().out == ""


def test_the_command_rejects_a_path_that_does_not_exist(tmp_path: Path) -> None:
    with pytest.raises(SystemExit):
        main(["check-imports", str(tmp_path / "missing")])


def test_what_cloud_and_the_runner_took_from_inside_the_package_is_public_now() -> None:
    for name in ("find_class", "covered_classes", "latest_version", "price_version"):
        assert name in sandbox_provider_pricing.__all__
