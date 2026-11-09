# SPDX-FileCopyrightText: BoxRouter, Inc.
# SPDX-License-Identifier: Apache-2.0
"""Rewrite each providers/*/fixtures/*/result.json from the evidence.json beside it, and
tests/fixtures/price-sheet.json from `build_price_sheet()`."""

import json
import sys
from pathlib import Path
from typing import Any, cast

from sandbox_provider_pricing import build_price_sheet, price
from sandbox_provider_pricing._util import write_json

ROOT = Path(__file__).resolve().parents[1]
PRICE_SHEET = ROOT / "tests" / "fixtures" / "price-sheet.json"
COMMAND = "make update-fixtures"


def fixture_dirs(root: Path = ROOT) -> list[Path]:
    """Every fixture folder, sorted: the ones that hold an evidence.json."""
    return sorted(path.parent for path in (root / "providers").glob("*/fixtures/*/evidence.json"))


def expected_result(folder: Path) -> dict[str, Any]:
    """What `price()` returns for the folder's evidence, as it reads back from JSON."""
    evidence = json.loads((folder / "evidence.json").read_text(encoding="utf-8"))
    return cast(dict[str, Any], json.loads(json.dumps(price(evidence))))


def render(result: dict[str, Any]) -> str:
    """The file text: two-space JSON with a trailing newline."""
    return json.dumps(result, indent=2, ensure_ascii=False) + "\n"


def comparable(result: dict[str, Any]) -> dict[str, Any]:
    """The result without the installed package version, which changes with every release."""
    versions = result.get("versions", {})
    return result | {
        "versions": {key: value for key, value in versions.items() if key != "package"}
    }


def is_current(folder: Path) -> bool:
    """Whether the stored result.json equals a fresh one, ignoring the package version."""
    if not (folder / "result.json").is_file():
        return False
    stored = json.loads((folder / "result.json").read_text(encoding="utf-8"))
    return comparable(stored) == comparable(expected_result(folder))


def write_price_sheet(out: Path) -> None:
    """Write the current price sheet as `spp-price-sheet` does, with the release version blanked
    so that a release alone does not change the file."""
    sheet = build_price_sheet()
    sheet["pricing_release_version"] = ""
    for provider in sheet["providers"]:
        provider["pricing_release_version"] = ""
    write_json(sheet, out, sort_keys=True)


def main() -> int:
    """Rewrite the stale fixture files, leaving current ones as they are."""
    for folder in fixture_dirs():
        if is_current(folder):
            continue
        (folder / "result.json").write_text(render(expected_result(folder)), encoding="utf-8")
        print(f"updated {folder.relative_to(ROOT) / 'result.json'}")
    stored = PRICE_SHEET.read_text(encoding="utf-8")
    write_price_sheet(PRICE_SHEET)
    if PRICE_SHEET.read_text(encoding="utf-8") != stored:
        print(f"updated {PRICE_SHEET.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
