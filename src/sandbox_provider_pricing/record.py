# SPDX-FileCopyrightText: BoxRouter, Inc.
# SPDX-License-Identifier: Apache-2.0
"""The one builder from what a consumer stored about a sandbox to the evidence `price()` takes.

A record (`schemas/record.schema.json`) is what Cloud or the benchmark runner keeps about one
sandbox: the provider, its id, the size, class and region asked for, our own call edges, the Core
reports as read, the provider's records and lifecycle times, and an observation time. Both
consumers store these differently; the rules that turn them into evidence are written once here.

- `record_evidence(record)`: the evidence for `price()`.
- `merge_reports(reads)`: several reads of one sandbox's Core reports, as one report envelope.

Nothing here reads a clock or a store.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from copy import deepcopy
from datetime import datetime
from typing import Any, cast

from sandbox_provider_pricing._util import parse_time
from sandbox_provider_pricing.evidence import PROVIDER_TIME_POINTS
from sandbox_provider_pricing.types import Document, JsonObject
from sandbox_provider_pricing.usage import utc_text

REPORT_KINDS = ("cost", "size", "usage")
_SIZE_KEYS = ("cpu", "memory_mib", "disk_mib", "gpu", "gpu_model")
_PROVIDER_TIME_FIELDS = ("kind", "at", "field", "read")
_EDGES = ("sent", "returned")
# Pause and resume are left out: pricing needs what a pause kept, which an edge does not say.
_CALL_CHOICES = (("create", min), ("destroy", max))
_NO_CREATION = {"value": None, "source": "unknown", "how": "No creation observation."}


def record_evidence(record: Mapping[str, Any]) -> JsonObject:
    """The evidence for one sandbox's record, ready for `price()`.

    The record's reports pass through unchanged (`price()` reads Core's own fields), but only
    those with a time they were read at. A report with none of its own takes the newest read
    among the envelope's and its records' times, else the usage report's `observed_at`, else the
    record's `read_at`. The provider's lifecycle times are kept when they are the provider's own
    and a time kind pricing takes; our call edges become `calls`, which only stand in for times
    the provider has not reported and never price a sandbox.
    """
    provider = record.get("provider")
    if not isinstance(provider, str) or not provider:
        raise ValueError("a record needs its provider")
    evidence: JsonObject = {
        "provider": provider,
        "sandbox_id": record.get("sandbox_id"),
        "sandbox_made": dict(_NO_CREATION),
        "requested": _requested(record, provider),
        "calls": _calls(record.get("calls") or ()),
        "provider_times": _provider_times(record.get("provider_times") or ()),
        "last_seen_alive": None,
        "noticed_gone": None,
        "measured": {},
        "provider_records": [deepcopy(dict(item)) for item in record.get("provider_records") or ()],
    }
    if reports := _reports(record):
        evidence["provider_reports"] = reports
    if operations := _operations(record.get("operations") or ()):
        evidence["operations"] = operations
    return evidence


def merge_reports(reads: Iterable[Mapping[str, Any]]) -> JsonObject:
    """Several reads of one sandbox's Core reports, as one `provider_reports` envelope.

    Each read is an envelope with the `read_at` it was made at, and may hold any of `cost`,
    `size`, `usage` and `target`. Reads are taken oldest first. Per kind:

    - A later report replaces an earlier one only when it carries readings or records. An empty
      later read never hides what an earlier one found, and a cost report that is not
      `available` never replaces one that is.
    - Usage records from every read are joined by (id, scope, source), a later read's record
      replacing the same record from an earlier one, because a provider's API pages expire.
    - The report's read time is the time of the read that supplied it (`read_times`); the
      envelope's `read_at` is the newest read's. The target of the newest read that has one stays.
    """
    merged: JsonObject = {}
    times: dict[str, str] = {}
    usage_records: dict[tuple[Any, Any, Any], Any] = {}
    for read in sorted(reads, key=_read_order):
        stamp = read.get("read_at")
        if isinstance(stamp, str):
            merged["read_at"] = stamp
        if "target" in read:
            merged["target"] = deepcopy(read["target"])
        for kind in REPORT_KINDS:
            report = read.get(kind)
            if not isinstance(report, Mapping):
                continue
            if kind == "usage":
                for item in report.get("records") or ():
                    usage_records[(item["id"], item["scope"], item["source"])] = deepcopy(item)
            if kind in merged and not _replaces(kind, merged[kind], report):
                continue
            merged[kind] = deepcopy(dict(report))
            if own := (read.get("read_times") or {}).get(kind) or stamp:
                times[kind] = own
            else:
                times.pop(kind, None)
    if usage_records:
        merged["usage"] = {**merged.get("usage", {}), "records": list(usage_records.values())}
    if times:
        merged["read_times"] = times
    return merged


def _read_order(read: Mapping[str, Any]) -> tuple[bool, datetime]:
    """Reads without a time come first, in the order given; the rest by when they were read."""
    stamp = read.get("read_at")
    return (True, parse_time(stamp)) if isinstance(stamp, str) else (False, datetime.min)


def _replaces(kind: str, kept: Mapping[str, Any], later: Mapping[str, Any]) -> bool:
    if not later.get("readings") and not later.get("records"):
        return False
    return not (kind == "cost" and kept.get("status") == "available" != later.get("status"))


def _reports(record: Mapping[str, Any]) -> JsonObject:
    """The record's Core reports, each with a time it was read at, or nothing when it has none."""
    given = record.get("reports") or {}
    reports: JsonObject = {
        name: deepcopy(given[name])
        for name in (*REPORT_KINDS, "target", "read_times")
        if name in given
    }
    if not any(name in reports for name in (*REPORT_KINDS, "target")):
        return {}
    observed = _observed(given, record.get("read_at"))
    if observed is not None:
        reports["read_at"] = observed
    return reports


def _observed(reports: Mapping[str, Any], fallback: Any) -> str | None:
    """The time reports without their own were read: as a time, never as sorted text, where
    `…:10Z` would sort after `…:10.298668Z`."""
    reads = [reports["read_at"]] if isinstance(reports.get("read_at"), str) else []
    for kind in REPORT_KINDS:
        for item in (reports.get(kind) or {}).get("records") or ():
            if isinstance(item, Mapping) and isinstance(item.get("read_at"), str):
                reads.append(item["read_at"])
    if reads:
        return _utc(max(reads, key=_moment))
    usage = reports.get("usage")
    stamp = usage.get("observed_at") if isinstance(usage, Mapping) else None
    stamp = stamp if isinstance(stamp, str) else fallback
    return _utc(stamp) if isinstance(stamp, str) else None


def _moment(text: str) -> datetime:
    """A read time as a point in time, which must say its zone."""
    moment = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if moment.utcoffset() is None:
        raise ValueError("Provider observation time must include a timezone")
    return moment


def _utc(text: str) -> str:
    return cast(str, utc_text(_moment(text)))


def region_name(region: object, provider: str) -> str | None:
    """A region without our `<provider>:` prefix, as pricing names it; None when there is none.

    Only the provider's own prefix goes: another provider's stays part of the name.
    """
    if isinstance(region, str) and (name := region.removeprefix(f"{provider}:")):
        return name
    return None


def _requested(record: Mapping[str, Any], provider: str) -> JsonObject:
    """What was asked for, as pricing names it: sizes in MiB, the region without our prefix."""
    asked = record.get("requested") or {}
    found: JsonObject = {"options": {}}
    found.update({key: asked[key] for key in _SIZE_KEYS if asked.get(key) is not None})
    if name := region_name(asked.get("region"), provider):
        found["region"] = name
    if isinstance(asked.get("class"), str) and asked["class"]:
        found["class"] = asked["class"]
    return found


def _provider_times(times: Iterable[Mapping[str, Any]]) -> list[Document]:
    """The provider's own lifecycle times of a kind pricing takes, without our extra fields."""
    return [
        {key: item[key] for key in _PROVIDER_TIME_FIELDS if key in item}
        for item in times
        if item.get("kind") in PROVIDER_TIME_POINTS
        and (item.get("at") or {}).get("source") == "provider"
    ]


def _calls(edges: Sequence[Mapping[str, Any]]) -> list[Document]:
    """One returned call per name: the first create and the last destroy, each with its send.

    A kept return is `returned`: an edge is only recorded once the call's answer came back. The
    send is the latest one at or before that return.
    """
    found: dict[str, dict[str, list[tuple[datetime, Mapping[str, Any]]]]] = {}
    for edge in edges:
        if edge.get("edge") in _EDGES:
            found.setdefault(edge["name"], {}).setdefault(edge["edge"], []).append(
                (parse_time(edge["at"]), edge)
            )
    calls: list[Document] = []
    for name, choose in _CALL_CHOICES:
        returns = found.get(name, {}).get("returned")
        if not returns:
            continue
        returned_at, returned = choose(returns, key=lambda item: item[0])
        sent = [item for item in found[name].get("sent", []) if item[0] <= returned_at]
        calls.append(
            {
                "name": name,
                "sent_at": _edge(max(sent, key=lambda item: item[0])[1]) if sent else None,
                "returned_at": _edge(returned),
                "outcome": "returned",
            }
        )
    return calls


def _edge(edge: Mapping[str, Any]) -> Document:
    at = {"value": utc_text(parse_time(edge["at"])), "source": "recorded"}
    return at | ({"how": edge["how"]} if edge.get("how") else {})


def _operations(operations: Iterable[Mapping[str, Any]]) -> list[Document]:
    return [{"name": item["name"], "outcome": item["outcome"]} for item in operations]
