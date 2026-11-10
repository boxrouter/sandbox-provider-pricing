# SPDX-FileCopyrightText: BoxRouter, Inc.
# SPDX-License-Identifier: Apache-2.0
"""Asks Claude for a draft, through the Claude Agent SDK. The only module that imports it.

The SDK is the optional `draft` extra, so a service that only prices usage does not install a
Claude Code binary. Nothing here judges the answer; `watch.verify` does.
"""

import asyncio
import os

from claude_agent_sdk import ClaudeAgentOptions, ResultMessage, query

from sandbox_provider_pricing.watch.draft import DraftError

# The one place the model is named.
MODEL = "claude-sonnet-5-5"
KEY_VARIABLE = "ANTHROPIC_API_KEY"
SYSTEM_PROMPT = (
    "You read a provider's pricing page and write down what it charges, exactly as the page "
    "says it. You have no tools and need none: everything you need is in the message. Answer "
    "with the one JSON object you were asked for, and nothing else."
)


async def _ask(prompt: str) -> str:
    options = ClaudeAgentOptions(
        model=MODEL,
        system_prompt=SYSTEM_PROMPT,
        tools=[],  # no built-in tools: the page is in the prompt
        setting_sources=[],  # nothing from the user's or the project's Claude settings
        max_turns=2,
    )
    answer = ""
    async for message in query(prompt=prompt, options=options):
        if isinstance(message, ResultMessage):
            if message.is_error:
                raise DraftError(
                    f"Claude answered with an error: {message.result or message.subtype}"
                )
            answer = message.result or ""
    return answer


def ask_claude(prompt: str) -> str:
    """Send one prompt to Claude and return its answer. The key must be in the environment.

    Without it the Claude Code binary would fall back to whoever is logged in on this machine,
    and a scheduled run must never bill a person's own account.
    """
    if not os.environ.get(KEY_VARIABLE):
        raise DraftError(f"{KEY_VARIABLE} is not set.")
    try:
        return asyncio.run(_ask(prompt))
    except DraftError:
        raise
    except Exception as error:
        raise DraftError(f"Claude could not be reached: {type(error).__name__}: {error}") from error
