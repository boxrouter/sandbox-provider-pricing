# SPDX-FileCopyrightText: BoxRouter, Inc.
# SPDX-License-Identifier: Apache-2.0
import pytest

import sandbox_provider_pricing

pytestmark = pytest.mark.unit


def test_package_names_what_it_owns() -> None:
    assert sandbox_provider_pricing.__doc__ is not None
    assert "price" in sandbox_provider_pricing.__doc__
