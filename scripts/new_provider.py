# SPDX-FileCopyrightText: BoxRouter, Inc.
# SPDX-License-Identifier: Apache-2.0
"""Scaffold a provider: the package skeleton, a first unknown fixture and a TODO list.

Everything the provider owns is emitted here; every other list in the repository is generated
from the provider folders by `make docs`, `make update-fixtures` and `make conformance`. Until
a first sourced price version lands the provider is unpriced and stays off the generated
surfaces.
"""

import argparse
import json
import sys
from pathlib import Path

from sandbox_provider_pricing.scaffold import add

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = Path("src/sandbox_provider_pricing/providers")

#: The provider-owned work the scaffold cannot do: each line names a TODO the onboarder fills.
TODO = """\
# {name} onboarding

Emitted by `make new-provider`; delete entries as they land, then this file.

- [ ] First sourced price version: research the provider's pages, write the version YAML and
      its saved pages, then `spp scaffold {provider} --price sourced-price.yaml --sources
      saved-pages.json`. The provider joins the price sheet, cost method and generated docs
      only once a version is in effect.
- [ ] `billing.yaml`: replace the unknown answers with sourced ones; set a `revisit` policy
      once the record read window is verified.
- [ ] `rules.py`, only if the provider's records need provider logic; the shared default rules
      read lifecycle times otherwise.
- [ ] `read-time.json`: the reviewed read-time declaration once the rules settle
      (docs/read-time-contract.md).
- [ ] `providers/{provider}/evidence/`: measurements for each `checks` entry (template in
      template/provider/evidence/).
- [ ] `fixtures/best/`: replace the scaffolded evidence with a recorded run; add fixtures as
      the record cases need them, then `make update-fixtures`.
"""

EVIDENCE = {
    "sandbox_id": "scaffolded-example",
    "sandbox_made": {
        "value": True,
        "source": "recorded",
        "how": "the scaffold's synthetic create call returned",
    },
    "requested": {"cpu": 2, "memory_mib": 4096, "region": None, "options": {}},
    "calls": [
        {
            "name": "create",
            "sent_at": {
                "value": "2026-01-01T00:00:00Z",
                "source": "recorded",
                "how": "the scaffold's synthetic create request was sent",
            },
            "returned_at": {
                "value": "2026-01-01T00:00:05Z",
                "source": "recorded",
                "how": "the scaffold's synthetic create request returned",
            },
            "outcome": "returned",
        },
        {
            "name": "destroy",
            "sent_at": {
                "value": "2026-01-01T00:10:00Z",
                "source": "recorded",
                "how": "the scaffold's synthetic destroy request was sent",
            },
            "returned_at": {
                "value": "2026-01-01T00:10:05Z",
                "source": "recorded",
                "how": "the scaffold's synthetic destroy request returned",
            },
            "outcome": "returned",
        },
    ],
    "provider_times": [],
    "last_seen_alive": None,
    "noticed_gone": None,
    "provider_records": [],
    "measured": {},
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("provider", help="the provider's registry id")
    parser.add_argument("--name", help="display name; defaults to the id")
    parser.add_argument(
        "--website",
        help="the provider's home page; a placeholder is emitted without one",
    )
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    provider, name = args.provider, args.name or args.provider
    website = args.website or f"https://{args.provider}.invalid"
    written = add(args.root, provider, name=name, website=website, dry_run=args.dry_run)
    folder = args.root / "providers" / provider
    written += [
        str(path.relative_to(args.root))
        for path in (folder / "fixtures/best/evidence.json", folder / "TODO.md")
    ]
    if not args.dry_run:
        (folder / "fixtures/best").mkdir(parents=True, exist_ok=True)
        (folder / "fixtures/best/evidence.json").write_text(
            json.dumps({"provider": provider, **EVIDENCE}, indent=2) + "\n", encoding="utf-8"
        )
        (folder / "TODO.md").write_text(TODO.format(name=name, provider=provider), encoding="utf-8")
    print(json.dumps({"writes": written, "dry_run": args.dry_run}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
