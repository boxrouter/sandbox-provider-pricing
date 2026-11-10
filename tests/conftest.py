# SPDX-FileCopyrightText: BoxRouter, Inc.
# SPDX-License-Identifier: Apache-2.0
"""Each test starts with no evidence proven valid by an earlier one."""

from collections.abc import Iterator

import pytest

from sandbox_provider_pricing import evidence


@pytest.fixture(autouse=True)
def no_proven_evidence() -> Iterator[None]:
    evidence._PROVEN.clear()
    yield
    evidence._PROVEN.clear()
