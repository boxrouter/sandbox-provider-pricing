# SPDX-FileCopyrightText: BoxRouter, Inc.
# SPDX-License-Identifier: Apache-2.0
"""Billing answers name the price version's rows instead of typing their rates."""

import copy
import re
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
import yaml  # type: ignore[import-untyped]

from sandbox_provider_pricing.billing_text import fill_answer
from sandbox_provider_pricing.versions import latest_version, priced_provider_ids

PACKAGES = Path(__file__).resolve().parents[1] / "src" / "sandbox_provider_pricing" / "providers"
#: Only a priced provider owns rates its billing answers could repeat.
PROVIDERS = priced_provider_ids()
AMOUNT = re.compile(r"(?:\$|USD )(\d[\d,]*(?:\.\d+)?)")
MONTH_SIZE_UNIT = re.compile(r"\bGi?B(?:-|\s*·\s*)month\b")


def _rate_amounts(node: Any) -> set[Decimal]:
    if not isinstance(node, dict):
        return set()
    own = {Decimal(node["usd"])} if isinstance(node.get("usd"), str) else set()
    return own.union(*(_rate_amounts(value) for value in node.values()))


def _price_amounts(provider: str) -> set[Decimal]:
    """Every amount the provider's price version owns: each class's rates and storage rows."""
    version = latest_version(provider)
    amounts = set().union(*(_rate_amounts(item.get("rates")) for item in version["classes"]))
    return amounts.union(
        Decimal(row["usd"]) for key, row in version.items() if key.endswith("_storage")
    )


def _raw_rules(provider: str) -> dict[str, Any]:
    """The answers as written in `billing.yaml`, before the loader fills their fields."""
    document = yaml.safe_load((PACKAGES / provider / "billing.yaml").read_text(encoding="utf-8"))
    rules: dict[str, Any] = document["rules"]
    return rules


@pytest.mark.parametrize("provider", PROVIDERS)
def test_billing_answers_type_no_price_the_price_version_owns(provider: str) -> None:
    amounts = _price_amounts(provider)
    typed = [
        f"{key}: {match[0]}"
        for key, rule in _raw_rules(provider).items()
        for match in AMOUNT.finditer(rule["answer"])
        if Decimal(match[1].replace(",", "")) in amounts
    ]
    units = [
        f"{key}: {match[0]}"
        for key, rule in _raw_rules(provider).items()
        for match in MONTH_SIZE_UNIT.finditer(rule["answer"])
    ]
    assert typed == [], "write a {rate.<resource>} or {storage.<kind>} field instead"
    assert units == [], "write {storage.<kind>} or {storage.unit} instead of a storage unit"


def test_fields_fill_from_the_billed_amount_and_unit() -> None:
    blaxel, vercel, boxd = (
        latest_version("blaxel"),
        latest_version("vercel"),
        latest_version("boxd"),
    )
    assert fill_answer("Snapshots {storage.snapshot}.", vercel) == "Snapshots $0.08 per GB-month."
    assert (
        fill_answer(
            "{storage.snapshot.amount} and {storage.volume.amount}, per {storage.unit}.", blaxel
        )
        == "$0.20 and $0.12, per GiB-month."
    )
    assert fill_answer("{rate.cpu}; {rate.disk.amount}", boxd) == "$0.047 per vCPU-hour; $0.000096"
    assert fill_answer("GET /sandboxes/{id}/usage", boxd) == "GET /sandboxes/{id}/usage"


@pytest.mark.parametrize(
    "text",
    ["{storage.disk}", "{storage.snapshot.size}", "{rate.network}", "{rate.machine}"],
)
def test_an_unknown_field_or_a_row_with_no_billed_rate_fails(text: str) -> None:
    with pytest.raises(ValueError):
        fill_answer(text, latest_version("boat"))


def test_a_disk_rate_proxy_is_not_a_billed_storage_rate() -> None:
    daytona = latest_version("daytona")
    assert daytona["snapshot_storage"]["rate_source"] == "published_disk_rate_proxy"
    with pytest.raises(ValueError, match="no billed snapshot storage rate"):
        fill_answer("{storage.snapshot}", daytona)


def test_storage_unit_needs_one_shared_unit() -> None:
    version = copy.deepcopy(latest_version("blaxel"))
    version["volume_storage"]["per"] = "gb-month"
    with pytest.raises(ValueError, match="one unit"):
        fill_answer(
            "{storage.snapshot.amount}, {storage.volume.amount} per {storage.unit}", version
        )
