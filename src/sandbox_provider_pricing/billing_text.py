# SPDX-FileCopyrightText: BoxRouter, Inc.
# SPDX-License-Identifier: Apache-2.0
"""Billing-rule answers name the price version's rows instead of typing their rates.

An answer in `billing.yaml` writes a field where it states a price, and the field is filled from
the price version, so the sentence and the rate cannot disagree:

- `{storage.<kind>}`: a storage row's billed amount and unit, "$0.08 per GB-month";
- `{storage.<kind>.amount}`: the amount alone, "$0.20";
- `{storage.unit}`: the billed unit every storage row named in the answer shares;
- `{rate.<resource>}` and `{rate.<resource>.amount}`: the same for a rate of the default price
  class, such as `{rate.cpu}` or `{rate.machine.small.amount}`.

"Billed" is the price version's own amount string and the unit the provider bills (`per`), never a
converted rate. The provider's billing document is filled when it is loaded, from its price version
in effect, so every reader, and the schema's length limits, see the filled text.
"""

import re
from collections.abc import Callable
from typing import Any

#: Display names of the parts of a price unit: `gib-month` is "GiB-month".
UNIT_PARTS = {"vcpu": "vCPU", "gib": "GiB", "gb": "GB", "gpu": "GPU"}
_FIELD = re.compile(r"\{(storage|rate)\.([^{}]+)\}")
_STORAGE_KINDS = ("image", "snapshot", "volume")


def unit_name(per: str) -> str:
    """The display name of a price unit, such as "GiB-month" for `gib-month`."""
    return "-".join(UNIT_PARTS.get(part, part) for part in per.split("-"))


def _storage_row(version: dict[str, Any], kind: str) -> dict[str, Any]:
    if kind not in _STORAGE_KINDS:
        raise ValueError(f"unknown storage kind {kind!r}")
    row = version.get(f"{kind}_storage")
    if not isinstance(row, dict) or row.get("rate_source") == "published_disk_rate_proxy":
        raise ValueError(f"{version['version']} has no billed {kind} storage rate")
    return row


def _rate_row(version: dict[str, Any], path: list[str]) -> dict[str, Any]:
    default = next((c for c in version["classes"] if c.get("default")), version["classes"][0])
    node: Any = default.get("rates") or {}
    for key in path:
        node = node.get(key) if isinstance(node, dict) else None
    if not isinstance(node, dict) or not isinstance(node.get("usd"), str):
        raise ValueError(f"{version['version']} has no rate {'.'.join(path)!r}")
    return node


def fill_answer(text: str, version: dict[str, Any]) -> str:
    """The answer with every field replaced from `version`; an unknown field raises."""
    units: set[str] = set()

    def field(match: re.Match[str]) -> str:
        group, name = match[1], match[2]
        if group == "storage" and name == "unit":
            return "{storage.unit}"
        *path, last = name.split(".")
        amount_only = last == "amount" and bool(path)
        path = path if amount_only else [*path, last]
        if group == "storage":
            if len(path) != 1:
                raise ValueError(f"unknown field {match[0]!r}")
            row = _storage_row(version, path[0])
            units.add(row["per"])
        else:
            row = _rate_row(version, path)
        amount = f"${row['usd']}"
        return amount if amount_only else f"{amount} per {unit_name(row['per'])}"

    filled = _FIELD.sub(field, text)
    if "{storage.unit}" in filled:
        if len(units) != 1:
            raise ValueError(
                f"{{storage.unit}} needs storage rows with one unit, got {sorted(units)}"
            )
        filled = filled.replace("{storage.unit}", unit_name(units.pop()))
    return filled


def fill_rules(document: Any, version: Callable[[], dict[str, Any]]) -> None:
    """Fill every rule answer of a billing document in place; `version` loads only when needed."""
    rules = document.get("rules") if isinstance(document, dict) else None
    if not isinstance(rules, dict):
        return
    answers = [rule for rule in rules.values() if isinstance(rule, dict) and "answer" in rule]
    if not any(_FIELD.search(str(rule["answer"])) for rule in answers):
        return
    current = version()
    for rule in answers:
        rule["answer"] = fill_answer(rule["answer"], current)
