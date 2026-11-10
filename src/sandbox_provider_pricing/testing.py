# SPDX-FileCopyrightText: BoxRouter, Inc.
# SPDX-License-Identifier: Apache-2.0
"""For a consumer's tests: read provider folders from somewhere else, and forget what was read.

- `bundled_providers()`: the folder of provider packages this release ships.
- `use_providers(root)`: price from the provider folders under `root` until the block ends, as
  when a new provider is onboarded and not yet released.
- `forget_caches()`: drop what pricing remembers from earlier reads.

Production code does not call these.
"""

from __future__ import annotations

import importlib
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from types import ModuleType

from sandbox_provider_pricing import _util, providers
from sandbox_provider_pricing import evidence as _evidence

__all__ = ["bundled_providers", "forget_caches", "use_providers"]

_PACKAGE = "sandbox_provider_pricing"
_ROOT_NAME = "providers_root"


def bundled_providers() -> Path:
    """The folder holding every bundled provider's package (`<id>/billing.yaml`, `prices/`, …)."""
    return Path(str(_util.providers_root()))


def forget_caches() -> None:
    """Clear every cached read of the provider folders and every proven document."""
    for name, module in list(sys.modules.items()):
        if name == _PACKAGE or name.startswith(f"{_PACKAGE}."):
            for value in vars(module).values():
                clear = getattr(value, "cache_clear", None)
                if callable(clear):
                    clear()
    with _evidence._PROVEN_LOCK:  # pylint: disable=protected-access
        _evidence._PROVEN.clear()  # pylint: disable=protected-access


@contextmanager
def use_providers(root: Path) -> Iterator[Path]:
    """Read provider folders from `root` inside the block, then go back to the bundled ones.

    `root` holds one folder per provider, as `bundled_providers()` does. A provider's `rules.py`
    is imported as a module of `sandbox_provider_pricing.providers`, and a provider that is not
    bundled is imported from `root`.
    """
    patched: list[tuple[ModuleType, object]] = []
    for name, module in list(sys.modules.items()):
        if (name == _PACKAGE or name.startswith(f"{_PACKAGE}.")) and hasattr(module, _ROOT_NAME):
            patched.append((module, getattr(module, _ROOT_NAME)))
            setattr(module, _ROOT_NAME, lambda: root)
    providers.__path__.append(str(root))  # a provider's `rules.py` imports from its folder
    importlib.invalidate_caches()
    forget_caches()
    try:
        yield root
    finally:
        providers.__path__.remove(str(root))
        for module, original in patched:
            setattr(module, _ROOT_NAME, original)
        forget_caches()
        for name in [n for n in sys.modules if n.startswith(f"{_PACKAGE}.providers.")]:
            if not (bundled_providers() / name.split(".")[2]).is_dir():
                del sys.modules[name]
