# SPDX-FileCopyrightText: BoxRouter, Inc.
# SPDX-License-Identifier: Apache-2.0
"""Bundled price versions and billing documents are read once per process."""

import yaml  # type: ignore[import-untyped]
from pytest_mock import MockerFixture

from sandbox_provider_pricing import hourly
from sandbox_provider_pricing.providers import billing
from sandbox_provider_pricing.versions import seed_versions


def test_repeated_lookups_do_not_reread_the_bundle(mocker: MockerFixture) -> None:
    seed_versions()
    billing("e2b")
    mocker.patch.object(yaml, "safe_load", side_effect=AssertionError("re-read"))
    for _ in range(3):
        seed_versions()
        billing("e2b")
        hourly("e2b", {"cpu": 2, "memory_mib": 4096})


def test_callers_get_their_own_copy() -> None:
    first = seed_versions()
    first[0]["provider"] = "changed"
    first[0]["classes"].clear()
    again = seed_versions()
    assert again[0]["provider"] != "changed"
    assert again[0]["classes"]

    document = billing("e2b")
    document["rules_version"] = -1
    assert billing("e2b")["rules_version"] != -1
