# SPDX-FileCopyrightText: BoxRouter, Inc.
# SPDX-License-Identifier: Apache-2.0
"""Provider rules are ordinary modules: imported by name, once, and fully initialized."""

import importlib
from concurrent.futures import ThreadPoolExecutor

from sandbox_provider_pricing import providers


def test_provider_rules_are_the_imported_module() -> None:
    module = providers.rules("e2b")
    assert module is importlib.import_module("sandbox_provider_pricing.providers.e2b.rules")
    assert module.__name__ == "sandbox_provider_pricing.providers.e2b.rules"


def test_concurrent_callers_receive_the_same_initialized_module() -> None:
    providers.rules.cache_clear()
    with ThreadPoolExecutor(max_workers=4) as pool:
        modules = list(pool.map(providers.rules, ["modal"] * 8))
    assert all(module is modules[0] for module in modules)
    assert callable(modules[0].billable)
