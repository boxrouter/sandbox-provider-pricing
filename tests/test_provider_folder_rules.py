# SPDX-FileCopyrightText: BoxRouter, Inc.
# SPDX-License-Identifier: Apache-2.0
"""Provider-specific rule discovery stays inside each provider folder."""

import json
import shutil
from pathlib import Path
from typing import Any, cast

import yaml  # type: ignore[import-untyped]

from sandbox_provider_pricing import price
from sandbox_provider_pricing import providers as provider_files

ROOT = Path(__file__).resolve().parents[1]


def test_data_only_provider_prices_without_central_registration(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """A billing document, price version and evidence fixture are enough for a new provider."""
    source = ROOT / "src" / "sandbox_provider_pricing" / "providers" / "e2b"
    folder = tmp_path / "acme"
    (folder / "fixtures" / "best").mkdir(parents=True)
    (folder / "prices").mkdir()
    shutil.copyfile(source / "billing.yaml", folder / "billing.yaml")
    fixture = ROOT / "providers" / "e2b" / "fixtures" / "best" / "evidence.json"

    evidence = cast(
        dict[str, Any],
        json.loads(fixture.read_text(encoding="utf-8")),
    )
    evidence["provider"] = "acme"
    (folder / "fixtures" / "best" / "evidence.json").write_text(
        json.dumps(evidence, indent=2) + "\n", encoding="utf-8"
    )

    version = cast(
        dict[str, Any],
        yaml.safe_load((source / "prices" / "2026-10-20-061802Z.yaml").read_text()),
    )
    version.update(provider="acme", version="acme@2026-10-20", supersedes=[])
    version["effective_from"] = "2026-10-11T00:00:00Z"
    (folder / "prices" / "2026-10-20.yaml").write_text(
        yaml.safe_dump(version, sort_keys=False), encoding="utf-8"
    )
    monkeypatch.setattr(provider_files, "providers_root", lambda: tmp_path)
    provider_files.rules.cache_clear()
    try:
        result = price(evidence, versions=[version])
    finally:
        provider_files.rules.cache_clear()
        provider_files.bundled_billing.cache_clear()

    assert result["provider"] == "acme"
    assert result["versions"]["prices"] == "acme@2026-10-20"
