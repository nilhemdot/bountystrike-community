# SPDX-License-Identifier: AGPL-3.0-or-later

"""Driver protocol — every concrete driver implements this interface."""

from __future__ import annotations

from typing import Protocol

from sandbox_mcp.types import RunRequest, RunResult


class Driver(Protocol):
    """Sandbox driver contract.

    Implementations MUST:
      - Verify ``request.scope_token`` before allocating any resources.
      - Apply ``request.egress_allowlist`` as a deny-by-default firewall.
      - Capture stdout/stderr up to ``MAX_OUTPUT_BYTES``; truncate beyond.
      - Hash ``stdout_bytes + stderr_bytes`` to ``content_hash_hex``.
      - Tear down the sandbox after run when ``request.cleanup`` is True.
      - Never persist secrets, scope tokens, or stdin payloads to disk
        outside the sandbox boundary.
    """

    name: str

    async def run(self, request: RunRequest) -> RunResult:
        """Execute one sandboxed run; return the result."""
        ...

    async def snapshot(self, run_id: str) -> dict:
        """Optional: snapshot the post-run filesystem.

        Drivers without filesystem snapshotting (LocalSubprocessDriver)
        return ``{"supported": False, "run_id": run_id}``.
        """
        ...


__all__ = ["Driver"]
