# SPDX-License-Identifier: AGPL-3.0-or-later
"""First BountyStrike Hatchet v1 task — heartbeat (plan 01-02).

Proves the durable-execution runtime end to end (trigger -> worker -> status)
with no business logic. v1 function-based API: ``@hatchet.task`` with a Pydantic
``input_validator`` and an async handler taking ``(input, ctx)``; triggered via
``aio_run``. The legacy class-based decorator API (hatchet . workflow) is NOT
used. Real agent tasks (recon -> scan -> exploit -> validate) land in later plans.
"""

from __future__ import annotations

from datetime import UTC, datetime

from hatchet_sdk import Context
from pydantic import BaseModel

from control_plane.workflows.client import hatchet


class HeartbeatInput(BaseModel):
    """Input schema for the heartbeat task."""

    message: str


@hatchet.task(name="bs-heartbeat", input_validator=HeartbeatInput)
async def heartbeat(input: HeartbeatInput, ctx: Context) -> dict[str, str]:
    """Echo the message back with a server timestamp — a durable no-op."""
    return {
        "echo": input.message,
        "completed_at": datetime.now(UTC).isoformat(timespec="seconds"),
    }
