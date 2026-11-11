# SPDX-FileCopyrightText: BoxRouter, Inc.
# SPDX-License-Identifier: Apache-2.0
"""The calculator prices usage with the meter rules in a price version, and never guesses."""

import copy
import itertools
import json
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any

import pytest
import yaml  # type: ignore[import-untyped]
from jsonschema import Draft202012Validator, FormatChecker

from sandbox_provider_pricing.calculator import cost, per_hour
from sandbox_provider_pricing.types import Document, JsonObject
from sandbox_provider_pricing.versions import priced_provider_ids

ROOT = Path(__file__).resolve().parents[1]
PACKAGES = ROOT / "src" / "sandbox_provider_pricing" / "providers"
OBSERVED = "2026-10-03T10:00:00Z"
SOURCES = ["provider", "published", "measured", "recorded", "calculated", "unknown"]
COST_VALIDATOR = Draft202012Validator(
    json.loads((ROOT / "schemas" / "cost.schema.json").read_text()), format_checker=FormatChecker()
)


def price(provider: str, date: str | None = None) -> JsonObject:
    stems = {
        "blaxel": "2026-10-20-061947Z",
        "boat": "2026-11-01",
        "daytona": "2026-10-24-065000Z",
        "e2b": "2026-10-20-061802Z",
        "modal": "2026-10-24-065000Z",
        "vercel": "2026-10-20-055630Z",
    }
    stem = stems[provider]
    document: JsonObject = yaml.safe_load(
        (PACKAGES / provider / "prices" / f"{stem}.yaml").read_text()
    )
    return document


def price_file(provider: str, stem: str) -> JsonObject:
    document: JsonObject = yaml.safe_load(
        (PACKAGES / provider / "prices" / f"{stem}.yaml").read_text()
    )
    return document


def example(kind: str) -> JsonObject:
    document: JsonObject = json.loads((ROOT / "examples" / f"{kind}.json").read_text())
    return document


def fact(source: str = "recorded", **fields: Any) -> JsonObject:
    return {**fields, "source": source, "observed_at": OBSERVED, "how": "test fixture"}


def interval(state: str, seconds: Any, source: str = "provider") -> JsonObject:
    return fact(source, state=state, seconds=seconds)


def usage(
    provider: str,
    seconds: Any = 1800,
    *,
    cpu: float = 2,
    memory_mib: int = 4096,
    disk_mib: int | None = None,
    size_source: str = "recorded",
    intervals: list[JsonObject] | None = None,
    class_fact: JsonObject | None = None,
    **facts: Any,
) -> JsonObject:
    """A sandbox of `cpu` vCPUs and `memory_mib` that ran `seconds`, with other facts as given."""
    record: JsonObject = {
        "provider": provider,
        "started": fact(at=OBSERVED),
        "region": fact(name="iad"),
        "size": fact(
            size_source,
            cpu=cpu,
            memory_mib=memory_mib,
            **({"disk_mib": disk_mib} if disk_mib is not None else {}),
        ),
        "intervals": intervals or [interval("running", seconds)],
        "creations": fact(count=1),
    }
    if class_fact is not None:
        record["class"] = class_fact
    record.update(facts)
    return record


def version_with(**class_parts: Any) -> JsonObject:
    """A price version with one default class built from `rates`, `meter` and the like."""
    document = example("price-version")
    document["classes"] = [{"name": "default", "default": True, **class_parts}]
    return document


def totals(answer: Document) -> tuple[str, str | None]:
    return answer["total"]["low"], answer["total"]["high"]


def lines_by_resource(answer: Document) -> dict[str, JsonObject]:
    return {line["what"]: line for line in answer["lines"]}


def valid(answer: Document) -> Document:
    errors = sorted(error.message for error in COST_VALIDATOR.iter_errors(answer))
    assert errors == []
    return answer


def finding(code: str, resource: str, text: str) -> JsonObject:
    return {"code": code, "resource": resource, "text": text}


def test_allocated_cpu_and_memory() -> None:
    # E2B bills the size it has, per second, while running only.
    # 2 vCPU x 600 s = 1200 vcpu-second x 0.000014 = 0.0168
    # 4 GiB x 600 s = 2400 gib-second x 0.0000045 = 0.0108; the 1200 s paused cost nothing
    paused = [interval("running", 600), interval("paused", 1200)]
    answer = valid(cost(usage("e2b", intervals=paused), price("e2b")))
    assert answer["label"] == "calculated"
    assert totals(answer) == ("0.0276", "0.0276")
    assert lines_by_resource(answer)["cpu"]["quantity"] == "1200"
    assert lines_by_resource(answer)["memory"]["quantity"] == "2400"

    # Daytona has separate container and VM prices, so an absent class is unknown.
    daytona = usage("daytona", size_source="provider")
    daytona["size"]["disk_mib"] = 5 * 1024
    answer = valid(cost(daytona, price("daytona")))
    assert answer["label"] == "unknown"
    assert answer["held_back_by"] == [
        finding("unreported_quantity", "class", "The provider did not report the class.")
    ]


def test_active_cpu_requires_provider_usage() -> None:
    for active in (None, fact("unknown", seconds=None), fact("measured", seconds=1800)):
        record = usage("vercel", 3600)
        if active is not None:
            record["active_cpu"] = active
        answer = valid(cost(record, price("vercel")))
        assert (answer["label"], answer["total"], answer["lines"]) == ("unknown", None, [])
    reported = usage("vercel", 3600, active_cpu=fact("provider", seconds=1800))
    assert totals(valid(cost(reported, price("vercel")))) == ("0.1488006", "0.1488006")
    assert per_hour(price("vercel"), {"cpu": 2, "memory_mib": 4096}) == {
        "low": "0.0848",
        "high": "0.3408",
    }


def test_larger_of_request_and_use_without_actual_usage_is_unknown() -> None:
    answer = valid(cost(usage("modal"), price("modal")))
    assert (answer["label"], answer["total"], answer["lines"]) == ("unknown", None, [])
    assert {item["resource"] for item in answer["held_back_by"]} == {"cpu", "memory"}
    assert per_hour(price("modal"), {"cpu": 2, "memory_mib": 4096}) == {
        "low": "0.23796",
        "high": "0.23796",
    }


def test_flat_per_size_machine_rate() -> None:
    # Boat: a 2 vCPU, 4 GiB sandbox matches the published `small` bundle at $0.018 per hour.
    answer = valid(cost(usage("boat", 3600, disk_mib=51 * 1024), price("boat")))
    assert lines_by_resource(answer)["machine"] == {
        "what": "machine",
        "quantity": "1",
        "unit": "machine-hour",
        "rate": "0.018",
        "amount": "0.018",
        "quantity_source": "recorded",
    }
    assert totals(answer) == ("0.018", "0.018")
    assert per_hour(price("boat"), {"cpu": 2, "memory_mib": 4096}) == {
        "low": "0.018",
        "high": "0.018",
    }
    assert per_hour(price("boat"), {"cpu": 16, "memory_mib": 32768}) == {
        "low": "0.2",
        "high": "0.2",
    }

    # a size that matches no published bundle has no machine price
    answer = valid(
        cost(usage("boat", 3600, cpu=1, memory_mib=2048, disk_mib=51 * 1024), price("boat"))
    )
    assert answer["label"] == "unknown"
    assert answer["held_back_by"] == [
        finding(
            "no_rate", "machine", "The price version has no machine size matching this sandbox."
        )
    ]
    assert per_hour(price("boat"), {"cpu": 1, "memory_mib": 2048}) is None


def test_unknown_active_time_cannot_produce_a_sandbox_cost() -> None:
    answer = valid(cost(usage("blaxel", size_source="provider"), price("blaxel")))
    assert (answer["label"], answer["total"], answer["lines"]) == ("unknown", None, [])
    assert answer["held_back_by"][0]["resource"] == "memory"


def test_snapshot_storage_requires_known_size_and_uses_the_version_month_length() -> None:
    version = version_with(
        rates={"snapshot_storage": {"usd": "0.08", "per": "gb-month"}},
        meter={"snapshot_storage": {"billed_states": ["stopped"]}},
    )
    version["provider"], version["month_hours"] = "vercel", "730"
    record = usage("vercel", intervals=[interval("stopped", 3600)])
    record["snapshot_storage"] = fact("provider", gb=1)
    answer = valid(cost(record, version))
    storage = lines_by_resource(answer)["snapshot_storage"]
    assert answer["label"] == "calculated"
    assert storage["quantity"].startswith("0.001369863013698630136986301369863")
    assert storage["amount"].startswith("0.000109589041095890410958904109589")
    record["snapshot_storage"] = fact("unknown", gb=None, max_gb=1)
    assert cost(record, version)["total"] is None


def test_modal_h100_gpu_rate_is_available_for_hourly_quotes() -> None:
    version = price_file("modal", "2026-10-20-061900Z")
    assert per_hour(version, {"gpu": 1, "gpu_model": "nvidia:h100"}) == {
        "low": "3.9492",
        "high": "3.9492",
    }
    sandbox = usage("modal", 3600)
    sandbox["size"].update(gpu=1, gpu_model="nvidia:h100")
    assert cost(sandbox, version)["total"] is None


def test_blaxel_hourly_memory_rounds_up_to_the_next_meter_tier() -> None:
    version = price_file("blaxel", "2026-10-20-061947Z")
    assert per_hour(version, {"memory_mib": 3000}) == {"low": "0", "high": "0.1656"}
    assert per_hour(version, {"memory_mib": 32769}) is None
    assert cost(usage("blaxel", 3600, memory_mib=3000), version)["total"] is None
    oversized = cost(usage("blaxel", memory_mib=32769), version)
    assert (
        finding("no_rate", "memory", "The price version has no memory tier for 32769 MiB.")
        in oversized["held_back_by"]
    )


def test_gpu_rate_for_an_unpriced_model_is_unknown() -> None:
    sandbox = usage("modal", 3600, size_source="provider")
    sandbox["size"].update(gpu=1, gpu_model="nvidia:unknown")
    answer = valid(cost(sandbox, price_file("modal", "2026-10-20-061900Z")))
    assert answer["label"] == "unknown"
    assert answer["total"] is None
    assert (
        finding("no_rate", "gpu", "The price version has no GPU rate for nvidia:unknown.")
        in answer["held_back_by"]
    )


def test_disk_while_stopped() -> None:
    # Daytona bills disk in every state, and CPU and memory only while running.
    # 10 GiB x (1800 running + 1800 paused + 3600 stopped = 7200 s) = 20 gib-hour x 0.000108
    # = 0.00216; CPU 1 vcpu-hour x 0.0504 and memory 2 gib-hour x 0.0162 cover the 1800 s run
    states = [
        interval("running", 1800),
        interval("paused", 1800),
        interval("stopped", 3600),
    ]
    sandbox = usage("daytona", size_source="provider", intervals=states)
    sandbox["size"]["disk_mib"] = 10 * 1024
    answer = valid(cost(sandbox, price("daytona")))
    assert answer["label"] == "unknown"
    assert answer["held_back_by"] == [
        finding("unreported_quantity", "class", "The provider did not report the class.")
    ]


def test_per_creation_fee() -> None:
    # Vercel: 3 creations = 0.000003 million x 0.60 = 0.0000018 (CPU 0 seconds, memory 0)
    sandbox = usage("vercel", 0, active_cpu=fact("provider", seconds=0), creations=fact(count=3))
    answer = valid(cost(sandbox, price("vercel")))
    assert lines_by_resource(answer)["creation"] == {
        "what": "creation",
        "quantity": "0.000003",
        "unit": "million-creations",
        "rate": "0.6",
        "amount": "0.0000018",
        "quantity_source": "recorded",
    }
    assert totals(answer) == ("0.0000018", "0.0000018")

    # a fee per creation: 5 creations x 0.0001 = 0.0005 on top of 60 s x 1 vCPU x 0.001 = 0.06
    fee = version_with(
        rates={
            "cpu": {"usd": "0.001", "per": "vcpu-second"},
            "creation": {"usd": "0.0001", "per": "creation"},
        },
        meter={"cpu": {"basis": "allocated", "billed_states": ["running"]}},
    )
    answer = valid(cost(usage("e2b", 60, cpu=1, creations=fact(count=5)), fee))
    assert totals(answer) == ("0.0605", "0.0605")

    # a creation count nobody knows is not a free creation
    answer = valid(cost(usage("e2b", 60, creations=fact("unknown", count=None)), fee))
    assert answer["label"] == "unknown"
    assert answer["total"] is None


def test_minimum_increment() -> None:
    # Each period is charged for at least `minimum_seconds`, then rounded up to a multiple of
    # `increment_seconds`; periods are not merged. With 30 and 60, 10 s bills 60 and 70 s bills
    # 120, so 180 s: 1 vCPU x 180 = 180 vcpu-second x 0.001 = 0.18 and 1 GiB x 180 = 180
    # gib-second x 0.0001 = 0.018
    rounded = version_with(
        rates={
            "cpu": {"usd": "0.001", "per": "vcpu-second"},
            "memory": {"usd": "0.0001", "per": "gib-second"},
        },
        meter={
            "cpu": {
                "basis": "allocated",
                "billed_states": ["running"],
                "minimum_seconds": 30,
                "increment_seconds": 60,
            },
            "memory": {
                "basis": "allocated",
                "billed_states": ["running"],
                "minimum_seconds": 30,
                "increment_seconds": 60,
            },
        },
    )
    periods = [interval("running", 10), interval("running", 70)]
    answer = valid(cost(usage("e2b", cpu=1, memory_mib=1024, intervals=periods), rounded))
    assert totals(answer) == ("0.198", "0.198")
    assert lines_by_resource(answer)["cpu"]["quantity"] == "180"

    # a period of no time is not a period: it is not rounded up to anything
    nothing = [interval("running", 0)]
    answer = cost(usage("e2b", cpu=1, memory_mib=1024, intervals=nothing), rounded)
    assert totals(answer) == ("0", "0")

    # Vercel's real rule, memory in whole minutes: 10 s bills 60 s, so 3 GB x 60 s = 0.05
    # gb-hour x 0.0212 = 0.00106 (CPU 0 seconds)
    vercel = usage(
        "vercel",
        10,
        memory_mib=3 * 1024,
        active_cpu=fact("provider", seconds=0),
        creations=fact(count=0),
    )
    answer = valid(cost(vercel, price("vercel")))
    assert lines_by_resource(answer)["memory"]["quantity"] == "0.05"
    assert totals(answer) == ("0.00106", "0.00106")

    # a time only known as a range is rounded at both ends: 50 s bills 60 and 70 s bills 120, so
    # 0.06 + 0.006 = 0.066 to 0.12 + 0.012 = 0.132, estimated; 61 to 119 s bills 120 s either way
    bounded = [interval("running", {"low": 50, "high": 70})]
    answer = cost(usage("e2b", cpu=1, memory_mib=1024, intervals=bounded), rounded)
    assert answer["label"] == "unknown"
    assert answer["total"] is None
    assert (
        answer["held_back_by"][0]["text"]
        == "The provider did not report the exact time in running."
    )
    tight = [interval("running", {"low": 61, "high": 119})]
    answer = cost(usage("e2b", cpu=1, memory_mib=1024, intervals=tight), rounded)
    assert answer["total"] is None


@pytest.mark.parametrize("source", ["calculated", "unknown"])
def test_unsourced_size_is_unknown(source: str) -> None:
    answer = valid(cost(usage("e2b", size_source=source), price("e2b")))
    assert (answer["label"], answer["total"], answer["lines"]) == ("unknown", None, [])
    assert all(
        item["text"] == "The provider did not report the sandbox's size."
        for item in answer["held_back_by"]
    )


@pytest.mark.parametrize("source", ["recorded", "measured", "calculated", "unknown"])
def test_non_provider_time_is_unknown(source: str) -> None:
    record = usage("e2b", intervals=[interval("running", 60, source)])
    record["intervals"][0]["how"] = "the reason is retained on the fact"
    answer = valid(cost(record, price("e2b")))
    assert (answer["label"], answer["total"]) == ("unknown", None)
    assert answer["held_back_by"] == [
        finding("unreported_quantity", "time", "The provider did not report the billed time.")
    ]


def test_missing_price_is_unknown() -> None:
    # No price version in effect: unknown, never zero, and it names no version.
    answer = valid(cost(usage("e2b"), None))
    assert answer["label"] == "unknown"
    assert answer["total"] is None
    assert answer["lines"] == []
    assert answer["price_version"] is None
    assert answer["held_back_by"] == [
        finding("no_rate", "usage", "No price version is in effect for e2b.")
    ]

    # without the provider's times there is no start to pick a version by: say what is missing
    waiting = usage("e2b", intervals=[interval("running", None, "unknown")])
    waiting["started"] = {"at": None, "source": "unknown", "observed_at": "2026-10-24T05:00:00Z"}
    answer = valid(cost(waiting, None))
    assert answer["held_back_by"] == [
        finding("unreported_quantity", "time", "The provider did not report the billed time.")
    ]

    # a price version for another provider is no price for this one
    answer = valid(cost(usage("e2b"), price("daytona")))
    assert answer["total"] is None
    assert answer["held_back_by"] == [
        finding(
            "no_rate", "usage", "The price version is for daytona, but this sandbox ran on e2b."
        )
    ]

    # a class the price version does not have
    named = usage("modal", class_fact=fact(name="windows"))
    answer = valid(cost(named, price("modal")))
    assert answer["total"] is None
    assert answer["held_back_by"] == [
        finding("no_rate", "class", "No class of the price version covers the class windows.")
    ]

    # a resource with a rate and no meter rule cannot be priced
    unmetered = version_with(rates={"cpu": {"usd": "0.001", "per": "vcpu-second"}}, meter={})
    answer = valid(cost(usage("e2b"), unmetered))
    assert answer["total"] is None
    assert answer["held_back_by"] == [
        finding(
            "no_rate",
            "cpu",
            "The price version has a cpu rate but no rule for how it is metered.",
        )
    ]

    # a version whose only rate is for something the sandbox did not use prices nothing
    egress_only = version_with(rates={"egress": {"usd": "0.15", "per": "gb"}}, meter={})
    answer = valid(cost(usage("e2b"), egress_only))
    assert answer["total"] is None
    assert answer["held_back_by"] == [
        finding("no_rate", "usage", "The price version has no rate for anything this sandbox used.")
    ]


@pytest.mark.parametrize(
    "broken",
    [
        {"size": fact("unknown")},
        {"size": fact(cpu=2)},
        {"size": fact(memory_mib=4096)},
        {"intervals": [interval("running", None, "unknown")]},
        {"intervals": [interval("running", {"low": 9, "high": 3})]},
        {"intervals": []},
    ],
    ids=["size-unknown", "no-memory", "no-cpu", "time-unknown", "bad-range", "no-intervals"],
)
def test_missing_input_is_unknown_not_zero(broken: JsonObject) -> None:
    answer = valid(cost(usage("e2b") | broken, price("e2b")))
    assert answer["label"] == "unknown"
    assert answer["total"] is None
    assert answer["lines"] == []
    assert answer["held_back_by"]
    assert answer["price_version"] == "e2b@2026-10-20-061802Z"


def test_never_reported() -> None:
    # `reported` is a consumer's to set when a provider's own figure replaces the calculation. No
    # price version, source or odd input makes the calculator say it, whatever the record claims.
    versions = sorted(PACKAGES.glob("*/prices/*.yaml"))
    assert sorted({path.parts[-3] for path in versions}) == priced_provider_ids()
    labels = set()
    for path, source in itertools.product(versions, SOURCES):
        version = yaml.safe_load(path.read_text())
        sandbox = usage(
            version["provider"],
            size_source=source,
            intervals=[interval("running", 90, source), interval("stopped", 30, source)],
            creations=fact(source, count=1),
            active_cpu=fact(source, seconds=None if source == "unknown" else 10),
            egress=fact(source, bytes=None if source == "unknown" else 1000),
            label="reported",
            provider_cost={"total": "1.00", "source": "provider"},
        )
        answer = valid(cost(sandbox, version))
        assert "reported_figure" not in answer
        labels.add(answer["label"])
    assert labels == {"calculated", "unknown"}


def test_e2b_demo() -> None:
    # The E2B demo sandbox: 2 vCPU and 1 GiB for 1,800 s.
    # 2 vCPU x 1800 s = 3600 vcpu-second x 0.000014 = 0.0504
    # 1 GiB x 1800 s = 1800 gib-second x 0.0000045 = 0.0081; total 0.0585
    demo, version, expected = example("usage"), example("price-version"), example("cost")
    answer = valid(cost(demo, version))
    assert answer["label"] == "calculated"
    assert totals(answer) == ("0.0585", "0.0585")
    assert answer["lines"] == expected["lines"]
    assert answer["price_version"] == expected["price_version"] == "e2b@2026-10-20-061802Z"
    assert answer["held_back_by"] == []
    # the cost is as of the latest moment a fact was observed, unless the caller says when
    assert answer["as_of"] == "2026-10-20T19:09:03Z"
    assert cost(demo, version, as_of=expected["as_of"])["as_of"] == expected["as_of"]
    # the version's own exclusions come back, with the one every list price has
    assert answer["exclusions"] == [*version["exclusions"], "Credits and discounts"]

    # the same sandbox with a size of unknown source has no number
    guessed = copy.deepcopy(demo)
    guessed["size"]["source"] = "unknown"
    answer = valid(cost(guessed, version))
    assert answer["label"] == "unknown"
    assert answer["total"] is None


def test_matches_independent_per_hour() -> None:
    # Per-hour figures are independently recalculated from current versions and their unit rates.
    # figures are rounded to six decimals, so ours are too; Vercel's low is memory only,
    # Blaxel's is standby (nothing).
    fixture = json.loads((ROOT / "tests" / "fixtures" / "benchmark_per_hour.json").read_text())

    def six(text: str) -> Decimal:
        return Decimal(text).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)

    checked = 0
    for provider, entry in fixture["providers"].items():
        version = price(provider, "2026-10-20-061802Z")
        for label, expected in entry["sizes"].items():
            cpu, memory_gib = (int(part) for part in label.split("x"))
            size = {"cpu": cpu, "memory_mib": memory_gib * 1024}
            answer = per_hour(version, size, region=entry.get("region"))
            if expected["availability"] == "not_offered":
                continue  # he could not price it; the rates alone would
            assert answer is not None, (provider, label)
            low = expected.get("low_usd", expected["total_usd"])
            assert (six(answer["low"]), six(answer["high"])) == (
                six(low),
                six(expected["total_usd"]),
            ), (provider, label)
            if "before_region_total_usd" in expected:
                unpinned = per_hour(version, size)
                assert unpinned is not None
                assert six(unpinned["high"]) == six(expected["before_region_total_usd"])
            checked += 1
    assert checked == 25


def test_region_multiplier_applies_to_hourly_quotes() -> None:
    size = {"cpu": 2, "memory_mib": 4096}
    assert per_hour(price("modal"), size, region="us") == {"low": "0.273654", "high": "0.273654"}
    assert per_hour(price("modal"), size, region="eu") == {"low": "0.23796", "high": "0.23796"}
    assert cost(usage("modal", region=fact("unknown", name=None)), price("modal"))["total"] is None


def test_modal_disk_does_not_create_a_sandbox_total() -> None:
    sandbox = usage("modal")
    sandbox["size"]["disk_mib"] = 100 * 1024
    assert cost(sandbox, price("modal"))["total"] is None


def test_modal_sandbox_disk_does_not_raise_hourly_memory_quote() -> None:
    size = {"cpu": 2, "memory_mib": 4096, "disk_mib": 512 * 1024}
    assert per_hour(price_file("modal", "2026-10-20-061900Z"), size) == {
        "low": "0.23796",
        "high": "0.23796",
    }


def test_class_selects_the_rate_set() -> None:
    # A named class selects its rate set; an absent class can use the only class, but not
    # choose among several classes.
    cheap = {"cpu": {"usd": "0.001", "per": "vcpu-second"}}
    meter = {"cpu": {"basis": "allocated", "billed_states": ["running"]}}
    version = version_with(rates=cheap, meter=meter)
    version["classes"].append(
        {"name": "vm", "rates": {"cpu": {"usd": "0.003", "per": "vcpu-second"}}, "meter": meter}
    )
    # 2 vCPU x 10 s = 20 vcpu-second: x 0.001 = 0.02, x 0.003 = 0.06
    absent = valid(cost(usage("e2b", 10), version))
    assert absent["label"] == "unknown"
    assert absent["total"] is None
    assert absent["held_back_by"] == [
        finding("unreported_quantity", "class", "The provider did not report the class.")
    ]
    named = usage("e2b", 10, class_fact=fact(name="vm"))
    assert totals(cost(named, version)) == ("0.06", "0.06")
    guessed = usage("e2b", 10, class_fact=fact("unknown", name=None))
    answer = valid(cost(guessed, version))
    assert answer["label"] == "unknown"
    assert answer["total"] is None
    assert answer["held_back_by"] == [
        finding(
            "unreported_quantity",
            "class",
            "The provider did not report the class.",
        )
    ]

    single_class = version_with(rates=cheap, meter=meter)
    assert totals(cost(usage("e2b", 10), single_class)) == ("0.02", "0.02")


def test_modal_absent_class_is_unknown_and_explicit_vm_uses_vm_rate() -> None:
    version = price("modal")
    default = next(item for item in version["classes"] if item.get("default"))
    default["rates"]["cpu"]["usd"] = "0.001"
    vm = copy.deepcopy(default)
    vm.update(name="vm", default=False, covers=["vm"])
    vm["rates"]["cpu"].update(usd="0.003", per="vcpu-second")
    vm["rates"].pop("memory", None)
    vm["rates"].pop("egress", None)
    vm["rates"].pop("gpu", None)
    vm["meter"] = {"cpu": {"basis": "allocated", "billed_states": ["running"]}}
    default["covers"] = ["default"]
    version["classes"].append(vm)

    absent = valid(cost(usage("modal", 10), version))
    assert absent["label"] == "unknown"
    assert absent["total"] is None
    assert absent["held_back_by"] == [
        finding("unreported_quantity", "class", "The provider did not report the class.")
    ]
    named_vm = usage("modal", 10, size_source="provider", class_fact=fact(name="vm"))
    named_vm["active_cpu"] = fact("provider", seconds=10)
    assert totals(cost(named_vm, version)) == ("0.03", "0.03")


def test_a_price_class_prices_the_spec_classes_it_covers() -> None:
    meter = {"cpu": {"basis": "allocated", "billed_states": ["running"]}}
    version = version_with(
        rates={"cpu": {"usd": "0.001", "per": "vcpu-second"}}, meter=meter, covers=["default", "vm"]
    )
    version["classes"].append(
        {
            "name": "windows",
            "rates": {"cpu": {"usd": "0.003", "per": "vcpu-second"}},
            "meter": meter,
        }
    )
    for spec_class, total in (("default", "0.02"), ("vm", "0.02"), ("windows", "0.06")):
        named = usage("e2b", 10, class_fact=fact(name=spec_class))
        assert totals(cost(named, version)) == (total, total)
    # a class nothing covers is unknown, never the default's price
    other = usage("e2b", 10, class_fact=fact(name="container"))
    answer = valid(cost(other, version))
    assert answer["total"] is None
    assert answer["held_back_by"] == [
        finding("no_rate", "class", "No class of the price version covers the class container.")
    ]
    assert per_hour(version, {"cpu": 2}, class_name="vm") == per_hour(version, {"cpu": 2})
    assert per_hour(version, {"cpu": 2}, class_name="container") is None


def test_shipped_vm_and_container_classes_share_the_one_rate_set() -> None:
    for provider, spec_classes in (("modal", ("default", "vm")), ("daytona", ("container", "vm"))):
        covering = [
            price_class
            for price_class in price(provider)["classes"]
            if set(spec_classes) <= set(price_class.get("covers", []))
        ]
        assert len(covering) == 1, provider
        assert covering[0].get("default") is True, provider


def test_free_quantity_and_egress() -> None:
    # A free allowance comes off the size: 10 GiB with 5 free = 5 GiB x 3600 s = 5 gib-hour x 0.1
    # = 0.5. Egress counts only where the record carries it: 2,000,000,000 bytes = 2 gb x 0.15
    # = 0.3; missing egress bytes leave the cost unknown.
    version = version_with(
        rates={
            "disk": {"usd": "0.1", "per": "gib-hour"},
            "egress": {"usd": "0.15", "per": "gb"},
        },
        meter={"disk": {"basis": "allocated", "billed_states": ["running"], "free_quantity": "5"}},
    )
    sandbox = usage("e2b", 3600)
    sandbox["size"]["disk_mib"] = 10 * 1024
    assert totals(cost(sandbox, version)) == ("0.5", "0.5")
    sandbox["egress"] = fact(bytes=2_000_000_000)
    answer = valid(cost(sandbox, version))
    assert totals(answer) == ("0.8", "0.8")
    assert lines_by_resource(answer)["egress"]["quantity"] == "2"
    sandbox["egress"] = fact("unknown", bytes=None)
    answer = valid(cost(sandbox, version))
    assert answer["label"] == "unknown"
    assert answer["total"] is None
    assert answer["held_back_by"] == [
        finding(
            "unreported_quantity",
            "egress",
            "The provider did not report the network egress.",
        )
    ]


def test_monthly_rates_are_730_hour_months() -> None:
    # A month rate is the price of 730 hours: 2 vCPU x $0.80 + 4 GB x $0.70 + 4 GB disk x $0.09
    # is $4.76 for 730 hours running, and a month stopped bills the disk alone, $0.36.
    month = version_with(
        rates={
            "cpu": {"usd": "0.80", "per": "vcpu-month"},
            "memory": {"usd": "0.70", "per": "gb-month", "size_per_unit": "1"},
            "disk": {"usd": "0.09", "per": "gb-month", "size_per_unit": "1"},
        },
        meter={
            "cpu": {"basis": "allocated", "billed_states": ["running"]},
            "memory": {"basis": "allocated", "billed_states": ["running"]},
            "disk": {"basis": "allocated", "billed_states": ["running", "stopped"]},
        },
    )
    month["provider"] = "agent37"
    hours = 730 * 3600
    running = usage("agent37", disk_mib=4096, intervals=[interval("running", hours)])
    assert totals(valid(cost(running, month))) == ("4.76", "4.76")
    stopped = usage("agent37", disk_mib=4096, intervals=[interval("stopped", hours)])
    assert totals(valid(cost(stopped, month))) == ("0.36", "0.36")
    hourly = per_hour(month, {"cpu": 2, "memory_mib": 4096, "disk_mib": 4096})
    assert hourly is not None and Decimal(hourly["low"]) * 730 == pytest.approx(Decimal("4.76"))


def test_per_hour_prices_only_what_the_size_lists() -> None:
    # Daytona's disk is a separate rate: a size with no disk is priced without it (1 vcpu-hour
    # x 0.0504 + 2 gib-hour x 0.0162 = 0.0828), and with one adds it (3 GiB x 0.000108)
    daytona = price("daytona")
    assert per_hour(daytona, {"cpu": 1, "memory_mib": 2048}) == {"low": "0.0828", "high": "0.0828"}
    sized = per_hour(daytona, {"cpu": 1, "memory_mib": 2048, "disk_mib": 3072})
    assert sized == {"low": "0.083124", "high": "0.083124"}
    # a size that names nothing the version prices, and a class it lacks, have no price
    assert per_hour(daytona, {}) is None
    assert per_hour(daytona, {"cpu": 1}, class_name="windows") is None
    # a resource billed only while stopped is not part of the price of a sandbox that runs
    stopped = version_with(
        rates={"disk": {"usd": "0.1", "per": "gib-hour"}},
        meter={"disk": {"basis": "allocated", "billed_states": ["stopped"]}},
    )
    assert per_hour(stopped, {"disk_mib": 1024}) is None
