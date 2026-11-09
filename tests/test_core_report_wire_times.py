# SPDX-FileCopyrightText: BoxRouter, Inc.
# SPDX-License-Identifier: Apache-2.0
"""Read-time precedence over Core's real report wire documents, frozen as JSON.

`data/core-report-wire.json` holds Core 0.13.180 cost, size and usage reports as Cloud serializes
them (supplied by Cloud from the real `to_dict`/`asdict` forms), in each status, and usage with
`observed_at` set and null. Every combination of present reports is
tried with each way of giving read times: each report's own, a bundle `read_at`, the usage
report's `observed_at` (the 0.4.39 form), and mixes. A needed time that is missing or malformed is
refused; a time nothing uses is never checked; the schema agrees with `normalize_evidence`.
"""

import json
from copy import deepcopy
from itertools import combinations, product
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator

from sandbox_provider_pricing import price
from sandbox_provider_pricing.evidence import normalize_evidence

ROOT = Path(__file__).parents[1]
WIRE = json.loads((ROOT / "tests/data/core-report-wire.json").read_text())
# Cloud's stored form leaves out a null `observed_at`; Core's own serialization (and Cloud's
# scheduling path) sends it as an explicit null. Test both.
for _variant in [v for v in WIRE["usage"] if v.endswith("_null")]:
    WIRE["usage"][f"{_variant}_explicit"] = {**WIRE["usage"][_variant], "observed_at": None}
KINDS = ("cost", "size", "usage")
OWN = {
    "cost": "2026-10-24T12:00:01Z",
    "size": "2026-10-24T12:00:02Z",
    "usage": "2026-10-24T12:00:03Z",
}
BUNDLE = "2026-10-24T12:30:00Z"
AS_OF = "2026-10-25T00:00:00Z"


def _validator() -> Draft202012Validator:
    schema = json.loads((ROOT / "schemas/evidence.schema.json").read_text())
    return Draft202012Validator({"$defs": schema["$defs"], "$ref": "#/$defs/provider_reports"})


VALIDATOR = _validator()


def _combos() -> list[tuple[str, dict[str, Any]]]:
    """Every non-empty set of present kinds, with every wire variant of each."""
    out = []
    for size in range(1, len(KINDS) + 1):
        for kinds in combinations(KINDS, size):
            for picks in product(*(sorted(WIRE[kind]) for kind in kinds)):
                reports = {k: deepcopy(WIRE[k][v]) for k, v in zip(kinds, picks, strict=True)}
                name = "+".join(f"{k}:{v}" for k, v in zip(kinds, picks, strict=True))
                out.append((name, reports))
    return out


COMBOS = _combos()


def _usage_time(reports: dict[str, Any]) -> Any:
    usage = reports.get("usage")
    return None if usage is None else usage.get("observed_at")


def _check(reports: dict[str, Any], expected: dict[str, str] | None) -> None:
    """`expected` maps each kind to its record's read time, or None when the input is refused."""
    evidence = {"provider": "e2b", "sandbox_id": "wire", "provider_reports": reports}
    if expected is None:
        assert not VALIDATOR.is_valid(reports)
        with pytest.raises(ValueError):
            normalize_evidence(deepcopy(evidence))
        return
    assert VALIDATOR.is_valid(reports), list(VALIDATOR.iter_errors(reports))
    records = normalize_evidence(deepcopy(evidence))["provider_records"]
    got = {
        r["source"].removeprefix("core."): r["read_at"]
        for r in records
        if r["source"].startswith("core.")
    }
    assert got == expected
    price(deepcopy(evidence), as_of=AS_OF)  # the public API accepts it too


@pytest.mark.parametrize(("name", "reports"), COMBOS, ids=[name for name, _ in COMBOS])
def test_own_times_win_and_unused_body_times_are_not_checked(name: str, reports: Any) -> None:
    del name
    reports = deepcopy(reports)
    reports["read_times"] = {kind: OWN[kind] for kind in KINDS if kind in reports}
    _check(reports, {kind: OWN[kind] for kind in KINDS if kind in reports})
    reports["read_at"] = BUNDLE  # an unused bundle time changes nothing
    _check(reports, {kind: OWN[kind] for kind in KINDS if kind in reports})
    if "usage" in reports:  # an unused malformed usage.observed_at is not checked
        reports["usage"]["observed_at"] = "bad"
        _check(reports, {kind: OWN[kind] for kind in KINDS if kind in reports})


@pytest.mark.parametrize(("name", "reports"), COMBOS, ids=[name for name, _ in COMBOS])
def test_bundle_read_at_covers_every_report_without_its_own(name: str, reports: Any) -> None:
    del name
    reports = deepcopy(reports)
    reports["read_at"] = BUNDLE
    _check(reports, {kind: BUNDLE for kind in KINDS if kind in reports})
    first = next(kind for kind in KINDS if kind in reports)
    reports["read_times"] = {first: OWN[first]}
    _check(
        reports, {kind: OWN[kind] if kind == first else BUNDLE for kind in KINDS if kind in reports}
    )
    reports["read_at"] = "bad"  # an explicit bundle time is always checked
    _check(reports, None)


@pytest.mark.parametrize(("name", "reports"), COMBOS, ids=[name for name, _ in COMBOS])
def test_usage_observed_at_is_the_last_fallback_only_when_needed(name: str, reports: Any) -> None:
    del name
    reports = deepcopy(reports)
    legacy = _usage_time(reports)
    usable = isinstance(legacy, str)
    _check(reports, {kind: legacy for kind in KINDS if kind in reports} if usable else None)
    first = next(kind for kind in KINDS if kind in reports)
    reports["read_times"] = {first: OWN[first]}
    rest = [kind for kind in KINDS if kind in reports and kind != first]
    if not rest:
        _check(reports, {first: OWN[first]})
    else:
        _check(reports, {first: OWN[first], **{k: legacy for k in rest}} if usable else None)
    if "usage" in reports and rest:  # a needed malformed fallback is refused
        reports["usage"]["observed_at"] = "bad"
        _check(reports, None)
