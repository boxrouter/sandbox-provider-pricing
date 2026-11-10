# SPDX-FileCopyrightText: BoxRouter, Inc.
# SPDX-License-Identifier: Apache-2.0
"""Generate native records; unknown billing facts and absent rates stay unknown."""

import json
import re
from pathlib import Path
from typing import Any, cast

import yaml  # type: ignore[import-untyped]

from sandbox_provider_pricing.providers import _billing_validator, validate_billing
from sandbox_provider_pricing.types import JsonObject
from sandbox_provider_pricing.watch.check import PageText, page_text
from sandbox_provider_pricing.watch.verify import verify

#: Where a provider's shipped files live, relative to the repository root.
PACKAGES = Path("src/sandbox_provider_pricing/providers")
# Built from parts so that REUSE does not read these lines as this file's own license information.
_SPDX = "SPDX"
_HEADER = f"# {_SPDX}-FileCopyrightText: BoxRouter, Inc.\n# {_SPDX}-License-Identifier: Apache-2.0"


def billing_record(name: str, website: str) -> JsonObject:
    """Use the owning schema's rule inventory, without guessing an answer or schedule."""
    rules = cast(dict[str, Any], _billing_validator().schema)["properties"]["rules"]["required"]
    document: JsonObject = {
        "name": name,
        "website": website,
        "rules_version": 1,
        "status": {
            "best_label": "unknown",
            "why_not_higher": "Provider billing evidence has not been verified.",
            "would_raise": "Verify provider records against the published list rates.",
        },
        "revisit": None,
        "reported_at_list_price": {
            "value": None,
            "unknown_how": "Compare a provider-reported sandbox charge with its list rates.",
        },
        "reported_under_account_rate": {
            "value": None,
            "unknown_how": (
                "Compare a reported sandbox charge on a discounted account with list rates."
            ),
        },
        "summary": "Billing rules have not been verified. Unknown facts remain unpriced.",
        "formula": "Unknown until the provider's meters and billing boundaries are verified.",
        "rules": {
            rule: {
                "answer": "Unknown; not yet verified.",
                "unknown_how": "Read the provider's billing documentation and verify its records.",
            }
            for rule in rules
        },
        "checks": [],
        "open_questions": [],
    }
    validate_billing(document)
    return document


def _price_text(provider: str, price: JsonObject, pages: dict[str, Path] | None) -> tuple[str, str]:
    """The watcher owns both price structure and evidence checks."""
    if failures := verify(price, PageText(visible=""), ""):
        raise ValueError("; ".join(failures))
    if price.get("provider") != provider:
        raise ValueError("price provider does not match the requested provider")
    pages = {} if pages is None else pages
    failures = []
    for source in price.get("sources", []):
        url = source["url"]
        if url not in pages:
            raise ValueError(f"saved provider source required: {url}")
        failures.extend(verify(price, page_text(pages[url].read_text()), url))
    if not price.get("sources"):
        failures.append("provider source quotes are required")
    if failures:
        raise ValueError("; ".join(sorted(set(failures))))
    # The version schema owns this identifier, including same-day correction suffixes.
    version = str(price["version"])
    filename = version.removeprefix(provider + "@")
    return filename + ".yaml", (
        "# yaml-language-server: $schema=../../../../../schemas/price-version.schema.json\n"
        + yaml.safe_dump(price, sort_keys=False)
    )


def add(  # pylint: disable=too-many-arguments
    root: Path,
    provider: str,
    *,
    name: str | None = None,
    website: str | None = None,
    price: JsonObject | None = None,
    pages: dict[str, Path] | None = None,
    dry_run: bool = False,
) -> list[str]:
    """Add a provider or price version using the explicit CLI authoring inputs."""
    if not re.fullmatch(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*", provider):
        raise ValueError("provider must be a lowercase registry id")
    folder = root / PACKAGES / provider
    pending: dict[Path, str] = {}
    billing = folder / "billing.yaml"
    if not billing.exists():
        if not name or not website:
            raise ValueError("a new provider requires --name and --website")
        record = billing_record(name, website)
        pending[folder / "__init__.py"] = (
            f"{_HEADER}\n"
            f'"""{name}: billing rules, price versions and rules for reading its records."""\n'
        )
        pending[billing] = (
            "# yaml-language-server: $schema=../../../../schemas/billing.schema.json\n"
            + yaml.safe_dump(record, sort_keys=False)
        )
    if price is not None:
        filename, text = _price_text(provider, price, pages)
        path = folder / "prices" / filename
        if path.exists():
            raise ValueError(f"price version already exists: {price['version']}")
        pending[path] = text
    elif billing.exists():
        raise ValueError("provider already exists; supply a new sourced --price version")
    if not dry_run:
        for path, text in pending.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("x") as stream:
                stream.write(text)
    return [str(path.relative_to(root)) for path in pending]


def source_pages(path: Path | None) -> dict[str, Path]:
    """Resolve a URL-to-saved-page JSON map beside the map, without any network access."""
    if path is None:
        return {}
    document: Any = json.loads(path.read_text())
    if not isinstance(document, dict) or not all(
        isinstance(key, str) and isinstance(value, str) for key, value in document.items()
    ):
        raise ValueError("sources must map provider URLs to saved page filenames")
    return {url: path.parent / filename for url, filename in document.items()}
