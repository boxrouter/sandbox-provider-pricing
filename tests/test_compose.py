# SPDX-FileCopyrightText: BoxRouter, Inc.
# SPDX-License-Identifier: Apache-2.0
"""Composition of resource-level price results."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest

from sandbox_provider_pricing import compose, price, record_evidence

ROOT = Path(__file__).resolve().parents[1]


def _part(
    label: str,
    total: dict[str, str] | None,
    *,
    revisit: dict[str, Any] | None = None,
    made: bool = True,
) -> dict[str, Any]:
    return {
        "provider": "sample",
        "label": label,
        "total": total,
        "currency": "USD",
        "basis": "list_price_usage",
        "revisit": revisit,
        "steps": {"evidence": {"sandbox_made": {"value": made}}},
    }


def test_one_unpriced_required_resource_makes_composed_total_unknown() -> None:
    priced = _part("calculated", {"low": "1.25", "high": "1.25"})
    missing = _part("unknown", None)

    result = compose([priced, missing])

    assert (result["label"], result["total"]) == ("unknown", None)
    assert result["parts"] == [priced, missing]


def test_failed_attempt_is_counted_and_raw_evidence_is_preserved() -> None:
    created = _part("calculated", {"low": "2", "high": "2"})
    failed = _part("unknown", None, made=False)

    result = compose([created, failed])

    assert len(result["parts"]) == 2
    assert result["parts"][1]["steps"]["evidence"]["sandbox_made"]["value"] is False
    assert result["total"] is None


def test_each_distinct_revisit_obligation_is_retained() -> None:
    first = {
        "after": "2026-01-01T00:00:00Z",
        "until": "2026-01-02T00:00:00Z",
        "interval_s": 60,
        "next_read_at": "2026-01-01T00:01:00Z",
    }
    second = {
        "after": "2026-01-03T00:00:00Z",
        "until": "2026-01-04T00:00:00Z",
        "interval_s": 300,
        "next_read_at": "2026-01-03T00:05:00Z",
    }

    result = compose(
        [
            _part("calculated", {"low": "1", "high": "1"}, revisit=first),
            _part("reported", {"low": "2", "high": "2"}, revisit=second),
        ]
    )

    assert result["revisits"] == [
        {"part": 0, "revisit": first},
        {"part": 1, "revisit": second},
    ]


def test_all_exact_parts_sum_with_weakest_label() -> None:
    result = compose(
        [
            _part("reported", {"low": "0.10", "high": "0.10"}),
            _part("calculated", {"low": "2.3", "high": "2.3"}),
        ]
    )

    assert result["label"] == "calculated"
    assert result["total"] == {"low": "2.4", "high": "2.4"}


def test_input_results_are_not_mutated() -> None:
    part = _part("calculated", {"low": "1", "high": "1"})
    before = deepcopy(part)
    compose([part])
    assert part == before


def test_empty_input_is_rejected() -> None:
    with pytest.raises(ValueError, match="at least one"):
        compose([])


@pytest.mark.parametrize(
    ("labels", "expected"),
    [
        (("reported", "reported"), "reported"),
        (("reported", "calculated"), "calculated"),
        (("calculated", "calculated"), "calculated"),
        (("reported", "unknown"), "unknown"),
        (("calculated", "reported", "unknown"), "unknown"),
    ],
)
def test_the_label_is_the_weakest_sandbox_label(labels: tuple[str, ...], expected: str) -> None:
    parts = [
        _part(label, None if label == "unknown" else {"low": "1", "high": "1"}) for label in labels
    ]
    assert compose(parts)["label"] == expected


def test_a_range_total_makes_the_composed_cost_unknown() -> None:
    result = compose(
        [
            _part("calculated", {"low": "1", "high": "2"}),
            _part("calculated", {"low": "1", "high": "1"}),
        ]
    )
    assert (result["label"], result["total"], result["lines"]) == ("unknown", None, [])


def _priced_sandbox(sandbox_id: str) -> dict[str, Any]:
    path = ROOT / "tests" / "fixtures" / "records" / "e2b-usage.json"
    case = json.loads(path.read_text())
    record = case["runner"]["record"] | {"sandbox_id": sandbox_id}
    return price(record_evidence(record), as_of=case["as_of"])


def test_two_sandboxes_of_one_trial_add_up_and_keep_the_working() -> None:
    first, second = _priced_sandbox("one"), _priced_sandbox("two")
    result = compose([first, second])

    assert (result["label"], result["total"]) == (
        "calculated",
        {"low": "0.01089", "high": "0.01089"},
    )
    assert result["lines"] == [*first["lines"], *second["lines"]]
    assert result["held_back_by"] == first["held_back_by"] == []
    assert result["excluded"] == first["excluded"]
    assert result["final"] is False  # final only when every sandbox's own result is
    assert result["versions"] == first["versions"]
    assert result["as_of"] == first["as_of"]
    usage = result["steps"]["usage"]["high"]
    assert usage["intervals"] == [
        *first["steps"]["usage"]["high"]["intervals"],
        *second["steps"]["usage"]["high"]["intervals"],
    ]
    assert [part["steps"]["evidence"]["sandbox_id"] for part in result["parts"]] == ["one", "two"]


def test_one_unknown_sandbox_hides_every_line_and_the_total() -> None:
    result = compose(
        [_priced_sandbox("one"), _priced_sandbox("two") | {"label": "unknown", "total": None}]
    )
    assert (result["label"], result["total"], result["lines"]) == ("unknown", None, [])


def test_final_needs_every_sandbox_final() -> None:
    final = _priced_sandbox("one") | {"final": True}
    assert compose([final, final])["final"] is True
    assert compose([final, final | {"final": False}])["final"] is False


def test_provider_reported_costs_add() -> None:
    reported = {"usd": "0.10", "source": "provider", "how": "metered"}
    a = _part("reported", {"low": "0.10", "high": "0.10"}) | {"reported": reported}
    b = _part("reported", {"low": "0.2", "high": "0.2"}) | {"reported": reported | {"usd": "0.2"}}
    summed = compose([a, b])["reported"]
    assert summed["usd"] == "0.3"
    assert summed["how"] == "sum of the provider-reported sandbox costs"
    assert compose([a, _part("calculated", {"low": "1", "high": "1"})])["reported"] is None


def test_one_part_keeps_its_total_digit_for_digit() -> None:
    long = "0.003012583900000000000000000000000000000000000000000000000001"  # 60 digits
    result = compose([_part("calculated", {"low": long, "high": long})])
    assert result["total"] == {"low": long, "high": long}
    assert result["label"] == "calculated"
    # Several parts are still added and written to 28 significant digits.
    two = compose([_part("calculated", {"low": long, "high": long})] * 2)
    assert two["total"] == {"low": "0.0060251678", "high": "0.0060251678"}
