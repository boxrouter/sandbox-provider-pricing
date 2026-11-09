# SPDX-FileCopyrightText: BoxRouter, Inc.
# SPDX-License-Identifier: Apache-2.0
"""Provider retry schedules for late per-sandbox records."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sandbox_provider_pricing.providers import bundled_billing

UNPRICED_WINDOW_S = 1800
UNPRICED_FIRST_S = 15


@dataclass(frozen=True, slots=True)
class RevisitPolicy:
    """Immutable operational retry policy measured from canonical sandbox end."""

    after_s: int
    until_s: int
    interval_s: int
    #: For this long after the end, a read that still finds no price is repeated sooner than
    #: `interval_s` (see `next_read`), and the sooner reads are at least `unpriced_first_s` apart.
    unpriced_window_s: int = UNPRICED_WINDOW_S
    unpriced_first_s: int = UNPRICED_FIRST_S

    def __post_init__(self) -> None:
        if any(
            not isinstance(value, int) or isinstance(value, bool)
            for value in (
                self.after_s,
                self.until_s,
                self.interval_s,
                self.unpriced_window_s,
                self.unpriced_first_s,
            )
        ):
            raise TypeError("revisit seconds must be integers")
        if self.after_s < 0 or self.until_s <= 0 or self.interval_s <= 0:
            raise ValueError(
                "revisit seconds must be non-negative, with positive window and interval"
            )
        if self.unpriced_window_s <= 0 or self.unpriced_first_s <= 0:
            raise ValueError("unpriced revisit seconds must be positive")
        if self.after_s > self.until_s:
            raise ValueError("after_s must not exceed until_s")

    def next_read(
        self, ended_at: datetime, *, last_read_at: datetime | None = None
    ) -> datetime | None:
        """Return the first scheduled read or the next cadence, including the final boundary."""
        _aware(ended_at, "ended_at")
        ended_at = ended_at.astimezone(UTC)
        if last_read_at is not None:
            _aware(last_read_at, "last_read_at")
            last_read_at = last_read_at.astimezone(UTC)
            if last_read_at >= ended_at + timedelta(seconds=self.until_s):
                return None
        first = ended_at + timedelta(seconds=self.after_s)
        if last_read_at is None:
            return first
        if last_read_at < first:
            return first
        candidate = max(first, last_read_at + timedelta(seconds=self.interval_s))
        return min(candidate, ended_at + timedelta(seconds=self.until_s))

    def may_change(self, ended_at: datetime, *, as_of: datetime) -> bool:
        """Whether the operational retry window remains open (not a finality promise)."""
        _aware(ended_at, "ended_at")
        _aware(as_of, "as_of")
        ended_at = ended_at.astimezone(UTC)
        as_of = as_of.astimezone(UTC)
        return as_of < ended_at + timedelta(seconds=self.until_s)


def revisit(provider: str) -> RevisitPolicy:
    """Load one provider's public revisit policy from bundled billing metadata."""
    policy = scheduled_revisit(provider)
    if policy is None:
        raise ValueError(f"provider {provider!r} has no revisit policy")
    return policy


def scheduled_revisit(provider: str) -> RevisitPolicy | None:
    """A provider's revisit policy, or None while its billing declares none (`revisit: null`,
    as a newly scaffolded provider does): no read is scheduled and no cost is final."""
    # Read only, so the shared bundled document needs no copy.
    data = bundled_billing(provider).get("revisit")
    if data is None:
        return None
    if not isinstance(data, dict):
        raise ValueError(f"provider {provider!r} has no revisit policy")
    return RevisitPolicy(
        after_s=data["after_s"],
        until_s=data["until_s"],
        interval_s=data["interval_s"],
        unpriced_window_s=data.get("unpriced_window_s", UNPRICED_WINDOW_S),
        unpriced_first_s=data.get("unpriced_first_s", UNPRICED_FIRST_S),
    )


def _aware(value: datetime, name: str) -> None:
    if not isinstance(value, datetime):
        raise TypeError(f"{name} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
