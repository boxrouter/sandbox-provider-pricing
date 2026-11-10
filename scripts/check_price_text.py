# SPDX-FileCopyrightText: BoxRouter, Inc.
# SPDX-License-Identifier: Apache-2.0
"""Capture authored price-page text for the shared benchmark text verifier."""

from __future__ import annotations

import json
import re
from collections.abc import Iterator, Mapping
from typing import Any

from sandbox_provider_pricing._util import bundled_schema
from sandbox_provider_pricing.price_sheet import _text_schema


def _strings(value: Any, path: str) -> Iterator[tuple[str, str]]:
    if isinstance(value, str):
        # @name is a schema-owned reference; its referenced text is checked at its source.
        if not value.startswith("@"):
            yield path, value
    elif isinstance(value, Mapping):
        for key, child in value.items():
            yield from _strings(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _strings(child, f"{path}[{index}]")


def capture() -> dict[str, list[dict[str, Any]]]:
    """Return authored reader text and hover templates with declared runtime fields."""
    schema = _text_schema()
    declared_runtime = schema["$defs"]["content_criteria"]["const"]["placeholders"]["runtime"]
    storage_statuses = schema["x-text"]["storage_statuses"]
    slots = [
        {"id": path, "template": template, "runtime_fields": declared_runtime}
        for path, template in _strings(
            {key: value for key, value in schema["x-text"].items() if key != "storage_statuses"},
            "x-text",
        )
    ]
    slots.extend(
        {
            "id": f"x-text.storage_statuses.{status}.hover_template",
            "template": entry["hover_template"],
            "runtime_fields": entry["runtime_fields"],
        }
        for status, entry in storage_statuses.items()
    )
    slots.extend(
        {
            "id": f"$defs.content_criteria.const.hover_slots.{code}.template",
            "template": entry["template"],
            "runtime_fields": entry["runtime_fields"],
        }
        for code, entry in schema["$defs"]["content_criteria"]["const"]["hover_slots"].items()
    )
    # The words that explain a cost; their `{name}` placeholders are filled from a result.
    explain = bundled_schema("cost-method")["x-text"]["explain"]
    slots.extend(
        {
            "id": path,
            "template": template,
            "runtime_fields": sorted(set(re.findall(r"\{([a-z_]+)\}", template))),
        }
        for path, template in _strings(explain, "cost-method.x-text.explain")
    )
    return {"authored_slots": slots}


if __name__ == "__main__":
    print(json.dumps(capture(), ensure_ascii=False, sort_keys=True))
