# SPDX-FileCopyrightText: BoxRouter, Inc.
# SPDX-License-Identifier: Apache-2.0
"""Build the canonical JSON price sheet used by BoxRouter price displays."""

from __future__ import annotations

import argparse
import json
import re
from collections.abc import Sequence
from decimal import Decimal, localcontext
from importlib import resources
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from sandbox_provider_pricing._util import decimal_text, package_version, write_json
from sandbox_provider_pricing.billing_text import unit_name
from sandbox_provider_pricing.calculator import CONTEXT, SECONDS_PER_HOUR, Span, per_hour
from sandbox_provider_pricing.calculator.documents import covered_classes
from sandbox_provider_pricing.calculator.quantities import in_rate_unit
from sandbox_provider_pricing.cost_method import RULES
from sandbox_provider_pricing.price import _basis_text
from sandbox_provider_pricing.providers import billing as provider_billing
from sandbox_provider_pricing.versions import (
    latest_version,
    priced_provider_ids,
    seed_versions,
)

SCHEMA_ID = "urn:boxrouter:sandbox-provider-pricing:price-sheet"
SCHEMA_VERSION = "2.4.0"


def _text_schema() -> dict[str, Any]:
    bundled = resources.files("sandbox_provider_pricing").joinpath(
        "schemas/price-sheet.schema.json"
    )
    path = (
        bundled
        if bundled.is_file()
        else Path(__file__).resolve().parents[2] / "schemas/price-sheet.schema.json"
    )
    schema: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return schema


def _page_text(schema: dict[str, Any]) -> dict[str, Any]:
    source = schema["x-text"]
    criteria = schema["x-content-criteria"]
    parameters = {
        "param:pricing.hourly.seconds_per_hour": str(SECONDS_PER_HOUR),
        "param:pricing.excludes": ", ".join(schema["properties"]["excludes"]["items"]["enum"]),
    }

    def expand(value: Any, bindings: dict[str, Any]) -> Any:
        if isinstance(value, str):
            if value.startswith("@"):
                return expand(source["shared"][value[1:]], bindings)
            return re.sub(
                r"\{([^{}]+)\}",
                lambda match: str(bindings.get(match[1], match[0])),
                value,
            )
        if isinstance(value, list):
            return [expand(item, bindings) for item in value]
        if isinstance(value, dict):
            return {key: expand(item, bindings) for key, item in value.items()}
        return value

    panels = expand(source["panels"], parameters)
    for panel in panels.values():
        metric = panel["metric"]
        direction = criteria["directions"][metric["direction"]]
        period = "" if metric["per"] in metric["unit"] else f" per {metric['per']}"
        measure = f"{metric['quantity']}{period} ({metric['unit']})"
        axis_unit = metric["unit"]
        if period:
            axis_unit = expand(
                source["shared"]["axis-rate-unit"],
                {
                    "metric:unit": metric["unit"],
                    "metric:per": source["shared"]["axis-periods"].get(
                        metric["per"], metric["per"]
                    ),
                },
            )
        axis_measure = expand(
            source["shared"]["axis-measure"],
            {"metric:quantity": metric["quantity"], "metric:unit": axis_unit},
        )
        panel["axis_measure"] = axis_measure[0].upper() + axis_measure[1:]
        panel["caption"] = expand(
            source["shared"]["chart-caption"],
            {
                **parameters,
                "metric:label": measure,
                "state": panel.pop("caption_state", ""),
                "direction": direction,
            },
        )
    return {"pages": source["pages"], "panels": panels, "content_criteria": criteria}


def validate_price_text(sheet: dict[str, Any]) -> None:
    """Fail source builds on missing, fragment, duplicate or unbound price text."""
    schema = _text_schema()
    error = next(Draft202012Validator(schema).iter_errors(sheet), None)
    if error is not None:
        raise ValueError(f"{list(error.absolute_path)}: {error.message}")
    for panel_id, panel in sheet["panels"].items():
        if any(panel["metric"][key] not in panel["caption"] for key in ("quantity", "per", "unit")):
            raise ValueError(f"{panel_id}.caption: missing metric quantity, period or unit")
        seen: dict[str, str] = {}
        for slot in schema["x-content-criteria"]["unique_slots"]:
            key = schema["x-content-criteria"]["slots"][slot]["source"]
            normalized = " ".join(panel[key].casefold().split())
            if normalized in seen:
                raise ValueError(f"{panel_id}.{key}: duplicates {seen[normalized]}")
            seen[normalized] = key

    def literals(value: Any) -> None:
        if isinstance(value, str):
            plain = re.sub(r"\{[^{}]+\}", "", value)
            if re.search(r"\d", plain):
                raise ValueError("numeric price text requires a parameter placeholder")
        elif isinstance(value, list):
            for item in value:
                literals(item)
        elif isinstance(value, dict):
            for item in value.values():
                literals(item)

    for provider in sheet["providers"]:
        reasons = [
            config[key]
            for config in provider["configs"]
            for key in ("reason", "idle_note", "paused_note")
            if config.get(key)
        ] + [storage["status_text"]["hover"] for storage in provider["storage"]]
        for reason in reasons:
            if not re.fullmatch(r"[A-Z].*[.!?]", reason):
                raise ValueError(
                    f"{provider['id']}: reader reason must be a complete sentence: {reason}"
                )

    literals(schema["x-text"])


# Published default coverage is the Cartesian product of these resource steps.
# Callers with a specific comparison set can pass their own pairs to the builder.
PUBLISHED_PRICE_CONFIGS = tuple(
    (vcpu, memory_gib) for vcpu in (1, 2, 4, 8) for memory_gib in (2, 4, 8, 16)
)
_UNKNOWN_STATES = {
    "idle": {
        "rule": "unknown",
        "note": "No idle billing fact is recorded for the provider.",
    },
    "paused": {
        "rule": "unknown",
        "note": "No paused billing fact is recorded for the provider.",
    },
}
# Storage prices are published per GiB-month (2^30 bytes); a source quoted per GB-month (10^9 bytes)
# is converted here and its own price and unit stay beside it.
GIB_PER_GB_MONTH = Decimal(2**30) / Decimal(10**9)
STORAGE_ORDER = {"image": 0, "disk": 1, "snapshot": 2, "volume": 3}


def build_price_sheet(
    price_configs: Sequence[tuple[int, int]] = PUBLISHED_PRICE_CONFIGS,
) -> dict[str, Any]:
    """Return a deterministic sheet for the requested (vCPU, GiB) sizes."""
    normalized_configs = _validate_price_configs(price_configs)
    versions = seed_versions()
    providers: list[dict[str, Any]] = []
    release_version = package_version()
    schema = _text_schema()
    for provider in priced_provider_ids(versions):
        current = latest_version(provider, versions)
        billing = provider_billing(provider)
        default = next(
            (item for item in current["classes"] if item.get("default")), current["classes"][0]
        )
        providers.extend(
            _provider_sheet(
                provider,
                spec_class,
                current,
                billing,
                release_version,
                normalized_configs,
                storage_statuses=schema["x-text"]["storage_statuses"],
            )
            for spec_class in covered_classes(default)
        )
    sheet = {
        "$schema": SCHEMA_ID,
        "schema_version": SCHEMA_VERSION,
        "pricing_release_version": release_version,
        **_page_text(schema),
        "hourly": {"seconds_per_hour": int(SECONDS_PER_HOUR)},
        "excludes": list(schema["properties"]["excludes"]["items"]["enum"]),
        "default_size": _size_label(2, 4),
        "sizes": [_size_label(vcpu, memory_gib) for vcpu, memory_gib in PUBLISHED_PRICE_CONFIGS],
        "billing_rule_titles": [{"key": key, "title": title} for key, title in RULES],
        "unit_names": {
            per: unit_name(per)
            for per in sorted(
                {
                    unit
                    for provider in providers
                    for storage in provider["storage"]
                    for unit in (storage["per"], storage["source_per"])
                    if unit is not None
                }
            )
        },
        "providers": providers,
    }
    validate_price_text(sheet)
    return sheet


def _provider_sheet(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    provider: str,
    spec_class: str,
    price_version: dict[str, Any],
    billing: dict[str, Any],
    release_version: str,
    price_configs: Sequence[tuple[int, int]] = PUBLISHED_PRICE_CONFIGS,
    *,
    storage_statuses: dict[str, Any],
) -> dict[str, Any]:
    # This assembly collects the independent benchmark display fields in one provider record.
    # pylint: disable=too-many-locals
    default = next(
        (item for item in price_version["classes"] if item.get("default")),
        price_version["classes"][0],
    )
    display_facts = billing.get("price_sheet") or {}
    class_facts = (display_facts.get("class_overrides") or {}).get(spec_class, {})
    states = {
        **_UNKNOWN_STATES,
        **(display_facts.get("states") or {}),
        **(class_facts.get("states") or {}),
    }
    notes = {f"{state}_note": states[state]["note"] for state in ("idle", "paused")}
    region_fact = display_facts.get("benchmark_region") or {}
    region = region_fact.get("value")
    multiplier = None if region is None else (default.get("region_multipliers") or {}).get(region)
    applied_region = region if multiplier is not None else None
    checked_at = str(price_version["retrieved_at"])[:10]
    source_url = price_version["sources"][0]["url"]
    configs = []
    for vcpu, memory_gib in price_configs:
        size = {"cpu": vcpu, "memory_mib": memory_gib * 1024}
        raw = per_hour(price_version, size, region=applied_region)
        if raw is None:
            configs.append(
                {
                    "size": {"vcpu": vcpu, "memory_gib": memory_gib},
                    "status": "in_development",
                    "reason": "No hourly list price is published for this configuration.",
                    **notes,
                    "running_per_hour_usd": None,
                    "cpu_per_hour_usd": None,
                    "memory_per_hour_usd": None,
                    "idle_per_hour_usd": None,
                    "paused_per_hour_usd": None,
                }
            )
            continue
        cpu = per_hour(price_version, {"cpu": vcpu}, region=applied_region)
        memory = per_hour(price_version, {"memory_mib": memory_gib * 1024}, region=applied_region)
        flat = isinstance((default.get("rates") or {}).get("machine"), dict)
        if memory is None and not flat:
            raise ValueError(f"{provider}: no memory component at {vcpu}x{memory_gib}")
        running = _range(raw)
        cpu_part = None if cpu is None else _range(cpu)
        memory_part = None if memory is None else _range(memory)
        if (
            cpu_part is not None
            and memory_part is not None
            and any(
                Decimal(str(cpu_part[end])) + Decimal(str(memory_part[end]))
                != Decimal(str(running[end]))
                for end in ("low", "high")
            )
        ):
            raise ValueError(f"{provider}: CPU and memory do not add up at {vcpu}x{memory_gib}")
        if (display_facts.get("active_time_priced") or {}).get("value", False):
            running = _upper(running)
            cpu_part = None if cpu_part is None else _upper(cpu_part)
            memory_part = None if memory_part is None else _upper(memory_part)
        idle, paused, idle_cpu, idle_memory = _idle_paused(
            states, memory_gib, running, (cpu_part, memory_part), price_version
        )
        configs.append(
            {
                "size": {"vcpu": vcpu, "memory_gib": memory_gib},
                "status": "priced",
                "reason": None,
                **notes,
                "running_per_hour_usd": _figure(running, source_url, checked_at),
                "cpu_per_hour_usd": _figure(cpu_part, source_url, checked_at),
                "memory_per_hour_usd": _figure(memory_part, source_url, checked_at),
                "idle_per_hour_usd": _figure(idle, source_url, checked_at),
                "paused_per_hour_usd": _figure(paused, source_url, checked_at),
                "idle_cpu_per_hour_usd": _figure(idle_cpu, source_url, checked_at),
                "idle_memory_per_hour_usd": _figure(idle_memory, source_url, checked_at),
            }
        )
    billing_mode = _billing_mode(default, display_facts)
    region_note = (
        None
        if multiplier is None or region is None
        else f"list rate × {multiplier} for a {region.upper()} region pin"
    )
    return {
        "id": provider,
        "class": spec_class,
        "name": billing["name"],
        "display_name": billing["name"],
        "label": class_facts.get("label") or spec_class,
        "price_version": price_version["version"],
        "region": region,
        "region_multiplier": None if multiplier is None else float(multiplier),
        "region_note": region_note,
        "region_source_url": region_fact.get("source_url"),
        "region_checked_at": checked_at if region_fact else None,
        "basis": (
            "active time"
            if (display_facts.get("active_time_priced") or {}).get("value", False)
            else _basis_text(price_version)
        ),
        **billing_mode,
        "unit_rates": _unit_rates(default, billing_mode["compute_rates"], applied_region),
        "configs": configs,
        "storage": _storage(display_facts.get("storage", []), price_version, storage_statuses),
        "source_url": source_url,
        "checked_at": checked_at,
        "billing_rules": _billing_rules(billing),
        "class_rules": {
            key: fact["text"] for key, fact in (class_facts.get("rules") or {}).items()
        },
        "billing_rules_source": f"src/sandbox_provider_pricing/providers/{provider}/billing.yaml",
        "pricing_release_version": release_version,
    }


COMPUTE_RESOURCES = ("cpu", "memory", "machine")


def _billing_mode(default: dict[str, Any], display_facts: dict[str, Any]) -> dict[str, Any]:
    """Project the typed meter, rate and active-time facts into the sheet.

    `billing_mode` is the one meter basis every running-billed compute resource shares, or `mixed`
    when they differ. `compute_rates` lists those resources with the meter's basis and billed
    states and the rate's own unit; a flat per-size machine rate has no single price, so its
    `usd` is null and the sized figures carry the amounts.
    """
    rates = default.get("rates") or {}
    meters: list[dict[str, Any]] = []
    for resource in COMPUTE_RESOURCES:
        meter = (default.get("meter") or {}).get(resource)
        if meter is None or "running" not in meter["billed_states"] or resource not in rates:
            continue
        rate = rates[resource]
        if resource == "machine":
            units = {entry["per"] for entry in rate.values()}
            if len(units) != 1:
                raise ValueError(f"machine rates mix units {sorted(units)}")
            per, usd, size_per_unit = units.pop(), None, None
        else:
            per = rate["per"]
            usd = float(rate["usd"])
            size_per_unit = float(rate["size_per_unit"]) if "size_per_unit" in rate else None
        meters.append(
            {
                "resource": resource,
                "basis": meter["basis"],
                "billed_states": list(meter["billed_states"]),
                "per": per,
                "usd": usd,
                "size_per_unit": size_per_unit,
            }
        )
    bases = {meter["basis"] for meter in meters}
    return {
        "billing_mode": next(iter(bases)) if len(bases) == 1 else "mixed",
        "active_time_priced": bool((display_facts.get("active_time_priced") or {}).get("value")),
        "compute_rates": meters,
    }


def _unit_rates(
    default: dict[str, Any], compute_rates: list[dict[str, Any]], region: str | None
) -> dict[str, float | None] | None:
    """The hourly price of one vCPU and of one GiB of memory while the sandbox runs.

    Each is the rate in its own unit converted to an hour of one vCPU or one GiB, times the
    benchmark region's multiplier: the rate a fully used resource pays, before memory steps and
    free allowances, which the sized figures apply. The CPU rate is null where memory is the only
    compute meter (its CPU is billed with the memory); the whole is null for a flat per-size
    machine rate, which has no per-resource price.
    """
    priced = {rate["resource"] for rate in compute_rates}
    if "memory" not in priced:
        return None
    multiplier = Decimal(
        (default.get("region_multipliers") or {}).get(region, "1") if region else "1"
    )

    def hourly(resource: str) -> float | None:
        if resource not in priced:
            return None
        rate = default["rates"][resource]
        with localcontext(CONTEXT):
            hours = in_rate_unit(rate, Span.exact(SECONDS_PER_HOUR))
            return float(decimal_text(hours.high * Decimal(rate["usd"]) * multiplier))

    return {"cpu_per_vcpu_hour": hourly("cpu"), "memory_per_gib_hour": hourly("memory")}


def _validate_price_configs(
    price_configs: Sequence[tuple[int, int]],
) -> tuple[tuple[int, int], ...]:
    """Validate and freeze caller-supplied positive integer resource pairs."""
    raw_configs = tuple(price_configs)
    if not raw_configs:
        raise ValueError("price_configs must contain at least one (vCPU, memory GiB) pair")
    configs = []
    for config in raw_configs:
        if (
            not isinstance(config, (tuple, list))
            or len(config) != 2
            or any(
                not isinstance(value, int) or isinstance(value, bool) or value <= 0
                for value in config
            )
        ):
            raise ValueError(
                "each price_configs entry must contain positive integer (vCPU, memory GiB)"
            )
        configs.append((config[0], config[1]))
    if len(set(configs)) != len(configs):
        raise ValueError("price_configs entries must be unique")
    return tuple(configs)


def _size_label(vcpu: int, memory_gib: int) -> dict[str, Any]:
    return {
        "vcpu": vcpu,
        "memory_gib": memory_gib,
        "label": f"{vcpu} vCPU, {memory_gib} GiB",
    }


def _idle_paused(
    states: dict[str, dict[str, str]],
    memory_gib: int,
    running: dict[str, float],
    parts: tuple[dict[str, float] | None, dict[str, float] | None],
    version_doc: dict[str, Any],
) -> tuple[
    dict[str, float] | None,
    dict[str, float] | None,
    dict[str, float] | None,
    dict[str, float] | None,
]:
    # Keep all five billing-state rules visible beside the values they produce.
    # pylint: disable=too-many-locals
    results: dict[str, dict[str, float] | None] = {}
    cpu, memory = parts
    idle_cpu: dict[str, float] | None = cpu
    idle_memory: dict[str, float] | None = memory
    for state, fact in states.items():
        rule = fact["rule"]
        result: dict[str, float] | None
        if rule == "running":
            result = running
        elif rule == "active":
            result = _upper(running)
            idle_cpu = None if cpu is None else _upper(cpu)
            idle_memory = None if memory is None else _upper(memory)
        elif rule == "memory":
            amount = per_hour(version_doc, {"memory_mib": memory_gib * 1024})
            result = None if amount is None else _range(amount)
            idle_cpu = {"low": 0.0, "high": 0.0}
            idle_memory = result
        elif rule == "none":
            result = {"low": 0.0, "high": 0.0}
        elif rule == "disk":
            full = per_hour(version_doc, {"disk_mib": 10 * 1024})
            free = per_hour(version_doc, {"disk_mib": 5 * 1024})
            result = (
                None
                if full is None or free is None
                else {"low": _range(free)["low"], "high": _range(full)["high"]}
            )
        else:
            result = None
        results[state] = result
    return results["idle"], results["paused"], idle_cpu, idle_memory


def _storage_entry(
    kind: str, status: str, source_url: str | None, checked_at: str
) -> dict[str, Any]:
    """A storage entry with no rate yet: a priced row's rate fields are filled after."""
    return {
        "kind": kind,
        "status": status,
        "usd": None,
        "per": None,
        "source_usd": None,
        "source_per": None,
        "included_gb": None,
        "included_unit": None,
        "source_url": source_url,
        "checked_at": checked_at,
    }


def _storage(
    storage_facts: list[dict[str, Any]],
    version_doc: dict[str, Any],
    storage_statuses: dict[str, Any],
) -> list[dict[str, Any]]:
    checked_at = str(version_doc["retrieved_at"])[:10]
    entries: list[dict[str, Any]] = [
        _storage_entry(fact["kind"], fact["status"], fact["source_url"], checked_at)
        for fact in storage_facts
        if "price_version_rate" not in fact
    ]
    for key, kind, per in (
        ("image_storage", "image", "gb-month"),
        ("snapshot_storage", "snapshot", "gb-month"),
        ("volume_storage", "volume", "gb-month"),
    ):
        rate = version_doc.get(key)
        if not isinstance(rate, dict) or rate.get("rate_source") == "published_disk_rate_proxy":
            continue
        entry = next((item for item in entries if item["kind"] == kind), None)
        if entry is None:
            entry = _storage_entry(kind, "priced", None, checked_at)
            entries.append(entry)
        source_per = rate.get("per", per)
        entry.update(
            {
                "status": "priced",
                "usd": _gib_month(rate["usd"], source_per),
                "per": "gib-month",
                "source_usd": float(rate["usd"]),
                "source_per": source_per,
                "source_url": rate["source_url"],
                "checked_at": str(rate["checked_at"])[:10],
                **(
                    {
                        "included_gb": float(rate["included_gb"]),
                        "included_unit": rate["included_unit"],
                    }
                    if "included_gb" in rate
                    else {}
                ),
            }
        )
    for fact in storage_facts:
        calculation = fact.get("price_version_rate")
        if calculation is None:
            continue
        default: dict[str, Any] = next((c for c in version_doc["classes"] if c.get("default")), {})
        rate = (default.get("rates") or {}).get(calculation["resource"])
        if rate is None:
            continue
        hours = (
            float(version_doc.get("month_hours", 730))
            if calculation.get("multiply_by_month_hours", False)
            else 1.0
        )
        entries.append(
            {
                "kind": fact["kind"],
                "status": fact["status"],
                "usd": round(float(rate["usd"]) * hours, 6),
                "per": "gib-month",
                "source_usd": float(rate["usd"]),
                "source_per": rate["per"],
                "included_gb": (
                    None
                    if calculation.get("included_gb") is None
                    else float(calculation["included_gb"])
                ),
                "included_unit": calculation.get("included_unit"),
                "source_url": fact["source_url"],
                "checked_at": checked_at,
            }
        )
    for entry in entries:
        entry["status_text"] = _storage_status_text(
            entry["status"], entry["kind"], storage_statuses
        )
    return sorted(entries, key=lambda entry: STORAGE_ORDER[entry["kind"]])


def _storage_status_text(
    status: str, kind: str, storage_statuses: dict[str, Any]
) -> dict[str, str]:
    source = storage_statuses[status]
    return {
        "word": source["word"],
        "hover": source["hover_template"].format(kind=kind),
    }


def _gib_month(usd: Any, per: str) -> float:
    """Return a storage rate per GiB-month from a rate quoted per GB-month or GiB-month."""
    if per == "gib-month":
        return float(usd)
    if per == "gb-month":
        return float(Decimal(str(usd)) * GIB_PER_GB_MONTH)
    raise ValueError(f"storage rate unit {per!r} is not gb-month or gib-month")


def _billing_rules(billing: dict[str, Any]) -> dict[str, Any]:
    rules = billing["rules"]
    return {
        "best_cost_label": billing["status"]["best_label"],
        **{key: rules[key] for key, _ in RULES},
        "sources": {key: rules[key].get("sources", []) for key, _ in RULES},
    }


def _range(value: dict[str, str]) -> dict[str, float]:
    return {"low": float(value["low"]), "high": float(value["high"])}


def _upper(value: dict[str, float]) -> dict[str, float]:
    return {"low": value["high"], "high": value["high"]}


def _figure(
    value: dict[str, float] | None, source_url: str | None, checked_at: str
) -> dict[str, Any] | None:
    if value is None:
        return None
    return {**value, "source_url": source_url, "checked_at": checked_at}


def main() -> int:
    """Write the canonical sheet as JSON to a file or stdout."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, help="write JSON to this file; default is stdout")
    arguments = parser.parse_args()
    write_json(build_price_sheet(), arguments.out, sort_keys=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
