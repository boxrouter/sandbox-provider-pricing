# SPDX-FileCopyrightText: BoxRouter, Inc.
# SPDX-License-Identifier: Apache-2.0
"""The agent fallback: a draft is believed only when code verifies it, with no network.

The replies under `fixtures/drafts/` are what Claude answered on 2026-10-03 for E2B's page and
for the same page with its 1 vCPU price changed to $0.000016/s, and with its Pro plan fee changed
to $175 a month (the page is the recorded one with that figure edited).
"""

import copy
import json
import subprocess
import sys
import tempfile
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
import yaml  # type: ignore[import-untyped]
from claude_agent_sdk import ClaudeAgentOptions, ResultMessage
from pytest_mock import MockerFixture

from sandbox_provider_pricing.types import JsonObject
from sandbox_provider_pricing.watch import agent, check, cli, draft
from sandbox_provider_pricing.watch import prompt as draft_prompt
from sandbox_provider_pricing.watch import verify as draft_verify
from sandbox_provider_pricing.watch.check import PageText

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).parent / "fixtures"
E2B_VERSION = ROOT / "src/sandbox_provider_pricing/providers/e2b/prices/2026-10-20-061802Z.yaml"
URL = "https://e2b.dev/pricing"
NOW = datetime(2026, 10, 21, 12, 0, tzinfo=UTC)
KEY = "sk-ant-test-secret"


def current() -> JsonObject:
    """Build the compact page shape these draft tests exercise from the current version."""
    document: JsonObject = yaml.safe_load(E2B_VERSION.read_text(encoding="utf-8"))
    original = json.loads(recorded("e2b-unchanged.reply.json"))
    page_sources = [{"url": URL, "quote": quote} for quote in original["sources"]]
    sources = []
    for source in document["sources"]:
        if source["url"] == URL:
            sources.extend(page_sources)
        else:
            sources.append(source)
    document["sources"] = sources
    document["classes"] = json.loads(recorded("e2b-unchanged.reply.json"))["classes"]
    document["exclusions"] = original["exclusions"]
    document["open_questions"] = json.loads(recorded("e2b-unchanged.reply.json"))["open_questions"]
    document.pop("supersedes", None)
    return document


def page(name: str) -> PageText:
    return check.page_text((FIXTURES / "pages" / f"{name}.html").read_text(encoding="utf-8"))


def plan_fee_page() -> str:
    """E2B's recorded page, with the Pro plan fee at $175 a month and nothing else changed."""
    html = (FIXTURES / "pages" / "e2b-pricing.html").read_text(encoding="utf-8")
    assert html.count("$150") == 2
    return html.replace("$150", "$175")


def recorded(name: str) -> str:
    return (FIXTURES / "drafts" / name).read_text(encoding="utf-8")


def reply(name: str = "e2b-cpu-changed.reply.json") -> dict[str, Any]:
    document: dict[str, Any] = json.loads(recorded(name))
    if name != "e2b-plan-fee-changed.reply.json":
        document["exclusions"] = json.loads(recorded("e2b-unchanged.reply.json"))["exclusions"]
    return document


def drafted(parts: dict[str, Any] | None = None) -> JsonObject:
    """The recorded changed-page answer, assembled as a draft of E2B's version."""
    return draft.assemble(parts or reply(), current(), URL, NOW)


class Drafter:
    """Stands in for Claude: answers in turn, and keeps the prompts it was sent."""

    def __init__(self, *answers: str) -> None:
        self.answers = list(answers)
        self.prompts: list[str] = []

    def __call__(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return self.answers.pop(0)


def with_cpu_rate(parts: dict[str, Any], **rate: str) -> dict[str, Any]:
    changed = copy.deepcopy(parts)
    changed["classes"][0]["rates"]["cpu"].update(rate)
    return changed


# verify: what a draft must pass


def test_a_draft_that_was_read_from_the_page_passes() -> None:
    assert draft.verify(drafted(), page("e2b-cpu-changed"), URL) == []


def test_a_digit_changed_in_a_rate_fails_naming_the_rate() -> None:
    failures = draft.verify(
        drafted(with_cpu_rate(reply(), usd="0.000017")), page("e2b-cpu-changed"), URL
    )
    assert failures == ["The rate cpu 0.000017 is not a number in any quote about cpu."]


def test_a_rate_taken_from_another_resources_row_fails() -> None:
    """$0.0000180/s is E2B's price of 4 GiB of memory; it is in a quote, but not one about CPU."""
    failures = draft.verify(
        drafted(with_cpu_rate(reply(), usd="0.000018")), page("e2b-cpu-changed"), URL
    )
    assert failures == ["The rate cpu 0.000018 is not a number in any quote about cpu."]


def test_a_quote_that_is_not_on_the_page_fails_naming_the_quote() -> None:
    parts = reply()
    parts["sources"][1] = parts["sources"][1].replace("$0.000028/s", "$0.000029/s")
    failures = draft.verify(drafted(parts), page("e2b-cpu-changed"), URL)
    assert failures == [f"The quote is not on the page: {parts['sources'][1]!r}"]


def test_a_quote_from_the_old_page_is_not_on_the_changed_page() -> None:
    """Today's unchanged answer still quotes $0.000014/s, which the changed page no longer says."""
    failures = draft.verify(
        drafted(reply("e2b-unchanged.reply.json")), page("e2b-cpu-changed"), URL
    )
    assert len(failures) == 1
    assert "$0.000014/s" in failures[0]


def test_a_quote_the_page_still_says_must_be_kept() -> None:
    """Dropping a quote that is still true would quietly shrink what the daily check watches."""
    baseline = current()
    dropped = baseline["sources"][0]["quote"]
    baseline["sources"] = [baseline["sources"][0]]
    parts = reply("e2b-unchanged.reply.json")
    kept_quotes = parts["sources"][1:]
    parts["sources"] = kept_quotes
    assembled = draft.assemble(parts, baseline, URL, NOW)
    failures = draft.verify(
        assembled, check.page_text(" ".join([dropped, *kept_quotes])), URL, baseline
    )
    assert failures == [f"The page still says this, but the draft leaves it out: {dropped!r}"]


def test_a_quote_may_be_kept_inside_a_longer_one() -> None:
    parts = reply("e2b-unchanged.reply.json")
    parts["sources"][1:3] = [" ".join(parts["sources"][1:3])]
    assert draft.verify(drafted(parts), page("e2b-pricing"), URL, current()) == []


def test_a_quote_the_page_no_longer_says_may_go() -> None:
    old = [source["quote"] for source in current()["sources"] if "$0.000014/s" in source["quote"]]
    assert old, "the current version quotes the old CPU price"
    failures = draft.verify(drafted(), page("e2b-cpu-changed"), URL, current())
    assert failures == []
    assert old[0] not in reply()["sources"]


def test_quotes_from_other_pages_are_not_held_to_this_page() -> None:
    other = [source for source in drafted()["sources"] if source["url"] != URL]
    assert other, "E2B's version also quotes its billing docs"
    assert draft.verify(drafted(), page("e2b-cpu-changed"), URL) == []


def test_a_rate_in_another_time_unit_than_its_quote_fails() -> None:
    parts = with_cpu_rate(reply(), per="vcpu-hour")
    failures = draft.verify(drafted(parts), page("e2b-cpu-changed"), URL)
    assert failures == [
        "The rate cpu 0.000016 is vcpu-hour, but its quote says per second.",
    ]


def test_a_gb_rate_read_from_a_gib_quote_fails() -> None:
    parts = reply()
    parts["classes"][0]["rates"]["memory"] = {
        "usd": "0.0000045",
        "per": "gb-second",
        "size_per_unit": "1",
    }
    failures = draft.verify(drafted(parts), page("e2b-cpu-changed"), URL)
    assert failures == ["The rate memory 0.0000045 is per GB, but its quote says GiB."]


def test_a_gib_rate_read_from_a_gb_quote_fails() -> None:
    parts = reply()
    parts["sources"] = [quote.replace("Memory (GiB)", "Memory (GB)") for quote in parts["sources"]]
    on_page = PageText(visible=" ".join(parts["sources"]))
    failures = draft.verify(drafted(parts), on_page, URL)
    assert failures == ["The rate memory 0.0000045 is per GiB, but its quote says GB."]


def test_the_calculator_prices_an_hour_of_a_rate_as_its_quote_does() -> None:
    """Per second to per hour: 0.000016 a vCPU-second is 0.0576 a vCPU-hour, as T4's code says."""
    rate = {"usd": "0.000016", "per": "vcpu-second"}
    assert str(draft_verify._calculator_hour("cpu", rate)) == "0.0576"
    core = {"usd": "0.00003942", "per": "core-second", "size_per_unit": "2"}
    assert str(draft_verify._calculator_hour("cpu", core)) == "0.070956"


def test_a_monthly_rate_is_checked_as_its_quote_does() -> None:
    """Per month to per hour over 730 hours: the calculator and the quote agree on $0.80 a
    vCPU-month, and a rate read per hour from a per-month quote fails."""
    month = {"usd": "0.80", "per": "vcpu-month"}
    hour = draft_verify._calculator_hour("cpu", month)
    assert hour is not None and abs(hour * 730 - Decimal("0.80")) < Decimal("1e-40")
    quote = draft_verify.Mention(
        Decimal("0.80"), " per vCPU per month", "vCPU | $0.80 per vCPU per month"
    )
    assert draft_verify._time_unit_failures("cpu", "cpu", month, [quote]) == []
    hourly = {"usd": "0.80", "per": "vcpu-hour"}
    assert draft_verify._time_unit_failures("cpu", "cpu", hourly, [quote]) == [
        "The rate cpu 0.80 is vcpu-hour, but its quote says per month."
    ]


def test_a_draft_that_is_not_a_price_version_fails() -> None:
    document = drafted()
    del document["classes"][0]["meter"]
    failures = draft.verify(document, page("e2b-cpu-changed"), URL)
    assert len(failures) == 1
    assert failures[0].startswith("The draft is not a valid price version: classes/0: ")


def test_gpu_rates_are_verified_against_the_model_named_in_the_quote() -> None:
    path = next(
        (ROOT / "src/sandbox_provider_pricing/providers/daytona/prices").glob("2026-10-20-*.yaml")
    )
    version: JsonObject = yaml.safe_load(path.read_text(encoding="utf-8"))
    quotes = [source["quote"] for source in version["sources"]]
    everything = PageText(visible=" ".join(quotes))
    on_demand = next(item for item in version["classes"] if item["name"] == "on-demand")
    on_demand["rates"]["gpu"]["nvidia:b300"]["usd"] = "3.59"
    failures = draft.verify(version, everything, "https://www.daytona.io/pricing")
    assert failures == [
        "The rate on-demand gpu nvidia:b300 3.59 is not a number in a quote that names nvidia:b300."
    ]


def test_a_version_for_another_provider_fails() -> None:
    document = drafted()
    document["version"] = "modal@2026-10-21"
    failures = draft.verify(document, page("e2b-cpu-changed"), URL)
    assert failures == ["The version modal@2026-10-21 is not for e2b."]


def test_a_free_rate_needs_a_quote_about_it_that_says_free_or_included() -> None:
    """A stray 0, such as `$0/month`, is not a free rate."""
    document = drafted()
    document["classes"][0]["rates"] = {"disk": {"usd": "0", "per": "gib-second"}}
    document["classes"][0]["meter"] = {"disk": {"basis": "allocated", "billed_states": ["running"]}}
    base = "Base price $0/month $150/month"
    free = "Storage (GiB) Plan Costs 10 Hobby Free 20 Pro Free"
    document["sources"] = [{"url": URL, "quote": base}]
    failures = draft.verify(document, PageText(visible=base), URL)
    assert failures == ["The rate disk 0 is free, but no quote about disk says free or included."]
    document["sources"].append({"url": URL, "quote": free})
    assert draft.verify(document, PageText(visible=f"{base} {free}"), URL) == []
    included = "Storage (GiB) costs are included in the Pro plan."
    document["sources"] = [{"url": URL, "quote": included}]
    assert draft.verify(document, PageText(visible=included), URL) == []


@pytest.mark.parametrize(
    "path",
    sorted((ROOT / "src/sandbox_provider_pricing/providers").glob("*/prices/*.yaml")),
    ids=lambda p: f"{p.parent.parent.name}/{p.stem}",
)
def test_every_price_version_in_the_repository_passes_its_own_checks(path: Path) -> None:
    """The checks must not reject the real versions, whose rates the provider pages print."""
    version: JsonObject = yaml.safe_load(path.read_text(encoding="utf-8"))
    everything = PageText(visible=" ".join(source["quote"] for source in version["sources"]))
    assert draft.verify(version, everything, version["sources"][0]["url"]) == []


# classify: reworded, or which rate moved


def test_the_answer_for_todays_page_is_reworded() -> None:
    document = drafted(reply("e2b-unchanged.reply.json"))
    assert draft.verify(document, page("e2b-pricing"), URL) == []
    assert draft.classify(current(), document) == []


def test_the_answer_for_the_changed_page_names_the_rate_that_moved() -> None:
    assert draft.classify(current(), drafted()) == ["cpu 0.000014 -> 0.000016"]


def test_a_rate_is_the_same_rate_however_its_zeros_are_written() -> None:
    document = drafted(with_cpu_rate(reply("e2b-unchanged.reply.json"), usd="0.0000140"))
    assert draft.classify(current(), document) == []


def test_every_change_to_a_rate_or_meter_rule_is_named() -> None:
    document = drafted(reply("e2b-unchanged.reply.json"))
    document["classes"][0]["rates"]["memory"]["usd"] = "0.000005"
    document["classes"][0]["rates"]["egress"] = {"usd": "0.04", "per": "gib"}
    document["classes"][0]["meter"]["cpu"]["billed_states"] = ["running", "paused"]
    document["classes"][0]["meter"]["memory"]["minimum_seconds"] = 60
    assert draft.classify(current(), document) == [
        "memory 0.0000045 -> 0.000005",
        "cpu meter billed_states running -> running,paused",
        "egress none -> 0.04",
        "egress per none -> gib",
        "memory meter minimum_seconds none -> 60",
    ]


def test_a_rate_that_is_gone_is_named() -> None:
    document = drafted(reply("e2b-unchanged.reply.json"))
    del document["classes"][0]["rates"]["memory"]
    assert draft.classify(current(), document) == [
        "memory 0.0000045 -> none",
        "memory per gib-second -> none",
    ]


def test_a_version_with_several_classes_names_the_class() -> None:
    old = current()
    old["classes"].append(
        {
            "name": "vm",
            "rates": {"cpu": {"usd": "0.0001", "per": "vcpu-second"}},
            "meter": old["classes"][0]["meter"],
        }
    )
    new = copy.deepcopy(old)
    new["classes"][1]["rates"]["cpu"]["usd"] = "0.0002"
    assert draft.classify(old, new) == ["vm cpu 0.0001 -> 0.0002"]


def test_new_wording_of_a_quote_is_not_a_price_change() -> None:
    document = drafted(reply("e2b-unchanged.reply.json"))
    document["sources"][0]["quote"] = "Reworded."
    assert draft.classify(current(), document) == []


def test_the_answer_for_a_changed_plan_fee_names_the_exclusion_that_moved() -> None:
    document = drafted(reply("e2b-plan-fee-changed.reply.json"))
    assert draft.verify(document, check.page_text(plan_fee_page()), URL, current()) == []
    before, after = current()["exclusions"][0], document["exclusions"][0]
    assert "$150/month" in before and "$175/month" in after
    assert draft.classify(current(), document) == [
        f"exclusion: {' '.join(before.split())} -> {' '.join(after.split())}"
    ]


def test_an_exclusion_added_or_dropped_is_named() -> None:
    document = drafted(reply("e2b-unchanged.reply.json"))
    dropped = " ".join(document["exclusions"].pop(3).split())
    document["exclusions"].append("Support: a $200/month support plan is available.")
    assert draft.classify(current(), document) == [
        f"exclusion: {dropped} -> none",
        "exclusion: none -> Support: a $200/month support plan is available.",
    ]


def test_an_exclusion_is_the_same_however_it_is_spaced_or_ordered() -> None:
    document = drafted(reply("e2b-unchanged.reply.json"))
    document["exclusions"][0] = document["exclusions"][0].replace(" ", "  ")
    document["exclusions"].reverse()
    assert draft.classify(current(), document) == []


def test_a_rate_and_an_exclusion_that_both_moved_are_both_named() -> None:
    document = drafted(reply("e2b-plan-fee-changed.reply.json"))
    document["classes"][0]["rates"]["memory"]["usd"] = "0.000005"
    changes = draft.classify(current(), document)
    assert changes[0] == "memory 0.0000045 -> 0.000005"
    assert [change.split(" ", 1)[0] for change in changes] == ["memory", "exclusion:"]


# assemble: what the agent writes and what the clock writes


def test_the_draft_keeps_other_pages_quotes_and_sets_its_own_dates() -> None:
    document = drafted()
    assert document["provider"] == "e2b"
    assert document["version"] == "e2b@2026-10-21"
    assert document["effective_from"] == document["retrieved_at"] == "2026-10-21T12:00:00Z"
    kept = [source for source in current()["sources"] if source["url"] != URL]
    assert [source for source in document["sources"] if source["url"] != URL] == kept
    assert [source["quote"] for source in document["sources"] if source["url"] == URL] == reply()[
        "sources"
    ]
    # the page's fresh quotes sit where its old ones were
    assert document["sources"][0]["url"] == URL
    assert list(document) == list(current())


def test_a_second_same_day_draft_gets_a_utc_time_suffix() -> None:
    old = current()
    old["version"] = "e2b@2026-10-21"
    document = draft.assemble(reply(), old, URL, NOW)
    assert document["version"] == "e2b@2026-10-21-120000Z"


# read_reply: the answer, however it is wrapped


def test_an_answer_that_is_the_object_is_read() -> None:
    found, problems = draft.read_reply(recorded("e2b-cpu-changed.reply.json"))
    assert problems == []
    assert found == reply()


def test_the_last_object_is_the_answer_when_a_stray_one_comes_first() -> None:
    """Claude once answered a placeholder object, and then the real one in a code fence."""
    found, problems = draft.read_reply(recorded("e2b-cpu-changed.stray.json"))
    assert problems == []
    assert found is not None
    assert found["classes"][0]["rates"]["cpu"]["usd"] == "0.000016"


@pytest.mark.parametrize(
    ("text", "problem"),
    [
        ("I could not read the page.", "The answer has no JSON object."),
        ('{"sources": ["a"', "The answer has no JSON object."),
        ('{"sources": ["a"]}', "The answer has no `classes`."),
        ("[1, 2]", "The answer has no JSON object."),
        (
            '{"sources": "a", "classes": [], "exclusions": [], "open_questions": []}',
            "`sources` must be a list of quote strings.",
        ),
        (
            '{"sources":[],"classes":[],"exclusions":[],"open_questions":[],"version":"x"}',
            "The answer has `version`, which is not asked for.",
        ),
    ],
)
def test_an_answer_that_is_not_the_object_asked_for_says_why(text: str, problem: str) -> None:
    found, problems = draft.read_reply(text)
    assert found is None
    assert problem in problems


# draft_version: one retry, then unreadable


def test_a_verified_first_answer_is_one_call() -> None:
    drafter = Drafter(recorded("e2b-cpu-changed.reply.json"))
    outcome = draft.draft_version(current(), page("e2b-cpu-changed"), URL, drafter, now=NOW)
    assert outcome.status == "price changed"
    assert outcome.result_line() == "price changed: cpu 0.000014 -> 0.000016"
    assert outcome.draft == drafted()
    assert len(drafter.prompts) == 1


def test_the_unchanged_page_is_reworded() -> None:
    drafter = Drafter(recorded("e2b-unchanged.reply.json"))
    outcome = draft.draft_version(current(), page("e2b-pricing"), URL, drafter, now=NOW)
    assert outcome.result_line() == "reworded"
    assert outcome.draft is not None
    assert outcome.draft["version"] == "e2b@2026-10-21"


def test_a_changed_exclusion_alone_is_a_price_change() -> None:
    drafter = Drafter(recorded("e2b-plan-fee-changed.reply.json"))
    changed = check.page_text(plan_fee_page())
    outcome = draft.draft_version(current(), changed, URL, drafter, now=NOW)
    assert outcome.status == "price changed"
    assert len(outcome.changes) == 1
    assert outcome.changes[0].startswith("exclusion: Plan fee: Hobby $0/month; Pro $150/month;")
    assert (
        outcome.changes[0].split(" -> ")[1].startswith("Plan fee: Hobby $0/month; Pro $175/month;")
    )
    assert outcome.result_line() == f"price changed: {outcome.changes[0]}"
    assert len(drafter.prompts) == 1


def test_a_rejected_draft_is_retried_once_with_the_failures_listed() -> None:
    bad = json.dumps(with_cpu_rate(reply(), usd="0.000017"))
    drafter = Drafter(bad, recorded("e2b-cpu-changed.reply.json"))
    outcome = draft.draft_version(current(), page("e2b-cpu-changed"), URL, drafter, now=NOW)
    assert outcome.result_line() == "price changed: cpu 0.000014 -> 0.000016"
    assert len(drafter.prompts) == 2
    assert "rejected" not in drafter.prompts[0]
    assert "- The rate cpu 0.000017 is not a number in any quote about cpu." in drafter.prompts[1]


def test_an_answer_that_is_not_json_is_retried_too() -> None:
    drafter = Drafter("Sorry, here is a table instead.", recorded("e2b-unchanged.reply.json"))
    outcome = draft.draft_version(current(), page("e2b-pricing"), URL, drafter, now=NOW)
    assert outcome.status == "reworded"
    assert "- The answer has no JSON object." in drafter.prompts[1]


def test_two_rejected_drafts_are_unreadable_and_ask_no_third_time() -> None:
    drafter = Drafter(
        json.dumps(with_cpu_rate(reply(), usd="0.000017")),
        json.dumps(with_cpu_rate(reply(), usd="0.000018")),
    )
    outcome = draft.draft_version(current(), page("e2b-cpu-changed"), URL, drafter, now=NOW)
    assert outcome.status == "unreadable"
    assert outcome.draft is None
    assert outcome.failures == [
        "attempt 1: The rate cpu 0.000017 is not a number in any quote about cpu.",
        "attempt 2: The rate cpu 0.000018 is not a number in any quote about cpu.",
    ]
    assert len(drafter.prompts) == 2


def test_a_page_too_long_to_send_is_unreadable_without_asking(mocker: MockerFixture) -> None:
    mocker.patch.object(draft, "MAX_PAGE_CHARS", 100)
    drafter = Drafter()
    outcome = draft.draft_version(current(), page("e2b-pricing"), URL, drafter, now=NOW)
    assert outcome.status == "unreadable"
    assert drafter.prompts == []


def test_a_drafter_that_cannot_be_reached_is_an_error_not_a_verdict() -> None:
    def unreachable(prompt: str) -> str:
        raise draft.DraftError("Claude could not be reached: ConnectionError")

    with pytest.raises(draft.DraftError, match="could not be reached"):
        draft.draft_version(current(), page("e2b-pricing"), URL, unreachable, now=NOW)


# the prompt and the page's address


def test_the_prompt_carries_the_version_the_page_and_the_format() -> None:
    prompt = draft.build_prompt(current(), URL, page("e2b-cpu-changed"))
    assert "version: e2b@2026-10-20-061802Z" in prompt
    assert "$0.000016/s" in prompt
    assert '"$id": "urn:boxrouter:sandbox-provider-pricing:price-version"' in prompt
    assert "<script-text>" not in prompt


def test_text_a_page_keeps_in_scripts_is_sent_only_when_a_quote_needs_it() -> None:
    version = {
        "provider": "x",
        "sources": [{"url": URL, "quote": "Must equal 1024"}],
        "classes": [],
    }
    hidden = PageText(visible="Prices.", embedded="Must equal 1024 MiB")
    shown = PageText(visible="Prices. Must equal 1024 MiB", embedded="Must equal 1024 MiB")
    assert "<script-text>\nMust equal 1024 MiB\n</script-text>" in draft.build_prompt(
        version, URL, hidden
    )
    assert "<script-text>" not in draft.build_prompt(version, URL, shown)


def test_script_text_is_sent_around_where_the_quotes_sit() -> None:
    filler = "x " * 50_000
    kept = "Must be 1, or an even number."
    changed = "The amount of memory in megabytes to allocate. Must equal vcpus * 2048."
    now_says = "The amount of memory in megabytes to allocate. Must equal 4096."
    embedded = f"{filler}{kept}{filler}{now_says}{filler}"
    version = {
        "provider": "x",
        "sources": [
            {"url": URL, "quote": kept},
            {"url": URL, "quote": changed},
            {"url": "https://example.com/other", "quote": "Elsewhere."},
        ],
        "classes": [],
    }
    excerpts = draft_prompt._script_excerpts(
        version, URL, PageText(visible="Prices.", embedded=embedded)
    )
    assert kept in excerpts
    assert "Must equal 4096." in excerpts  # found by its first words, since its end changed
    assert "\n...\n" in excerpts
    assert len(excerpts) < 20_000


def test_script_text_is_cut_to_the_limit(mocker: MockerFixture) -> None:
    mocker.patch.object(draft_prompt, "MAX_EMBEDDED_CHARS", 50)
    version = {"provider": "x", "sources": [{"url": URL, "quote": "Quoted."}], "classes": []}
    excerpts = draft_prompt._script_excerpts(
        version, URL, PageText(visible="", embedded="Quoted." + "y" * 999)
    )
    assert len(excerpts) == 50


def test_the_page_is_the_source_whose_quotes_it_holds() -> None:
    version = current()
    assert draft.infer_url(version, page("e2b-cpu-changed")) == URL


def test_a_page_that_holds_no_quote_needs_to_be_named() -> None:
    with pytest.raises(draft.DraftError, match="--url"):
        draft.infer_url(current(), PageText(visible="Nothing here."))


# the command


def command(drafter: draft.Drafter, name: str = "e2b-cpu-changed", **options: str) -> int:
    with tempfile.TemporaryDirectory() as directory:
        version_path = Path(directory) / "current.yaml"
        version_path.write_text(yaml.safe_dump(current(), sort_keys=False), encoding="utf-8")
        return draft.run(
            str(version_path), str(FIXTURES / "pages" / f"{name}.html"), drafter, **options
        )


def test_the_last_line_names_the_price_that_changed(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    status = command(Drafter(recorded("e2b-cpu-changed.reply.json")))
    assert status == 0
    assert capsys.readouterr().out.splitlines()[-1] == "price changed: cpu 0.000014 -> 0.000016"


def test_the_last_line_for_a_changed_plan_fee_names_the_exclusion(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "plan-fee.html").write_text(plan_fee_page(), encoding="utf-8")
    drafter = Drafter(recorded("e2b-plan-fee-changed.reply.json"))
    assert draft.run(str(E2B_VERSION), str(tmp_path / "plan-fee.html"), drafter) == 0
    last = capsys.readouterr().out.splitlines()[-1]
    assert last.startswith("price changed: exclusion: Plan fee: Hobby $0/month; Pro $150/month;")
    assert " -> Plan fee: Hobby $0/month; Pro $175/month;" in last


def test_the_last_line_for_an_unchanged_page_is_reworded(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert command(Drafter(recorded("e2b-unchanged.reply.json")), "e2b-pricing") == 0
    assert capsys.readouterr().out.splitlines()[-1] == "reworded"


def test_the_verified_draft_is_written_where_asked_and_nowhere_else(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out = tmp_path / "draft.yaml"
    before = sorted(path.name for path in tmp_path.iterdir())
    command(Drafter(recorded("e2b-cpu-changed.reply.json")), out=str(out))
    assert out.read_text(encoding="utf-8").startswith(draft.PRICE_FILE_HEADER)
    written = yaml.safe_load(out.read_text(encoding="utf-8"))
    assert written["classes"][0]["rates"]["cpu"]["usd"] == "0.000016"
    assert draft.verify(written, page("e2b-cpu-changed"), URL) == []
    assert sorted(path.name for path in tmp_path.iterdir()) == sorted([*before, "draft.yaml"])
    capsys.readouterr()


def test_an_unreadable_page_lists_the_failures_and_exits_1(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out = tmp_path / "draft.yaml"
    bad = json.dumps(with_cpu_rate(reply(), usd="0.000017"))
    assert command(Drafter(bad, bad), out=str(out)) == 1
    lines = capsys.readouterr().out.splitlines()
    assert lines[-1] == "unreadable"
    assert "  attempt 2: The rate cpu 0.000017 is not a number in any quote about cpu." in lines
    assert not out.exists()


def test_a_page_that_cannot_be_read_exits_2(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert draft.run(str(E2B_VERSION), str(tmp_path / "missing.html"), Drafter()) == 2
    assert "missing.html" in capsys.readouterr().err


def test_the_key_is_never_printed(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", KEY)

    def echoes(prompt: str) -> str:
        raise draft.DraftError(f"401 invalid x-api-key {KEY}")

    assert command(echoes) == 2
    captured = capsys.readouterr()
    assert KEY not in captured.out + captured.err
    assert "invalid x-api-key [redacted]" in captured.err


def test_the_draft_command_without_a_key_exits_2(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    page_file = str(FIXTURES / "pages" / "e2b-cpu-changed.html")
    assert cli.main(["draft", "--page", page_file, str(E2B_VERSION)]) == 2
    assert capsys.readouterr().err == "ANTHROPIC_API_KEY is not set.\n"


# the agent: how Claude is asked


def result(**fields: Any) -> ResultMessage:
    base: dict[str, Any] = {
        "subtype": "success",
        "duration_ms": 1,
        "duration_api_ms": 1,
        "is_error": False,
        "num_turns": 1,
        "session_id": "test",
    }
    return ResultMessage(**{**base, **fields})


def stub_query(
    mocker: MockerFixture, *messages: ResultMessage | Exception
) -> list[ClaudeAgentOptions]:
    """Replace the SDK's `query` with one that answers `messages`; returns the options it got."""
    seen: list[ClaudeAgentOptions] = []

    async def fake(*, prompt: str, options: ClaudeAgentOptions) -> AsyncIterator[ResultMessage]:
        seen.append(options)
        for message in messages:
            if isinstance(message, Exception):
                raise message
            yield message

    mocker.patch.object(agent, "query", fake)
    return seen


def test_claude_is_asked_with_no_tools_and_none_of_the_machines_settings(
    mocker: MockerFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", KEY)
    seen = stub_query(mocker, result(result='{"ok": true}'))
    assert agent.ask_claude("prompt") == '{"ok": true}'
    assert seen[0].model == agent.MODEL
    assert seen[0].tools == []
    assert seen[0].setting_sources == []


def test_the_model_is_named_in_one_place() -> None:
    assert agent.MODEL.startswith("claude-")
    sources = [path.read_text(encoding="utf-8") for path in (ROOT / "src").rglob("*.py")]
    assert sum(source.count(agent.MODEL) for source in sources) == 1


def test_claude_is_not_asked_without_a_key(
    mocker: MockerFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Without the key the Claude Code binary would use whoever is logged in on the machine."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    seen = stub_query(mocker, result(result="{}"))
    with pytest.raises(draft.DraftError, match="ANTHROPIC_API_KEY is not set"):
        agent.ask_claude("prompt")
    assert seen == []


def test_an_error_from_claude_is_a_draft_error(
    mocker: MockerFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", KEY)
    stub_query(mocker, result(is_error=True, subtype="error_during_execution", result="Overloaded"))
    with pytest.raises(draft.DraftError, match="Claude answered with an error: Overloaded"):
        agent.ask_claude("prompt")


def test_a_failure_to_reach_claude_is_a_draft_error(
    mocker: MockerFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", KEY)
    stub_query(mocker, ConnectionError("no route"))
    with pytest.raises(draft.DraftError, match="could not be reached: ConnectionError: no route"):
        agent.ask_claude("prompt")


def test_the_drafting_does_not_need_the_agent_sdk() -> None:
    """The SDK is the `draft` extra: pricing usage must not pull in a Claude Code binary."""
    program = (
        "import sys; import sandbox_provider_pricing, sandbox_provider_pricing.calculator, "
        "sandbox_provider_pricing.watch.draft; assert 'claude_agent_sdk' not in sys.modules"
    )
    subprocess.run([sys.executable, "-c", program], check=True)
