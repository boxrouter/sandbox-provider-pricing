# SPDX-FileCopyrightText: BoxRouter, Inc.
# SPDX-License-Identifier: Apache-2.0
"""How sure each usage fact is, and the gaps that keep a cost from being calculated."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from sandbox_provider_pricing.evidence import CERTAINTY
from sandbox_provider_pricing.types import Document, Finding

# Sources whose facts are not guesses. `calculated` is not here: the answer only keeps the
# source of the final fact, not the sources it was worked out from.
KNOWN_SOURCES = ("provider", "published", "measured", "recorded")


@dataclass
class Findings:
    """What keeps a cost from being `calculated`: guesses, and gaps that stop it entirely."""

    gaps: list[Finding] = field(default_factory=list)

    def gap(self, reason: str, code: str, resource: str) -> None:
        finding: Finding = {"code": code, "resource": resource, "text": reason}
        if finding not in self.gaps:
            self.gaps.append(finding)

    def read(
        self,
        what: str,
        fact: Document | None,
        present: bool,
        *,
        resource: str,
    ) -> bool:
        """Judge a usage fact by its source; True when its value can be used.

        A value is usable only when its source is retained and recognized.
        """
        source = None if fact is None else fact.get("source")
        if source not in KNOWN_SOURCES or not present:
            self.gap(_not_reported(what), "unreported_quantity", resource)
            return False
        return True


def _not_reported(what: str) -> str:
    """Describe missing provider evidence without repeating a fact's `how` field."""
    detail = what.removeprefix("The ").lower()
    if not detail.startswith(("the ", "a ")):
        detail = f"the {detail}"
    return f"The provider did not report {detail}."


def usage_fact(usage: Document, name: str) -> Document | None:
    fact = usage.get(name)
    return fact if isinstance(fact, Mapping) else None


def fact_source(fact: Document | None) -> str:
    return "unknown" if fact is None else str(fact.get("source", "unknown"))


def uncertainty(source: str) -> int:
    return CERTAINTY.index(source) if source in CERTAINTY else len(CERTAINTY)
