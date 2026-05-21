"""Outbound integration clients for upstream scope sources."""

from __future__ import annotations

from .arkadiyt import (
    DEFAULT_BASE_URL as ARKADIYT_BASE_URL,
    FEED_FILES,
    ArkadiytClient,
    FederationProgram,
)
from .hackerone import (
    DEFAULT_BASE_URL as H1_BASE_URL,
    H1Asset,
    H1AuthError,
    H1ClientError,
    H1RateLimitError,
    H1ServerError,
    HackerOneClient,
)
from .normalize import (
    CanonicalScope,
    normalize_bugcrowd_target,
    normalize_h1_org_asset,
    normalize_immunefi_impact,
    normalize_intigriti_scope,
    normalize_yeswehack_program,
)

__all__ = [
    "ARKADIYT_BASE_URL",
    "ArkadiytClient",
    "CanonicalScope",
    "FEED_FILES",
    "FederationProgram",
    "H1Asset",
    "H1AuthError",
    "H1ClientError",
    "H1RateLimitError",
    "H1ServerError",
    "H1_BASE_URL",
    "HackerOneClient",
    "normalize_bugcrowd_target",
    "normalize_h1_org_asset",
    "normalize_immunefi_impact",
    "normalize_intigriti_scope",
    "normalize_yeswehack_program",
]
