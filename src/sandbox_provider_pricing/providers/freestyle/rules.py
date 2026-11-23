# SPDX-FileCopyrightText: BoxRouter, Inc.
# SPDX-License-Identifier: Apache-2.0
"""Freestyle: the spec's cost lines, priced here from the provider's own run-seconds record.

Freestyle has no per-sandbox cost API, and its VM record goes with the VM. The in-process
provider captures the cost just before the delete: lines whose quantities come from the VM's own
`totalRunSeconds`, its `createdAt` and its allocated size. This package prices those quantities at
the stored list rates; it never uses a call time or clock of ours as the provider's usage. Without
a record in the spec's shape the cost stays waiting, then unknown.
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
