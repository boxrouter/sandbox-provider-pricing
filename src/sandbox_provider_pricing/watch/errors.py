# SPDX-FileCopyrightText: BoxRouter, Inc.
# SPDX-License-Identifier: Apache-2.0
"""The error for a draft that could not be made at all."""


class DraftError(Exception):
    """The drafting could not be done at all: no key, no connection, an error from Claude."""
