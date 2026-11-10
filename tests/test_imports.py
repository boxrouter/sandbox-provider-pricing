# SPDX-FileCopyrightText: BoxRouter, Inc.
# SPDX-License-Identifier: Apache-2.0
"""Keep provider-specific rules behind one seam and usage independent of pricing."""

import ast
import json
from pathlib import Path

import pytest

from sandbox_provider_pricing.providers import provider_ids, rules
from sandbox_provider_pricing.rules import default
from sandbox_provider_pricing.usage import default_billable

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "sandbox_provider_pricing"
PACKAGES = SRC / "providers"
PROVIDERS = set(provider_ids())


def imports(tree: ast.AST) -> set[str]:
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module)
    return found


def import_targets(tree: ast.AST) -> set[str]:
    found = imports(tree)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.level:
            prefix = "." * node.level + (node.module or "")
            found.update(f"{prefix}.{alias.name}" for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is None:
            found.update(alias.name for alias in node.names)
    return found


def test_generic_modules_do_not_name_or_import_providers() -> None:
    for path in SRC.rglob("*.py"):
        relative = path.relative_to(SRC)
        # The aggregate price-sheet builder intentionally joins the provider display rules.
        if relative.name == "price_sheet.py" or relative.parts[0] in {
            "providers",
            "rules",
            "watch",
        }:
            continue
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                assert node.value not in PROVIDERS, f"{path} names provider {node.value!r}"
        for module in imports(tree):
            parts = module.split(".")
            if "sandbox_provider_pricing" in parts and "providers" in parts:
                index = parts.index("providers")
                assert not any(part in PROVIDERS for part in parts[index + 1 :]), (
                    f"{path} imports provider module {module!r}"
                )


def test_tests_read_the_provider_list_instead_of_typing_it() -> None:
    """A typed list of providers goes stale when one is added, so tests read `provider_ids()`.

    The exceptions: a per-provider expectation dict, whose keys the test compares with
    `provider_ids()`, and the providers a test takes out of it (`set(provider_ids()) - {...}`).
    """
    for path in sorted((ROOT / "tests").glob("*.py")):
        tree = ast.parse(path.read_text(), filename=str(path))
        taken_out = {
            id(node.right)
            for node in ast.walk(tree)
            if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Sub)
        }
        for node in ast.walk(tree):
            if isinstance(node, (ast.List, ast.Set, ast.Tuple)) and id(node) not in taken_out:
                named = [
                    item.value
                    for item in node.elts
                    if isinstance(item, ast.Constant) and item.value in PROVIDERS
                ]
                assert len(named) < 2, f"{path.name}:{node.lineno} types providers {named}"


def test_provider_rules_import_only_evidence_and_usage() -> None:
    allowed = {
        "sandbox_provider_pricing.evidence",
        "sandbox_provider_pricing.types",
        "sandbox_provider_pricing.usage",
    }
    for path in sorted(PACKAGES.glob("*/rules.py")):
        tree = ast.parse(path.read_text(), filename=str(path))
        package = {
            name for name in imports(tree) if name.split(".")[0] == "sandbox_provider_pricing"
        }
        assert package <= allowed, f"{path} imports {package - allowed}"


def test_provider_conformance_cases_import_only_types() -> None:
    for path in sorted(PACKAGES.glob("*/conformance.py")):
        tree = ast.parse(path.read_text(), filename=str(path))
        package = {
            name for name in imports(tree) if name.split(".")[0] == "sandbox_provider_pricing"
        }
        assert package <= {"sandbox_provider_pricing.types"}, f"{path} imports {package}"


def test_usage_imports_neither_calculator_nor_price() -> None:
    tree = ast.parse((SRC / "usage.py").read_text())
    assert not any(
        any(part in {"calculator", "price"} for part in target.split("."))
        for target in import_targets(tree)
    )


def test_every_provider_rule_is_loaded_from_its_folder() -> None:
    assert {provider for provider in PROVIDERS if rules(provider) is not default} == {
        path.parent.name for path in PACKAGES.glob("*/rules.py")
    }
    with pytest.raises(ValueError, match="no billing document"):
        rules("not-a-billing-folder")
    with pytest.raises(ValueError, match="invalid provider slug"):
        rules("../e2b")


def test_default_rules_use_lifecycle_times_only() -> None:
    evidence = json.loads((ROOT / "providers/e2b/fixtures/best/evidence.json").read_text())
    as_of = "2026-12-31T00:00:00Z"
    assert default.billable(evidence, {}, as_of=as_of) == default_billable(evidence, as_of=as_of)
