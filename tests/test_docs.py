# SPDX-FileCopyrightText: BoxRouter, Inc.
# SPDX-License-Identifier: Apache-2.0
"""Generated documentation stays in sync with billing records."""

import subprocess
from importlib import util
from pathlib import Path

import pytest
import yaml  # type: ignore[import-untyped]

_spec = util.spec_from_file_location(
    "pricing_docs", Path(__file__).resolve().parents[1] / "scripts" / "docs.py"
)
assert _spec is not None and _spec.loader is not None
docs = util.module_from_spec(_spec)
_spec.loader.exec_module(docs)


def _block(text: str, start: str, end: str) -> str:
    return text.split(start, 1)[1].split(end, 1)[0].strip()


def test_provider_pages_match_billing_records() -> None:
    for provider, document in docs.load_documents():
        page = (docs.ROOT / "providers" / provider / "README.md").read_text(encoding="utf-8")
        assert page == docs.render_provider_page(provider, document)


def test_root_readme_status_table_matches_billing_records() -> None:
    readme = (docs.ROOT / "README.md").read_text(encoding="utf-8")
    assert _block(readme, docs.STATUS_START, docs.STATUS_END) == docs.render_status_table(
        docs.load_documents()
    )


def test_comparing_hourly_table_matches_price_versions() -> None:
    comparing = (docs.ROOT / "COMPARING.md").read_text(encoding="utf-8")
    assert _block(comparing, docs.HOURLY_START, docs.HOURLY_END) == docs.render_hourly_table(
        docs.load_documents()
    )


@pytest.mark.skipif(
    not (docs.ROOT / ".github/actions/public-guardrails/action.yml").is_file(),
    reason="the private guardrails action is not in the public snapshot",
)
def test_public_document_boundary_uses_shared_checker_on_current_tracked_docs(
    tmp_path: Path,
) -> None:
    action = yaml.safe_load(
        (docs.ROOT / ".github/actions/public-guardrails/action.yml").read_text()
    )
    source = next(
        step["with"]
        for step in action["runs"]["steps"]
        if step.get("uses", "").startswith("actions/checkout@")
    )
    assert "src/sandbox_benchmark_verifier/public_provenance.py" in source["sparse-checkout"]
    assert source["sparse-checkout-cone-mode"] is False
    step = next(
        step
        for step in action["runs"]["steps"]
        if step.get("name") == "Check current public document provenance"
    )
    shared = tmp_path / ".public-guardrails/src/sandbox_benchmark_verifier/public_provenance.py"
    shared.parent.mkdir(parents=True)
    shared.write_text(
        "def closed_revision_errors(text):\n"
        "    return ['closed revision'] if 'closed-version' in text else []\n"
    )
    subprocess.run(["git", "init", "--quiet"], cwd=tmp_path, check=True)
    page = tmp_path / "METHOD.md"
    page.write_text("closed-version\n")
    subprocess.run(["git", "add", "METHOD.md"], cwd=tmp_path, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Example",
            "-c",
            "user.email=example@example.invalid",
            "commit",
            "--quiet",
            "-m",
            "initial",
        ],
        cwd=tmp_path,
        check=True,
    )
    before = subprocess.run(
        ["bash", "-c", step["run"]], cwd=tmp_path, capture_output=True, text=True
    )
    assert before.returncode == 1
    assert before.stderr.strip() == "METHOD.md: closed revision"

    page.write_text("Public pricing and source versions remain.\n")
    (tmp_path / "untracked.md").write_text("closed-version\n")
    (tmp_path / "private.json").write_text('"closed-version"\n')
    subprocess.run(["git", "add", "private.json"], cwd=tmp_path, check=True)
    after = subprocess.run(
        ["bash", "-c", step["run"]], cwd=tmp_path, capture_output=True, text=True
    )
    assert after.returncode == 0, after.stderr
