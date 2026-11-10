# SPDX-FileCopyrightText: BoxRouter, Inc.
# SPDX-License-Identifier: Apache-2.0
"""When to read a sandbox's provider records again: one answer for every consumer."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timedelta

from sandbox_provider_pricing._util import parse_time
from sandbox_provider_pricing.revisit import revisit
from sandbox_provider_pricing.types import Document


def next_read(result: Document, ended_at: datetime, now: datetime) -> datetime | None:
    """When to read the provider's records for this result again, or None when no read is due.

    A result that is `final` needs none. Otherwise the provider's revisit policy sets the time
    (`result["revisit"]["next_read_at"]`), except while the price is still unknown shortly after
    the end: the policy repeats only every `interval_s`, so a first read that finds the
    provider's records incomplete would leave the cost unknown for an hour. For the policy's
    `unpriced_window_s` after the end, the read comes after half the time since the end, at
    least `unpriced_first_s` from `now`, if that is sooner than the policy's time. After the
    window the policy's time stands.

    A composed result (`compose()`) is due when its earliest unfinished part is. `ended_at` is the
    sandbox's canonical end, the same one given to `price()`; both times must carry a zone.
    """
    for name, value in (("ended_at", ended_at), ("now", now)):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError(f"{name} must be timezone-aware")
    parts = result.get("parts")
    if isinstance(parts, list):
        due = [next_read(part, ended_at, now) for part in parts]
        return min((moment for moment in due if moment is not None), default=None)
    scheduled = None if result["final"] else result.get("revisit")
    if not isinstance(scheduled, Mapping):
        return None
    planned = parse_time(scheduled["next_read_at"])
    policy = revisit(result["provider"])
    since_end = now - ended_at
    if result["label"] != "unknown" or since_end >= timedelta(seconds=policy.unpriced_window_s):
        return planned
    return min(planned, now + max(timedelta(seconds=policy.unpriced_first_s), since_end / 2))
