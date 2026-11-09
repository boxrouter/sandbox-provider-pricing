# SPDX-FileCopyrightText: BoxRouter, Inc.
# SPDX-License-Identifier: Apache-2.0
"""Reviewed, opt-in bounds for reusing a priced document at later read times."""

import json
import re
from typing import Any

from sandbox_provider_pricing._util import providers_root
from sandbox_provider_pricing.revisit import revisit

READ_TIME_CONTRACT = 1
READ_TIME_PATHS = (
    "as_of",
    "steps.rated.*.as_of",
    "steps.usage.*.*.observed_at",
    "steps.usage.*.intervals.*.observed_at",
    "steps.usage.*.intervals.*.size.observed_at",
)
# A full calendar day, the supremum of legal UTC-offset spread (<48h),
# subsecond precision rounded up, and a separate one-second strict-comparison margin.
_CALENDAR_SECONDS = 86400 + 172800 + 1
_MARGIN_SECONDS = 1


def _valid_use(entry: Any) -> bool:
    return (
        isinstance(entry, dict)
        and set(entry) == {"file", "function", "kind", "offset", "uses"}
        and entry["kind"] in ("copied verbatim", "compared with input", "bounded comparison")
        and all(
            isinstance(entry[key], str) and entry[key] for key in ("file", "function", "offset")
        )
        and isinstance(entry["uses"], list)
        and all(isinstance(use, str) and use for use in entry["uses"])
    )


def _valid_declaration(data: Any) -> bool:
    return (
        isinstance(data, dict)
        and set(data) == {"contract", "settles", "uses"}
        and isinstance(data["contract"], int)
        and not isinstance(data["contract"], bool)
        and data["contract"] == READ_TIME_CONTRACT
        and data["settles"] == "bounded"
        and isinstance(data["uses"], list)
        and all(_valid_use(entry) for entry in data["uses"])
    )


def settles_after(provider: str) -> int | None:
    """Seconds past all input times after which only READ_TIME_PATHS can change.

    Unknown providers, missing/malformed declarations and `settles: never` return None.
    See docs/read-time-contract.md for the reviewed guarantee and its limitations.
    """
    if re.fullmatch(r"[a-z][a-z0-9-]*", provider) is None:
        return None
    declaration = providers_root() / provider / "read-time.json"
    if not declaration.is_file():
        return None
    try:
        data = json.loads(declaration.read_text(encoding="utf-8"))
        if not _valid_declaration(data):
            return None
        policy = revisit(provider)
    except (ValueError, TypeError, KeyError):
        return None
    return policy.after_s + policy.until_s + policy.interval_s + _CALENDAR_SECONDS + _MARGIN_SECONDS
