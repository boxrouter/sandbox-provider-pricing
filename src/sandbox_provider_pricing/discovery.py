# SPDX-FileCopyrightText: BoxRouter, Inc.
# SPDX-License-Identifier: Apache-2.0
"""Write a price version from the price block of a provider's discovery document.

Discovery is an input feed, not a second price source: the version this module writes is an
ordinary immutable price version, and this repository stays the one owner of prices. Each rate
cites the discovery document's address and the canonical JSON of the price item it came from. An
item that the document does not price stays out of the version, which means unknown, never zero.
A version that looks wrong is refused, so the caller reports it instead of publishing it.
"""

import hashlib
import json
import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, cast

import yaml  # type: ignore[import-untyped]
from jsonschema import Draft202012Validator, FormatChecker

from sandbox_provider_pricing._util import (
    CONTEXT,
    MIB_PER_GIB,
    bundled_schema,
    decimal_text,
)
from sandbox_provider_pricing.calculator.quantities import RATE_TIME_SECONDS
from sandbox_provider_pricing.calculator.spans import (
    BYTES_PER_GB,
    BYTES_PER_GIB,
    CREATIONS_PER_MILLION,
    HOURS_PER_MONTH,
)
from sandbox_provider_pricing.scaffold import PACKAGES
from sandbox_provider_pricing.types import JsonObject
from sandbox_provider_pricing.versions import latest_version

#: A rate that moves by more than this factor, up or down, is refused.
MAX_RATE_MOVE = Decimal(10)

_AMOUNT = re.compile(r"-?(0|[1-9][0-9]*)(\.[0-9]+)?")
_GPU_MODEL = re.compile(r"[a-z][a-z0-9-]*:[a-z0-9][a-z0-9-]*")
_CLASS_NAME = re.compile(r"[a-z0-9][a-z0-9._-]*")

_BASES = {"allocated", "used", "max_allocated_used", "fixed", "count"}
_METER_BASIS = {
    "allocated": "allocated",
    "fixed": "allocated",
    "used": "active",
    "max_allocated_used": "larger_of_request_and_use",
}
_STATES = ("running", "paused", "stopped")

#: The units each item may use. A unit is the provider's own spelling, so none is converted.
_UNITS: dict[str, tuple[str, ...]] = {
    "cpu": ("vcpu_second", "vcpu_hour", "vcpu_month", "core_second", "core_hour"),
    "memory": ("gib_second", "gib_hour", "gib_month", "gb_second", "gb_hour", "gb_month"),
    "disk": ("gib_second", "gib_hour", "gib_month", "gb_second", "gb_hour", "gb_month"),
    "gpu": ("gpu_second", "gpu_hour"),
    "machine": ("machine_second", "machine_hour"),
    "create": ("each",),
    "egress": ("gib", "gb"),
}
_ITEMS = tuple(_UNITS)

#: A GB is 10^9 bytes and a GiB is 2^30 bytes, so one GB covers this many GiB, exactly.
_GIB_PER_GB = CONTEXT.divide(BYTES_PER_GB, BYTES_PER_GIB)
#: A physical core is read as two vCPUs, as the hand-written Modal version reads it.
_VCPU_PER_CORE = Decimal(2)


class Refused(ValueError):
    """The discovery document cannot become a price version; the message is the reason."""


@dataclass(frozen=True)
class _Item:
    """One price item that maps onto a rate of a class."""

    raw: JsonObject
    kind: str
    unit: str
    amount: Decimal


def canonical_json(value: object) -> str:
    """The one JSON text of a value: sorted keys, no spacing, characters kept as they are."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def price_block(discovery: JsonObject) -> list[JsonObject]:
    """The price block: each class's id and its `prices` list, in the document's order."""
    classes = discovery.get("classes")
    if not isinstance(classes, list) or not classes:
        raise Refused("refused: discovery has no classes")
    block: list[JsonObject] = []
    for entry in classes:
        if not isinstance(entry, dict) or not isinstance(entry.get("id"), str):
            raise Refused("refused: a class has no id")
        prices = entry.get("prices", [])
        if not isinstance(prices, list) or not all(isinstance(item, dict) for item in prices):
            raise Refused(f"refused: class {entry['id']} has prices that are not a list of items")
        block.append({"class": entry["id"], "prices": prices})
    return block


def digest(discovery: JsonObject) -> str:
    """`sha256:` and the hex digest of the price block's canonical JSON.

    Nothing else in the document moves it, so a changed digest means a changed price block.
    """
    return "sha256:" + hashlib.sha256(canonical_json(price_block(discovery)).encode()).hexdigest()


def _text_amount(value: object) -> Decimal:
    if not isinstance(value, str) or not _AMOUNT.fullmatch(value):
        raise Refused("refused: price_usd must be a decimal string")
    return Decimal(value)


def _read_item(raw: JsonObject) -> _Item:
    kind, unit, basis = raw.get("item"), raw.get("unit"), raw.get("basis")
    if kind not in _ITEMS:
        raise Refused(f"refused: unknown item {kind!r}")
    if unit not in _UNITS[cast(str, kind)]:
        raise Refused(f"refused: unit {unit!r} does not fit item {kind}")
    if basis not in _BASES:
        raise Refused(f"refused: unknown basis {basis!r}")
    amount = _text_amount(raw.get("price_usd"))
    if amount < 0:
        raise Refused("refused: negative amount")
    if raw.get("included") is True and amount != 0:
        raise Refused("refused: an included item must have amount 0")
    if amount == 0 and raw.get("included") is not True:
        raise Refused("refused: zero amount on an item not marked included")
    return _Item(raw, cast(str, kind), cast(str, unit), amount)


def _per(unit: str) -> str:
    return unit.replace("_", "-")


def _rate(item: _Item) -> JsonObject:
    rate: JsonObject = {"usd": item.raw["price_usd"], "per": _per(item.unit)}
    if item.kind == "create":
        rate["per"] = "creation"
    elif (size := _size_factor(item.unit)) != 1:
        rate["size_per_unit"] = decimal_text(size)
    return rate


def _size_factor(unit: str) -> Decimal:
    """Size units of the price base per unit of the unit's quantity (GiB per GB, vCPU per core)."""
    # `gb_`, not `gb`: the bare `gb` egress unit takes no size factor.
    if unit.startswith("gb_"):
        return _GIB_PER_GB
    if unit.startswith("core_"):
        return _VCPU_PER_CORE
    return Decimal(1)


def comparable_rate(kind: str, rate: JsonObject) -> Decimal | None:
    """The rate in one base unit, so versions that spell a unit differently compare: USD per
    vCPU-, GiB-, GPU- or machine-second, per creation, or per GiB of egress."""
    per = str(rate["per"])
    usd = Decimal(str(rate["usd"]))
    if kind == "creation":
        return usd / CREATIONS_PER_MILLION if per == "million-creations" else usd
    if kind == "egress":
        return usd / _GIB_PER_GB if per == "gb" else usd
    period = per.rpartition("-")[2]
    if period not in RATE_TIME_SECONDS:
        return None
    size = Decimal(str(rate["size_per_unit"])) if "size_per_unit" in rate else Decimal(1)
    return CONTEXT.divide(usd, size * RATE_TIME_SECONDS[period])


def _billed_states(raw: JsonObject) -> list[str]:
    states = raw.get("states")
    if states is None:
        return ["running"]
    if not isinstance(states, list) or not states or not set(states) <= set(_STATES):
        raise Refused("refused: states must list running, paused or stopped")
    return [state for state in _STATES if state in states]


def _meter(items: list[_Item]) -> JsonObject:
    """One meter rule for the items of a resource; items of one resource must agree."""
    meters: list[JsonObject] = []
    for item in items:
        raw = item.raw
        meter: JsonObject = {
            "basis": _METER_BASIS[cast(str, raw["basis"])],
            "billed_states": _billed_states(raw),
        }
        for field in ("minimum_seconds", "increment_seconds"):
            if field in raw:
                value = raw[field]
                if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                    raise Refused(f"refused: {field} must be a positive integer")
                meter[field] = value
        allowance = raw.get("allowance")
        if (
            isinstance(allowance, dict)
            and allowance.get("period") == "sandbox"
            and allowance.get("scope") == "sandbox"
        ):
            quantity = _text_amount(allowance.get("quantity"))
            meter["free_quantity"] = decimal_text(quantity * _size_factor(item.unit))
        meters.append(meter)
    if any(meter != meters[0] for meter in meters):
        raise Refused(f"refused: items of {items[0].kind} disagree on how they are metered")
    return meters[0]


def _machine_key(size: object) -> tuple[str, str, str]:
    if (
        not isinstance(size, dict)
        or not isinstance(size.get("cpu"), int | float)
        or not isinstance(size.get("memory_mib"), int)
        or size["memory_mib"] < 1
        or size["cpu"] <= 0
    ):
        raise Refused("refused: a machine item needs a size of cpu and memory_mib")
    cpu = decimal_text(Decimal(str(size["cpu"])))
    memory_gib = decimal_text(CONTEXT.divide(Decimal(size["memory_mib"]), MIB_PER_GIB))
    return f"{cpu}vcpu-{size['memory_mib']}mib", cpu, memory_gib


def _allowance_note(item: _Item) -> str | None:
    allowance = item.raw.get("allowance")
    if not isinstance(allowance, dict):
        return None
    scope, period = allowance.get("scope"), allowance.get("period")
    if (scope, period) == ("sandbox", "sandbox") and item.kind not in ("egress", "create"):
        return None  # the meter's `free_quantity` holds it
    return (
        f"Allowance: {allowance.get('quantity')} {item.unit} per {period} for each {scope} is "
        f"included before the {item.kind} price applies; this version does not apply it."
    )


@dataclass
class _Class:
    """The rates and notes of one discovery class, while the version is built."""

    name: str
    rates: JsonObject
    meters: dict[str, list[_Item]]
    cited: list[_Item]
    notes: list[str]
    exclusions: list[str]


def _build_class(entry: JsonObject) -> _Class | None:
    built = _Class(str(entry["class"]), {}, {}, [], [], [])
    if not _CLASS_NAME.fullmatch(built.name):
        raise Refused(f"refused: class id {built.name!r} is not a valid class name")
    seen: set[str] = set()
    for raw in cast(list[JsonObject], entry["prices"]):
        item = _read_item(raw)
        if "region" in raw or "variant" in raw:
            qualifier = raw.get("region") or raw.get("variant")
            built.notes.append(
                f"Not priced here, because it applies only to {qualifier}: "
                f"{canonical_json(raw)} (class {built.name})."
            )
            continue
        key = {"gpu": f"gpu:{raw.get('gpu_model')}", "machine": f"machine:{raw.get('size')}"}.get(
            item.kind, item.kind
        )
        if key in seen:
            raise Refused(f"refused: item {item.kind} is priced twice in class {built.name}")
        seen.add(key)
        _place(built, item)
        built.cited.append(item)
        if note := _allowance_note(item):
            built.exclusions.append(f"{note} Class {built.name}.")
        if "minimum_quantity" in raw:
            built.notes.append(
                f"The provider states a minimum quantity of {raw['minimum_quantity']} "
                f"{item.unit} for {item.kind}; this version does not apply it "
                f"(class {built.name})."
            )
        if "states" not in raw and item.kind in ("cpu", "memory", "disk", "gpu", "machine"):
            built.notes.append(
                f"Billing of {item.kind} in states other than running is not declared "
                f"(class {built.name})."
            )
    return built if built.rates else None


def _place(built: _Class, item: _Item) -> None:
    raw = item.raw
    if item.kind == "gpu":
        model = raw.get("gpu_model")
        if not isinstance(model, str) or not _GPU_MODEL.fullmatch(model):
            raise Refused("refused: a gpu item needs a gpu_model such as nvidia:h100")
        built.rates.setdefault("gpu", {})[model] = _rate(item)
    elif item.kind == "machine":
        key, cpu, memory_gib = _machine_key(raw.get("size"))
        rate = _rate(item) | {"cpu": cpu, "memory_gib": memory_gib}
        built.rates.setdefault("machine", {})[key] = rate
    else:
        built.rates[item.kind if item.kind != "create" else "creation"] = _rate(item)
    if item.kind in ("cpu", "memory", "disk", "gpu", "machine"):
        built.meters.setdefault(item.kind, []).append(item)


def _class_document(built: _Class, default: bool) -> JsonObject:
    document: JsonObject = {"name": built.name}
    if default:
        document["default"] = True
    document["rates"] = built.rates
    document["meter"] = {kind: _meter(items) for kind, items in built.meters.items()}
    return document


def _source(url: str, item: _Item) -> JsonObject:
    return {"url": url, "quote": canonical_json(item.raw)}


def _timestamp(moment: datetime) -> str:
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _version_id(provider: str, moment: datetime, taken: set[str]) -> str:
    moment = moment.astimezone(UTC)
    for text in (moment.strftime("%Y-%m-%d"), moment.strftime("%Y-%m-%d-%H%M%SZ")):
        if f"{provider}@{text}" not in taken:
            return f"{provider}@{text}"
    raise Refused(f"refused: version {provider}@{moment:%Y-%m-%d-%H%M%SZ} already exists")


def _check_provider(discovery: JsonObject, provider: str) -> None:
    named = discovery.get("provider")
    if isinstance(named, dict) and named.get("id") not in (None, provider):
        raise Refused("refused: discovery names another provider")


def generate(
    discovery: JsonObject,
    *,
    provider: str,
    source: str,
    now: datetime,
    previous: list[JsonObject] | None = None,
) -> JsonObject:
    """The new price version for a discovery document, or `Refused` with the reason.

    `previous` is every price version of the provider that is known; the newest is the one the
    new rates are compared with.
    """
    moment = now
    _check_provider(discovery, provider)
    classes = [built for entry in price_block(discovery) if (built := _build_class(entry))]
    if not any(built.name == "default" for built in classes):
        raise Refused("refused: no prices for the default class")
    documents = [_class_document(built, built.name == "default") for built in classes]
    known = previous or []
    newest = latest_version(provider, known) if known else None
    if newest is not None:
        _guard(newest, documents)
    version = _version_id(provider, moment, {str(item["version"]) for item in known})
    cited = [item for built in classes for item in built.cited]
    document: JsonObject = {
        "provider": provider,
        "version": version,
        "effective_from": _timestamp(moment),
        "retrieved_at": _timestamp(moment),
        "discovery_digest": digest(discovery),
    }
    if any(item.unit.endswith("_month") for item in cited):
        document["month_hours"] = decimal_text(HOURS_PER_MONTH)
    document |= {
        "sources": [_source(source, item) for item in cited],
        "classes": documents,
        "exclusions": [text for built in classes for text in built.exclusions],
        "open_questions": _open_questions(classes, cited, newest, documents),
    }
    _check_schema(document)
    return document


def _open_questions(
    classes: list[_Class],
    cited: list[_Item],
    newest: JsonObject | None,
    documents: list[JsonObject],
) -> list[str]:
    notes = [note for built in classes for note in built.notes]
    if any(item.unit.startswith("core_") for item in cited):
        notes.append("A physical core is read as 2 vCPUs.")
    if newest is not None:
        notes += _dropped(newest, documents)
    return notes


def _check_schema(document: JsonObject) -> None:
    validator = Draft202012Validator(
        bundled_schema("price-version"), format_checker=FormatChecker()
    )
    failures = sorted(error.message for error in validator.iter_errors(document))
    if failures:
        raise Refused(f"refused: the version fails the price-version schema: {failures[0]}")


def _comparable_rates(classes: Iterable[JsonObject]) -> dict[tuple[str, str], Decimal]:
    rates: dict[tuple[str, str], Decimal] = {}
    for entry in classes:
        for kind, rate in cast(JsonObject, entry.get("rates", {})).items():
            nested = kind in ("gpu", "machine")
            for name, one in rate.items() if nested else [(kind, rate)]:
                label = f"{kind}:{name}" if nested else kind
                base = comparable_rate(kind, one)
                if base is not None:
                    rates[(str(entry["name"]), label)] = base
    return rates


def _guard(newest: JsonObject, documents: list[JsonObject]) -> None:
    """Refuse a rate that became zero or moved more than 10x against the previous version."""
    before = _comparable_rates(cast(list[JsonObject], newest["classes"]))
    for key, now in _comparable_rates(documents).items():
        was = before.get(key)
        if was is None or was == 0:
            continue
        if now == 0:
            raise Refused(
                "refused: item priced in the previous version became zero\n"
                f"  class {key[0]}, item {key[1]}"
            )
        if now > was * MAX_RATE_MOVE or now * MAX_RATE_MOVE < was:
            raise Refused(f"refused: rate moved more than 10x\n  class {key[0]}, item {key[1]}")


def _dropped(newest: JsonObject, documents: list[JsonObject]) -> list[str]:
    now = set(_comparable_rates(documents))
    gone = sorted(
        f"{name}:{label}"
        for (name, label) in _comparable_rates(cast(list[JsonObject], newest["classes"]))
        if (name, label) not in now
    )
    if not gone:
        return []
    return [
        f"Priced in {newest['version']} and not priced in this discovery document, so unknown "
        f"here: {', '.join(gone)}."
    ]


def known_versions(root: Path, provider: str, out: Path) -> list[JsonObject]:
    """The provider's price versions in the checkout's package and in the output directory."""
    versions: list[JsonObject] = []
    for folder in (root / PACKAGES / provider / "prices", out):
        if folder.is_dir():
            for path in sorted(folder.glob("*.yaml")):
                loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict) and loaded.get("provider") == provider:
                    versions.append(loaded)
    return versions


def check_billing_record(root: Path, provider: str) -> None:
    """Refuse a provider whose billing record exists and does not say `prices: discovery`."""
    path = root / PACKAGES / provider / "billing.yaml"
    if not path.is_file():
        return
    record: Any = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(record, dict) or record.get("prices") != "discovery":
        raise Refused("refused: the provider's billing record does not say prices: discovery")


def write_version(document: JsonObject, out: Path) -> Path:
    """Write the version under its date, as YAML; an existing file is never replaced."""
    out.mkdir(parents=True, exist_ok=True)
    filename = str(document["version"]).split("@", 1)[1] + ".yaml"
    path = out / filename
    text = (
        "# yaml-language-server: $schema=../../../../../schemas/price-version.schema.json\n"
        + yaml.safe_dump(document, sort_keys=False, allow_unicode=True, width=100)
    )
    with path.open("x", encoding="utf-8") as stream:
        stream.write(text)
    return path


def run(  # pylint: disable=too-many-arguments
    provider: str,
    discovery: Path,
    source: str,
    out: Path,
    root: Path,
    *,
    now: datetime,
) -> int:
    """The `spp from-discovery` command: print the written path, or `refused: <reason>` and 2."""
    try:
        if not re.fullmatch(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*", provider):
            raise Refused("refused: provider must be a lowercase registry id")
        if not re.fullmatch(r"https?://[^\s]+", source):
            raise Refused("refused: --source must be the discovery document's http(s) address")
        try:
            loaded = json.loads(discovery.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            raise Refused(f"refused: {discovery} is not readable JSON") from error
        if not isinstance(loaded, dict):
            raise Refused("refused: discovery is not a JSON object")
        check_billing_record(root, provider)
        previous = known_versions(root, provider, out)
        document = generate(loaded, provider=provider, source=source, previous=previous, now=now)
        path = write_version(document, out)
    except Refused as error:
        print(error)
        return 2
    print(path)
    return 0


__all__ = ["Refused", "canonical_json", "digest", "generate", "run"]
