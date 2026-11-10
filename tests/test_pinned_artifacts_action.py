# SPDX-FileCopyrightText: BoxRouter, Inc.
# SPDX-License-Identifier: Apache-2.0
"""CI verifies the committed pinned artifacts locally, with no credential or fetch."""

import hashlib
import os
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml  # type: ignore[import-untyped]

ROOT = Path(__file__).resolve().parents[1]
ACTION = ROOT / ".github/actions/pinned-artifacts/action.yml"

pytestmark = [
    pytest.mark.unit,
    pytest.mark.skipif(
        not ACTION.exists(),
        reason="the private pinned-artifacts action is not in the public snapshot",
    ),
]
WORKFLOWS = ("checks.yml", "price-watch.yml", "public-text-check.yml", "release.yml")
WHEEL = b"pinned wheel bytes"
TREE = "592c7cf3a5a4d17b07632de29add90f9b727ef79"


def _action() -> dict[str, Any]:
    action: dict[str, Any] = yaml.safe_load(ACTION.read_text())
    return action


def _script() -> str:
    (step,) = _action()["runs"]["steps"]
    script: str = step["run"]
    return script


def _run(
    tmp_path: Path, pins: str, wheel: bytes = WHEEL, asset: str = "v.whl"
) -> subprocess.CompletedProcess[str]:
    """Run the verify step offline in a checkout-shaped temporary directory."""
    (tmp_path / "wheels").mkdir(exist_ok=True)
    (tmp_path / "wheels" / asset).write_bytes(wheel)
    (tmp_path / "artifacts.lock").write_text(pins)
    return subprocess.run(
        ["bash", "-c", _script()],
        cwd=tmp_path,
        env={**os.environ},
        text=True,
        capture_output=True,
        check=False,
    )


def _pins(
    sha256: str,
    repo: str = "boxrouter/sandbox-provider-benchmarks",
    tree: str = TREE,
    asset: str = "v.whl",
    extra: str = "",
) -> str:
    row = f"{repo} {tree} {asset} {sha256}{extra}"
    return f"# owner/repo tree asset sha256\n{row}\n"


def test_the_action_verifies_committed_artifacts_with_no_token_or_fetch() -> None:
    action = _action()
    assert not action.get("inputs")
    (step,) = action["runs"]["steps"]
    assert set(step) <= {"name", "shell", "run"}
    text = ACTION.read_text()
    for forbidden in ("create-github-app-token", "private_key", "GH_TOKEN", "gh "):
        assert forbidden not in text


def test_the_real_lock_and_committed_wheels_verify(tmp_path: Path) -> None:
    (tmp_path / "wheels").mkdir()
    for wheel in (ROOT / "wheels").iterdir():
        (tmp_path / "wheels" / wheel.name).write_bytes(wheel.read_bytes())
    (tmp_path / "artifacts.lock").write_text((ROOT / "artifacts.lock").read_text())
    result = subprocess.run(
        ["bash", "-c", _script()],
        cwd=tmp_path,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "matches artifacts.lock" in result.stdout


def test_a_committed_wheel_matching_the_lock_passes(tmp_path: Path) -> None:
    result = _run(tmp_path, _pins(hashlib.sha256(WHEEL).hexdigest()))
    assert result.returncode == 0, result.stderr
    assert "matches artifacts.lock" in result.stdout


def test_a_committed_wheel_that_misses_the_lock_fails(tmp_path: Path) -> None:
    result = _run(tmp_path, _pins("0" * 64))
    assert result.returncode != 0
    assert "does not match pinned" in result.stderr


def test_a_lock_without_rows_fails(tmp_path: Path) -> None:
    result = _run(tmp_path, "# owner/repo tree asset sha256\n")
    assert result.returncode != 0
    assert "no pinned artifacts" in result.stderr


def test_a_pin_outside_the_organization_is_refused(tmp_path: Path) -> None:
    result = _run(tmp_path, _pins(hashlib.sha256(WHEEL).hexdigest(), repo="someone/else"))
    assert result.returncode != 0
    assert "Unexpected pinned repository" in result.stderr


@pytest.mark.parametrize("tree", ["not-a-sha", "0" * 64, "0" * 39])
def test_a_malformed_tree_field_fails(tmp_path: Path, tree: str) -> None:
    result = _run(tmp_path, _pins(hashlib.sha256(WHEEL).hexdigest(), tree=tree))
    assert result.returncode != 0
    assert "tree field" in result.stderr


@pytest.mark.parametrize("asset", ["../v.whl", "dir/v.whl", "v.tar.gz", ".whl"])
def test_a_malformed_asset_field_fails(tmp_path: Path, asset: str) -> None:
    result = _run(tmp_path, _pins(hashlib.sha256(WHEEL).hexdigest(), asset=asset))
    assert result.returncode != 0
    assert "Unexpected pinned asset name" in result.stderr


@pytest.mark.parametrize("sha256", ["not-a-sha", "0" * 40, "A" * 64])
def test_a_malformed_sha256_field_fails(tmp_path: Path, sha256: str) -> None:
    result = _run(tmp_path, _pins(sha256))
    assert result.returncode != 0
    assert "sha256 field" in result.stderr


def test_a_lock_row_with_extra_fields_fails(tmp_path: Path) -> None:
    pins = _pins(hashlib.sha256(WHEEL).hexdigest(), extra=" repack=" + "0" * 64)
    result = _run(tmp_path, pins)
    assert result.returncode != 0
    assert "extra fields" in result.stderr


@pytest.mark.parametrize("workflow", WORKFLOWS)
def test_no_workflow_passes_a_token_or_inputs_for_pins(workflow: str) -> None:
    jobs = yaml.safe_load((ROOT / ".github/workflows" / workflow).read_text())["jobs"]
    uses = [
        step
        for job in jobs.values()
        for step in job.get("steps", [])
        if step.get("uses") == "./.github/actions/pinned-artifacts"
    ]
    assert len(uses) == 1
    assert not uses[0].get("with")
