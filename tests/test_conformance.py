# SPDX-FileCopyrightText: BoxRouter, Inc.
# SPDX-License-Identifier: Apache-2.0
"""The released data regenerates exactly and detects consumer drift."""

from collections import Counter

import pytest

from sandbox_provider_pricing import build_price_sheet, price
from sandbox_provider_pricing.conformance import (
    cost_answer,
    evidence_for,
    generate,
    load_cases,
    run_cases,
    sheet_answer,
)
from sandbox_provider_pricing.types import Document


def test_released_conformance_regenerates_without_changes() -> None:
    assert generate() == {"schema_version": 1, "cases": load_cases()}


def test_all_released_cases_and_certainty_labels() -> None:
    sheet = build_price_sheet()

    def evaluate(case: Document) -> Document:
        return (
            cost_answer(price(evidence_for(case)))
            if case["kind"] == "price"
            else sheet_answer(case, sheet)
        )

    assert run_cases(evaluate, kinds={"price", "hourly", "storage"}) == len(load_cases())
    labels = Counter(case["expected"]["label"] for case in load_cases() if case["kind"] == "price")
    assert set(labels) == {"reported", "calculated", "unknown"}


def test_consumer_difference_and_empty_selection_fail() -> None:
    with pytest.raises(AssertionError, match="expected"):
        run_cases(lambda _: {}, kinds={"price"})
    with pytest.raises(ValueError, match="no conformance cases"):
        run_cases(lambda _: {}, kinds={"unsupported"})
