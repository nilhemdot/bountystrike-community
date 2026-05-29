# SPDX-License-Identifier: AGPL-3.0-or-later

"""Platform value object — the typed enum of supported bug-bounty platforms.

Both the JWT issuer and every integration client must agree on this set; we
keep it as a `Literal` rather than a Python `Enum` because Pydantic v2 can
validate `Literal` directly without a custom field type.
"""

from __future__ import annotations

from typing import Literal

Platform = Literal["hackerone", "bugcrowd", "intigriti", "yeswehack", "immunefi"]
"""Platforms supported by the federation + JWT layers."""


SUPPORTED_PLATFORMS: tuple[Platform, ...] = (
    "hackerone",
    "bugcrowd",
    "intigriti",
    "yeswehack",
    "immunefi",
)


def is_supported_platform(value: str) -> bool:
    """Return ``True`` iff ``value`` is one of :data:`SUPPORTED_PLATFORMS`."""
    return value in SUPPORTED_PLATFORMS


__all__ = ["Platform", "SUPPORTED_PLATFORMS", "is_supported_platform"]
