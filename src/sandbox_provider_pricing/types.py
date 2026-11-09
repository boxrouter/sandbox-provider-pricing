# SPDX-FileCopyrightText: BoxRouter, Inc.
# SPDX-License-Identifier: Apache-2.0
"""The JSON shapes this package reads and returns.

Everything here is plain JSON. `Document` is an object read as input, such as a price version or
a usage document. `JsonObject` is an object this package builds and may still change. The typed
dictionaries name the documents passed between steps.
"""

import marshal
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any, NotRequired, TypedDict, TypeVar, cast

Document = Mapping[str, Any]
JsonObject = dict[str, Any]
_Tree = TypeVar("_Tree")


def json_copy(value: _Tree) -> _Tree:
    """A deep copy of a tree of dicts, lists and scalars, as `copy.deepcopy` makes it.

    The bundled billing and price documents are such trees with no part shared between two places
    (a test checks), so this is the same copy, made without `deepcopy`'s bookkeeping.
    """
    if isinstance(value, dict):
        return cast(_Tree, {key: json_copy(item) for key, item in value.items()})
    if isinstance(value, list):
        return cast(_Tree, [json_copy(item) for item in value])
    return value


#: Each bundled document's serialized form, kept beside the document so its id stays its own.
_SERIALIZED: dict[int, tuple[object, bytes]] = {}


def bundled_copy(document: _Tree) -> _Tree:
    """`json_copy(document)` for a bundled document, which never changes once loaded.

    The document is serialized once per process with `marshal` format 2, which records no shared
    references, so each copy is one `marshal.loads`: an equal tree sharing no container with the
    document or another copy, as `json_copy` makes it, without walking it in Python.
    """
    found = _SERIALIZED.get(id(document))
    if found is None or found[0] is not document:
        try:
            found = (document, marshal.dumps(cast(Any, document), 2))
        except ValueError:
            return json_copy(document)
        _SERIALIZED[id(document)] = found
    return cast(_Tree, marshal.loads(found[1]))


class Evidence(TypedDict):
    """One sandbox's requested size, lifecycle evidence and provider records."""

    provider: str
    sandbox_id: NotRequired[str | None]
    sandbox_made: JsonObject
    requested: JsonObject
    calls: list[JsonObject]
    provider_times: list[JsonObject]
    last_seen_alive: JsonObject | None
    noticed_gone: JsonObject | None
    deadline: NotRequired[JsonObject | None]
    report_target: NotRequired[JsonObject]
    measured: JsonObject
    provider_records: list[JsonObject]


@dataclass(frozen=True)
class TimeValue:
    """An exact provider time, or a missing time with its reason."""

    value: datetime | None
    source: str
    how: str


class BillableUsage(TypedDict):
    """What a provider's rules derive from evidence: usage at each end of what is known.

    `low` and `high` are usage documents (`schemas/usage.schema.json`). `times` holds the start
    and end used to choose a price version, and `reported` the provider's own cost, if any.
    `sandbox_start` and `sandbox_end` are the sandbox's own times when `times` carries a cost
    report's period instead.
    """

    low: JsonObject
    high: JsonObject
    times: dict[str, TimeValue]
    reported: JsonObject | None
    sandbox_start: NotRequired[TimeValue]
    sandbox_end: NotRequired[TimeValue]


class Finding(TypedDict):
    """Why a cost is held back: a code, the resource it is about, and a sentence."""

    code: str
    resource: str
    text: str


class Cost(TypedDict):
    """One usage document rated at one price version (`schemas/cost.schema.json`)."""

    label: str
    total: dict[str, str] | None
    lines: list[JsonObject]
    held_back_by: list[Finding]
    exclusions: list[str]
    price_version: str | None
    as_of: str
