# SPDX-FileCopyrightText: BoxRouter, Inc.
# SPDX-License-Identifier: Apache-2.0
"""Sail: the spec's cost lines, the provider's own figure.

Sail's spend API (`GET /sailboxes/spend`) reports each Sailbox's usage and cost in its own
figure; the in-process provider states it as one `reported` line. Without a record in the spec's
shape the cost stays waiting, then unknown, never a list-price estimate.
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
