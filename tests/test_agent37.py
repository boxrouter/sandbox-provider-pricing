# SPDX-FileCopyrightText: BoxRouter, Inc.
# SPDX-License-Identifier: Apache-2.0
"""Agent37's price is the settled compute spend of the instance, never its managed services."""

import json
from decimal import Decimal
from pathlib import Path
from typing import Any, cast

from sandbox_provider_pricing import price, reservation_quote
from sandbox_provider_pricing.versions import latest_version

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


def test_a_vm_reservation_is_the_published_vm_monthly_price() -> None:
    # The VM page's 2 vCPU / 4 GB / 4 GB disk row is $11.36 a month (730 hours); the default
    # type's same shape is $4.76, so the VM class prices compute at 2.5x and disk unchanged.
    version = latest_version("agent37")
    size = {"cpu": 2, "memory_mib": 4096, "disk_mib": 4096}
    month = 730 * 3600
    for class_name, monthly in (("vm", "11.36"), ("default", "4.76")):
        quote = reservation_quote(version, size, month, class_name=class_name, creation=False)
        assert quote["status"] == "bounded", quote
        assert Decimal(str(quote["ceiling_usd"])).quantize(Decimal("0.01")) == Decimal(monthly)
