# SPDX-License-Identifier: AGPL-3.0-or-later

"""Sandbox driver registry.

Drivers are NOT auto-instantiated — the server selects one explicitly via
``SANDBOX_DRIVER`` env. Default = none (raises on first call). This
guards against a deploy that accidentally falls back to the dev driver.
"""

from __future__ import annotations

from sandbox_mcp.drivers.protocol import Driver

__all__ = ["Driver"]
