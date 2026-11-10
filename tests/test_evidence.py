# SPDX-FileCopyrightText: BoxRouter, Inc.
# SPDX-License-Identifier: Apache-2.0
"""The shared evidence time vocabulary and benchmark call-time compatibility."""

import json
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator

from sandbox_provider_pricing import evidence as evidence_module
from sandbox_provider_pricing.evidence import (
    TIME_POINTS,
    decimal_total,
    validate_evidence,
)

ROOT = Path(__file__).resolve().parents[1]


def evidence(**changes: Any) -> dict[str, Any]:
    sample: dict[str, Any] = {
        "provider": "example",
        "sandbox_made": {"value": True, "source": "recorded", "how": "create succeeded"},
        "requested": {"cpu": 2, "memory_mib": 4096, "region": "iad", "options": {}},
        "calls": [],
        "provider_times": [],
        "last_seen_alive": None,
        "noticed_gone": None,
        "measured": {},
        "provider_records": [],
    }
    sample.update(changes)
    return sample


def test_evidence_schema_is_valid_json_schema_2020_12() -> None:
    schema = json.loads((ROOT / "schemas" / "evidence.schema.json").read_text())
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    Draft202012Validator.check_schema(schema)


def test_minimal_evidence_validates_against_the_schema() -> None:
    schema = json.loads((ROOT / "schemas" / "evidence.schema.json").read_text())
    errors = list(Draft202012Validator(schema).iter_errors(evidence()))
    assert errors == []


def test_provider_record_keeps_an_array_response_body() -> None:
    validate_evidence(
        evidence(
            provider_records=[
                {
                    "source": "Daytona usage API",
                    "read_at": "2026-10-11T12:00:00Z",
                    "body": [
                        {
                            "startAt": "2026-10-11T11:00:00Z",
                            "endAt": "2026-10-11T12:00:00Z",
                            "price": 1,
                        }
                    ],
                }
            ]
        )
    )


def test_decimal_total_adds_provider_amounts_without_float_rounding() -> None:
    assert decimal_total([0.0021, 0.0015]) == "0.0036"


def test_time_points_has_the_shared_clock_and_provider_vocabulary() -> None:
    assert len(TIME_POINTS) == 19
    assert TIME_POINTS[:10] == (
        "create_sent",
        "create_returned",
        "pause_sent",
        "pause_returned",
        "resume_sent",
        "resume_returned",
        "destroy_sent",
        "destroy_returned",
        "last_seen_alive",
        "noticed_gone",
    )
    assert TIME_POINTS[10:] == (
        "created",
        "started",
        "ready",
        "paused",
        "resumed",
        "stopped",
        "ended",
        "billed_start",
        "billed_end",
    )


def test_evidence_rejects_undefined_lifecycle_and_provider_times() -> None:
    call = {
        "name": "read_times",
        "sent_at": None,
        "returned_at": None,
        "outcome": "returned",
    }
    with pytest.raises(ValueError, match="is not one of"):
        validate_evidence(evidence(calls=[call]))
    with pytest.raises(ValueError, match="'deleted' is not one of"):
        validate_evidence(
            evidence(
                provider_times=[
                    {
                        "kind": "deleted",
                        "at": {
                            "value": "2026-10-11T12:00:00Z",
                            "source": "provider",
                            "how": "provider event",
                        },
                        "field": "deletedAt",
                    }
                ]
            )
        )


def test_evidence_schema_rejects_timestamps_without_a_timezone() -> None:
    with pytest.raises(ValueError, match="not valid under any"):
        validate_evidence(
            evidence(
                provider_times=[
                    {
                        "kind": "created",
                        "at": {
                            "value": "2026-10-11T12:00:00",
                            "source": "provider",
                            "how": "provider event",
                        },
                        "field": "createdAt",
                    }
                ]
            )
        )


def test_evidence_keeps_provider_times_to_provider_event_points() -> None:
    with pytest.raises(ValueError, match="not a provider time point"):
        validate_evidence(
            evidence(
                provider_times=[
                    {
                        "kind": "create_sent",
                        "at": {
                            "value": "2026-10-11T12:00:00Z",
                            "source": "provider",
                            "how": "provider event",
                        },
                        "field": "createdAt",
                    }
                ]
            )
        )


def _record(read_at: object) -> dict[str, Any]:
    return {"source": "Daytona usage API", "read_at": read_at, "body": {"price": 1}}


def _fresh_error(document: dict[str, Any]) -> str:
    evidence_module._PROVEN.clear()
    with pytest.raises(ValueError) as raised:
        validate_evidence(document)
    return str(raised.value)


def test_a_record_read_time_is_only_a_timestamp_no_other_keyword_reads() -> None:
    # Proven evidence skips validation when only its records' read times differ; that is exact
    # only while `read_at` is this one timestamp field. A schema change here needs a new look.
    schema = json.loads((ROOT / "schemas" / "evidence.schema.json").read_text())
    record = schema["properties"]["provider_records"]["items"]
    assert record["properties"] == {
        "source": {"type": "string", "minLength": 1},
        "read_at": {"$ref": "#/$defs/timestamp"},
        "body": {},
    }
    # Provider rules for records are added from each provider's `record-rules.json`; none may
    # read `read_at`.
    composed = evidence_module._schema()["properties"]["provider_records"]["items"]
    assert composed["allOf"][0]["if"] == {
        "properties": {"source": {"const": "Modal Workspace.billing.report"}},
        "required": ["source"],
    }
    assert "read_at" not in json.dumps(composed["allOf"])
    # The transport envelope is removed before normalized evidence validation. Its independent
    # definition must stay unreachable from the normalized schema and its proof cache.
    schema["$defs"].pop("provider_reports")
    assert "#/$defs/provider_reports" not in json.dumps(schema)
    assert json.dumps(schema).count('"read_at"') == 2
    assert "read_at" not in json.dumps(schema["$defs"]["timestamp"])


def test_proven_evidence_still_checks_each_new_read_time() -> None:
    validate_evidence(evidence(provider_records=[_record("2026-10-11T12:00:00Z")]))
    validate_evidence(evidence(provider_records=[_record("2026-10-12T08:30:00.123456Z")]))
    assert len(evidence_module._PROVEN) == 1
    for bad in ("yesterday", None, 7):
        document = evidence(provider_records=[_record(bad)])
        with pytest.raises(ValueError) as raised:
            validate_evidence(document)
        assert str(raised.value) == _fresh_error(document)
        validate_evidence(evidence(provider_records=[_record("2026-10-11T12:00:00Z")]))


def test_invalid_evidence_is_never_remembered() -> None:
    document = evidence(provider="")
    for _ in range(2):
        with pytest.raises(ValueError):
            validate_evidence(document)
    assert not evidence_module._PROVEN


def test_other_changes_are_validated_again() -> None:
    validate_evidence(evidence(provider_records=[_record("2026-10-11T12:00:00Z")]))
    with pytest.raises(ValueError):
        validate_evidence(
            evidence(provider_records=[{**_record("2026-10-11T12:00:00Z"), "extra": 1}])
        )
    with pytest.raises(ValueError):
        validate_evidence(evidence(provider_records=[_record("2026-10-11T12:00:00Z")], calls=7))


def test_derived_records_still_check_each_new_read_time() -> None:
    base = evidence(provider_records=[_record("2026-10-11T12:00:00Z")])
    validate_evidence(base)
    with evidence_module.validated(base):
        evidence_module.validate_derived(
            base, dict(base) | {"provider_records": [_record("2026-10-12T00:00:00Z")]}
        )
        evidence_module.validate_derived(
            base, dict(base) | {"provider_records": [_record("2026-10-13T00:00:00Z")]}
        )
        with pytest.raises(ValueError, match="provider_records/0/read_at"):
            evidence_module.validate_derived(
                base, dict(base) | {"provider_records": [_record("later")]}
            )


def test_the_timestamp_check_accepts_exactly_what_the_schema_does() -> None:
    schema = json.loads((ROOT / "schemas" / "evidence.schema.json").read_text())
    validator = Draft202012Validator({"$schema": schema["$schema"], **schema["$defs"]["timestamp"]})
    samples: list[Any] = [
        "2026-10-11T12:00:00Z",
        "2026-10-11T12:00:00.123456Z",
        "2026-10-11T12:00:00+02:00",
        "2026-13-45T99:99:99Z",
        "2026-10-11 12:00:00Z",
        "2026-10-11T12:00Z",
        " 2026-10-11T12:00:00Z",
        "2026-10-11T12:00:00Z\n",
        "",
        "later",
        None,
        7,
        1.5,
        True,
        ["2026-10-11T12:00:00Z"],
        {"at": "2026-10-11T12:00:00Z"},
    ]
    for sample in samples:
        assert evidence_module._is_timestamp(sample) is validator.is_valid(sample), sample
