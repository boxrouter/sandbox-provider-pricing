# SPDX-FileCopyrightText: BoxRouter, Inc.
# SPDX-License-Identifier: Apache-2.0
"""Helpers every module shares: the time parser, decimal text and the package version."""

import json
from datetime import UTC, datetime
from decimal import ROUND_HALF_EVEN, Context, Decimal
from functools import cache
from importlib import resources
from importlib.metadata import PackageNotFoundError, version
from importlib.resources.abc import Traversable
from pathlib import Path
from typing import Any

# Exact for every answer a price list can give; division is the only step that could round.
CONTEXT = Context(prec=60, rounding=ROUND_HALF_EVEN)


def providers_root() -> Traversable:
    """The one folder holding every provider's package (`providers/<id>/`), wheel or checkout."""
    return resources.files("sandbox_provider_pricing") / "providers"


def bundled_schema(name: str) -> dict[str, Any]:
    """`schemas/<name>.schema.json`, from the wheel or the checkout."""
    bundled = resources.files("sandbox_provider_pricing").joinpath(f"schemas/{name}.schema.json")
    path = (
        bundled
        if bundled.is_file()
        else Path(__file__).resolve().parents[2] / "schemas" / f"{name}.schema.json"
    )
    schema: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return schema


def write_json(document: object, out: Path | None, *, sort_keys: bool = False) -> None:
    """Write a document as indented JSON to a file, or to stdout when `out` is None."""
    output = json.dumps(document, indent=2, sort_keys=sort_keys) + "\n"
    if out is None:
        print(output, end="")
    else:
        out.write_text(output, encoding="utf-8")


def parse_time(value: str) -> datetime:
    """An ISO 8601 time, with a trailing `Z` read as UTC; aware input normalizes to UTC.

    A naive input stays naive so callers' timezone checks reject it — localizing it here
    would silently depend on the host clock.
    """
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed.astimezone(UTC) if parsed.tzinfo is not None else parsed


def decimal_text(value: Decimal) -> str:
    """Plain decimal notation with no exponent and no trailing zeros."""
    return format(CONTEXT.normalize(value), "f")


@cache
def package_version() -> str:
    """This package's installed version, read from its metadata once per process."""
    try:
        return version("sandbox-provider-pricing")
    except PackageNotFoundError:
        return "0.0.0+uninstalled"
