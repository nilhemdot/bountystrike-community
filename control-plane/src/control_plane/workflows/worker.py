# SPDX-License-Identifier: AGPL-3.0-or-later
"""Hatchet worker entry point — ``python -m control_plane.workflows.worker``.

Registers the heartbeat task against the engine and blocks, serving runs. This
is a separate process from the FastAPI control-plane; both share the single
``hatchet`` client (plan 01-02 AC-6). Requires ``HATCHET_CLIENT_TOKEN`` (and,
for the insecure solo-mode engine, ``HATCHET_CLIENT_TLS_STRATEGY=none``) in the
environment.
"""

from __future__ import annotations

from control_plane.workflows.client import hatchet
from control_plane.workflows.tasks import (
    heartbeat,
    record_evidence,
    scope_poll,
    verify_finding,
)


def main() -> None:
    worker = hatchet.worker(
        "bs-worker",
        slots=1,
        workflows=[heartbeat, record_evidence, scope_poll, verify_finding],
    )
    worker.start()


if __name__ == "__main__":
    main()
