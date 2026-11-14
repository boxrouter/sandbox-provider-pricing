# SPDX-FileCopyrightText: BoxRouter, Inc.
# SPDX-License-Identifier: Apache-2.0
"""A create by minimums gets its allocated size from the provider's own record.

The billing declaration names the record field carrying the provider's size name; the price
version keys its flat per-size machine rates by the same names, so the latest record read
resolves the published cpu, memory and disk of what was allocated. Nothing resolvable leaves
the size unknown — it is never estimated.
"""

import json
from pathlib import Path
from typing import Any, cast

from sandbox_provider_pricing import price

ROOT = Path(__file__).resolve().parents[1]
BEST = ROOT / "providers/boat/fixtures/best/evidence.json"


def _minimums() -> dict[str, Any]:
    """The best fixture requested by minimums: no exact cpu, memory or disk."""
    evidence = cast(dict[str, Any], json.loads(BEST.read_text(encoding="utf-8")))
    for key in ("cpu", "memory_mib", "disk_mib"):
        evidence["requested"].pop(key, None)
    return evidence


def test_the_record_resolves_the_allocated_size() -> None:
    result = price(_minimums())
    size = result["steps"]["usage"]["low"]["size"]
    assert size["cpu"] == 4
    assert size["memory_mib"] == 8192
    assert size["disk_mib"] == 52224
    assert size["source"] == "provider"
    assert size["observed_at"] == "2026-11-01T04:05:20Z"
    assert result["total"] == {"low": "0.00288", "high": "0.00288"}
    assert result["held_back_by"] == []


def test_the_resolved_size_leaves_no_size_gap() -> None:
    result = price(_minimums())
    held = {gap["resource"] for gap in result["steps"]["rated"]["low"]["held_back_by"]}
    assert "machine" not in held
    assert "disk" not in held


def test_a_name_the_version_does_not_sell_stays_unknown() -> None:
    evidence = _minimums()
    evidence["provider_records"][0]["body"]["sandboxType"] = "medium"
    result = price(evidence)
    size = result["steps"]["usage"]["low"]["size"]
    assert size["source"] == "unknown"
    assert "cpu" not in size


def test_no_record_means_no_size() -> None:
    evidence = _minimums()
    evidence["provider_records"] = []
    result = price(evidence)
    size = result["steps"]["usage"]["low"]["size"]
    assert size["source"] == "unknown"
    assert result["total"] is None


def test_the_newest_record_read_names_the_size() -> None:
    evidence = _minimums()
    record = json.loads(json.dumps(evidence["provider_records"][0]))
    record["read_at"] = "2026-11-01T04:02:00Z"
    record["body"]["sandboxType"] = "medium"
    evidence["provider_records"].append(record)
    size = price(evidence)["steps"]["usage"]["low"]["size"]
    assert size["source"] == "provider"
    assert size["cpu"] == 4


def test_an_exact_requested_size_is_still_the_allocated_one() -> None:
    result = price(json.loads(BEST.read_text(encoding="utf-8")))
    size = result["steps"]["usage"]["low"]["size"]
    assert size["source"] == "provider"
    assert size["cpu"] == 4
    assert result["total"] == {"low": "0.00288", "high": "0.00288"}
