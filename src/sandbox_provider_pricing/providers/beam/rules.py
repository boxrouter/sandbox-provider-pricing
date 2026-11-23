# SPDX-FileCopyrightText: BoxRouter, Inc.
# SPDX-License-Identifier: Apache-2.0
"""Beam: the spec's cost lines when a provider states them, else waiting and then unknown.

Beam documents no per-sandbox usage or cost record (SDK, gateway REST and platform API, read
2026-11-23), so no cost is known today. A cost in the spec's shape is read as it comes; without one
the cost stays waiting, then unknown, never a list-price estimate.
"""

from sandbox_provider_pricing.types import BillableUsage, Document, Evidence
from sandbox_provider_pricing.usage import spec_cost, waiting_for_record


def billable(
    evidence: Evidence,
    billing: Document,
    *,
    as_of: str | None = None,
    **_: object,
) -> BillableUsage:
    priced = spec_cost(evidence, billing, as_of=as_of)
    return waiting_for_record(evidence, billing, as_of=as_of) if priced is None else priced
