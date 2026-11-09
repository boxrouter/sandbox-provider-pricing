# SPDX-FileCopyrightText: BoxRouter, Inc.
# SPDX-License-Identifier: Apache-2.0
"""Each generated fixture is current: every result.json is what `price()` returns for the
evidence.json beside it, and tests/fixtures/price-sheet.json is what `build_price_sheet()`
returns."""

import difflib
import json
from importlib import util
from pathlib import Path

from sandbox_provider_pricing.providers import provider_ids

_spec = util.spec_from_file_location(
    "update_fixtures", Path(__file__).resolve().parents[1] / "scripts" / "update_fixtures.py"
)
assert _spec is not None and _spec.loader is not None
update_fixtures = util.module_from_spec(_spec)
_spec.loader.exec_module(update_fixtures)


def _stale(path: Path, stored: str, fresh: str, source: str) -> AssertionError:
    diff = "".join(
        difflib.unified_diff(
            stored.splitlines(keepends=True),
            fresh.splitlines(keepends=True),
            f"{path.name} (stored)",
            f"{path.name} (from {source})",
        )
    )
    return AssertionError(
        f"{path.relative_to(update_fixtures.ROOT)} is stale. "
        f"Run `{update_fixtures.COMMAND}` and commit the result.\n{diff}"
    )


def test_new_fixture_without_result_needs_generation(tmp_path: Path) -> None:
    assert update_fixtures.is_current(tmp_path) is False


def test_stored_results_are_current() -> None:
    for folder in update_fixtures.fixture_dirs():
        stored = (folder / "result.json").read_text(encoding="utf-8")
        if update_fixtures.is_current(folder):
            continue
        fresh = update_fixtures.render(update_fixtures.expected_result(folder))
        raise _stale(folder / "result.json", stored, fresh, "evidence.json")


def test_stored_price_sheet_is_current(tmp_path: Path) -> None:
    fresh = tmp_path / "price-sheet.json"
    update_fixtures.write_price_sheet(fresh)
    stored_text = update_fixtures.PRICE_SHEET.read_text(encoding="utf-8")
    fresh_text = fresh.read_text(encoding="utf-8")
    if stored_text != fresh_text:
        raise _stale(update_fixtures.PRICE_SHEET, stored_text, fresh_text, "build_price_sheet()")


def test_every_provider_has_an_unknown_fixture_that_says_why() -> None:
    explained = set()
    for folder in update_fixtures.fixture_dirs():
        result = json.loads((folder / "result.json").read_text(encoding="utf-8"))
        if result["label"] == "unknown" and result["total"] is None and result["held_back_by"]:
            explained.add(folder.parents[1].name)
    assert sorted(explained) == provider_ids()


def test_a_new_package_version_alone_does_not_make_a_result_stale() -> None:
    folder = update_fixtures.fixture_dirs()[0]
    result = update_fixtures.expected_result(folder)
    other = result | {"versions": result["versions"] | {"package": "0.0.0"}}
    assert update_fixtures.comparable(other) == update_fixtures.comparable(result)
    changed = result | {"versions": result["versions"] | {"prices": "other@2000-01-01"}}
    assert update_fixtures.comparable(changed) != update_fixtures.comparable(result)
