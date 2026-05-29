# SPDX-License-Identifier: AGPL-3.0-or-later

"""Seed/refresh the ``programs`` + ``scopes`` tables from arkadiyt feeds.

Pulls the public ``arkadiyt/bounty-targets-data`` JSON snapshots for
HackerOne, Bugcrowd, Intigriti, YesWeHack and upserts them via the
existing :func:`ingest_arkadiyt_all` service. No API keys required.

Stage-2 prerequisite: the ``programs`` table seeded by this script is the
input for ``mcp__ev__rank_programs``. Without it the EV ranker has nothing
to rank.

Upsert is idempotent — safe to re-run; existing rows update in place.

Usage:
    DATABASE_URL=postgresql://bs:bspass@127.0.0.1:5432/bountystrike_v5 \\
        python scripts/seed_programs.py
"""

from __future__ import annotations

import asyncio
import json
import sys

from control_plane.domains.scope_management.services import ingest_arkadiyt_all
from control_plane.infrastructure.database import create_engine, make_session_factory


async def _run() -> dict[str, int]:
    engine = create_engine()
    factory = make_session_factory(engine)
    try:
        async with factory() as session:
            return await ingest_arkadiyt_all(session)
    finally:
        await engine.dispose()


def main() -> int:
    counts = asyncio.run(_run())
    print(json.dumps(counts, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
