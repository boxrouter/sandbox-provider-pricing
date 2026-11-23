# SPDX-FileCopyrightText: BoxRouter, Inc.
# SPDX-License-Identifier: Apache-2.0
"""The shapes each provider class sells, as the provider's own pages state them.

A provider's `billing.yaml` lists them under `shapes`, per spec class, each with its source page,
the date it was read and the quote. The price version owns what a shape costs. This module reads
the list and says whether a shape the Sandbox Provider Specification declares has a price.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Any

from sandbox_provider_pricing.calculator import per_hour
from sandbox_provider_pricing.providers import billing as provider_billing
from sandbox_provider_pricing.versions import latest_version

#: One shape or range: (low, high) for its vCPU count and for its MiB of memory. A provider that
#: publishes no maximum has an infinite high end.
Shape = tuple[tuple[float, float], tuple[float, float]]


def bounds(value: Any) -> tuple[float, float]:
    """A size field as (low, high): a number is a shape, a pair a range, a null high is open."""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value, value
    if isinstance(value, Sequence) and not isinstance(value, str) and len(value) == 2:
        low, high = value
        if isinstance(low, (int, float)) and (high is None or isinstance(high, (int, float))):
            return low, math.inf if high is None else high
    raise ValueError(f"a size is a number or a [low, high] pair, not {value!r}")


def class_shapes(provider: str, spec_class: str) -> list[Shape]:
    """The shapes a provider class sells, as its billing record lists them."""
    entries = (provider_billing(provider).get("shapes") or {}).get(spec_class)
    if not entries:
        raise ValueError(f"{provider}/{spec_class}: pricing records no shapes")
    return [(bounds(entry["cpu"]), bounds(entry["memory_mib"])) for entry in entries]


def is_priced(provider: str, spec_class: str, cpu: Any, memory_mib: Any) -> bool:
    """Whether pricing prices every size inside the declared shape (a number or a [low, high]).

    The shape must lie inside one of the class's recorded shapes, and the price version must price
    its low end. A class with no recorded shapes prices nothing.
    """
    try:
        shapes = class_shapes(provider, spec_class)
    except ValueError:
        return False
    (cpu_low, cpu_high), (memory_low, memory_high) = bounds(cpu), bounds(memory_mib)
    if not any(
        shape_cpu[0] <= cpu_low
        and cpu_high <= shape_cpu[1]
        and shape_memory[0] <= memory_low
        and memory_high <= shape_memory[1]
        for shape_cpu, shape_memory in shapes
    ):
        return False
    price = per_hour(
        latest_version(provider),
        {"cpu": cpu_low, "memory_mib": memory_low},
        class_name=spec_class,
    )
    return price is not None
