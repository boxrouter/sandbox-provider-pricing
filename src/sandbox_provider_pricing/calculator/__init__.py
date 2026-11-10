# SPDX-FileCopyrightText: BoxRouter, Inc.
# SPDX-License-Identifier: Apache-2.0
"""The cost calculator: what a sandbox used, priced by one provider's price version.

Pure arithmetic over the three formats in `schemas/`: no I/O, no clock, no provider names.
Every quirk of a provider is a meter rule in its price version. Money is `Decimal`, kept
as plain decimal strings in the answer, and never rounded to cents.

A sandbox cost is `calculated` from provider usage or `unknown` with a null total.
Assumptions, our own clocks and bounded quantities never produce a sandbox cost.
Hourly rate-card quotes may still be ranges.

- `documents`: `cost` and `per_hour`, the two answers.
- `charges`: one cost line per resource, from its quantity and rate.
- `quantities`: each resource's size and billed time, in the rate's unit.
- `findings`: how sure each usage fact is, and what holds a cost back.
- `spans`: exact or bounded decimal quantities.
"""

from sandbox_provider_pricing._util import CONTEXT
from sandbox_provider_pricing.calculator.charges import Charge, find_rate
from sandbox_provider_pricing.calculator.documents import (
    CREDITS_EXCLUSION,
    FACTS_WITH_TIMES,
    cost,
    find_class,
    per_hour,
)
from sandbox_provider_pricing.calculator.findings import KNOWN_SOURCES, Findings
from sandbox_provider_pricing.calculator.quantities import BASES, TIME_RESOURCES
from sandbox_provider_pricing.calculator.spans import (
    BYTES_PER_GB,
    BYTES_PER_GIB,
    CREATIONS_PER_MILLION,
    MIB_PER_GIB,
    ONE,
    SECONDS_PER_HOUR,
    ZERO,
    Span,
)

__all__ = [
    "BASES",
    "BYTES_PER_GB",
    "BYTES_PER_GIB",
    "CONTEXT",
    "CREATIONS_PER_MILLION",
    "CREDITS_EXCLUSION",
    "FACTS_WITH_TIMES",
    "KNOWN_SOURCES",
    "MIB_PER_GIB",
    "ONE",
    "SECONDS_PER_HOUR",
    "TIME_RESOURCES",
    "ZERO",
    "Charge",
    "Findings",
    "Span",
    "cost",
    "find_class",
    "find_rate",
    "per_hour",
]
