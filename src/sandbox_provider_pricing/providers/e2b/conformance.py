# SPDX-FileCopyrightText: BoxRouter, Inc.
# SPDX-License-Identifier: Apache-2.0
"""E2B's synthetic conformance cases: a recorded run whose events report the requested size."""

from collections.abc import Callable

from sandbox_provider_pricing.types import Document, JsonObject

Load = Callable[[Document], JsonObject]


def allocations(cases: list[JsonObject], _load: Load) -> list[JsonObject]:
    """Each recorded case of the fixture again, with its execution events at the requested size."""
    synthetic: list[JsonObject] = []
    for case in cases:
        if case["kind"] != "price" or not case["id"].endswith("/recorded"):
            continue
        if not case["input"]["fixture"].startswith("e2b/"):
            continue
        changes = dict(case["input"]["set"])
        allocation = {
            "vcpu_count": changes["requested/cpu"],
            "memory_mb": changes["requested/memory_mib"],
        }
        for index in (1, 3):
            changes[f"provider_records/{index}/body/event_data/execution"] = allocation
        synthetic.append(
            {
                "id": case["id"].removesuffix("recorded") + "synthetic-allocation",
                "kind": "price",
                "input": {**case["input"], "set": changes},
            }
        )
    return synthetic
