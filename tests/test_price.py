# SPDX-FileCopyrightText: BoxRouter, Inc.
# SPDX-License-Identifier: Apache-2.0
"""Evidence-to-result pricing, fixture parity and deterministic reproduction."""

from __future__ import annotations

import json
from copy import deepcopy
from importlib import import_module
from pathlib import Path
from typing import Any, cast

import pytest
from jsonschema import Draft202012Validator, FormatChecker

from sandbox_provider_pricing import hourly, price
from sandbox_provider_pricing.conformance import evidence_for, load_cases
from sandbox_provider_pricing.providers import billing, provider_ids, rules

ROOT = Path(__file__).resolve().parents[1]
# Goal-8 best fixtures are checked separately by test_status.
FIXTURES = sorted(
    path for path in ROOT.glob("providers/*/fixtures/*/evidence.json") if path.parent.name != "best"
)
ALL_FIXTURES = sorted(ROOT.glob("providers/*/fixtures/*/evidence.json"))
RESULT_VALIDATOR = Draft202012Validator(
    json.loads((ROOT / "schemas" / "result.schema.json").read_text()),
    format_checker=FormatChecker(),
)
USAGE_VALIDATOR = Draft202012Validator(
    json.loads((ROOT / "schemas" / "usage.schema.json").read_text()),
    format_checker=FormatChecker(),
)
COST_VALIDATOR = Draft202012Validator(
    json.loads((ROOT / "schemas" / "cost.schema.json").read_text()),
    format_checker=FormatChecker(),
)
LABEL_ORDER = {"unknown": 0, "estimated": 1, "calculated": 2, "reported": 3}


def _load(path: Path) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(path.read_text()))


def test_fixture_parity_and_result_schema() -> None:
    counts = dict.fromkeys(provider_ids(), 0)
    for evidence_path in FIXTURES:
        counts[evidence_path.parents[2].name] += 1
        result = price(_load(evidence_path))
        expected = _load(evidence_path.parent / "result.json")
        assert {"label": result["label"], "total": result["total"]} == {
            key: expected[key] for key in ("label", "total")
        }
        assert not list(RESULT_VALIDATOR.iter_errors(result))
    expected = {
        "agent37": 3,
        "blaxel": 5,
        "boat": 1,
        "boxd": 1,
        "daytona": 5,
        "e2b": 3,
        "modal": 2,
        "superserve": 6,
        "vercel": 4,
    }
    for provider, count in counts.items():
        assert count == expected.get(provider, 0), provider


def test_all_price_outputs_match_usage_and_cost_schemas() -> None:
    assert ALL_FIXTURES
    for evidence_path in ALL_FIXTURES:
        result = price(_load(evidence_path))
        for side, usage in result["steps"]["usage"].items():
            errors = list(USAGE_VALIDATOR.iter_errors(usage))
            assert not errors, f"{evidence_path} usage.{side}: {errors}"
        for side, cost in result["steps"]["rated"].items():
            errors = list(COST_VALIDATOR.iter_errors(cost))
            assert not errors, f"{evidence_path} rated.{side}: {errors}"


def test_modal_real_app_row_is_reported_after_measured_revisit_delay() -> None:
    evidence = _load(ROOT / "providers/modal/fixtures/best/evidence.json")
    assert (
        evidence["provider_records"][1]["read_at"]
        > evidence["provider_records"][0]["body"]["stopped_at"]
    )
    policy = {
        "after_s": 600,
        "until_s": 604800,
        "interval_s": 3600,
        "rationale": "A measured margin after the latest final billing-row value.",
        "unverified_default": True,
    }
    result = rules("modal").billable(evidence, {"name": "Modal", "revisit": policy})
    assert result["reported"] == {
        "usd": "0.01431635",
        "source": "provider",
        "how": (
            "Modal's hourly billing rows for boxrouter-internal/main App "
            "ap-lWZkAcuA3y5Tn3B2RsXP8e, proven to hold only sandbox "
            "sb-01M5NS7HS82KH89F8J5KTDEYN2."
        ),
    }
    assert result["times"]["start"].source == "provider"
    assert result["times"]["end"].source == "provider"


def test_the_recorded_class_reaches_the_usage_and_leaves_the_bill_alone() -> None:
    evidence = _load(ROOT / "providers/modal/fixtures/best/evidence.json")
    unnamed = price(evidence)
    evidence["requested"]["class"] = "vm"
    named = price(evidence)
    for usage in named["steps"]["usage"].values():
        assert usage["class"]["name"] == "vm"
        assert not list(USAGE_VALIDATOR.iter_errors(usage))
    assert (named["label"], named["total"]) == (unnamed["label"], unnamed["total"])


def test_modal_sandbox_end_is_not_the_billing_hours_end() -> None:
    evidence = _load(ROOT / "providers/modal/fixtures/best/evidence.json")
    steps = price(evidence)["steps"]
    assert steps["times"]["end"]["value"] == "2026-10-24T02:00:00Z"
    assert steps["sandbox_end"] == {
        "value": "2026-10-24T01:45:29.522000Z",
        "source": "provider",
        "how": "The provider's own time: Modal sandbox listing finished_at.",
    }


def test_modal_sandbox_start_is_not_the_billing_hours_start() -> None:
    evidence = _load(ROOT / "providers/modal/fixtures/best/evidence.json")
    steps = price(evidence)["steps"]
    assert steps["times"]["start"]["value"] == "2026-10-24T01:00:00Z"
    assert steps["sandbox_start"]["value"] == "2026-10-24T01:43:29.326784Z"
    assert steps["sandbox_start"]["source"] == "provider"


def test_modal_usage_started_is_the_sandbox_start_not_the_billing_hours() -> None:
    evidence = _load(ROOT / "providers/modal/fixtures/best/evidence.json")
    result = price(evidence)
    assert result["label"] == "reported"
    for usage in result["steps"]["usage"].values():
        assert usage["started"]["at"] == "2026-10-24T01:43:29.326784Z"
        assert usage["started"]["source"] == "provider"
        assert "interval" not in usage["started"]["how"]


def test_modal_without_a_provider_start_uses_the_create_return() -> None:
    evidence = _load(ROOT / "providers/modal/fixtures/best/evidence.json")
    evidence["provider_times"] = [t for t in evidence["provider_times"] if t["kind"] != "created"]
    create = next(call for call in evidence["calls"] if call["name"] == "create")
    sandbox_start = price(evidence)["steps"]["sandbox_start"]
    assert sandbox_start["value"] == "2026-10-24T01:43:29.343000Z"
    assert create["returned_at"]["value"].startswith("2026-10-24T01:43:29.343")
    assert sandbox_start["source"] == "recorded"
    for usage in price(evidence)["steps"]["usage"].values():
        assert usage["started"]["at"] == sandbox_start["value"]
        assert usage["started"]["source"] == "recorded"


def test_modal_without_a_provider_end_uses_the_destroy_return() -> None:
    evidence = _load(ROOT / "providers/modal/fixtures/best/evidence.json")
    evidence["provider_times"] = [t for t in evidence["provider_times"] if t["kind"] != "ended"]
    sandbox_end = price(evidence)["steps"]["sandbox_end"]
    assert sandbox_end["value"] == "2026-10-24T01:45:29.539000Z"
    assert sandbox_end["source"] == "recorded"


def test_modal_keeps_early_or_nonexclusive_app_rows_unknown() -> None:
    evidence = _load(ROOT / "providers/modal/fixtures/best/evidence.json")
    policy = {"after_s": 600, "until_s": 604800}
    too_early = deepcopy(evidence)
    too_early["provider_records"][1]["read_at"] = "2026-10-24T01:55:29.521+00:00"
    early_result = rules("modal").billable(too_early, {"name": "Modal", "revisit": policy})
    assert early_result["reported"] is None

    at_boundary = deepcopy(evidence)
    at_boundary["provider_records"][1]["read_at"] = "2026-10-24T01:55:29.522+00:00"
    boundary_result = rules("modal").billable(at_boundary, {"name": "Modal", "revisit": policy})
    assert boundary_result["reported"]["usd"] == "0.01431635"

    shared_app = deepcopy(evidence)
    shared_app["provider_records"][1]["body"]["sandbox_ids"].append("another-sandbox")
    shared_result = rules("modal").billable(shared_app, {"name": "Modal", "revisit": policy})
    assert shared_result["reported"] is None

    cross_namespace = deepcopy(evidence)
    cross_namespace["provider_records"][1]["body"]["namespace"]["workspace"] = "other-workspace"
    namespace_result = rules("modal").billable(
        cross_namespace, {"name": "Modal", "revisit": policy}
    )
    assert namespace_result["reported"] is None

    incomplete = deepcopy(evidence)
    incomplete["provider_records"][1]["body"]["rows"] = []
    incomplete_result = rules("modal").billable(incomplete, {"name": "Modal", "revisit": policy})
    assert incomplete_result["reported"] is None


def test_modal_reads_the_namespace_from_the_report_target_account_identity() -> None:
    evidence = _load(ROOT / "providers/modal/fixtures/best/evidence.json")
    policy = {"after_s": 600, "until_s": 604800}
    identity = evidence["report_target"]["identities"][0]

    def usd(changed: dict[str, Any]) -> Any:
        result = rules("modal").billable(changed, {"name": "Modal", "revisit": policy})
        return result["reported"] and result["reported"]["usd"]

    assert usd(evidence) == "0.01431635"

    other_env = deepcopy(evidence)
    other_env["report_target"]["identities"][0]["id"] = (
        '{"environment":"dev","workspace":"boxrouter-internal"}'
    )
    assert usd(other_env) is None

    missing = deepcopy(evidence)
    del missing["report_target"]
    assert usd(missing) is None

    no_account = deepcopy(evidence)
    no_account["report_target"]["identities"][0]["scope"] = "sandbox"
    assert usd(no_account) is None

    two_accounts = deepcopy(evidence)
    two_accounts["report_target"]["identities"].append(dict(identity))
    assert usd(two_accounts) is None

    other_sandbox = deepcopy(evidence)
    other_sandbox["report_target"]["sandbox_id"] = "sb-other"
    assert usd(other_sandbox) is None

    for bad in (
        "not json",
        '["main"]',
        '{"workspace":"boxrouter-internal"}',
        '{"workspace":"boxrouter-internal","environment":"main","x":1}',
        '{"workspace":"boxrouter-internal","environment":""}',
    ):
        malformed = deepcopy(evidence)
        malformed["report_target"]["identities"][0]["id"] = bad
        assert usd(malformed) is None

    legacy = deepcopy(evidence)
    del legacy["report_target"]
    legacy["requested"]["options"] = {
        "modal_namespace": {"workspace": "boxrouter-internal", "environment": "main"}
    }
    assert usd(legacy) is None


def test_modal_two_hour_rows_are_summed_for_a_boundary_spanning_sandbox() -> None:
    evidence = _load(ROOT / "providers/modal/fixtures/best/evidence.json")
    evidence["provider_times"][1]["at"]["value"] = "2026-10-24T02:03:28.88+00:00"
    evidence["provider_records"][1]["read_at"] = "2026-10-24T02:13:28.88+00:00"
    evidence["provider_records"][1]["body"]["rows"].append(
        {
            "object_id": "ap-lWZkAcuA3y5Tn3B2RsXP8e",
            "description": "bench-cost-ma1024-11",
            "environment": "main",
            "interval_start": "2026-10-24T02:00:00+00:00",
            "cost": "0.00429512",
            "cost_by_resource": {"CPU": "0.00320844", "Memory": "0.00108668"},
        }
    )
    result = rules("modal").billable(
        evidence,
        {"name": "Modal", "revisit": {"after_s": 600, "until_s": 604800}},
    )
    assert result["reported"]["usd"] == "0.01861147"


def test_modal_covered_empty_hour_is_zero_only_when_the_request_covers_it() -> None:
    evidence = _load(ROOT / "providers/modal/fixtures/best/evidence.json")
    ended = "2026-10-24T02:03:28.88+00:00"
    record = evidence["provider_records"][1]
    record["read_at"] = "2026-10-24T02:13:28.88+00:00"
    record["body"]["interval"] = {
        "start": "2026-10-24T01:00:00+00:00",
        "end": "2026-10-24T03:00:00+00:00",
    }
    evidence["provider_times"][1]["at"]["value"] = ended

    result = rules("modal").billable(
        evidence,
        {"name": "Modal", "revisit": {"after_s": 600, "until_s": 604800}},
    )

    assert result["reported"]["usd"] == "0.01431635"
    assert (
        "The report covered 2026-10-24T02:00:00+00:00 and returned no billing row"
        in result["reported"]["how"]
    )
    assert result["reported"]["how"].endswith("each is read as USD 0.")

    without_interval = deepcopy(evidence)
    del without_interval["provider_records"][1]["body"]["interval"]
    assert (
        rules("modal").billable(
            without_interval,
            {"name": "Modal", "revisit": {"after_s": 600, "until_s": 604800}},
        )["reported"]
        is None
    )

    uncovered = deepcopy(evidence)
    uncovered["provider_records"][1]["body"]["interval"]["end"] = "2026-10-24T02:00:00+00:00"
    assert (
        rules("modal").billable(
            uncovered,
            {"name": "Modal", "revisit": {"after_s": 600, "until_s": 604800}},
        )["reported"]
        is None
    )

    outside_span = deepcopy(evidence)
    outside_span["provider_records"][1]["body"]["rows"].append(
        {
            "object_id": "ap-lWZkAcuA3y5Tn3B2RsXP8e",
            "environment": "main",
            "interval_start": "2026-10-24T03:00:00+00:00",
            "cost": "0.001",
            "cost_by_resource": {"CPU": "0.001"},
        }
    )
    assert (
        rules("modal").billable(
            outside_span,
            {"name": "Modal", "revisit": {"after_s": 600, "until_s": 604800}},
        )["reported"]
        is None
    )


def test_vercel_usage_start_is_normalized_to_utc_z() -> None:
    evidence = _load(ROOT / "providers/vercel/fixtures/best/evidence.json")
    evidence["provider_records"][0]["body"]["startedAt"] = "2026-10-12T12:00:00+00:00"

    result = price(evidence)

    for usage in result["steps"]["usage"].values():
        assert usage["started"]["at"].endswith("Z")
        assert not list(USAGE_VALIDATOR.iter_errors(usage))


def test_e2b_resumed_fixture_does_not_end_at_pause() -> None:
    evidence = _load(ROOT / "providers/e2b/fixtures/paused-no-kill/evidence.json")

    result = price(evidence)

    assert result["steps"]["times"]["end"]["value"] != "2026-10-11T16:03:40Z"


def test_vercel_pause_without_session_records_is_unknown() -> None:
    evidence = _load(ROOT / "providers/vercel/fixtures/paused-no-provider-records/evidence.json")
    result = price(evidence)
    assert (result["label"], result["total"], result["lines"]) == ("unknown", None, [])
    assert all("test fixture" not in row["text"] for row in result["held_back_by"])


def test_hourly_uses_the_selected_price_version() -> None:
    result = hourly("daytona", {"cpu": 2, "memory_mib": 4096})
    assert (result["low"], result["high"]) == ("0.1656", "0.1656")
    assert result["basis_text"] == "allocated CPU and memory"
    assert result["prices"]["version"] == "daytona@2026-10-24-065001Z"
    assert result["source_url"]
    assert result["checked_at"] == "2026-10-24"
    current_vercel = hourly("vercel", {"cpu": 2, "memory_mib": 4096})
    assert current_vercel["prices"]["version"] == "vercel@2026-10-20-055631Z"


def test_price_uses_the_supplied_price_version_pool() -> None:
    price_module = import_module("sandbox_provider_pricing.price")
    evidence = _load(ROOT / "providers/vercel/fixtures/best/evidence.json")
    version = deepcopy(
        next(item for item in price_module.seed_versions() if item["provider"] == "vercel")
    )
    version["version"] = "vercel@test-only"
    version["classes"][0]["rates"]["memory"]["usd"] = "9"

    baseline = price(evidence)
    priced = price(evidence, versions=(version,))

    assert priced["versions"]["prices"] == "vercel@test-only"
    assert priced["total"]["high"] != baseline["total"]["high"]


def _drop_fields(value: Any, path: tuple[str | int, ...] = ()) -> Any:
    if isinstance(value, dict):
        for key in value:
            changed = deepcopy(value)
            del changed[key]
            yield "/".join(map(str, (*path, key))), changed
        for key, child in value.items():
            for dropped, changed in _drop_fields(child, (*path, key)):
                yield dropped, {**value, key: changed}
    elif isinstance(value, list):
        for index, child in enumerate(value):
            for dropped, changed in _drop_fields(child, (*path, index)):
                copy = list(value)
                copy[index] = changed
                yield dropped, copy


def _holds_back_by_the_sandbox_times(evidence_path: Path, field: str) -> bool:
    """A cost report that leaves part of the sandbox out is held back by the sandbox's own times;
    dropping them leaves nothing to show it with (see `usage.covers_sandbox`)."""
    held = evidence_path.parent.name in {"core-cost-report-partial", "core-cost-report-gap"}
    return held and field.split("/")[0] in {"calls", "provider_times"}


def test_dropping_an_evidence_field_never_improves_the_result() -> None:
    for evidence_path in FIXTURES:
        evidence = _load(evidence_path)
        original = price(evidence)
        originally_zero = original["total"] == {"low": "0", "high": "0"}
        for field, reduced in _drop_fields(evidence):
            if _holds_back_by_the_sandbox_times(evidence_path, field):
                continue
            try:
                result = price(reduced)
            except ValueError:
                continue
            assert LABEL_ORDER[result["label"]] <= LABEL_ORDER[original["label"]], field
            if not originally_zero and result["total"] is not None:
                assert result["total"] != {"low": "0", "high": "0"}, field


def test_reported_cost_requires_the_billing_list_price_gate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    price_module = import_module("sandbox_provider_pricing.price")
    report = {"usd": "0.7", "source": "metrics.get", "how": "per-sandbox cost"}

    def with_report(provider: str, fixture: str) -> dict[str, Any]:
        evidence_path = ROOT / "providers" / provider / "fixtures" / fixture / "evidence.json"
        evidence = _load(evidence_path)
        rule_module = rules(provider)
        original = rule_module.billable

        def billable(*args: Any, **kwargs: Any) -> dict[str, Any]:
            usage = cast(dict[str, Any], original(*args, **kwargs))
            return usage | {"reported": report}

        monkeypatch.setattr(rule_module, "billable", billable)
        return evidence

    blaxel_bill = billing("blaxel")
    monkeypatch.setattr(price_module, "billing", lambda _: blaxel_bill)
    reported = price(with_report("blaxel", "deep-swe"))
    assert reported["label"] == "reported"
    assert reported["basis"] == "provider_reported"
    assert reported["total"] == {"low": "0.7", "high": "0.7"}
    assert reported["reported"] == report

    e2b_bill = billing("e2b")
    monkeypatch.setattr(price_module, "billing", lambda _: e2b_bill)
    missing_allocation = price(with_report("e2b", "best"))
    assert missing_allocation["label"] == "unknown"
    assert missing_allocation["basis"] == "list_price_usage"
    assert missing_allocation["total"] is None
    assert missing_allocation["reported"] == report


def test_reproduce_keeps_the_recorded_price_and_rules_versions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    price_module = import_module("sandbox_provider_pricing.price")
    evidence = _load(ROOT / "providers/e2b/fixtures/best/evidence.json")
    original = price(evidence)
    pool = price_module.seed_versions()
    latest = next(item for item in pool if item["version"] == original["versions"]["prices"])
    newer = deepcopy(latest)
    newer.update(
        version="e2b@test-version",
        effective_from="2026-10-12T00:00:00Z",
        retrieved_at="2026-10-12T00:00:00Z",
    )
    newer["classes"][0]["rates"]["memory"]["usd"] = "9"
    monkeypatch.setattr(price_module, "seed_versions", lambda: [*pool, newer])
    current_billing = billing("e2b")
    current_billing["rules_version"] += 1
    monkeypatch.setattr(price_module, "billing", lambda _: current_billing)

    current = price(evidence)
    assert current["versions"]["rules"] == original["versions"]["rules"] + 1
    assert current["versions"]["prices"] == original["versions"]["prices"]
    assert price_module.reproduce(original) == original


def test_e2b_execution_sizes_price_each_event_timestamp_segment() -> None:
    evidence = _load(ROOT / "providers/e2b/fixtures/best/evidence.json")
    for index, cpu, memory in ((1, 1, 512), (3, 4, 2048)):
        evidence["provider_records"][index]["body"]["event_data"]["execution"] = {
            "started_at": "2026-10-11T00:00:00Z",
            "execution_time": 1,
            "vcpu_count": cpu,
            "memory_mb": memory,
        }
    evidence["requested"].update(cpu=99, memory_mib=99999)
    result = price(evidence)
    assert result["label"] == "calculated"
    assert result["total"] == {"low": "0.00078", "high": "0.00078"}
    lines = {row["what"]: row for row in result["lines"]}
    assert (lines["cpu"]["quantity"], lines["memory"]["quantity"]) == ("48", "24")
    assert {row["quantity_source"] for row in result["lines"]} == {"provider"}


def test_e2b_events_api_camelcase_payload_matches_webhook_pricing() -> None:
    evidence = _load(ROOT / "providers/e2b/fixtures/best/evidence.json")
    expected = price(evidence)
    events = []
    for record in evidence["provider_records"]:
        body = deepcopy(record["body"])
        body["sandboxId"] = body.pop("sandbox_id")
        body["eventData"] = body.pop("event_data")
        events.append(body)
    evidence["provider_records"] = [
        {
            "source": "E2B lifecycle API",
            "read_at": "2026-10-11T16:04:15Z",
            "body": events,
        }
    ]
    result = price(evidence)
    assert (result["label"], result["total"]) == (expected["label"], expected["total"])


def test_e2b_call_clocks_do_not_select_a_different_cost_or_rate() -> None:
    evidence = _load(ROOT / "providers/e2b/fixtures/best/evidence.json")
    baseline = price(evidence, as_of="2026-10-11T17:00:00Z")
    for call in evidence["calls"]:
        call["sent_at"]["value"] = "2020-01-01T00:00:00Z"
        call["returned_at"]["value"] = "2030-01-01T00:00:00Z"
    changed = price(evidence, as_of="2026-10-11T17:00:00Z")
    assert changed["total"] == baseline["total"]
    assert changed["versions"]["prices"] == baseline["versions"]["prices"]


def test_vercel_snapshot_record_prices_storage_between_sessions() -> None:
    cases = {case["id"]: case for case in load_cases()}
    missing = price(evidence_for(cases["vercel/synthetic/snapshot-missing"]))
    assert (missing["label"], missing["total"]) == ("unknown", None)
    evidence = evidence_for(cases["vercel/synthetic/snapshot-known"])
    result = price(evidence)
    assert result["label"] == "calculated"
    assert result["total"]["low"] == result["total"]["high"]
    storage = next(row for row in result["lines"] if row["what"] == "snapshot_storage")
    assert storage["quantity"].startswith("0.000182648401826484018264840182648")
    evidence["provider_records"][-1]["body"]["id"] = "unrelated-snapshot"
    assert price(evidence)["total"] is None


def test_vercel_rereading_one_session_does_not_double_count_it() -> None:
    evidence = _load(ROOT / "providers/vercel/fixtures/best/evidence.json")
    expected = price(evidence)
    later = deepcopy(evidence["provider_records"][0])
    later["read_at"] = "2026-10-12T12:08:00Z"
    evidence["provider_records"].append(later)
    assert price(evidence)["total"] == expected["total"]


@pytest.mark.parametrize("provider", provider_ids())
def test_no_provider_records_times_or_reports_never_produce_a_cost(provider: str) -> None:
    evidence = _load(ROOT / f"providers/{provider}/fixtures/best/evidence.json")
    evidence["provider_records"], evidence["provider_times"] = [], []
    evidence["provider_reports"] = {}
    result = price(evidence)
    assert (result["label"], result["total"], result["lines"]) == ("unknown", None, [])
    assert result["held_back_by"]


def _containers(value: object) -> set[int]:
    found: set[int] = set()
    stack = [value]
    while stack:
        item = stack.pop()
        if isinstance(item, (dict, list)):
            found.add(id(item))
            stack.extend(item.values() if isinstance(item, dict) else item)
    return found


def test_price_never_hands_out_the_bundled_price_versions() -> None:
    evidence = _load(ROOT / "providers/e2b/fixtures/best/evidence.json")
    bundle = import_module("sandbox_provider_pricing.versions").bundled_pool()
    before = deepcopy(bundle)
    assert not _containers(price(evidence)) & _containers(bundle)
    assert bundle == before


@pytest.fixture(name="validations")
def fixture_validations(monkeypatch: pytest.MonkeyPatch) -> list[object]:
    """Each document the evidence schema validates from here on."""
    evidence_module = import_module("sandbox_provider_pricing.evidence")
    checked = evidence_module._evidence_validator()
    calls: list[object] = []

    class Counting:
        def iter_errors(self, instance: object) -> Any:
            calls.append(instance)
            return checked.iter_errors(instance)

    monkeypatch.setattr(evidence_module, "_evidence_validator", Counting)
    return calls


@pytest.mark.parametrize(
    "provider",
    [
        pytest.param("daytona", id="a-rule-that-derives-no-evidence"),
        pytest.param("e2b", id="a-rule-that-checks-only-what-it-derived"),
    ],
)
def test_price_validates_its_evidence_once(provider: str, validations: list[object]) -> None:
    price(_load(ROOT / f"providers/{provider}/fixtures/best/evidence.json"))
    assert len(validations) == 1


def test_billable_rules_still_validate_evidence_given_to_them_directly() -> None:
    evidence = _load(ROOT / "providers/daytona/fixtures/best/evidence.json")
    del evidence["provider"]
    with pytest.raises(ValueError, match="provider"):
        import_module("sandbox_provider_pricing.usage").default_billable(evidence)


def test_derived_evidence_is_refused_as_full_validation_would_refuse_it() -> None:
    evidence_module = import_module("sandbox_provider_pricing.evidence")
    base = evidence_module.normalize_evidence(
        _load(ROOT / "providers/e2b/fixtures/best/evidence.json")
    )
    evidence_module.validate_evidence(base)
    bad_time = {"kind": "created", "at": {"value": "not a time"}, "field": "E2B event created"}
    for derived in (
        dict(base) | {"provider_times": [bad_time]},
        dict(base) | {"provider_times": [dict(bad_time, kind="noticed")]},
        dict(base) | {"provider_records": [{"source": ""}]},
    ):
        with pytest.raises(ValueError) as full:
            evidence_module.validate_evidence(derived)
        with evidence_module.validated(base), pytest.raises(ValueError) as partial:
            evidence_module.validate_derived(base, derived)
        assert str(partial.value) == str(full.value)


def test_derived_evidence_with_another_field_is_validated_whole() -> None:
    evidence_module = import_module("sandbox_provider_pricing.evidence")
    base = evidence_module.normalize_evidence(
        _load(ROOT / "providers/e2b/fixtures/best/evidence.json")
    )
    with evidence_module.validated(base), pytest.raises(ValueError, match="unexpected"):
        evidence_module.validate_derived(base, dict(base) | {"unexpected": 1})


def test_pricing_the_same_sandbox_at_a_later_read_validates_nothing_again(
    validations: list[object],
) -> None:
    evidence_module = import_module("sandbox_provider_pricing.evidence")
    first = _load(ROOT / "providers/daytona/fixtures/best/evidence.json")
    later = deepcopy(first)
    for record in later["provider_records"]:
        record["read_at"] = "2030-01-02T03:04:05.678901Z"
    assert first["provider_records"], "the fixture needs a provider record"
    price(first)
    priced = price(later)
    assert len(validations) == 1
    evidence_module._PROVEN.clear()
    assert price(later) == priced


def test_reported_cost_intervals_say_no_billed_seconds_rather_than_waiting() -> None:
    # Modal, Blaxel and Daytona report a sandbox's cost, not its billed seconds. Once that cost is
    # read, an interval without seconds is not waiting for a record; before it, it still is.
    seen = {"reported": 0, "waiting": 0}
    for evidence_path in ALL_FIXTURES:
        expected = _load(evidence_path.parent / "result.json")
        result = price(_load(evidence_path), as_of=expected["as_of"])
        notes = {
            interval["how"]
            for side in ("low", "high")
            for interval in result["steps"]["usage"][side]["intervals"]
            if interval["seconds"] is None
        }
        if not notes:
            continue
        if result["reported"]:
            seen["reported"] += 1
            assert notes == {
                "No billed seconds for this sandbox: the provider reports its cost instead."
            }
        elif any(note.startswith("Waiting for") for note in notes):
            seen["waiting"] += 1
    assert seen["reported"] >= 3
    assert seen["waiting"] >= 1
