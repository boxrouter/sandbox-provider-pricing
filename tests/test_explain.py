# SPDX-FileCopyrightText: BoxRouter, Inc.
# SPDX-License-Identifier: Apache-2.0
"""`explain()` words a result's working: every line has text and sources, and the lines add up."""

import json
from decimal import Decimal
from functools import reduce
from pathlib import Path

import pytest

from sandbox_provider_pricing import explain
from sandbox_provider_pricing._util import CONTEXT
from sandbox_provider_pricing.explain import _dollars, _quantity

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
RESULTS = sorted(ROOT.glob("providers/*/fixtures/*/result.json"))
PRICED = [path for path in RESULTS if json.loads(path.read_text(encoding="utf-8"))["total"]]
UNPRICED = [path for path in RESULTS if path not in PRICED]


def _name(path: Path) -> str:
    return f"{path.parents[2].name}/{path.parent.name}"


def test_the_fixtures_include_each_label() -> None:
    labels = {json.loads(path.read_text(encoding="utf-8"))["label"] for path in RESULTS}
    assert labels == {"reported", "calculated", "unknown"}


@pytest.mark.parametrize("path", PRICED, ids=_name)
def test_every_line_has_text_and_a_source_and_the_amounts_sum_to_the_total(path: Path) -> None:
    result = json.loads(path.read_text(encoding="utf-8"))
    explained = explain(result)
    assert explained["lines"]
    for line in explained["lines"]:
        assert line["text"]
        assert line["sources"]
        assert all(line["sources"].values())
    total = Decimal(result["total"]["low"])
    assert total == Decimal(result["total"]["high"])
    # `price()` adds the amounts in this 60-digit context, so the test adds them the same way.
    assert reduce(CONTEXT.add, (Decimal(line["amount"]) for line in explained["lines"])) == total
    assert explained["summary"].startswith(
        "Reported by the provider" if result["label"] == "reported" else "Calculated"
    )
    assert explained["price_version"] == result["versions"]["prices"]


@pytest.mark.parametrize("path", UNPRICED, ids=_name)
def test_an_unpriced_result_has_no_lines_and_says_why(path: Path) -> None:
    result = json.loads(path.read_text(encoding="utf-8"))
    explained = explain(result)
    assert explained["lines"] == []
    assert explained["summary"].startswith("Unknown: ")
    assert result["held_back_by"][0]["text"] in explained["summary"]


def test_a_calculated_line_reads_quantity_rate_and_amount_with_each_source() -> None:
    result = json.loads(
        (ROOT / "providers/vercel/fixtures/best/result.json").read_text(encoding="utf-8")
    )
    first = explain(result)["lines"][0]
    assert first["text"] == "CPU: 0.003067 vCPU-hour × $0.128 per vCPU-hour = $0.00039"
    assert first["sources"] == {
        "quantity": "provider record",
        "rate": "published rate",
        "amount": "calculated",
    }
    assert first.get("exact_quantity", "").startswith("Exactly 0.0030666666")
    assert first["amount"] == result["lines"][0]["amount"]


def test_a_reported_result_has_one_line_that_is_the_providers_figure() -> None:
    result = json.loads(
        (ROOT / "providers/blaxel/fixtures/best/result.json").read_text(encoding="utf-8")
    )
    explained = explain(result)
    assert [line["text"] for line in explained["lines"]] == ["Reported by the provider: $0.0036"]
    assert explained["lines"][0]["sources"] == {"amount": "provider record"}
    assert explained["summary"] == "Reported by the provider: $0.0036."


def test_an_unknown_result_without_a_reason_still_says_something() -> None:
    result = json.loads(
        (ROOT / "providers/e2b/fixtures/best/result.json").read_text(encoding="utf-8")
    )
    result["held_back_by"] = []
    assert explain(result)["summary"].startswith("Unknown: No provider record")


@pytest.mark.parametrize(
    ("amount", "shown"),
    [
        ("0.0585", "$0.059"),
        ("0.0007", "$0.0007"),
        ("0.0007123", "$0.00071"),
        ("0.1", "$0.10"),
        ("0", "$0"),
        ("1.2449", "$1.24"),
        ("1.245", "$1.25"),
        ("0.999", "$1.00"),
        ("12", "$12.00"),
    ],
)
def test_amounts_read_with_two_significant_digits_under_a_dollar(amount: str, shown: str) -> None:
    assert _dollars(amount) == shown


@pytest.mark.parametrize(
    ("quantity", "shown", "exact"),
    [
        ("0.0416666", "0.04167", "0.0416666"),
        ("150", "150", None),
        ("1234.5678", "1,235", "1,234.5678"),
        ("0.5", "0.5", None),
        ("0.041", "0.041", None),
        ("12345", "12,345", None),
    ],
)
def test_quantities_keep_four_significant_digits(
    quantity: str, shown: str, exact: str | None
) -> None:
    assert _quantity(quantity) == (shown, exact)
