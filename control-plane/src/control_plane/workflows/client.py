# SPDX-License-Identifier: AGPL-3.0-or-later
"""Shared Hatchet v1 client — single source of truth (plan 01-02 AC-6).

Every workflow task and the worker import ``hatchet`` from this module so the
SDK client is instantiated exactly once. The client reads its connection
settings (``HATCHET_CLIENT_TOKEN``, ``HATCHET_CLIENT_TLS_STRATEGY``) from the
environment; the auth token embeds the engine's gRPC broadcast address, so no
host/port is hard-coded here.
"""

from __future__ import annotations

from hatchet_sdk import Hatchet

# Single shared instance. Do NOT construct Hatchet() anywhere else — import this
# object instead, so worker registration and trigger call sites share one
# client/config.
hatchet = Hatchet()
