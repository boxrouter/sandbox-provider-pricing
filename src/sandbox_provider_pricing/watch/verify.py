# SPDX-FileCopyrightText: BoxRouter, Inc.
# SPDX-License-Identifier: Apache-2.0
"""The checks a drafted price version must pass, with no AI, and the price changes it makes.

`verify` lists every reason to reject a draft: a quote that is not on the page, a rate that is not
a number in one of its quotes, a rate in another unit than its quote prints, or a draft that does
not validate against the price-version schema. `classify` names each change to the rates, meter
rules and exclusions; none means the page was only reworded.
"""

import difflib
import json
import re
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, localcontext
from functools import cache
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

from sandbox_provider_pricing import calculator
from sandbox_provider_pricing.types import JsonObject
from sandbox_provider_pricing.watch.check import PageText
from sandbox_provider_pricing.watch.errors import DraftError

MAX_FAILURE_CHARS = 400
TIME_RESOURCES = ("cpu", "memory", "disk", "gpu")
SIZE_OF_ONE = {
    "cpu": {"cpu": 1},
    "memory": {"memory_mib": 1024},
    "disk": {"disk_mib": 1024},
    "gpu": {"gpu": 1},
}
SECONDS = {"s", "sec", "secs", "second", "seconds"}
HOURS = {"h", "hr", "hrs", "hour", "hours"}
NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")
FREE = re.compile(r"\b(free|included|no charge|no cost)\b", re.IGNORECASE)
# What a quote must mention to be about a resource: a price in a memory table is not the CPU's.
ABOUT = {
    "cpu": re.compile(r"cpu|core", re.IGNORECASE),
    "memory": re.compile(r"memory|ram\b", re.IGNORECASE),
    "disk": re.compile(r"disk|storage", re.IGNORECASE),
    "gpu": re.compile(r"gpu", re.IGNORECASE),
    "machine": re.compile(r"machine|per hour|size", re.IGNORECASE),
    "creation": re.compile(r"creat", re.IGNORECASE),
    "egress": re.compile(r"egress|network|bandwidth|transfer", re.IGNORECASE),
    "snapshot_storage": re.compile(r"snapshot storage", re.IGNORECASE),
}
GIB = re.compile(r"\bGiB\b")
GB = re.compile(r"\bGB\b")
DECIMAL = re.compile(r"^\d+(\.\d+)?$")
UNIT_WINDOW = 40
SAME_EXCLUSION = 0.6  # how alike two exclusions must be to be one, reworded or repriced


@cache
def price_version_schema() -> JsonObject:
    here = Path(__file__).resolve().parent
    for folder in (here.parent / "schemas", here.parents[2] / "schemas"):  # the wheel, a checkout
        path = folder / "price-version.schema.json"
        if path.is_file():
            schema: JsonObject = json.loads(path.read_text(encoding="utf-8"))
            return schema
    raise DraftError("price-version.schema.json is not installed with this package.")


def verify(
    draft: JsonObject, page: PageText, url: str, current: JsonObject | None = None
) -> list[str]:
    """Every reason to reject the draft, with no AI; none means it can be trusted as drafted.

    The quotes the draft takes from `url` must be on `page`. The quotes from other pages cannot
    be checked against it, and `assemble` keeps them as they were. Given the `current` version,
    a quote of it that the page still says must still be in the draft: dropping one would quietly
    shrink what the daily check watches.
    """
    failures = _schema_failures(draft)
    if failures:
        return failures
    if not draft["version"].startswith(f"{draft['provider']}@"):
        failures.append(f"The version {draft['version']} is not for {draft['provider']}.")
    failures += [
        f"The quote is not on the page: {source['quote']!r}"
        for source in draft["sources"]
        if source["url"] == url and not page.contains(source["quote"])
    ]
    if current is not None:
        failures += _dropped_quotes(draft, page, url, current)
    mentions = list(_mentions(draft))
    quotes = [source["quote"] for source in draft["sources"]]
    for rate in _rates(draft):
        failures += _rate_failures(rate, mentions, quotes)
    return [_short(failure) for failure in failures]


def _dropped_quotes(draft: JsonObject, page: PageText, url: str, current: JsonObject) -> list[str]:
    kept = [PageText(visible=s["quote"]) for s in draft["sources"] if s["url"] == url]
    return [
        f"The page still says this, but the draft leaves it out: {source['quote']!r}"
        for source in current["sources"]
        if source["url"] == url
        and page.contains(source["quote"])
        and not any(quote.contains(source["quote"]) for quote in kept)
    ]


def _schema_failures(draft: JsonObject) -> list[str]:
    validator = Draft202012Validator(price_version_schema(), format_checker=FormatChecker())
    errors = sorted(
        f"The draft is not a valid price version: {_path(error.absolute_path)}: {error.message}"
        for error in validator.iter_errors(draft)
    )
    return [_short(error) for error in errors]


def _path(parts: Iterable[Any]) -> str:
    return "/".join(map(str, parts)) or "<root>"


def _short(failure: str) -> str:
    if len(failure) <= MAX_FAILURE_CHARS:
        return failure
    return failure[: MAX_FAILURE_CHARS - 1] + "…"


@dataclass(frozen=True)
class Mention:
    """A number in a quote, and the few words printed after it, up to the next price or cell."""

    number: Decimal
    after: str
    quote: str


@dataclass(frozen=True)
class PricedRate:
    """One price rate, with its class label and GPU model when it has one."""

    label: str
    resource: str
    rate: JsonObject
    model: str | None = None


def _mentions(draft: JsonObject) -> Iterator[Mention]:
    for source in draft["sources"]:
        quote = source["quote"]
        for match in NUMBER.finditer(quote):
            try:
                number = Decimal(match.group().replace(",", ""))
            except InvalidOperation:
                continue
            after = quote[match.end() : match.end() + UNIT_WINDOW]
            yield Mention(number, re.split(r"[|$\d]", after, maxsplit=1)[0], quote)


def _rates(version: JsonObject) -> Iterator[PricedRate]:
    """Each unit rate: how to name it, which resource it is for, and the rate itself."""
    several = len(version["classes"]) > 1
    for price_class in version["classes"]:
        prefix = f"{price_class['name']} " if several else ""
        for resource, rate in price_class["rates"].items():
            if resource == "gpu":
                for model, model_rate in rate.items():
                    yield PricedRate(f"{prefix}gpu {model}", resource, model_rate, model)
            elif resource == "machine":
                for size_name, size_rate in rate.items():
                    yield PricedRate(f"{prefix}machine {size_name}", resource, size_rate, size_name)
            else:
                yield PricedRate(f"{prefix}{resource}", resource, rate)


def _rate_failures(
    priced_rate: PricedRate, mentions: list[Mention], quotes: list[str]
) -> list[str]:
    label, resource, rate, model = (
        priced_rate.label,
        priced_rate.resource,
        priced_rate.rate,
        priced_rate.model,
    )
    usd = Decimal(rate["usd"])
    about = [quote for quote in quotes if ABOUT[resource].search(quote)]
    if usd == 0:  # a published free rate: a stray 0 in a quote is not that
        if any(FREE.search(quote) for quote in about):
            return []
        return [f"The rate {label} 0 is free, but no quote about {resource} says free or included."]
    found = [
        m
        for m in mentions
        if m.number == usd
        and ABOUT[resource].search(m.quote)
        and _names_the_entry(resource, model, m.quote)
    ]
    if not found:
        if model is not None:
            return [
                f"The rate {label} {rate['usd']} is not a number in a quote that names {model}."
            ]
        return [f"The rate {label} {rate['usd']} is not a number in any quote about {resource}."]
    failures = []
    if resource in ("memory", "disk"):
        failures += _size_unit_failures(label, rate, found)
    if resource in TIME_RESOURCES:
        failures += _time_unit_failures(label, resource, rate, found, model)
    return failures


def _names_the_entry(resource: str, model: str | None, quote: str) -> bool:
    """A model- or size-keyed rate's quote must name that model or size."""
    if model is None:
        return True
    if resource == "gpu":
        return _names_gpu_model(model, quote)
    if resource == "machine":
        wanted = re.sub(r"[^a-z0-9]", "", model.lower())
        actual = re.sub(r"[^a-z0-9]", "", quote.lower())
        return bool(wanted and wanted in actual)
    return True


def _names_gpu_model(model: str, quote: str) -> bool:
    """A GPU rate's quote must name that registry model, even when prices repeat."""
    identifier = model.partition(":")[2]
    wanted = re.sub(r"[^a-z0-9]", "", identifier.lower())
    actual = re.sub(r"[^a-z0-9]", "", quote.lower())
    return bool(wanted and wanted in actual)


def _size_unit_failures(label: str, rate: JsonObject, found: list[Mention]) -> list[str]:
    """A GiB rate must not be read from a quote that only says GB, and the other way round."""
    words = {"gib": ("GiB", GIB), "gb": ("GB", GB)}
    key = rate["per"].split("-")[0]
    name, own = words[key]
    other_name, other = words["gb" if key == "gib" else "gib"]
    text = " ".join(mention.quote for mention in found)
    if own.search(text) or not other.search(text):
        return []
    return [f"The rate {label} {rate['usd']} is per {name}, but its quote says {other_name}."]


def _time_unit(after: str) -> str | None:
    for word in re.findall(r"[A-Za-z]+", after)[:4]:
        if word.lower() in SECONDS:
            return "second"
        if word.lower() in HOURS:
            return "hour"
    return None


def _time_unit_failures(
    label: str, resource: str, rate: JsonObject, found: list[Mention], model: str | None = None
) -> list[str]:
    """The rate's time unit must be the quote's, and the calculator must price an hour of one
    unit at what the quote gives: the number, times 3600 where it is per second, over the
    vCPUs or GiB one of the rate's units covers."""
    unit = "second" if rate["per"].endswith("-second") else "hour"
    quoted = {mention: _time_unit(mention.after) for mention in found}
    stated = {value for value in quoted.values() if value is not None}
    if not stated:
        return []  # the quote prints no time unit, so there is nothing to convert
    if unit not in stated:
        return [
            f"The rate {label} {rate['usd']} is {rate['per']}, but its quote says per "
            f"{' or '.join(sorted(stated))}."
        ]
    number = next(mention.number for mention, value in quoted.items() if value == unit)
    with localcontext(calculator.CONTEXT):
        expected = number * (calculator.SECONDS_PER_HOUR if unit == "second" else 1)
        expected /= Decimal(rate.get("size_per_unit", 1))
        actual = _calculator_hour(resource, rate, model)
    if actual != expected:
        return [
            f"The rate {label} {rate['usd']} {rate['per']} comes to {actual} an hour for one "
            f"unit, but its quote gives {expected}."
        ]
    return []


def _calculator_hour(resource: str, rate: JsonObject, model: str | None = None) -> Decimal | None:
    """What the calculator charges for an hour of one vCPU, GiB or GPU at this rate alone."""
    rates = {resource: rate}
    if resource == "gpu" and model is not None:
        rates[resource] = {model: rate}
    version = {
        "classes": [
            {
                "name": "one",
                "default": True,
                "rates": rates,
                "meter": {resource: {"basis": "allocated", "billed_states": ["running"]}},
            }
        ]
    }
    size: JsonObject = dict(SIZE_OF_ONE[resource])
    if resource == "gpu" and model is not None:
        size["gpu_model"] = model
    price = calculator.per_hour(version, size)
    return None if price is None else Decimal(price["low"])


def classify(current: JsonObject, draft: JsonObject) -> list[str]:
    """The changes to the rates, meter rules and exclusions; none if reworded.

    A rate or meter rule change is `<name> <old> -> <new>`, an exclusion change is
    `exclusion: <old> -> <new>`. An exclusion is a charge outside the rates (a plan fee), so a
    changed one is a price change, and so is one added or dropped. The quotes are not compared:
    they are only what the version was read from.
    """
    old, new = _terms(current), _terms(draft)
    changes = []
    for name in [*old, *(name for name in new if name not in old)]:
        before, after = old.get(name), new.get(name)
        if before != after:
            changes.append(f"{name} {before or 'none'} -> {after or 'none'}")
    return changes + _exclusion_changes(current["exclusions"], draft["exclusions"])


def _exclusion_changes(old: list[str], new: list[str]) -> list[str]:
    """Each exclusion that differs, as `exclusion: <old> -> <new>`, spacing and order aside.

    One that is gone is paired with the added one most like it, as its old wording, when they
    are alike enough; otherwise it, and each added one left over, is `none` on the other side.
    """
    gone = [" ".join(text.split()) for text in old]
    added = [" ".join(text.split()) for text in new]
    for text in list(gone):
        if text in added:
            gone.remove(text)
            added.remove(text)
    changes = []
    for text in gone:
        likeness = [difflib.SequenceMatcher(None, text, other).ratio() for other in added]
        best = max(range(len(added)), key=likeness.__getitem__, default=None)
        if best is not None and likeness[best] >= SAME_EXCLUSION:
            changes.append(f"exclusion: {text} -> {added.pop(best)}")
        else:
            changes.append(f"exclusion: {text} -> none")
    return changes + [f"exclusion: none -> {text}" for text in added]


def _terms(version: JsonObject) -> dict[str, str]:
    """Every rate and meter rule of the version as `name -> value`, decimals in one spelling."""
    terms: dict[str, str] = {}
    for price_class in version["classes"]:
        prefix = f"{price_class['name']} " if len(version["classes"]) > 1 else ""
        if price_class.get("default"):
            terms[f"{prefix}default"] = "yes"
        terms.update(_rate_terms(prefix, price_class["rates"]))
        for resource, meter in price_class["meter"].items():
            for key, value in meter.items():
                terms[f"{prefix}{resource} meter {key}"] = _text(value)
        for region, factor in (price_class.get("region_multipliers") or {}).items():
            terms[f"{prefix}region {region}"] = _text(factor)
    return terms


def _rate_terms(prefix: str, rates: JsonObject) -> dict[str, str]:
    """Names every ordinary rate and each model-specific GPU rate for price comparisons."""
    terms: dict[str, str] = {}
    for resource, rate in rates.items():
        if resource in ("gpu", "machine"):
            for model, model_rate in rate.items():
                for key, value in model_rate.items():
                    name = f"{prefix}{resource} {model}"
                    if key != "usd":
                        name += f" {key}"
                    terms[name] = _text(value)
            continue
        for key, value in rate.items():
            name = f"{prefix}{resource}" if key == "usd" else f"{prefix}{resource} {key}"
            terms[name] = _text(value)
    return terms


def _text(value: Any) -> str:
    if isinstance(value, list):
        return ",".join(_text(item) for item in value)
    if isinstance(value, str) and DECIMAL.match(value):
        return format(Decimal(value).normalize(), "f")
    return str(value)
