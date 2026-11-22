# SPDX-FileCopyrightText: BoxRouter, Inc.
# SPDX-License-Identifier: Apache-2.0
"""Superserve: the spec's cost lines, priced at the stored list rates.

Superserve reports no cost. Its in-process provider states each active period as `usage` lines
(vCPU-seconds and GiB-seconds) and no amount, which this package prices. A cost that is not in the
spec's shape falls back to the default rules: billed time from the provider's lifecycle times.
"""

from sandbox_provider_pricing.types import BillableUsage, Document, Evidence
from sandbox_provider_pricing.usage import default_billable, spec_cost


def billable(
    evidence: Evidence,
    billing: Document,
    *,
    as_of: str | None = None,
    **_: object,
) -> BillableUsage:
    priced = spec_cost(evidence, billing, as_of=as_of)
    return default_billable(evidence, as_of=as_of) if priced is None else priced
