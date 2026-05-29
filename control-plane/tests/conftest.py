# SPDX-License-Identifier: AGPL-3.0-or-later

"""Pytest configuration for control-plane unit tests.

Sets up sys.path to ensure control_plane module is importable
when running tests from the control-plane directory.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Add control-plane/src to sys.path so control_plane module is importable
CONTROL_PLANE_SRC = Path(__file__).parent.parent / "src"
if str(CONTROL_PLANE_SRC) not in sys.path:
    sys.path.insert(0, str(CONTROL_PLANE_SRC))
