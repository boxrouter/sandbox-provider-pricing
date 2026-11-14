# SPDX-FileCopyrightText: BoxRouter, Inc.
# SPDX-License-Identifier: Apache-2.0
"""Released golden cases for evidence costs and published display prices."""

from __future__ import annotations

import argparse
import json
from collections.abc import Callable, Iterable
from importlib import import_module, resources
from importlib.resources.abc import Traversable
from pathlib import Path
from typing import Any, cast

from sandbox_provider_pricing._util import providers_root
from sandbox_provider_pricing.price import price
from sandbox_provider_pricing.price_sheet import build_price_sheet
from sandbox_provider_pricing.types import Document, JsonObject

__all__ = ["cost_answer", "evidence_for", "load_cases", "run_cases", "sheet_answer"]


def load_cases() -> list[JsonObject]:
    """Read the data shipped with this exact package release."""
    data = resources.files("sandbox_provider_pricing").joinpath("conformance.json").read_text()
    return cast(list[JsonObject], json.loads(data)["cases"])


def _fixture(relative: str) -> Traversable:
    """A fixture file: in the wheel it sits in the providers folder; in a checkout, beside it."""
    shipped = providers_root().joinpath(*relative.split("/"))
    if shipped.is_file():
        return shipped
    return Path(__file__).resolve().parents[2] / "providers" / relative


def evidence_for(case: Document) -> JsonObject:
    """Resolve a case's bundled fixture and JSON-path substitutions."""
    path = _fixture(case["input"]["fixture"])
    evidence: JsonObject = json.loads(path.read_text())
    for pointer, value in case["input"].get("set", {}).items():
        target: Any = evidence
        parts = pointer.split("/")
        for part in parts[:-1]:
            target = target[int(part)] if isinstance(target, list) else target[part]
        if isinstance(target, list):
            target[int(parts[-1])] = value
        else:
            target[parts[-1]] = value
    return evidence


def cost_answer(result: Document) -> JsonObject:
    """Keep exact decimal amounts and the certainty label, excluding release metadata."""
    return {key: result[key] for key in ("label", "total")}


def sheet_answer(case: Document, sheet: Document) -> JsonObject:
    """Select a public price without inventing zero for an unpublished amount."""
    request = case["input"]
    provider = next(
        row
        for row in sheet["providers"]
        if (row["id"], row["class"]) == (request["provider"], request["class"])
    )
    if case["kind"] == "storage":
        row = next(row for row in provider["storage"] if row["kind"] == request["storage"])
        return {"status": row["status"], "label": row["status_text"]["word"], "usd": row["usd"]}
    config = next(row for row in provider["configs"] if row["size"] == request["size"])
    return {"status": config["status"], "amount": config[request["field"]]}


def run_cases(
    evaluate: Callable[[Document], Document],
    *,
    kinds: Iterable[str],
) -> int:
    """Assert every selected golden answer against a consumer's real callable."""
    selected = set(kinds)
    cases = [case for case in load_cases() if case["kind"] in selected]
    missing = selected - {case["kind"] for case in cases}
    if missing or not cases:
        raise ValueError(f"no conformance cases for {sorted(missing or selected)}")
    differences = []
    for case in cases:
        actual = evaluate(case)
        if actual != case["expected"]:
            differences.append(f"{case['id']}: expected {case['expected']!r}, got {actual!r}")
    if differences:
        raise AssertionError("\n".join(differences))
    return len(cases)


def _sheet_cases(sheet: Document) -> list[JsonObject]:
    cases: list[JsonObject] = []
    for provider in sheet["providers"]:
        identity = {key: provider[key] for key in ("class",)} | {"provider": provider["id"]}
        prefix = f"{provider['id']}/{provider['class']}"
        for config in provider["configs"]:
            size = config["size"]
            suffix = f"{size['vcpu']}x{size['memory_gib']}"
            for state in ("running", "idle", "paused"):
                cases.append(
                    {
                        "id": f"{prefix}/{suffix}/{state}",
                        "kind": "hourly",
                        "input": identity | {"size": size, "field": f"{state}_per_hour_usd"},
                    }
                )
            # Every published size is exercised; actual provider allocations in the fixture
            # remain evidence, independently of the requested size.
            changes = {
                "requested/cpu": size["vcpu"],
                "requested/memory_mib": size["memory_gib"] * 1024,
                "requested/class": provider["class"],
            }
            fixture = f"{provider['id']}/fixtures/best/evidence.json"
            for scenario, extra in (
                ("recorded", {}),
                (
                    "missing-records",
                    {"provider_records": [], "provider_times": [], "provider_reports": {}},
                ),
                ("unknown-class", {"requested/class": "unpublished-conformance-class"}),
            ):
                cases.append(
                    {
                        "id": f"{prefix}/{suffix}/{scenario}",
                        "kind": "price",
                        "input": {"fixture": fixture, "set": changes | extra},
                    }
                )
        for storage in provider["storage"]:
            cases.append(
                {
                    "id": f"{prefix}/storage/{storage['kind']}",
                    "kind": "storage",
                    "input": identity | {"storage": storage["kind"]},
                }
            )
    return cases


# The stages in which a provider's own `conformance.py` adds cases, in the order they are listed.
_STAGES = ("boundaries", "allocations", "records")


def _provider_cases(cases: list[JsonObject]) -> None:
    """Add the synthetic cases each provider's folder defines, stage by stage."""
    modules = [
        import_module(f"sandbox_provider_pricing.providers.{folder.name}.conformance")
        for folder in sorted(providers_root().iterdir(), key=lambda item: item.name)
        if folder.is_dir() and (folder / "conformance.py").is_file()
    ]
    for stage in _STAGES:
        for module in modules:
            make = getattr(module, stage, None)
            if make is not None:
                cases.extend(make(cases, evidence_for))


def generate() -> JsonObject:
    """Derive every expected answer from price() or the authoritative sheet builder."""
    sheet = build_price_sheet()
    cases = _sheet_cases(sheet)
    _provider_cases(cases)
    for case in cases:
        case["expected"] = (
            cost_answer(price(evidence_for(case)))
            if case["kind"] == "price"
            else sheet_answer(case, sheet)
        )
    return {"schema_version": 1, "cases": cases}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    args.out.write_text(json.dumps(generate(), indent=2, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
