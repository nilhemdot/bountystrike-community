# SPDX-License-Identifier: AGPL-3.0-or-later

"""kev-mcp — CISA KEV + EPSS v4 lookups via FastMCP.

Build-plan §4.7 specifies three sources (CISA KEV, EPSS, VulnCheck KEV).
This module ships the two free, no-auth sources. VulnCheck integration
is a swap of :class:`KevSource` impls — defer until the API key is
available in the deployment env.
"""

from __future__ import annotations

from .cache import KevCache
from .epss import EpssClient, EpssScore
from .loader import CisaKevLoader, KevEntry

__all__ = [
    "CisaKevLoader",
    "EpssClient",
    "EpssScore",
    "KevCache",
    "KevEntry",
]
