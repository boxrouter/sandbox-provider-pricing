# SPDX-FileCopyrightText: BoxRouter, Inc.
# SPDX-License-Identifier: Apache-2.0
"""Vercel's synthetic conformance cases: the whole-minute boundary and snapshot storage."""

from collections.abc import Callable
from datetime import datetime, timedelta

from sandbox_provider_pricing.types import Document, JsonObject

FIXTURE = "vercel/fixtures/best/evidence.json"
Load = Callable[[Document], JsonObject]


def boundaries(_cases: list[JsonObject], _load: Load) -> list[JsonObject]:
    """Fractional seconds around the documented whole-minute boundary.

    These are synthetic inputs, not measurements or provider observations.
    """
    cases: list[JsonObject] = []
    for seconds in (0, 0.001, 0.999, 1, 59.999, 60, 60.001, 120):
        start = datetime.fromisoformat("2026-10-12T12:00:00.500+00:00")
        stop = (start + timedelta(seconds=seconds)).isoformat().replace("+00:00", "Z")
        cases.append(
            {
                "id": f"vercel/synthetic/seconds-{seconds}",
                "kind": "price",
                "input": {
                    "fixture": FIXTURE,
                    "set": {
                        "provider_records/0/body/stoppedAt": stop,
                        "provider_records/0/body/activeCpuDurationMs": 0,
                    },
                },
            }
        )
    return cases


def records(_cases: list[JsonObject], load: Load) -> list[JsonObject]:
    """A second run from a snapshot, with the snapshot's size known and missing."""
    later = load({"input": {"fixture": FIXTURE}})["provider_records"][0]
    later["body"].update(
        startedAt="2026-10-12T12:10:00.500Z",
        stoppedAt="2026-10-12T12:12:00.500Z",
        sourceSnapshotId="snapshot-test",
    )
    recorded = load({"input": {"fixture": FIXTURE}})["provider_records"] + [later]
    cases: list[JsonObject] = []
    for known in (False, True):
        storage = (
            [
                {
                    "source": "vercel.snapshots.get",
                    "read_at": "2026-10-12T12:17:00Z",
                    "body": {"id": "snapshot-test", "sizeBytes": 1_000_000_000},
                }
            ]
            if known
            else []
        )
        cases.append(
            {
                "id": f"vercel/synthetic/snapshot-{'known' if known else 'missing'}",
                "kind": "price",
                "input": {"fixture": FIXTURE, "set": {"provider_records": recorded + storage}},
            }
        )
    return cases
