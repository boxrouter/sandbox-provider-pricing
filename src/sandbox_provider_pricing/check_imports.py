# SPDX-FileCopyrightText: BoxRouter, Inc.
# SPDX-License-Identifier: Apache-2.0
"""Find the names a consumer takes from the package that its public API does not promise."""

from __future__ import annotations

import ast
from collections.abc import Iterator
from importlib import import_module
from pathlib import Path
from typing import NamedTuple

import sandbox_provider_pricing

PACKAGE = "sandbox_provider_pricing"
#: Submodules with a public surface of their own: a name in the module's `__all__` is public.
PUBLIC_MODULES = ("conformance", "testing", "watch")
_SKIPPED = frozenset({".git", ".venv", "node_modules", "__pycache__", ".mypy_cache"})


class PrivateImport(NamedTuple):
    """One use of a name outside `__all__`: where, and the dotted name used."""

    path: Path
    line: int
    name: str

    def __str__(self) -> str:
        return f"{self.path}:{self.line}: {self.name}"


def private_imports(root: Path) -> list[PrivateImport]:
    """Every use of a `sandbox_provider_pricing` name outside `__all__` in `root`'s Python files.

    Imports of a submodule or of a name `__all__` lacks count, and so does reaching one through
    the package (`pricing.versions` after `import sandbox_provider_pricing as pricing`). The
    package's own modules, in any folder named `sandbox_provider_pricing`, are not checked.
    """
    found: list[PrivateImport] = []
    for path in _python_files(root):
        if PACKAGE not in path.parts[:-1]:  # the package's own modules import each other
            found.extend(_in_file(path))
    return found


def _python_files(root: Path) -> Iterator[Path]:
    if root.is_file():
        yield root
        return
    for path in sorted(root.rglob("*.py")):
        if not _SKIPPED.intersection(path.relative_to(root).parts):
            yield path


def _in_file(path: Path) -> Iterator[PrivateImport]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    aliases = {PACKAGE}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == PACKAGE:
                    aliases.add(alias.asname or PACKAGE)
                elif alias.name.startswith(f"{PACKAGE}."):
                    yield PrivateImport(path, node.lineno, alias.name)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            yield from _from_import(path, node)
    public = frozenset(sandbox_provider_pricing.__all__)
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id in aliases
            and node.attr not in public
        ):
            yield PrivateImport(path, node.lineno, f"{PACKAGE}.{node.attr}")


def _from_import(path: Path, node: ast.ImportFrom) -> Iterator[PrivateImport]:
    public = frozenset(sandbox_provider_pricing.__all__)
    for alias in node.names:
        if node.module == PACKAGE and alias.name not in public:
            yield PrivateImport(path, node.lineno, f"{PACKAGE}.{alias.name}")
        elif node.module and node.module.startswith(f"{PACKAGE}."):
            if alias.name not in _module_names(node.module):
                yield PrivateImport(path, node.lineno, f"{node.module}.{alias.name}")


def _module_names(module: str) -> frozenset[str]:
    """The public names of a public submodule: its `__all__`; none for any other module."""
    name = module.removeprefix(f"{PACKAGE}.")
    if name not in PUBLIC_MODULES:
        return frozenset()
    return frozenset(import_module(module).__all__)
