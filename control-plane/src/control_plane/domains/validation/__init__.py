# SPDX-License-Identifier: AGPL-3.0-or-later
"""Validation domain — deterministic-verifier wiring (plan 01-06).

Bridges the field-validated oracle-mcp oracles into the Phase-1 runtime: a
``cwe`` → oracle dispatch plus the ``VerifyFindingService`` that enforces the
"no validated without evidence" moat.
"""

from __future__ import annotations

from control_plane.domains.validation.dispatch import normalise_cwe, resolve_oracle
from control_plane.domains.validation.services import VerifyFindingService

__all__ = ["VerifyFindingService", "normalise_cwe", "resolve_oracle"]
