# SPDX-FileCopyrightText: BoxRouter, Inc.
# SPDX-License-Identifier: Apache-2.0
"""The `spp` command."""

import argparse
import json
from collections.abc import Sequence
from decimal import Decimal
from importlib import import_module
from pathlib import Path
from typing import Any, cast

import yaml  # type: ignore[import-untyped]

from sandbox_provider_pricing.scaffold import add, source_pages
from sandbox_provider_pricing.types import JsonObject


def _reconcile_summary(result: Any) -> str:
    meters = cast(list[JsonObject], result["meters"])
    counts = ", ".join(
        f"{item['meter']}{'s' if item['meter'] == 'creation' else ''} "
        f"{item['matched']}/{item['rows']}"
        for item in meters
    )
    return f"rates check: {counts} rows within 1e-11 USD"


def _read_bill_rows(path: Path) -> list[JsonObject]:
    rows: list[JsonObject] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line, parse_float=Decimal)
        except json.JSONDecodeError as error:
            raise ValueError(f"{path}:{number} is not valid JSON") from error
        if not isinstance(row, dict):
            raise ValueError(f"{path}:{number} must be a JSON object")
        rows.append(row)
    if not rows:
        raise ValueError(f"{path} has no bill rows")
    return rows


def _run_reconcile(module: Any, directory: str) -> JsonObject:
    path = Path(directory)
    if not path.is_dir():
        raise ValueError(f"{path} is not a reconciliation directory")
    if path.parent.name != "reconciliations" or path.parent.parent.name != "evidence":
        raise ValueError(f"{path} must be under a provider's evidence/reconciliations directory")
    provider_dir = path.parents[2]
    versions = import_module("sandbox_provider_pricing.versions").load_price_versions(provider_dir)
    result = cast(
        JsonObject,
        module.reconcile(_read_bill_rows(path / "bill.jsonl"), provider_dir.name, versions),
    )
    (path / "result.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return result


def _add_check_imports(commands: Any) -> None:
    imports_parser = commands.add_parser(
        "check-imports",
        help="List the names a path takes from the package that its public API does not promise.",
        description=(
            "Print one line per use of a sandbox_provider_pricing name that is not in its "
            "__all__, and exit 1 if there is any."
        ),
    )
    imports_parser.add_argument("path", type=Path)


def _check_imports(parser: argparse.ArgumentParser, path: Path) -> int:
    if not path.exists():
        parser.error(f"{path} does not exist")
    found = import_module("sandbox_provider_pricing.check_imports").private_imports(path)
    for item in found:
        print(item)
    return 1 if found else 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="spp", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    scaffold_parser = commands.add_parser(
        "scaffold", help="Generate provider or sourced price records"
    )
    scaffold_parser.add_argument("provider")
    scaffold_parser.add_argument("--root", type=Path, default=Path.cwd())
    scaffold_parser.add_argument("--name")
    scaffold_parser.add_argument("--website")
    scaffold_parser.add_argument("--price", type=Path)
    scaffold_parser.add_argument(
        "--sources", type=Path, help="JSON map of URLs to saved provider pages"
    )
    scaffold_parser.add_argument("--dry-run", action="store_true")
    check_parser = commands.add_parser(
        "check",
        help="Check that every provider page still contains its price version's quotes.",
        description="Print one JSON line per price version file: confirmed, changed or unreadable.",
    )
    check_parser.add_argument("versions", nargs="+", metavar="version-file")
    reconcile_parser = commands.add_parser(
        "reconcile",
        help="Compare a normalized bill with rates effective at each period start.",
    )
    reconcile_parser.add_argument("directory", metavar="reconciliation-directory")
    _add_check_imports(commands)
    draft_parser = commands.add_parser(
        "draft",
        help="Have an agent draft the new price version from a page that changed.",
        description=(
            "Ask Claude for a new version of the price version from the page, check its work "
            "with no AI, and print on the last line `reworded`, `price changed: <changes>` or "
            "`unreadable`. Needs ANTHROPIC_API_KEY."
        ),
    )
    draft_parser.add_argument("--page", required=True, metavar="file", help="the page, as saved")
    draft_parser.add_argument(
        "--url",
        help="the page's address; by default the version's page most of whose quotes it holds",
    )
    draft_parser.add_argument(
        "--out", metavar="file", help="write the verified draft here, as YAML"
    )
    draft_parser.add_argument("version", metavar="current-version-file")
    arguments = parser.parse_args(argv)
    if arguments.command == "scaffold":
        try:
            written = add(
                arguments.root,
                arguments.provider,
                name=arguments.name,
                website=arguments.website,
                price=yaml.safe_load(arguments.price.read_text()) if arguments.price else None,
                pages=source_pages(arguments.sources),
                dry_run=arguments.dry_run,
            )
        except (ValueError, OSError) as error:
            parser.error(str(error))
        print(json.dumps({"writes": written, "dry_run": arguments.dry_run}))
        return 0
    if arguments.command == "check-imports":
        return _check_imports(parser, arguments.path)
    if arguments.command == "draft":
        agent = import_module("sandbox_provider_pricing.watch.agent")
        draft = import_module("sandbox_provider_pricing.watch.draft")

        return cast(
            int,
            draft.run(
                arguments.version,
                arguments.page,
                agent.ask_claude,
                url=arguments.url,
                out=arguments.out,
            ),
        )
    if arguments.command == "check":
        check = import_module("sandbox_provider_pricing.watch.check")

        return cast(int, check.run(arguments.versions))
    reconcile = import_module("sandbox_provider_pricing.reconcile")
    print(_reconcile_summary(_run_reconcile(reconcile, arguments.directory)))
    return 0
