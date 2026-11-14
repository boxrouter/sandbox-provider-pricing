# SPDX-FileCopyrightText: BoxRouter, Inc.
# SPDX-License-Identifier: Apache-2.0
"""Evidence accepted by the pricing interface and its shared lifecycle time vocabulary."""

from __future__ import annotations

import hashlib
import json
import marshal
import re
import threading
from collections import OrderedDict
from collections.abc import Iterable, Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import fields, is_dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from functools import cache
from typing import Any, cast

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError

from sandbox_provider_pricing._util import bundled_schema, parse_time, providers_root
from sandbox_provider_pricing.types import Document, JsonObject


def decimal_total(values: Iterable[object]) -> str:
    """Sum JSON numbers exactly, returning a non-negative decimal string."""
    total = Decimal(0)
    for value in values:
        if isinstance(value, bool) or not isinstance(value, int | float | str):
            raise ValueError("decimal value must be a number")
        try:
            amount = Decimal(str(value))
        except InvalidOperation:
            raise ValueError("decimal value must be a number") from None
        if not amount.is_finite() or amount < 0:
            raise ValueError("decimal value must be finite and not negative")
        total += amount
    return format(total, "f")


@cache
def _schema() -> JsonObject:
    return _with_record_rules(bundled_schema("evidence"))


def _with_record_rules(schema: JsonObject) -> JsonObject:
    """Add each provider's own `record-rules.json` to the rules every provider record meets."""
    rules: list[Any] = []
    for folder in sorted(providers_root().iterdir(), key=lambda item: item.name):
        declared = folder / "record-rules.json"
        if folder.is_dir() and declared.is_file():
            rules.extend(json.loads(declared.read_text(encoding="utf-8")))
    if rules:
        schema["properties"]["provider_records"]["items"]["allOf"] = rules
    return schema


TIME_POINTS = tuple(_schema()["$defs"]["time_point"]["enum"])
CALL_NAMES = tuple(_schema()["properties"]["calls"]["items"]["properties"]["name"]["enum"])
CERTAINTY = ("provider", "measured", "recorded", "published", "calculated", "unknown")
_CALL_TIME_POINTS = {f"{name}_{edge}" for name in CALL_NAMES for edge in ("sent", "returned")}
PROVIDER_TIME_POINTS = tuple(
    point
    for point in TIME_POINTS
    if point not in _CALL_TIME_POINTS | {"last_seen_alive", "noticed_gone"}
)


def _message(error: ValidationError) -> str:
    path = "/".join(map(str, error.absolute_path)) or "<root>"
    return f"{path}: {error.message}"


@cache
def _evidence_validator() -> Draft202012Validator:
    return Draft202012Validator(_schema())


# The evidence object `price()` has just validated, while its rules run on it.
_VALIDATED: ContextVar[object | None] = ContextVar("validated_evidence", default=None)


@contextmanager
def validated(evidence: Document) -> Iterator[None]:
    """While the block runs, `validate_evidence` passes this exact, already-checked object."""
    token = _VALIDATED.set(evidence)
    try:
        yield
    finally:
        _VALIDATED.reset(token)


# Evidence already proven valid, by a digest of its JSON with each provider record's `read_at`
# left out. Validation is a pure function of the document, and in the evidence schema a record's
# `read_at` is a timestamp that no other keyword reads (a test checks this), so evidence equal to
# valid evidence apart from those times is valid exactly when each of its own times is valid.
# A caller that prices the same sandbox at each read changes only those times. Failures are
# never remembered.
_PROVEN: OrderedDict[bytes, None] = OrderedDict()
_PROVEN_LOCK = threading.Lock()
_PROVEN_LIMIT = 65_536


@cache
def _timestamp_pattern() -> re.Pattern[str]:
    """The schema's timestamp: a string its pattern finds (format is not asserted, as validation
    runs without a format checker). A test holds this to the schema's own validator."""
    definition = _schema()["$defs"]["timestamp"]
    if (
        set(definition) - {"type", "format", "pattern", "description"}
        or definition["type"] != "string"
    ):
        raise ValueError("the evidence timestamp is no longer a pattern-checked string")
    return re.compile(definition["pattern"])


def _is_timestamp(value: object) -> bool:
    return isinstance(value, str) and _timestamp_pattern().search(value) is not None


def _without_read_times(records: object, times: list[Any]) -> object:
    if not isinstance(records, list):
        return records
    kept: list[Any] = []
    for record in records:
        if isinstance(record, Mapping) and "read_at" in record:
            times.append(record["read_at"])
            kept.append({**record, "read_at": None})
        else:
            kept.append(record)
    return kept


def _proof(scope: str, value: object) -> tuple[bytes, list[Any]] | None:
    """The digest naming `value` (all evidence, or one field) without its records' read times."""
    times: list[Any] = []
    if scope == "provider_records":
        value = _without_read_times(value, times)
    elif not scope and isinstance(value, Mapping) and "provider_records" in value:
        value = {**value, "provider_records": _without_read_times(value["provider_records"], times)}
    # `marshal` format 2 writes every value with its type and each dict in its own order, so equal
    # bytes mean equal values of equal types: a reordered object only misses and is validated again.
    try:
        payload = marshal.dumps([scope, value], 2)
    except ValueError:
        return None
    return hashlib.blake2s(payload, digest_size=16).digest(), times


def _proven(proof: tuple[bytes, list[Any]] | None) -> bool:
    if proof is None:
        return False
    digest, times = proof
    with _PROVEN_LOCK:
        if digest not in _PROVEN:
            return False
        _PROVEN.move_to_end(digest)
    return all(_is_timestamp(time) for time in times)


def _remember(proof: tuple[bytes, list[Any]] | None) -> None:
    if proof is None:
        return
    with _PROVEN_LOCK:
        _PROVEN[proof[0]] = None
        while len(_PROVEN) > _PROVEN_LIMIT:
            _PROVEN.popitem(last=False)


def _check_provider_time_kinds(provider_times: Iterable[Mapping[str, Any]], prefix: str) -> None:
    for index, provider_time in enumerate(provider_times):
        if provider_time["kind"] not in PROVIDER_TIME_POINTS:
            raise ValueError(
                f"{prefix}{index}/kind: {provider_time['kind']!r} is not a provider time point"
            )


def validate_evidence(evidence: Document) -> None:
    """Validate evidence against its bundled schema plus the provider-time subset rule."""
    if _VALIDATED.get() is evidence:
        return
    if not isinstance(evidence, Mapping):
        raise TypeError("evidence must be an object")
    proof = _proof("", evidence)
    if _proven(proof):
        return
    error = next(_evidence_validator().iter_errors(evidence), None)
    if error is not None:
        raise ValueError(_message(error))
    _check_provider_time_kinds(evidence["provider_times"], "provider_times/")
    _remember(proof)


@cache
def _property_validator(name: str) -> Draft202012Validator:
    schema = _schema()
    return Draft202012Validator(
        {"$schema": schema["$schema"], "$defs": schema["$defs"], **schema["properties"][name]}
    )


def validate_derived(base: Document, derived: Document) -> None:
    """Validate `derived`, evidence a rule built from `base` by replacing some of its values.

    When `price()` has just validated `base` and `derived` has the same fields, only the values
    that are not `base`'s own objects are checked, each against its field's schema: the evidence
    schema constrains nothing across fields, so that is the whole check. Otherwise all of
    `derived` is validated.
    """
    if _VALIDATED.get() is not base or set(derived) != set(base):
        validate_evidence(derived)
        return
    for name, value in derived.items():
        if value is base[name]:
            continue
        proof = _proof(name, value)
        if _proven(proof):
            continue
        error = next(_property_validator(name).iter_errors(value), None)
        if error is not None:
            raise ValueError(f"{name}/{_message(error)}".replace("/<root>", ""))
        if name == "provider_times":
            _check_provider_time_kinds(value, "provider_times/")
        _remember(proof)


#: Exact JSON scalar types: never a dataclass, Mapping, sequence, Decimal or datetime.
_JSON_SCALARS = frozenset({str, int, float, bool, type(None)})


def _json_record(value: Any) -> Any:
    """Serialize Core report dataclasses without importing Core or interpreting meters."""
    # Plain JSON, most of the evidence, takes the branch `_core_value` would choose for it.
    kind = type(value)
    if kind is dict:
        return {key: _json_record(item) for key, item in value.items()}
    if kind is list:
        return [_json_record(item) for item in value]
    if kind in _JSON_SCALARS:
        return value
    return _core_value(value)


def _core_value(value: Any) -> Any:
    """`_json_record` for every value that is not exactly a dict, list or JSON scalar."""
    if is_dataclass(value) and not isinstance(value, type):
        return {item.name: _json_record(getattr(value, item.name)) for item in fields(value)}
    if isinstance(value, Mapping):
        return {key: _json_record(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_json_record(item) for item in value]
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, datetime):
        if value.utcoffset() is None:
            raise ValueError("Core report timestamps must be timezone-aware")
        return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
    return value


def _core_provider_records(records: Any) -> list[JsonObject]:
    """Core `CostReport.records` kept as provider records: the same source, read_at and body."""
    if not isinstance(records, list):
        raise ValueError("provider_reports.cost.records must be a list")
    kept: list[JsonObject] = []
    for record in records:
        if isinstance(record, Mapping) and "body" not in record and "body_json" in record:
            # A Core ProviderRecord object serializes its body as the JSON string it holds.
            try:
                record = {**record, "body": json.loads(record["body_json"])}
            except (TypeError, ValueError):
                raise ValueError("provider record body_json must be JSON") from None
            del record["body_json"]
        if not isinstance(record, Mapping) or set(record) != {"source", "read_at", "body"}:
            raise ValueError("provider record needs source, read_at and an object body")
        if (
            not isinstance(record["source"], str)
            or not record["source"]
            or not isinstance(record["read_at"], str)
            or not isinstance(record["body"], Mapping)
        ):
            raise ValueError("provider record needs source, read_at and an object body")
        kept.append(dict(record))
    return kept


def _bundle_read_time(reports: Mapping[str, Any], needed: bool) -> Any:
    """The read time for a report without its own: `read_at`, else the usage report's
    `observed_at` (the form pricing 0.4.39 documented). Both are input times, never a clock.

    `observed_at` is a field of Core's report body and may be null (events still pending), so it
    is checked only when `needed`: some present report has no time of its own.
    """
    if "read_at" in reports:
        if not _is_timestamp(reports["read_at"]):
            raise ValueError("provider_reports.read_at must be a timestamp")
        return reports["read_at"]
    if not needed:
        return None
    usage = reports.get("usage")
    if not isinstance(usage, Mapping) or "observed_at" not in usage:
        return None
    if not _is_timestamp(usage["observed_at"]):
        raise ValueError("provider_reports.usage.observed_at must be a timestamp")
    return usage["observed_at"]


def normalize_evidence(evidence: Document) -> JsonObject:
    """Accept collected Core reports; only serialize the transport envelope here."""
    normalized = _json_record(evidence)
    reports = normalized.pop("provider_reports", None)
    if reports is None:
        return cast(JsonObject, normalized)
    if not isinstance(reports, Mapping):
        raise ValueError("provider_reports must contain selected Core reports")
    kinds = ("cost", "size", "usage")
    read_times = reports.get("read_times", {})
    if not isinstance(read_times, Mapping):
        raise ValueError("provider_reports.read_times must be an object")
    for kind, stamp in read_times.items():
        if kind not in kinds or kind not in reports or not _is_timestamp(stamp):
            raise ValueError(
                "provider_reports.read_times must map present Core report kinds to timestamps"
            )
    bundle = _bundle_read_time(
        reports, any(kind in reports and kind not in read_times for kind in kinds)
    )
    defaults: JsonObject = {
        "sandbox_made": {"value": None, "source": "unknown", "how": "No creation observation."},
        "requested": {"options": {}},
        "calls": [],
        "provider_times": [],
        "last_seen_alive": None,
        "noticed_gone": None,
        "measured": {},
        "provider_records": [],
    }
    normalized = defaults | normalized
    records = list(normalized["provider_records"])
    if "target" in reports:
        normalized["report_target"] = reports["target"]
    for kind in kinds:
        if kind not in reports:
            continue
        report = reports[kind]
        if not isinstance(report, Mapping) or report.get("status") not in (
            "available",
            "unknown",
            "unavailable",
        ):
            raise ValueError(f"provider_reports.{kind} must be a selected Core report")
        read_at = read_times.get(kind, bundle)
        if read_at is None:
            raise ValueError(
                f"provider_reports.{kind} needs read_times.{kind}, read_at or usage.observed_at"
            )
        records.append({"source": f"core.{kind}", "read_at": read_at, "body": report})
        if kind == "cost":
            records.extend(_core_provider_records(report.get("records", [])))
    normalized["provider_records"] = records
    return cast(JsonObject, normalized)


def core_report(evidence: Document, kind: str) -> JsonObject | None:
    """The latest serialized Core report of one kind, including explicit missing statuses."""
    records = [item for item in evidence["provider_records"] if item["source"] == f"core.{kind}"]
    if not records:
        return None
    record = max(records, key=lambda item: parse_time(item["read_at"]))
    body = record["body"]
    return cast(JsonObject, body) if isinstance(body, dict) else None


def sandbox_cost_readings(report: Document, *, source: str, meter: str) -> list[Any]:
    """An available Core cost report's readings, if every one is this sandbox's USD `meter`
    from `source` with an amount; otherwise none."""
    readings = report.get("readings", [])
    if report["status"] != "available" or not readings:
        return []
    if all(
        row.get("amount") is not None
        and row.get("scope") == "sandbox"
        and row.get("currency") == "USD"
        and row.get("source") == source
        and row.get("meter") == meter
        for row in readings
    ):
        return list(readings)
    return []


def report_number(value: Any, *, integer: bool = False) -> int | float:
    """A serialized Core decimal, validated before conversion to a usage quantity."""
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
        raise ValueError("Core report quantity must be finite and non-negative")
    try:
        number = Decimal(str(value))
    except InvalidOperation as error:
        raise ValueError("Core report quantity must be finite and non-negative") from error
    if not number.is_finite() or number < 0 or (integer and number != number.to_integral_value()):
        raise ValueError("Core report quantity must be finite, non-negative and match its unit")
    return int(number) if number == number.to_integral_value() else float(number)
