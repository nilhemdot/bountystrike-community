# SPDX-License-Identifier: AGPL-3.0-or-later

"""Recon bounded context.

Wraps the ProjectDiscovery toolchain (subfinder → httpx → katana) and
persists discovered hosts/endpoints into ``scan_jobs`` + ``findings``
under a scope JWT's allow/deny boundary.

Public entry point: :class:`ReconService` (composed with :class:`BinaryRunner`,
:class:`ScanPersistence`, and a :class:`ScopeFilter` parsed from JWT claims).
"""

from __future__ import annotations

from .persistence import ScanPersistence
from .scope_filter import ScopeFilter
from .service import ReconService
from .tool_runner import BinaryRunner, KatanaEndpoint, RealBinaryRunner, SubprocessError

__all__ = [
    "BinaryRunner",
    "KatanaEndpoint",
    "RealBinaryRunner",
    "ReconService",
    "ScanPersistence",
    "ScopeFilter",
    "SubprocessError",
]
