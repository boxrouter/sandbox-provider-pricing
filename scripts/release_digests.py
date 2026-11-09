# SPDX-FileCopyrightText: BoxRouter, Inc.
# SPDX-License-Identifier: Apache-2.0
"""Append the digests of price files not yet listed in tests/released-digests.txt.

Run it in the release commit (`make release-digests`). It only appends: a listed line never changes.
"""

import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIGESTS = ROOT / "tests" / "released-digests.txt"


def price_files(root: Path = ROOT) -> list[Path]:
    """Every price file in the checkout, as paths relative to the root, sorted."""
    return sorted(
        path.relative_to(root)
        for path in (root / "src/sandbox_provider_pricing/providers").glob("*/prices/*.yaml")
    )


def digest(path: Path, root: Path = ROOT) -> str:
    """sha256 of the file's bytes."""
    return hashlib.sha256((root / path).read_bytes()).hexdigest()


def listed(digests: Path = DIGESTS) -> dict[str, str]:
    """The released digests by path. Blank lines and `#` comments are skipped."""
    entries: dict[str, str] = {}
    for line in digests.read_text(encoding="utf-8").splitlines():
        if line.strip() and not line.startswith("#"):
            path, sha = line.split()
            entries[path] = sha
    return entries


def main() -> int:
    """Append a line for each price file that has none."""
    known = listed()
    new = [path for path in price_files() if path.as_posix() not in known]
    with DIGESTS.open("a", encoding="utf-8") as file:
        for path in new:
            file.write(f"{path.as_posix()} {digest(path)}\n")
            print(f"listed {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
