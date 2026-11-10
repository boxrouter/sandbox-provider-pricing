# SPDX-FileCopyrightText: BoxRouter, Inc.
# SPDX-License-Identifier: Apache-2.0
"""The provider-sourced-cost contract over every recorded fixture.

Given a recorded provider usage response, the reader yields an exact final cost or
Unknown — never an estimate. A provider-reported figure is the provider's own USD
record (`source: "provider"`); partial or ambiguous reads fall back to `unknown`,
and nothing synthesizes a cost from them.
"""

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import pytest

from sandbox_provider_pricing import price, record_evidence, scheduled_revisit
from sandbox_provider_pricing.providers import billing, provider_ids
from sandbox_provider_pricing.scaffold import add
from sandbox_provider_pricing.testing import use_providers
from sandbox_provider_pricing.versions import priced_provider_ids

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = sorted(ROOT.glob("providers/*/fixtures/*/evidence.json"))


def _load(path: Path) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))


@pytest.mark.parametrize("evidence_path", EVIDENCE, ids=lambda p: str(p.relative_to(ROOT)))
def test_a_recorded_read_is_an_exact_provider_cost_or_unknown(evidence_path: Path) -> None:
    result = price(_load(evidence_path))
    # There is no estimated label: a cost is reported by the provider, calculated
    # from published list prices, or unknown.
    assert result["label"] in {"reported", "calculated", "unknown"}, evidence_path
    reported = result["reported"]
    if result["label"] == "reported":
        assert reported is not None
        assert reported["source"] == "provider"
        assert re.fullmatch(r"[0-9]+(\.[0-9]+)?", reported["usd"]), evidence_path
        # The figure is the provider's exact record: low and high are that one value.
        assert result["total"] == {"low": reported["usd"], "high": reported["usd"]}
        assert result["basis"] == "provider_reported"
    else:
        # A read the provider did not settle is never filled in as if it had.
        assert result["total"] is None or result["basis"] == "list_price_usage"
    if reported is not None:
        assert reported["source"] == "provider"
        assert reported["how"]


def test_every_priced_provider_reports_an_exact_cost_or_is_a_listed_gap() -> None:
    """A provider whose billing best is calculated or unknown reports no cost, and its billing
    `why_not_higher` is the listed reason for the missing reported fixture."""
    reported = {
        path.parents[2].name for path in EVIDENCE if price(_load(path))["label"] == "reported"
    }
    gaps = {
        provider: billing(provider)["status"]["why_not_higher"]
        for provider in priced_provider_ids()
        if billing(provider)["status"]["best_label"] != "reported"
    }
    assert reported == set(priced_provider_ids()) - set(gaps), (
        f"providers with a reporting best but no reported fixture: "
        f"{sorted(set(priced_provider_ids()) - reported - set(gaps))}"
    )


def test_discovery_covers_every_provider_with_fixtures() -> None:
    with_fixtures = {path.parents[2].name for path in EVIDENCE}
    assert with_fixtures <= set(provider_ids())


def test_a_fresh_scaffold_is_discovered_unpriced_and_reports_only_unknown(
    tmp_path: Path,
) -> None:
    """`make new-provider` emits a provider the discovery reads but every priced surface skips,
    and its records price only to unknown."""
    add(tmp_path, "acme", name="Acme", website="https://acme.invalid")
    with use_providers(tmp_path / "src/sandbox_provider_pricing/providers"):
        assert provider_ids() == ["acme"]
        assert priced_provider_ids() == []
        assert scheduled_revisit("acme") is None
        status = billing("acme")["status"]
        assert status["best_label"] == "unknown"
        result = price(
            record_evidence({"provider": "acme", "sandbox_id": "scaffolded"}),
            ended_at=datetime(2026, 1, 1, 0, 10, tzinfo=UTC),
            as_of="2026-01-01T00:10:30Z",
        )
        assert result["label"] == "unknown"
        assert result["total"] is None
        assert result["reported"] is None
