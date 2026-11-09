# SPDX-FileCopyrightText: BoxRouter, Inc.
# SPDX-License-Identifier: Apache-2.0
"""The default rules: billed time from the provider's own lifecycle times, nothing else."""

from sandbox_provider_pricing.types import BillableUsage, Document, Evidence
from sandbox_provider_pricing.usage import default_billable


def billable(
    evidence: Evidence,
    _billing: Document,
    *,
    as_of: str | None = None,
    **_: object,
) -> BillableUsage:
    return default_billable(evidence, as_of=as_of)
