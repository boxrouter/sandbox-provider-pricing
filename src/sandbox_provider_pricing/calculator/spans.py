# SPDX-FileCopyrightText: BoxRouter, Inc.
# SPDX-License-Identifier: Apache-2.0
"""Exact decimal quantities, known exactly or only between two bounds, and their text."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from sandbox_provider_pricing._util import decimal_text

SECONDS_PER_HOUR = Decimal(3600)
MIB_PER_GIB = Decimal(1024)
BYTES_PER_GIB = Decimal(2**30)
BYTES_PER_GB = Decimal(10**9)
CREATIONS_PER_MILLION = Decimal(1_000_000)


@dataclass(frozen=True)
class Span:
    """A quantity known exactly (low equals high) or only to lie between two bounds."""

    low: Decimal
    high: Decimal

    @classmethod
    def exact(cls, value: Decimal) -> Span:
        return cls(value, value)

    @property
    def is_exact(self) -> bool:
        return self.low == self.high

    def __add__(self, other: Span) -> Span:
        return Span(self.low + other.low, self.high + other.high)

    def times(self, factor: Decimal | Span) -> Span:
        if isinstance(factor, Span):
            return Span(self.low * factor.low, self.high * factor.high)
        return Span(self.low * factor, self.high * factor)

    def divided_by(self, divisor: Decimal) -> Span:
        return Span(self.low / divisor, self.high / divisor)


ZERO = Span.exact(Decimal(0))
ONE = Span.exact(Decimal(1))


def as_decimal(value: Any) -> Decimal | None:
    """A JSON number as an exact decimal; None for anything else, or below zero."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = Decimal(str(value))
    return number if number >= 0 else None


def span_text(span: Span) -> str | dict[str, str]:
    if span.is_exact:
        return decimal_text(span.low)
    return {"low": decimal_text(span.low), "high": decimal_text(span.high)}
