# SPDX-FileCopyrightText: BoxRouter, Inc.
# SPDX-License-Identifier: Apache-2.0
"""Blaxel's and Modal's volume storage rates come from their raw pricing pages."""

import re
from pathlib import Path

from sandbox_provider_pricing.price_sheet import build_price_sheet
from sandbox_provider_pricing.providers import provider_ids
from sandbox_provider_pricing.versions import latest_version
from sandbox_provider_pricing.watch import check

PAGE = Path(__file__).parent / "fixtures" / "pages" / "blaxel-pricing.html"
VOLUMES_ROW = (
    "Provisioned capacity Billed on the volume size you provision, for as long as the volume "
    "exists, regardless of how much data you actually write in it. $0.12 / GB · month"
)


def test_the_raw_pricing_page_lists_the_volumes_row() -> None:
    page = check.page_text(PAGE.read_text(encoding="utf-8"))
    assert page.contains(VOLUMES_ROW)
    text = re.sub(r"[\s|]+", " ", page.visible)
    rates = set(
        re.findall(r"Provisioned capacity Billed on the volume[^$]*\$([0-9.]+) / GB · month", text)
    )
    assert rates == {"0.12"}


def test_the_latest_blaxel_version_records_the_volume_rate() -> None:
    document = latest_version("blaxel")
    storage = document["volume_storage"]
    assert (storage["usd"], storage["per"], storage["rate_source"]) == (
        "0.12",
        "gib-month",
        "published_volume_rate",
    )
    assert storage["source_url"] == "https://blaxel.ai/pricing"
    assert any(
        item["url"] == storage["source_url"] and "$0.12 / GB" in item["quote"]
        for item in document["sources"]
    )
    # The rates beside it are unchanged.
    assert document["snapshot_storage"]["usd"] == "0.20"
    assert document["image_storage"]["usd"] == "0.045"


MODAL_PAGE = Path(__file__).parent / "fixtures" / "pages" / "modal-pricing.html"
MODAL_VOLUMES_ROW = "Volumes $0.09 / GiB / mo *includes 1 TiB / mo free"


def test_the_raw_modal_pricing_page_lists_the_volumes_row() -> None:
    page = check.page_text(MODAL_PAGE.read_text(encoding="utf-8"))
    assert page.contains(MODAL_VOLUMES_ROW)
    text = re.sub(r"[\s|]+", " ", page.visible)
    assert set(re.findall(r"Volumes \$([0-9.]+) / GiB / mo", text)) == {"0.09"}


def test_the_latest_modal_version_records_the_volume_rate() -> None:
    document = latest_version("modal")
    storage = document["volume_storage"]
    assert (storage["usd"], storage["per"], storage["rate_source"]) == (
        "0.09",
        "gib-month",
        "published_volume_rate",
    )
    assert any(
        item["url"] == storage["source_url"] and MODAL_VOLUMES_ROW in item["quote"]
        for item in document["sources"]
    )
    # "*includes 1 TiB / mo free": the allowance is on the row, and the sheet carries it.
    assert (storage["included_gb"], storage["included_unit"]) == ("1024", "GiB")
    sheet_rows = [
        row
        for entry in build_price_sheet()["providers"]
        if entry["id"] == "modal"
        for row in entry["storage"]
        if row["kind"] == "volume"
    ]
    assert sheet_rows and all(
        (row["included_gb"], row["included_unit"]) == (1024.0, "GiB") for row in sheet_rows
    )


def test_no_other_provider_records_a_volume_rate() -> None:
    for provider in set(provider_ids()) - {"blaxel", "modal"}:
        assert "volume_storage" not in latest_version(provider)
