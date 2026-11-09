# SPDX-FileCopyrightText: BoxRouter, Inc.
# SPDX-License-Identifier: Apache-2.0
"""Compose price results, of one sandbox's resources or of several sandboxes, into one cost."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from copy import deepcopy
from decimal import Decimal, InvalidOperation
from typing import Any, cast

from sandbox_provider_pricing._util import decimal_text
from sandbox_provider_pricing.providers import billing, rules
from sandbox_provider_pricing.types import Document, JsonObject

BilledHours = Callable[..., list[tuple[str, str, str]] | None]
_LABEL_ORDER = {"unknown": 0, "calculated": 1, "reported": 2}


def compose(results: Iterable[Document]) -> JsonObject:
    """Compose every required result while retaining each original result.

    The results may be the resources of one sandbox or the sandboxes of one trial or job. The
    label is the weakest part's: any `unknown` part makes it `unknown`, otherwise any `calculated`
    part makes it `calculated`, and it is `reported` only when every part is.

    A total is emitted only when every part has a reported or calculated point total. A provider
    billing hour that several reported parts count, such as one Modal App hour, is counted once;
    the same hour reported with different amounts leaves the total unknown. The total of a single
    part is that part's, digit for digit; several are added and written to 28 significant digits.
    ``parts`` retains full raw evidence, including failed attempts, and ``revisits``
    retains each part's pending revisit obligation independently. ``lines`` (none when the total
    is unknown), ``held_back_by``, ``excluded``, ``reported`` (the sum, when every part has one),
    ``final`` (every part is), ``versions`` (the first part's), ``as_of`` (the latest) and the
    summed ``steps.usage`` are present when the parts carry them.
    """
    parts = [deepcopy(dict(result)) for result in results]
    if not parts:
        raise ValueError("at least one price result is required")
    for index, part in enumerate(parts):
        _validate_part(part, index)

    label = min((part["label"] for part in parts), key=_LABEL_ORDER.__getitem__)
    totals = [_point_total(part) for part in parts]
    duplicate = _counted_twice(parts)
    exact = all(total is not None for total in totals) and duplicate is not None
    total = None
    if exact and len(parts) == 1:
        # One part is its own total: not rounded again, so a stored 60-digit total stays as priced.
        total = {side: str(parts[0]["total"][side]) for side in ("low", "high")}
    elif exact:
        assert duplicate is not None
        amounts = [total for total in totals if total is not None]
        total = {
            "low": decimal_text(sum((amount[0] for amount in amounts), Decimal(0)) - duplicate),
            "high": decimal_text(sum((amount[1] for amount in amounts), Decimal(0)) - duplicate),
        }
    else:
        label = "unknown"

    revisits = [
        {"part": index, "revisit": deepcopy(part["revisit"])}
        for index, part in enumerate(parts)
        if part.get("revisit") is not None
    ]
    composed: JsonObject = {
        "provider": "composed",
        "label": label,
        "total": total,
        "currency": "USD",
        "basis": "composed",
        "lines": []
        if total is None
        else [line for part in parts for line in part.get("lines", [])],
        "reported": _summed_reported(parts),
        "held_back_by": _unique(item for part in parts for item in part.get("held_back_by", [])),
        "excluded": _unique(item for part in parts for item in part.get("excluded", [])),
        "final": all(part.get("final") is True for part in parts),
        "parts": parts,
        "revisits": revisits,
    }
    if all("versions" in part and "as_of" in part for part in parts):
        composed["versions"] = parts[0]["versions"]
        composed["as_of"] = max(part["as_of"] for part in parts)
    if all("usage" in part.get("steps", {}) for part in parts):
        composed["steps"] = {
            "usage": {
                side: _sum_usage([part["steps"]["usage"][side] for part in parts])
                for side in ("low", "high")
            }
        }
    return composed


def _unique(items: Iterable[Any]) -> list[Any]:
    found: list[Any] = []
    for item in items:
        if item not in found:
            found.append(item)
    return found


def _summed_reported(parts: list[JsonObject]) -> JsonObject | None:
    """The parts' provider-reported costs added, when every part has one."""
    reported = [part.get("reported") for part in parts]
    if not all(isinstance(item, Mapping) for item in reported):
        return None
    documents = cast(list[Mapping[str, Any]], reported)
    return dict(documents[0]) | {
        "usd": decimal_text(sum((Decimal(str(item["usd"])) for item in documents), Decimal(0))),
        "how": "sum of the provider-reported sandbox costs",
    }


def _sum_usage(items: list[Any], key: str | None = None) -> Any:
    """Add the parts' usage documents: seconds, counts and bytes add, intervals join, and the
    description of what ran (provider, size, class, region) is the first part's. A quantity any
    part lacks is lacking in the sum, and a source is `unknown` if any part's is."""
    if len(items) == 1:
        return items[0]
    if key is not None and key in _DESCRIPTIONS | {"intervals", "source"} | _QUANTITIES:
        return _sum_named(items, key)
    if all(isinstance(item, Mapping) for item in items):
        names = set().union(*(item.keys() for item in items))
        return {
            name: _sum_usage([item.get(name) for item in items], name)
            for name in names
            if all(name in item for item in items)
        }
    if all(
        isinstance(item, int | float | Decimal) and not isinstance(item, bool) for item in items
    ):
        return sum(items)
    return items[0]


_DESCRIPTIONS = frozenset({"provider", "started", "region", "size", "class"})
_QUANTITIES = frozenset({"seconds", "count", "bytes", "gb", "max_gb"})


def _sum_named(items: list[Any], key: str) -> Any:
    if key == "intervals":
        return [item for intervals in items for item in intervals]
    if key == "source":
        if "unknown" in items:
            return "unknown"
        return items[0] if all(item == items[0] for item in items) else "calculated"
    if key in _QUANTITIES and any(item is None for item in items):
        return None
    if key in _DESCRIPTIONS:
        return items[0]
    return _sum_usage(items)


def _counted_twice(parts: list[JsonObject]) -> Decimal | None:
    """USD of provider billing hours already counted by an earlier reported part.

    None when two parts report the same hour with different amounts: which one holds is unknown.
    """
    seen: dict[tuple[str, str, str], Decimal] = {}
    duplicate = Decimal(0)
    for part in parts:
        if part["label"] != "reported" or part.get("basis") != "provider_reported":
            continue
        provider_rules = rules(part["provider"])
        if not hasattr(provider_rules, "billed_hours"):
            continue
        hours = cast(BilledHours, provider_rules.billed_hours)(
            part["steps"]["evidence"], billing(part["provider"]), as_of=part["as_of"]
        )
        for owner, start, usd in hours or ():
            key, amount = (part["provider"], owner, start), Decimal(usd)
            if key not in seen:
                seen[key] = amount
            elif seen[key] != amount:
                return None
            else:
                duplicate += amount
    return duplicate


def _validate_part(part: Document, index: int) -> None:
    if part.get("currency") != "USD":
        raise ValueError(f"price result {index} must use USD")
    label = part.get("label")
    if label not in _LABEL_ORDER:
        raise ValueError(f"price result {index} has an unsupported label")
    if "total" not in part:
        raise ValueError(f"price result {index} is missing total")


def _point_total(part: Document) -> tuple[Decimal, Decimal] | None:
    if part["label"] == "unknown":
        return None
    total = part["total"]
    if not isinstance(total, Mapping) or set(total) < {"low", "high"}:
        return None
    try:
        low = Decimal(str(total["low"]))
        high = Decimal(str(total["high"]))
    except (InvalidOperation, TypeError, ValueError):
        return None
    if not low.is_finite() or low != high:
        return None
    return low, high
