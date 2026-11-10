# SPDX-FileCopyrightText: BoxRouter, Inc.
# SPDX-License-Identifier: Apache-2.0
"""Independent snapshot storage rates keep their supplier evidence and proxy label."""

from sandbox_provider_pricing.providers import provider_ids
from sandbox_provider_pricing.versions import latest_version, seed_versions


def test_published_snapshot_rates_and_approved_daytona_proxy() -> None:
    expected = {
        "vercel": ("0.08", "gb-month", "published_snapshot_rate", "vercel.com"),
        "blaxel": ("0.20", "gib-month", "published_snapshot_rate", "blaxel.ai"),
        "daytona": ("0.000108", "gib-hour", "published_disk_rate_proxy", "daytona.io"),
    }
    for provider, (amount, unit, source, domain) in expected.items():
        document = latest_version(provider)
        storage = document["snapshot_storage"]
        assert (storage["usd"], storage["per"], storage["rate_source"]) == (
            amount,
            unit,
            source,
        )
        assert domain in storage["source_url"]
        assert any(
            item["url"] == storage["source_url"] and amount in item["quote"]
            for item in document["sources"]
        )
    assert (
        "does not publish a snapshot rate" in latest_version("daytona")["snapshot_storage"]["note"]
    )
    for provider in set(provider_ids()) - set(expected):
        assert "snapshot_storage" not in latest_version(provider)


def test_blaxel_binary_gigabyte_correction_preserves_first_version() -> None:
    corrected = next(
        version for version in seed_versions() if version["version"] == "blaxel@2026-10-20-061947Z"
    )
    assert "blaxel@2026-10-20" in corrected["supersedes"]
    assert any(
        item["url"] == "https://blaxel.ai/platform/storage" and "1 GB = 2^30 bytes" in item["quote"]
        for item in corrected["sources"]
    )
