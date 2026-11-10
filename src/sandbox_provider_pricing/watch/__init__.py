# SPDX-FileCopyrightText: BoxRouter, Inc.
# SPDX-License-Identifier: Apache-2.0
"""The daily price check, for a consumer that runs it: the names `spp check-imports` accepts.

- `check_version(...)`, `fetch_page(url)`, `PageText` and `VersionCheck`: does each page still say
  what a price version quotes?
- `draft_version(...)`, `Outcome` and `DraftError`: draft a new version when a page changed.
- `ask_claude(prompt)`: the agent the draft asks. It needs the `draft` extra, and reading it does
  not import the agent's SDK until it is called.

Nothing else in this folder is promised.
"""

from importlib import import_module

from sandbox_provider_pricing.watch.check import PageText, VersionCheck, check_version, fetch_page
from sandbox_provider_pricing.watch.draft import DraftError, Outcome, draft_version

__all__ = [
    "DraftError",
    "Outcome",
    "PageText",
    "VersionCheck",
    "ask_claude",
    "check_version",
    "draft_version",
    "fetch_page",
]


def ask_claude(prompt: str) -> str:
    """The agent's reply to a prompt; see `watch.agent`."""
    reply: str = import_module("sandbox_provider_pricing.watch.agent").ask_claude(prompt)
    return reply
