# SPDX-FileCopyrightText: BoxRouter, Inc.
# SPDX-License-Identifier: Apache-2.0
"""Every provider's rules price the spec's cost lines (`cost.capture`, `cost` of the in-process
provider), and give the label and total the old adapter's records gave (the G1 parity rule).

Each case takes a provider's `best` fixture, replaces its old records with the cost lines the
provider's in-process package states, and compares with the result the old records gave.
"""

from __future__ import annotations

import copy
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

import pytest

from sandbox_provider_pricing import price

PROVIDERS = Path(__file__).resolve().parents[1] / "providers"


def _fixture(provider: str, name: str = "best") -> dict[str, Any]:
    return cast(
        dict[str, Any],
        json.loads((PROVIDERS / provider / "fixtures" / name / "evidence.json").read_text()),
    )


def _line(
    source: str, item: str, start: str | None, end: str | None, **fields: Any
) -> dict[str, Any]:
    return {
        "amount": None,
        "currency": "USD",
        "meter": item,
        "interval_start": start,
        "interval_end": end,
        "scope": "sandbox",
        "source": source,
    } | fields


def _with_lines(
    evidence: dict[str, Any], readings: list[dict[str, Any]], read_at: str
) -> dict[str, Any]:
    """The evidence with only the spec's cost report: no old record, no old report."""
    evidence = copy.deepcopy(evidence)
    evidence["provider_records"] = []
    evidence.pop("provider_reports", None)
    evidence["provider_reports"] = {
        "read_at": read_at,
        "cost": {"status": "available", "reason": None, "readings": readings},
    }
    return evidence


def _agent37() -> dict[str, Any]:
    lines = [_line("reported", "machine", None, None, amount="0.000543")]
    return _with_lines(_fixture("agent37"), lines, "2026-11-13T21:33:25Z")


def _boat() -> dict[str, Any]:
    line = _line(
        "reported", "machine", "2026-11-01T04:00:10Z", "2026-11-01T04:05:20Z", amount="0.00288"
    )
    return _with_lines(_fixture("boat"), [line], "2026-11-01T04:05:20Z")


def _daytona() -> dict[str, Any]:
    lines = [
        _line(
            "reported",
            "machine",
            "2026-10-19T18:39:03Z",
            "2026-10-19T19:00:00Z",
            amount="0.04104105",
        ),
        _line(
            "reported",
            "machine",
            "2026-10-19T19:00:00Z",
            "2026-10-19T19:39:03Z",
            amount="0.07649895",
        ),
    ]
    return _with_lines(_fixture("daytona"), lines, "2026-10-19T20:00:00Z")


def _modal() -> dict[str, Any]:
    start, end = "2026-10-24T01:00:00Z", "2026-10-24T02:00:00Z"
    lines = [
        _line("reported", "memory", start, end, amount="0.00361867"),
        _line("reported", "cpu", start, end, amount="0.01069769"),
    ]
    return _with_lines(_fixture("modal"), lines, "2026-10-24T04:05:03Z")


def _superserve() -> dict[str, Any]:
    start, end = "2026-11-13T09:13:55.565760Z", "2026-11-13T09:14:26.771243Z"
    lines = [
        _line("usage", "cpu", start, end, quantity="62.410966", unit="vcpu_second"),
        _line("usage", "memory", start, end, quantity="124.821932", unit="gib_second"),
    ]
    return _with_lines(_fixture("superserve"), lines, "2026-11-13T09:15:00Z")


def _vercel() -> dict[str, Any]:
    start, end = "2026-10-12T12:00:00.500Z", "2026-10-12T12:02:00.500Z"
    lines = [
        _line("usage", "create", None, None, quantity="1", unit="each"),
        _line("usage", "memory", start, end, quantity="480", unit="gib_second"),
        _line("usage", "cpu", start, end, quantity="11.04", unit="vcpu_second"),
        _line("usage", "egress", start, end, quantity="0", unit="gb"),
    ]
    return _with_lines(_fixture("vercel"), lines, "2026-10-12T12:07:00Z")


#: Provider -> (the evidence with the spec's lines, the label and basis it must give).
CASES: dict[str, tuple[Callable[[], dict[str, Any]], str, str]] = {
    "agent37": (_agent37, "reported", "provider_reported"),
    "boat": (_boat, "reported", "provider_reported"),
    "daytona": (_daytona, "reported", "provider_reported"),
    "modal": (_modal, "reported", "provider_reported"),
    "superserve": (_superserve, "calculated", "list_price_usage"),
    "vercel": (_vercel, "calculated", "list_price_usage"),
}


@pytest.mark.parametrize("provider", sorted(CASES))
def test_spec_lines_give_the_label_and_total_the_old_records_gave(provider: str) -> None:
    build, label, basis = CASES[provider]
    old = price(_fixture(provider))
    new = price(build())
    assert (new["label"], new["basis"]) == (label, basis)
    assert (old["label"], old["basis"]) == (label, basis)
    # The fixture's modal resource figures sum to 0.01431636; its hour total is rounded to ...35.
    assert new["total"] == (
        {"low": "0.01431636", "high": "0.01431636"} if provider == "modal" else old["total"]
    )


@pytest.mark.parametrize("provider", sorted(CASES))
def test_spec_lines_are_not_priced_before_the_provider_s_own_delay(provider: str) -> None:
    build, _, _ = CASES[provider]
    evidence = build()
    # The read is taken the instant the sandbox ends: before any provider's revisit delay.
    ended = evidence["calls"][-1]["returned_at"]["value"]
    evidence["provider_reports"]["read_at"] = ended
    assert price(evidence)["label"] == "unknown"


def test_agent37_prices_the_machine_line_alone() -> None:
    """The sandbox's own cost holds no feature line: managed services are the account's."""
    result = price(_agent37())
    assert result["total"] == {"low": "0.000543", "high": "0.000543"}


def test_vercel_prices_create_memory_cpu_and_egress_from_the_sheet() -> None:
    """One creation at $0.60 per million, 4 GiB for 120 s at $0.0212 per GB-hour, 11.04 s of
    active CPU at $0.128 per vCPU-hour, and egress at the sheet's rate."""
    result = price(_vercel())
    lines = {line["what"]: line for line in result["lines"]}
    assert set(lines) == {"creation", "memory", "cpu", "egress"}
    assert lines["creation"]["quantity"] == "0.000001"
    assert lines["creation"]["amount"] == "0.0000006"
    assert lines["memory"]["unit"] == "gb-hour"
    assert result["total"] == price(_fixture("vercel"))["total"]


def test_vercel_egress_is_priced_at_the_sheet_rate() -> None:
    evidence = _vercel()
    evidence["provider_reports"]["cost"]["readings"][3]["quantity"] = "2"
    lines = {line["what"]: line for line in price(evidence)["lines"]}
    assert lines["egress"]["quantity"] == "2"
    assert lines["egress"]["amount"] == str(2 * float(lines["egress"]["rate"])).rstrip("0").rstrip(
        "."
    )


def test_vercel_a_line_the_sheet_has_no_rate_for_is_unknown() -> None:
    evidence = _vercel()
    evidence["provider_reports"]["cost"]["readings"].append(
        _line("usage", "disk", None, None, quantity="3", unit="gib_second")
    )
    result = price(evidence)
    assert (result["label"], result["total"]) == ("unknown", None)


def test_vercel_a_gib_egress_is_never_taken_for_the_sheet_s_decimal_gb() -> None:
    evidence = _vercel()
    evidence["provider_reports"]["cost"]["readings"][3]["unit"] = "gib"
    result = price(evidence)
    assert (result["label"], result["total"]) == ("unknown", None)


def test_e2b_prices_cpu_and_memory_seconds_at_the_sheet_rates() -> None:
    """Two runs of 9 s and 7 s at 2 vCPUs and 4 GiB: 32 vCPU-seconds and 64 GiB-seconds, at
    $0.000014 and $0.0000045, which is $0.000736."""
    first = ("2026-10-11T16:03:30Z", "2026-10-11T16:03:39Z")
    second = ("2026-10-11T16:03:51Z", "2026-10-11T16:03:58Z")
    lines = [
        _line("usage", "cpu", *first, quantity="18", unit="vcpu_second"),
        _line("usage", "memory", *first, quantity="36", unit="gib_second"),
        _line("usage", "cpu", *second, quantity="14", unit="vcpu_second"),
        _line("usage", "memory", *second, quantity="28", unit="gib_second"),
    ]
    result = price(_with_lines(_fixture("e2b"), lines, "2026-10-11T16:04:30Z"))
    assert (result["label"], result["basis"]) == ("calculated", "list_price_usage")
    assert result["total"] == {"low": "0.000736", "high": "0.000736"}
    assert {line["what"]: line["quantity"] for line in result["lines"]} == {
        "cpu": "32",
        "memory": "64",
    }


def test_e2b_a_pause_longer_than_a_minute_leaves_no_cost_unpriced() -> None:
    """Usage lines are the active runs: the minutes the sandbox sat paused between them are not
    a gap in the cost."""
    evidence = _fixture("e2b")
    evidence["calls"][-1]["returned_at"]["value"] = "2026-10-11T16:13:00Z"
    evidence["calls"][-1]["sent_at"]["value"] = "2026-10-11T16:12:58Z"
    first = ("2026-10-11T16:03:30Z", "2026-10-11T16:03:39Z")
    last = ("2026-10-11T16:12:51Z", "2026-10-11T16:12:58Z")
    lines = [
        _line("usage", "cpu", *first, quantity="18", unit="vcpu_second"),
        _line("usage", "memory", *first, quantity="36", unit="gib_second"),
        _line("usage", "cpu", *last, quantity="14", unit="vcpu_second"),
        _line("usage", "memory", *last, quantity="28", unit="gib_second"),
    ]
    result = price(_with_lines(evidence, lines, "2026-10-11T16:13:30Z"))
    assert result["label"] == "calculated"
    assert result["total"] == {"low": "0.000736", "high": "0.000736"}


def test_e2b_usage_that_misses_the_end_of_the_sandbox_is_not_priced() -> None:
    first = ("2026-10-11T16:03:30Z", "2026-10-11T16:03:39Z")
    lines = [
        _line("usage", "cpu", *first, quantity="18", unit="vcpu_second"),
        _line("usage", "memory", *first, quantity="36", unit="gib_second"),
    ]
    evidence = _fixture("e2b")
    evidence["calls"][-1]["returned_at"]["value"] = "2026-10-11T16:08:00Z"
    result = price(_with_lines(evidence, lines, "2026-10-11T16:09:00Z"))
    assert (result["label"], result["total"]) == ("unknown", None)


def test_reported_lines_with_a_gap_are_still_not_priced() -> None:
    """Money for stretches of time must leave none of the sandbox's life out."""
    evidence = _daytona()
    del evidence["provider_reports"]["cost"]["readings"][0]
    assert price(evidence)["label"] == "unknown"


#: Providers whose per-sandbox cost goes with the sandbox, so Cloud captures it just before the end.
#: A dict, not a typed list: `test_imports` has tests read the provider list instead of typing it.
CAPTURED_BEFORE_END = {"boat": CASES["boat"], "vercel": CASES["vercel"]}


@pytest.mark.parametrize("provider", sorted(CAPTURED_BEFORE_END))
def test_a_final_cost_captured_before_the_end_counts_without_waiting(provider: str) -> None:
    """`cost.capture` is read just before the destroy of a provider that deletes its cost with the
    sandbox: there is no later read, so the adapter's `final` is all the figure needs."""
    evidence = CASES[provider][0]()
    ended = evidence["calls"][-1]["returned_at"]["value"]
    evidence["provider_reports"]["read_at"] = evidence["calls"][-1]["sent_at"]["value"]
    assert evidence["provider_reports"]["read_at"] <= ended
    result = price(evidence)
    assert result["label"] == CASES[provider][1]
    assert result["total"] == price(_fixture(provider))["total"]


def test_a_cost_captured_before_the_end_still_waits_while_the_adapter_says_accruing() -> None:
    evidence = _vercel()
    evidence["provider_reports"]["read_at"] = evidence["calls"][-1]["sent_at"]["value"]
    evidence["provider_reports"]["cost"]["final"] = False
    assert price(evidence)["label"] == "unknown"
