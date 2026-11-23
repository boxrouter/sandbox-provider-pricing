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
    (`result["revisit"]["next_read_at"]`), except while the price is still unknown: the policy
    repeats only every `interval_s`, so a read that finds the provider's records incomplete would
    leave the cost unknown for an hour. While it is unknown, the next read comes after half the
    time since the end (at least `unpriced_first_s` from `now`) if that is sooner than the
    policy's time, so the wait grows with the age of the sandbox up to the policy's interval and
    a record that lands late is read soon after it does.

    Where the policy states `final_after_s` (the provider's declared final time plus the spec's
    grace) and that time is still ahead, the next read is never later than it, known price or
    not: the read made then is the one that can find the cost final, so a cost known early is
    settled at the provider's own final time instead of one `interval_s` after its first read.

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
    when = planned
    if result["label"] == "unknown":
        since_end = now - ended_at
        when = min(planned, now + max(timedelta(seconds=policy.unpriced_first_s), since_end / 2))
    if policy.final_after_s is not None:
        final_at = ended_at + timedelta(seconds=policy.final_after_s)
        if now < final_at:
            when = min(when, final_at)
    return when
