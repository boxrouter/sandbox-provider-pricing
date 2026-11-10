# SPDX-FileCopyrightText: BoxRouter, Inc.
# SPDX-License-Identifier: Apache-2.0
"""Blaxel's deployment-image storage rate is recorded from its pricing page, read as raw HTML."""

import re
from pathlib import Path

from sandbox_provider_pricing.versions import latest_version, priced_provider_ids
from sandbox_provider_pricing.watch import check

PAGE = Path(__file__).parent / "fixtures" / "pages" / "blaxel-pricing.html"
IMAGES_ROW = (
    "Images Templated deployment images stored for fast and repeatable creation. "
    "$0.045 / GB · month"
)


def test_the_raw_pricing_page_lists_the_images_row() -> None:
    page = check.page_text(PAGE.read_text(encoding="utf-8"))
    assert page.contains(IMAGES_ROW)
    text = re.sub(r"[\s|]+", " ", page.visible)
    # The page repeats the row for each plan view; every one says the same rate.
    rates = set(
        re.findall(r"Images Templated deployment images[^$]*\$([0-9.]+) / GB · month", text)
    )
    assert rates == {"0.045"}


def test_the_latest_blaxel_version_records_the_image_rate() -> None:
    document = latest_version("blaxel")
    storage = document["image_storage"]
    assert (storage["usd"], storage["per"], storage["rate_source"]) == (
        "0.045",
        "gib-month",
        "published_image_rate",
    )
    assert storage["source_url"] == "https://blaxel.ai/pricing"
    assert any(
        item["url"] == storage["source_url"] and "$0.045 / GB" in item["quote"]
        for item in document["sources"]
    )
    # The snapshot rate beside it is unchanged.
    assert document["snapshot_storage"]["usd"] == "0.20"


def test_every_quote_of_the_latest_blaxel_version_found_on_the_pricing_page_still_reads() -> None:
    page = check.page_text(PAGE.read_text(encoding="utf-8"))
    document = latest_version("blaxel")
    quotes = [
        item["quote"] for item in document["sources"] if item["url"] == "https://blaxel.ai/pricing"
    ]
    assert quotes
    assert [quote for quote in quotes if not page.contains(quote)] == []


def test_no_other_provider_records_an_image_rate() -> None:
    for provider in set(priced_provider_ids()) - {"blaxel"}:
        assert "image_storage" not in latest_version(provider)
