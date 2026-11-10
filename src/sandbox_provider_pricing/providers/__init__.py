# SPDX-FileCopyrightText: BoxRouter, Inc.
# SPDX-License-Identifier: Apache-2.0
"""The single provider-specific seam: each provider's billing document, rules and prices."""

import json
import re
from functools import cache
from importlib import import_module, resources
from pathlib import Path
from types import ModuleType

import yaml  # type: ignore[import-untyped]
from jsonschema import Draft202012Validator

from sandbox_provider_pricing._util import providers_root
from sandbox_provider_pricing.billing_text import fill_rules
from sandbox_provider_pricing.rules import default
from sandbox_provider_pricing.types import Document, JsonObject, bundled_copy
from sandbox_provider_pricing.versions import latest_version


def provider_ids() -> list[str]:
    """Every bundled provider in name order: each providers-root folder with a `billing.yaml`."""
    return sorted(
        folder.name
        for folder in providers_root().iterdir()
        if folder.joinpath("billing.yaml").is_file()
    )


def billing(provider: str) -> JsonObject:
    """Load one provider's billing rules and rule version (read once per process, copied)."""
    return bundled_copy(bundled_billing(provider))


@cache
def bundled_billing(provider: str) -> JsonObject:
    """The process's one copy of a provider's billing document; callers must not change it."""
    path = providers_root() / provider / "billing.yaml"
    if not path.is_file():
        raise ValueError(f"no billing document for provider {provider!r}")
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise ValueError(f"{provider}/billing.yaml is not a billing document")
    try:
        fill_rules(document, lambda: latest_version(provider))
        validate_billing(document)
    except ValueError as error:
        raise ValueError(f"{provider}/billing.yaml: {error}") from error
    return document


#: The oldest `rules_version` whose document is kept; earlier ones used another format.
FIRST_KEPT_RULES_VERSION = 2


def billing_history(provider: str) -> dict[int, JsonObject]:
    """Each superseded `rules_version`'s billing document, exactly as it was when it priced results.

    When a provider's `billing.yaml` moves to a new `rules_version`, its old document is copied
    to `billing-history/<old version>.yaml` in the provider's package, so a result that recorded the
    old version can still be explained with the rules and formula that priced it.
    """
    folder = providers_root() / provider / "billing-history"
    if not folder.is_dir():
        return {}
    history: dict[int, JsonObject] = {}
    for path in sorted(folder.iterdir(), key=lambda item: item.name):
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        try:
            fill_rules(document, lambda: latest_version(provider))
            validate_billing(document)
        except ValueError as error:
            raise ValueError(f"{provider}/billing-history/{path.name}: {error}") from error
        history[int(document["rules_version"])] = document
    return history


@cache
def _billing_validator() -> Draft202012Validator:
    bundled = resources.files("sandbox_provider_pricing").joinpath("schemas", "billing.schema.json")
    if bundled.is_file():
        schema = json.loads(bundled.read_text(encoding="utf-8"))
    else:
        source = Path(__file__).resolve().parents[3] / "schemas" / "billing.schema.json"
        schema = json.loads(source.read_text(encoding="utf-8"))
    return Draft202012Validator(schema)


def validate_billing(document: Document) -> None:
    """Validate provider billing data against its bundled JSON Schema."""
    error = next(_billing_validator().iter_errors(document), None)
    if error is not None:
        path = "/".join(map(str, error.absolute_path)) or "<root>"
        raise ValueError(f"{path}: {error.message}")


@cache
def rules(provider: str) -> ModuleType:
    """The provider's `rules` module, or the shared defaults when its folder has none."""
    if re.fullmatch(r"[a-z][a-z0-9-]*", provider) is None:
        raise ValueError(f"invalid provider slug {provider!r}")
    folder = providers_root() / provider
    if not folder.joinpath("billing.yaml").is_file():
        raise ValueError(f"no billing document for provider {provider!r}")
    if not folder.joinpath("rules.py").is_file():
        return default
    return import_module(f"{__name__}.{provider}.rules")
