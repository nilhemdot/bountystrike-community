# SPDX-License-Identifier: AGPL-3.0-or-later

"""ev-mcp — Expected Value-ranked program scoring via FastMCP.

Thin transport layer over
:mod:`control_plane.domains.program_ranking`. The EV formula and weights
live in control-plane and are imported here, so any change to scoring
takes effect across the platform without touching this MCP.
"""

from __future__ import annotations

from .db import ProgramFeatureLoader

__all__ = ["ProgramFeatureLoader"]
