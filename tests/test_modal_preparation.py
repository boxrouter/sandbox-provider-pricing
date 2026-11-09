# SPDX-FileCopyrightText: BoxRouter, Inc.
# SPDX-License-Identifier: Apache-2.0
"""Modal image preparations are priced from their own stopped App, or stay unknown."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator, FormatChecker

from sandbox_provider_pricing import compose, price

ROOT = Path(__file__).resolve().parents[1]
RESULT_VALIDATOR = Draft202012Validator(
    json.loads((ROOT / "schemas" / "result.schema.json").read_text()),
    format_checker=FormatChecker(),
)
SOURCE = "Modal Workspace.billing.report"
APP = "ap-prep0000000000000000001"
KEY = "a" * 64
ACCOUNT = json.dumps(
    {"environment": "main", "workspace": "boxrouter-internal"},
    sort_keys=True,
    separators=(",", ":"),
)
CREATED = "2026-10-24T01:43:29.326784+00:00"
STOPPED = "2026-10-24T01:45:29.522000+00:00"


def _row(hour: str, cost: str = "0.01431635", app: str = APP) -> dict[str, Any]:
    return {
        "object_id": app,
        "description": "boxrouter-image-prep",
        "environment": "main",
        "interval_start": hour,
        "cost": cost,
        "cost_by_resource": {"CPU": cost},
    }


def preparation(
    *,
    created: str = CREATED,
    stopped: str = STOPPED,
    read_at: str = "2026-10-24T02:05:03+00:00",
    rows: list[dict[str, Any]] | None = None,
    interval: tuple[str, str] = ("2026-10-24T01:00:00+00:00", "2026-10-24T02:00:00+00:00"),
    app: str = APP,
) -> dict[str, Any]:
    """Evidence for one image preparation in its own App, as the Modal adapter records it."""
    return {
        "provider": "modal",
        "sandbox_id": None,
        "sandbox_made": {
            "value": False,
            "source": "recorded",
            "how": "Image preparation; no sandbox.",
        },
        "requested": {"cpu": 2, "memory_mib": 4096, "region": "us", "options": {}},
        "calls": [],
        "provider_times": [
            {
                "kind": "created",
                "at": {"value": created, "source": "provider", "how": "Modal App created_at."},
                "field": "Modal AppLifecycle.created_at",
            },
            {
                "kind": "ended",
                "at": {"value": stopped, "source": "provider", "how": "Modal App stopped_at."},
                "field": "Modal AppLifecycle.stopped_at",
            },
        ],
        "last_seen_alive": None,
        "noticed_gone": None,
        "measured": {},
        "provider_records": [
            {
                "source": SOURCE,
                "read_at": read_at,
                "body": {
                    "namespace": {"workspace": "boxrouter-internal", "environment": "main"},
                    "app_id": app,
                    "app": {"state": "stopped", "created_at": created, "stopped_at": stopped},
                    "preparation": {"key": KEY, "image_id": "im-0001", "outcome": "succeeded"},
                    "sandbox_ids": [],
                    "function_ids": [],
                    "class_ids": [],
                    "interval": {"start": interval[0], "end": interval[1]},
                    "rows": [_row("2026-10-24T01:00:00+00:00", app=app)] if rows is None else rows,
                },
            }
        ],
        "report_target": {
            "sandbox_id": None,
            "created_at": created,
            "identities": [{"scope": "app", "id": app}, {"scope": "account", "id": ACCOUNT}],
        },
    }


def _body(evidence: dict[str, Any]) -> dict[str, Any]:
    body: dict[str, Any] = evidence["provider_records"][0]["body"]
    return body


def _total(evidence: dict[str, Any]) -> str | None:
    result = price(evidence)
    RESULT_VALIDATOR.validate(result)
    if result["total"] is None:
        assert result["label"] == "unknown"
        return None
    assert result["label"] == "reported"
    assert result["total"]["low"] == result["total"]["high"]
    total: str = result["total"]["low"]
    return total


def test_a_preparation_is_its_own_apps_reported_hourly_rows() -> None:
    result = price(preparation())
    RESULT_VALIDATOR.validate(result)
    assert (result["label"], result["total"]) == (
        "reported",
        {"low": "0.01431635", "high": "0.01431635"},
    )
    assert result["reported"]["how"] == (
        f"Modal's hourly billing rows for boxrouter-internal/main App {APP}, proven to hold only "
        f"image preparation {KEY} (succeeded, image im-0001) and no sandbox, function or class."
    )


@pytest.mark.parametrize("outcome", ["failed", "cancelled", "unknown"])
def test_a_preparation_without_an_image_is_still_priced_from_its_app(outcome: str) -> None:
    evidence = preparation()
    _body(evidence)["preparation"] |= {"image_id": None, "outcome": outcome}
    assert _total(evidence) == "0.01431635"
    assert f"({outcome}, no image)" in price(evidence)["reported"]["how"]


def _drop(name: str) -> Any:
    return lambda body: body.pop(name)


def _set(path: tuple[str, ...], value: Any) -> Any:
    def change(body: dict[str, Any]) -> None:
        for key in path[:-1]:
            body = body[key]
        body[path[-1]] = value

    return change


UNPROVEN = {
    "sandbox membership unread": _drop("sandbox_ids"),
    "function membership unread": _drop("function_ids"),
    "class membership unread": _drop("class_ids"),
    "App held a sandbox": _set(("sandbox_ids",), ["sb-1"]),
    "App held a function": _set(("function_ids",), ["fu-1"]),
    "App held a class": _set(("class_ids",), ["cs-1"]),
    "membership is not a list": _set(("sandbox_ids",), None),
    "no App lifecycle": _drop("app"),
    "App not stopped": _set(("app", "state"), "ephemeral"),
    "App without a stop time": _set(("app", "stopped_at"), None),
    "lifecycle without a timezone": _set(("app", "created_at"), "2026-10-24T01:43:29.326784"),
    "lifecycle differs from provider times": _set(
        ("app", "stopped_at"), "2026-10-24T01:46:00+00:00"
    ),
    "no preparation": _drop("preparation"),
    "preparation key not sha256": _set(("preparation", "key"), "abc"),
    "outcome not recorded": _set(("preparation", "outcome"), None),
    "outcome outside the vocabulary": _set(("preparation", "outcome"), "partial"),
    "succeeded without an image": _set(("preparation", "image_id"), None),
    "empty image id": _set(("preparation", "image_id"), ""),
    "preparation with extra fields": _set(("preparation", "sandbox_id"), "sb-1"),
    "another workspace": _set(("namespace", "workspace"), "other"),
    "another environment": _set(("namespace", "environment"), "dev"),
    "row from another App": _set(("rows",), [_row("2026-10-24T01:00:00+00:00", app="ap-other")]),
    "rows unread": _drop("rows"),
}


@pytest.mark.parametrize("change", UNPROVEN.values(), ids=UNPROVEN.keys())
def test_an_unproven_preparation_report_stays_unknown(change: Any) -> None:
    evidence = preparation()
    change(_body(evidence))
    assert _total(evidence) is None


TARGETS = {
    "no report target": lambda target: None,
    "no App identity": lambda target: (
        target | {"identities": [item for item in target["identities"] if item["scope"] != "app"]}
    ),
    "another App identity": lambda target: (
        target | {"identities": [{"scope": "app", "id": "ap-other"}, target["identities"][1]]}
    ),
    "two App identities": lambda target: (
        target | {"identities": [*target["identities"], {"scope": "app", "id": "ap-other"}]}
    ),
    "no account identity": lambda target: target | {"identities": target["identities"][:1]},
    "a sandbox target": lambda target: target | {"sandbox_id": "sb-1"},
}


@pytest.mark.parametrize("change", TARGETS.values(), ids=TARGETS.keys())
def test_a_preparation_needs_a_target_naming_only_its_app_and_account(change: Any) -> None:
    evidence = preparation()
    target = change(deepcopy(evidence["report_target"]))
    if target is None:
        del evidence["report_target"]
    else:
        evidence["report_target"] = target
    assert _total(evidence) is None


def test_a_preparation_read_before_the_revisit_delay_stays_unknown() -> None:
    assert _total(preparation(read_at="2026-10-24T01:55:00+00:00")) is None
    assert _total(preparation(read_at="2026-10-24T01:55:29.522+00:00")) == "0.01431635"


def test_a_sandbox_report_is_never_read_as_a_preparation() -> None:
    sandbox = json.loads((ROOT / "providers/modal/fixtures/best/evidence.json").read_text())
    assert _total(deepcopy(sandbox)) is not None
    zero_members = deepcopy(sandbox)
    zero_members["provider_records"][1]["body"] |= {
        "sandbox_ids": [],
        "function_ids": [],
        "class_ids": [],
        "app": {"state": "stopped", "created_at": CREATED, "stopped_at": STOPPED},
        "preparation": {"key": KEY, "image_id": "im-0001", "outcome": "succeeded"},
    }
    assert _total(zero_members) is None
    untargeted = deepcopy(sandbox)
    untargeted["report_target"]["sandbox_id"] = None
    assert _total(untargeted) is None
    no_sandbox = deepcopy(sandbox)
    no_sandbox["sandbox_id"] = None
    assert _total(no_sandbox) is None


def across_hours(
    rows: list[dict[str, Any]], read_at: str, *, interval_end: str = "2026-10-24T03:00:00+00:00"
) -> dict[str, Any]:
    """A preparation from 01:50 to 02:10, requested from 01:00 to `interval_end`."""
    return preparation(
        created="2026-10-24T01:50:00+00:00",
        stopped="2026-10-24T02:10:00+00:00",
        interval=("2026-10-24T01:00:00+00:00", interval_end),
        rows=rows,
        read_at=read_at,
    )


def test_a_preparation_across_an_hour_sums_both_hourly_rows() -> None:
    rows = [
        _row("2026-10-24T01:00:00+00:00", "0.0125"),
        _row("2026-10-24T02:00:00+00:00", "0.0100"),
    ]
    evidence = across_hours(rows, "2026-10-24T02:20:00+00:00")
    assert _total(evidence) == "0.0225"


def test_a_missing_hour_is_zero_only_once_it_closed_inside_the_request() -> None:
    rows = [_row("2026-10-24T01:00:00+00:00", "0.0125")]
    still_open = across_hours(rows, "2026-10-24T02:30:00+00:00")
    assert _total(still_open) is None
    closed = across_hours(rows, "2026-10-24T03:00:00+00:00")
    assert _total(closed) == "0.0125"
    assert "returned no billing row" in price(closed)["reported"]["how"]
    uncovered = across_hours(
        rows, "2026-10-24T03:00:00+00:00", interval_end="2026-10-24T02:00:00+00:00"
    )
    assert _total(uncovered) is None


def test_a_preparation_with_no_rows_is_zero_only_for_covered_closed_hours() -> None:
    assert _total(preparation(rows=[], read_at="2026-10-24T01:59:00+00:00")) is None
    assert _total(preparation(rows=[], read_at="2026-10-24T02:00:00+00:00")) == "0"
    no_window = preparation(rows=[], read_at="2026-10-24T02:00:00+00:00")
    del _body(no_window)["interval"]
    assert _total(no_window) is None


def test_a_row_outside_the_apps_lifetime_stays_unknown() -> None:
    rows = [_row("2026-10-24T01:00:00+00:00"), _row("2026-10-24T03:00:00+00:00")]
    assert _total(preparation(rows=rows)) is None


def test_composed_totals_count_one_app_hour_once() -> None:
    first = price(preparation())
    again = price(preparation(read_at="2026-10-24T02:35:00+00:00"))
    assert compose([first, again])["total"] == {"low": "0.01431635", "high": "0.01431635"}


def test_composed_totals_with_conflicting_reads_of_one_app_hour_are_unknown() -> None:
    first = price(preparation())
    revised = preparation(
        rows=[_row("2026-10-24T01:00:00+00:00", "0.02")], read_at="2026-10-24T02:35:00+00:00"
    )
    assert compose([first, price(revised)])["total"] is None


def test_a_preparation_and_its_sandbox_compose_and_any_unknown_part_leaves_it_incomplete() -> None:
    sandbox = json.loads((ROOT / "providers/modal/fixtures/best/evidence.json").read_text())
    prepared = price(preparation())
    composed = compose([prepared, price(deepcopy(sandbox))])
    assert composed["total"] == {"low": "0.0286327", "high": "0.0286327"}
    unread = deepcopy(sandbox)
    unread["provider_records"] = unread["provider_records"][:1]
    assert compose([prepared, price(unread)])["total"] is None
    unproven = preparation()
    del _body(unproven)["class_ids"]
    assert compose([price(unproven), price(deepcopy(sandbox))])["total"] is None
