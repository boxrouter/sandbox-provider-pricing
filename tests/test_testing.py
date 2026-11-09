# SPDX-FileCopyrightText: BoxRouter, Inc.
# SPDX-License-Identifier: Apache-2.0
"""`sandbox_provider_pricing.testing`: price from another provider folder, then come back."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from sandbox_provider_pricing import billing, seed_versions
from sandbox_provider_pricing.providers import provider_ids
from sandbox_provider_pricing.testing import bundled_providers, forget_caches, use_providers


def test_the_bundled_folder_holds_every_provider() -> None:
    names = {path.name for path in bundled_providers().iterdir() if path.is_dir()}
    assert provider_ids() and set(provider_ids()) <= names


def test_a_provider_folder_is_read_only_inside_the_block(tmp_path: Path) -> None:
    for folder in bundled_providers().iterdir():
        if folder.name == "e2b":
            shutil.copytree(folder, tmp_path / "e2b", ignore=shutil.ignore_patterns("__pycache__"))
    before = {row["provider"] for row in seed_versions()}
    assert "modal" in before
    with use_providers(tmp_path):
        assert {row["provider"] for row in seed_versions()} == {"e2b"}
        assert billing("e2b")
    assert {row["provider"] for row in seed_versions()} == before


def test_the_folder_comes_back_when_the_block_raises(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError), use_providers(tmp_path):
        raise RuntimeError("inside")
    assert "modal" in {row["provider"] for row in seed_versions()}


def test_forgetting_caches_is_harmless() -> None:
    forget_caches()
    assert seed_versions()


def test_a_provider_that_is_not_bundled_prices_with_its_own_rules(tmp_path: Path) -> None:
    for folder in bundled_providers().iterdir():
        if folder.is_dir() and folder.name != "__pycache__":
            shutil.copytree(
                folder, tmp_path / folder.name, ignore=shutil.ignore_patterns("__pycache__")
            )
    source = tmp_path / "e2b"
    shutil.copytree(source, tmp_path / "zeta")
    with use_providers(tmp_path):
        assert billing("zeta") == billing("e2b")
        assert any(row["provider"] == "e2b" for row in seed_versions())
    with pytest.raises(ValueError, match="zeta"):
        billing("zeta")
