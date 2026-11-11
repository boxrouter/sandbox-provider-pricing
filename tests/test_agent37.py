# SPDX-FileCopyrightText: BoxRouter, Inc.
# SPDX-License-Identifier: Apache-2.0
"""Agent37's price is the settled compute spend of the instance, never its managed services."""

import json
from pathlib import Path
from typing import Any, cast

from sandbox_provider_pricing import price

ROOT = Path(__file__).resolve().parents[1]


def evidence() -> dict[str, Any]:
    return cast(
        dict[str, Any],
        json.loads((ROOT / "providers/agent37/fixtures/best/evidence.json").read_text()),
    )


def _with_usage(item: dict[str, Any], *, total: int, llm: int, reading: str) -> dict[str, Any]:
    """The fixture with its usage entry and the settled reading in Core's cost report changed."""
    for record in item["provider_records"]:
        if record["source"] == "core.cost":
            record["body"]["readings"][0]["amount"] = reading
        else:
            record["body"]["total_micros"], record["body"]["llm_micros"] = total, llm
    return item


def test_the_settled_compute_spend_is_the_reported_price() -> None:
    result = price(evidence())
    assert result["label"] == "reported"
    assert result["total"] == {"low": "0.001413", "high": "0.001413"}


def test_managed_services_billed_to_the_instance_are_left_out() -> None:
    # 500 micro-dollars of managed LLM calls: the settled reading is the instance's whole spend,
    # the price is its compute alone.
    result = price(_with_usage(evidence(), total=1913, llm=500, reading="0.001913"))
    assert result["label"] == "reported"
    assert result["total"] == {"low": "0.001413", "high": "0.001413"}


def test_a_usage_entry_that_is_not_the_settled_total_is_not_priced() -> None:
    result = price(_with_usage(evidence(), total=1500, llm=87, reading="0.001413"))
    assert result["label"] == "unknown"


def test_another_instances_usage_entry_is_not_priced() -> None:
    item = evidence()
    item["sandbox_id"] = "someotherid"
    assert price(item)["label"] == "unknown"
