# SPDX-FileCopyrightText: BoxRouter, Inc.
# SPDX-License-Identifier: Apache-2.0
"""The fast copy and the validation-memo key keep what they stand for, on seeded random trees."""

import importlib
import random
from collections import OrderedDict
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

import pytest

from sandbox_provider_pricing.providers import bundled_billing, provider_ids
from sandbox_provider_pricing.types import bundled_copy, json_copy
from sandbox_provider_pricing.versions import bundled_pool

evidence_module = importlib.import_module("sandbox_provider_pricing.evidence")
SEED = 20261027
_TIME = "2026-10-27T03:03:55Z"


def _strictly_equal(left: Any, right: Any) -> bool:
    """Equal values of identical types, dict keys in the same order."""
    if type(left) is not type(right):
        return False
    if isinstance(left, dict):
        return list(left) == list(right) and all(
            _strictly_equal(left[key], right[key]) for key in left
        )
    if isinstance(left, (list, tuple)):
        return len(left) == len(right) and all(map(_strictly_equal, left, right))
    if isinstance(left, float) and left != left:  # NaN
        return bool(right != right)
    return bool(left == right)


def _containers(node: Any) -> Iterator[int]:
    if isinstance(node, (dict, list)):
        yield id(node)
        for item in node.values() if isinstance(node, dict) else node:
            yield from _containers(item)


def _scalar(rng: random.Random) -> Any:
    return rng.choice(
        [
            None,
            True,
            False,
            0,
            rng.randint(-(10**12), 10**12),
            rng.random() * 1000,
            -0.0,
            "",
            "x" * rng.randint(1, 12),
            _TIME,
            "2026-10-27",
        ]
    )


def _tree(rng: random.Random, depth: int = 0) -> Any:
    """A random plain-JSON tree of dicts, lists and scalars."""
    kind = rng.random()
    if depth > 4 or kind < 0.4:
        return _scalar(rng)
    if kind < 0.7:
        return {f"k{rng.randint(0, 30)}": _tree(rng, depth + 1) for _ in range(rng.randint(0, 6))}
    return [_tree(rng, depth + 1) for _ in range(rng.randint(0, 6))]


def test_bundled_copy_is_json_copy_on_random_trees_and_every_bundled_document() -> None:
    rng = random.Random(SEED)
    documents: list[Any] = [_tree(rng) for _ in range(2000)]
    documents += [bundled_billing(provider) for provider in provider_ids()]
    documents += bundled_pool()
    for document in documents:
        first, second = bundled_copy(document), bundled_copy(document)
        assert _strictly_equal(first, json_copy(document))
        assert _strictly_equal(second, document)
        # Like json_copy: no container shared with the document or with another copy.
        mine, again, theirs = (
            set(_containers(first)),
            set(_containers(second)),
            set(_containers(document)),
        )
        assert not mine & theirs and not mine & again


def test_bundled_copy_never_aliases_a_part_used_twice() -> None:
    # json_copy copies a shared part once per place; marshal format 3 and later would alias it.
    shared: dict[str, Any] = {"rate": "0.01"}
    document: dict[str, Any] = {"low": shared, "high": shared, "both": [shared, shared]}
    copied = bundled_copy(document)
    assert copied == json_copy(document)
    assert copied["low"] is not copied["high"]
    assert copied["both"][0] is not copied["both"][1]


def test_bundled_copy_falls_back_to_json_copy_beyond_marshal() -> None:
    document = {"at": datetime(2026, 10, 27, tzinfo=UTC), "items": [Decimal("1.5")]}
    copied = bundled_copy(document)
    assert (
        copied == document and copied is not document and copied["items"] is not document["items"]
    )


def test_json_record_writes_mappings_decimals_and_aware_times_as_json() -> None:
    record = OrderedDict(
        at=datetime(2026, 10, 27, 3, tzinfo=timezone(timedelta(hours=-4))),
        usd=(Decimal("1.50"),),
        unit=OrderedDict(n=1),
    )
    assert evidence_module._json_record(record) == {  # pylint: disable=protected-access
        "at": "2026-10-27T07:00:00Z",
        "usd": ["1.50"],
        "unit": {"n": 1},
    }
    with pytest.raises(ValueError, match="timezone-aware"):
        evidence_module._json_record({"at": [datetime(2026, 10, 27)]})  # pylint: disable=protected-access


def test_equal_proofs_only_ever_name_strictly_equal_values() -> None:
    rng = random.Random(SEED)
    values = [_tree(rng) for _ in range(3000)]
    values += [
        {"a": 1, "b": 2},
        {"b": 2, "a": 1},
        [1],
        [1.0],
        [True],
        (1,),
        {"1": 1},
        [float("nan")],
    ]
    seen: dict[bytes, Any] = {}
    for value in values:
        proof = evidence_module._proof("calls", value)  # pylint: disable=protected-access
        assert proof is not None
        if proof[0] in seen:
            assert _strictly_equal(seen[proof[0]], value)
        seen[proof[0]] = value
    for value in (Decimal("1"), {"at": datetime(2026, 10, 27, tzinfo=UTC)}):
        assert evidence_module._proof("calls", value) is None  # pylint: disable=protected-access
