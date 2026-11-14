# SPDX-FileCopyrightText: BoxRouter, Inc.
# SPDX-License-Identifier: Apache-2.0
"""Price version loading, effective-date selection and class lookup."""

from datetime import datetime
from functools import cache
from importlib.resources.abc import Traversable
from pathlib import Path

import yaml  # type: ignore[import-untyped]

from sandbox_provider_pricing._util import parse_time, providers_root
from sandbox_provider_pricing.types import Document, JsonObject, bundled_copy


def seed_versions() -> list[JsonObject]:
    """Every bundled price version, parsed: one document per
    `providers/<provider>/prices/<date>[-<UTC-time>].yaml` in this package.

    Sorted by provider, then version filename, so the order is the same on every machine. Each
    document is a price version as `schemas/price-version.schema.json` describes it, with quoted
    decimals kept as strings. The bundle is read once per process; each call returns a fresh copy.
    """
    return [bundled_copy(version) for version in _bundled_versions()]


def bundled_pool() -> list[JsonObject]:
    """The bundled price versions themselves, shared and uncopied, only to select from.

    Copy any version taken from it before it can reach a caller; `seed_versions` is the public,
    copied form.
    """
    return list(_bundled_versions())


@cache
def _bundled_versions() -> tuple[JsonObject, ...]:
    versions: list[JsonObject] = []
    for provider_dir in sorted(providers_root().iterdir(), key=lambda item: item.name):
        if not provider_dir.is_dir():
            continue
        price_dir = provider_dir / "prices"
        if not price_dir.is_dir():
            continue
        versions.extend(_read_price_versions(price_dir, provider_dir.name))
    return tuple(versions)


def load_price_versions(provider_dir: Path) -> list[JsonObject]:
    """Read all price versions in a provider directory, for reconciliation."""
    price_dir = provider_dir / "prices"
    if not price_dir.is_dir():
        raise ValueError(f"{provider_dir} has no price versions")
    versions = _read_price_versions(price_dir, str(price_dir))
    if not versions:
        raise ValueError(f"{provider_dir} has no price versions")
    return versions


def _read_price_versions(price_dir: Traversable, label: str) -> list[JsonObject]:
    versions = []
    paths = sorted(
        (path for path in price_dir.iterdir() if path.name.endswith(".yaml")),
        key=lambda path: path.name,
    )
    for path in paths:
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(document, dict):
            raise ValueError(f"{label}/{path.name} is not a price version")
        versions.append(document)
    return versions


def priced_provider_ids(versions: list[JsonObject] | None = None) -> list[str]:
    """Every bundled provider with a current price version, in name order.

    A provider folder scaffolded ahead of its first sourced version has none yet and stays
    off the price sheet, the cost method and the generated docs until a version lands.
    """
    pool = _not_superseded(seed_versions() if versions is None else versions)
    return sorted({version["provider"] for version in pool})


def price_version(
    provider: str, started: str | None, versions: list[JsonObject] | None = None
) -> JsonObject | None:
    """The latest non-superseded price effective when the run started."""
    if started is None:
        return None
    at = parse_time(started)
    pool = _not_superseded(seed_versions() if versions is None else versions)
    effective = [
        version
        for version in pool
        if version["provider"] == provider and parse_time(version["effective_from"]) <= at
    ]
    return max(effective, key=_version_order, default=None)


def latest_version(provider: str, versions: list[JsonObject] | None = None) -> JsonObject:
    """The provider's newest bundled price version."""
    pool = _not_superseded(seed_versions() if versions is None else versions)
    matches = [version for version in pool if version["provider"] == provider]
    if not matches:
        raise ValueError(f"no price versions for provider {provider!r}")
    return max(matches, key=_version_order)


def _not_superseded(pool: list[JsonObject]) -> list[JsonObject]:
    superseded = {item for version in pool for item in version.get("supersedes", [])}
    return [version for version in pool if version["version"] not in superseded]


def _version_order(version: JsonObject) -> tuple[datetime, datetime]:
    return parse_time(version["effective_from"]), parse_time(version["retrieved_at"])


def covered_classes(price_class: Document) -> list[str]:
    """The spec classes a price class prices: its `covers`, or its own name when it has none."""
    covers = price_class.get("covers")
    return list(covers) if covers else [str(price_class.get("name"))]


def find_class(version: Document, name: str | None) -> Document | None:
    """The price class covering `name`, or the default class when `name` is None."""
    classes: list[Document] = version.get("classes", [])
    for price_class in classes:
        if name is None and price_class.get("default") is True:
            return price_class
        if name is not None and name in covered_classes(price_class):
            return price_class
    return None
