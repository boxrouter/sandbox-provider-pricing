# SPDX-FileCopyrightText: BoxRouter, Inc.
# SPDX-License-Identifier: Apache-2.0
"""A price result's working as display text: one line per charge, each number with its source."""

import re
from functools import cache
from typing import Any, NotRequired, TypedDict

from sandbox_provider_pricing._util import bundled_schema
from sandbox_provider_pricing.types import JsonObject


class ExplainedLine(TypedDict):
    """One charge, as text and as the exact numbers behind the text."""

    what: str
    text: str
    amount_text: str
    amount: str
    sources: dict[str, str]
    working: NotRequired[str]
    exact_quantity: NotRequired[str]
    quantity: NotRequired[str]
    unit: NotRequired[str]
    rate: NotRequired[str]
    quantity_source: NotRequired[str]


class Explanation(TypedDict):
    """A result's working: its lines and a one-line summary of the total."""

    summary: str
    lines: list[ExplainedLine]
    price_version: str | None


@cache
def _text() -> dict[str, Any]:
    text: dict[str, Any] = bundled_schema("cost-method")["x-text"]["explain"]
    return text


def _fill(template: str, **values: str) -> str:
    return re.sub(r"\{([a-z_]+)\}", lambda match: values[match[1]], template)


def _round_to(text: str, places: int) -> str:
    """`text`, a plain decimal string, rounded half up to `places` decimals, without floats."""
    whole, _, fraction = text.partition(".")
    scaled = int(whole + (fraction + "0" * places)[:places])
    if len(fraction) > places and fraction[places] >= "5":
        scaled += 1
    digits = str(scaled).rjust(places + 1, "0")
    return digits if places == 0 else f"{digits[:-places]}.{digits[-places:]}"


def _dollars(text: str) -> str:
    """An amount as people read it: two significant digits under $1, cents from $1."""
    whole, _, fraction = text.partition(".")
    if int(whole) == 0:
        zeros = len(fraction) - len(fraction.lstrip("0"))
        if zeros == len(fraction):
            return "$0"
        places = zeros + 2
        rounded = _round_to(text, places)
        if int(rounded.split(".")[0]) == 0:
            if len(fraction) <= places:
                return f"$0.{fraction.rstrip('0').ljust(2, '0')}"
            return f"${rounded}"
    return f"${_round_to(text, 2)}"


def _plain(text: str) -> str:
    """A number with thousands separators; decimals stay exactly as given."""
    whole, dot, fraction = text.partition(".")
    return f"{int(whole):,}{dot}{fraction}"


def _quantity(text: str) -> tuple[str, str | None]:
    """A quantity to read, with four significant digits, and its exact form when digits dropped."""
    whole, _, fraction = text.partition(".")
    if int(whole) == 0:
        places = len(fraction) - len(fraction.lstrip("0")) + 4
    else:
        places = max(0, 4 - len(whole))
    if not re.search(r"[1-9]", fraction[places:]):
        return _plain(text), None
    rounded = _round_to(text, places)
    if "." in rounded:
        rounded = rounded.rstrip("0").rstrip(".")
    return _plain(rounded), _plain(text)


def _unit(unit: str) -> str:
    words = _text()["unit_words"]
    return "-".join(words.get(word, word) for word in unit.split("-"))


def _line(line: JsonObject) -> ExplainedLine:
    text = _text()
    quantity, exact = _quantity(line["quantity"])
    unit = _unit(line["unit"])
    working = _fill(text["working"], quantity=quantity, unit=unit, rate=f"${line['rate']}")
    amount = _dollars(line["amount"])
    explained: ExplainedLine = {
        "what": line["what"],
        "text": _fill(
            text["line"],
            resource=text["resources"].get(line["what"], line["what"]),
            working=working,
            amount=amount,
        ),
        "working": working,
        "amount_text": amount,
        "quantity": line["quantity"],
        "unit": line["unit"],
        "rate": line["rate"],
        "amount": line["amount"],
        "quantity_source": line["quantity_source"],
        "sources": {
            "quantity": text["sources"][line["quantity_source"]],
            "rate": text["rate_source"],
            "amount": text["amount_source"],
        },
    }
    if exact is not None:
        explained["exact_quantity"] = _fill(text["exact_quantity"], quantity=exact, unit=unit)
    return explained


def _reported_line(result: JsonObject) -> ExplainedLine:
    text = _text()
    figure = result["reported"]["usd"]
    amount = _dollars(figure)
    return {
        "what": "reported",
        "text": _fill(text["reported_line"], amount=amount),
        "amount_text": amount,
        "amount": figure,
        "sources": {"amount": text["sources"]["provider"]},
    }


def _total(total: JsonObject) -> str:
    if total["low"] == total["high"]:
        return _dollars(total["low"])
    return _fill(_text()["range"], low=_dollars(total["low"]), high=_dollars(total["high"]))


def explain(result: JsonObject) -> Explanation:
    """The working of a `price()` result as display text, with each number's source.

    Each charge of a `calculated` result is one line: the quantity with its unit, the published
    rate per unit and the amount, with where each came from. A `reported` result has one line, the
    provider's own figure. An `unknown` result has no lines. The summary is one sentence for the
    total, or for why there is none. The exact decimals stay beside their text; the lines' exact
    amounts add up to the total.
    """
    text = _text()
    label = result["label"]
    if label == "reported":
        lines = [_reported_line(result)]
    elif label == "calculated":
        lines = [_line(line) for line in result["lines"]]
    else:
        lines = []
    if label == "unknown" or result["total"] is None:
        held_back = result["held_back_by"]
        reason = held_back[0]["text"] if held_back else text["unknown_reason"]
        summary = _fill(text["summary"]["unknown"], reason=reason)
    else:
        summary = _fill(text["summary"][label], total=_total(result["total"]))
    return {"summary": summary, "lines": lines, "price_version": result["versions"]["prices"]}
