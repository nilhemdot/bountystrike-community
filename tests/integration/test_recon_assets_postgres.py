"""Real-Postgres integration tests for ``recon_assets`` persistence.

Migration 06 added the ``recon_assets`` table; ``ScanPersistence``
populates it after the httpx phase. These tests run the persistence
layer against a live database with migrations 00-06 applied so the
SELECT path scanner-agent uses
(``.claude/agents/scanner-agent.md`` line 0:
``SELECT host, url, tech, status_code FROM recon_assets ...``)
returns the data this code wrote.

Skipped when ``BS5_PG_TEST_DSN`` is unset so CI without a Postgres
fixture stays green. To run locally::

    BS5_PG_TEST_DSN=postgresql://bs:bspass@127.0.0.1:5432/bountystrike_dryrun \\
        uv run pytest tests/integration/test_recon_assets_postgres.py -v
"""

from __future__ import annotations

import os
import sys
import uuid

import asyncpg
import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, "control-plane", "src"))

from control_plane.domains.recon.persistence import ScanPersistence  # noqa: E402
from control_plane.domains.recon.tool_runner import HttpxProbe  # noqa: E402

_DSN = os.environ.get("BS5_PG_TEST_DSN", "").replace("+asyncpg", "")
_skip_if_no_dsn = pytest.mark.skipif(
    not _DSN, reason="BS5_PG_TEST_DSN not set; skipping real-Postgres tests"
)

_TEST_PROGRAM = "recon-assets-pg-test"


@pytest.fixture
async def conn():
    if not _DSN:
        pytest.skip("BS5_PG_TEST_DSN not set")
    c = await asyncpg.connect(_DSN)
    try:
        # FK target — recon_assets.job_id REFERENCES scan_jobs(id).
        await c.execute(
            """
            INSERT INTO programs (handle, platform, name)
            VALUES ($1, 'hackerone', $1)
            ON CONFLICT DO NOTHING
            """,
            _TEST_PROGRAM,
        )
        # Wipe any leftover rows from a prior interrupted run.
        await c.execute(
            "DELETE FROM recon_assets WHERE job_id IN "
            "(SELECT id FROM scan_jobs WHERE program_handle = $1)",
            _TEST_PROGRAM,
        )
        await c.execute(
            "DELETE FROM scan_jobs WHERE program_handle = $1",
            _TEST_PROGRAM,
        )
        yield c
    finally:
        await c.execute(
            "DELETE FROM recon_assets WHERE job_id IN "
            "(SELECT id FROM scan_jobs WHERE program_handle = $1)",
            _TEST_PROGRAM,
        )
        await c.execute(
            "DELETE FROM scan_jobs WHERE program_handle = $1",
            _TEST_PROGRAM,
        )
        await c.close()


async def _seed_job(c: asyncpg.Connection) -> uuid.UUID:
    job_id = uuid.uuid4()
    await c.execute(
        """
        INSERT INTO scan_jobs (id, program_handle, platform, status, started_at)
        VALUES ($1, $2, 'hackerone', 'running', now())
        """,
        job_id,
        _TEST_PROGRAM,
    )
    return job_id


# ---------------------------------------------------------------------------
# 1. Insert probes → rows visible via the spec's SELECT.
# ---------------------------------------------------------------------------


@_skip_if_no_dsn
@pytest.mark.asyncio
async def test_insert_recon_assets_persists_rows_visible_to_spec_select(
    conn: asyncpg.Connection,
) -> None:
    job_id = await _seed_job(conn)
    persistence = ScanPersistence()
    probes = [
        HttpxProbe(
            url="https://www.acme.example",
            host="www.acme.example",
            status_code=200,
            title="Acme",
            tech=("nginx", "react"),
            raw={"http2": True},
        ),
        HttpxProbe(
            url="https://api.acme.example",
            host="api.acme.example",
            status_code=403,
            title="Forbidden",
            tech=(),
            raw={},
        ),
    ]

    n = await persistence.insert_recon_assets(conn, job_id, probes)
    assert n == 2

    # Use the same SELECT scanner-agent.md fence #0 declares.
    rows = await conn.fetch(
        "SELECT host, url, tech, status_code FROM recon_assets "
        "WHERE job_id = $1 ORDER BY host",
        job_id,
    )
    assert len(rows) == 2
    assert rows[0]["host"] == "api.acme.example"
    assert rows[0]["status_code"] == 403
    assert rows[0]["tech"] is None
    assert rows[1]["host"] == "www.acme.example"
    assert rows[1]["url"] == "https://www.acme.example"
    assert rows[1]["tech"] == "nginx,react"
    assert rows[1]["status_code"] == 200


# ---------------------------------------------------------------------------
# 2. Idempotent on re-run — UNIQUE (job_id, host, url) blocks duplicates.
# ---------------------------------------------------------------------------


@_skip_if_no_dsn
@pytest.mark.asyncio
async def test_insert_recon_assets_idempotent_on_rerun(
    conn: asyncpg.Connection,
) -> None:
    job_id = await _seed_job(conn)
    persistence = ScanPersistence()
    probes = [
        HttpxProbe(
            url="https://only.acme.example",
            host="only.acme.example",
            status_code=200,
            title="",
            tech=("apache",),
            raw={},
        ),
    ]

    await persistence.insert_recon_assets(conn, job_id, probes)
    await persistence.insert_recon_assets(conn, job_id, probes)  # rerun
    await persistence.insert_recon_assets(conn, job_id, probes)  # 3rd time

    count = await conn.fetchval(
        "SELECT count(*) FROM recon_assets WHERE job_id = $1",
        job_id,
    )
    assert count == 1


# ---------------------------------------------------------------------------
# 3. Cross-job isolation — same host under two jobs produces two rows.
# ---------------------------------------------------------------------------


@_skip_if_no_dsn
@pytest.mark.asyncio
async def test_insert_recon_assets_isolates_by_job_id(
    conn: asyncpg.Connection,
) -> None:
    job_a = await _seed_job(conn)
    job_b = await _seed_job(conn)
    persistence = ScanPersistence()
    probe = HttpxProbe(
        url="https://shared.acme.example",
        host="shared.acme.example",
        status_code=200,
        title="",
        tech=(),
        raw={},
    )
    await persistence.insert_recon_assets(conn, job_a, [probe])
    await persistence.insert_recon_assets(conn, job_b, [probe])

    counts = await conn.fetch(
        "SELECT job_id, count(*) AS n FROM recon_assets "
        "WHERE host = 'shared.acme.example' GROUP BY job_id",
    )
    assert len(counts) == 2
    assert all(r["n"] == 1 for r in counts)


# ---------------------------------------------------------------------------
# 4. Empty input → no SQL emitted, return 0.
# ---------------------------------------------------------------------------


@_skip_if_no_dsn
@pytest.mark.asyncio
async def test_insert_recon_assets_zero_when_no_probes(
    conn: asyncpg.Connection,
) -> None:
    job_id = await _seed_job(conn)
    persistence = ScanPersistence()
    n = await persistence.insert_recon_assets(conn, job_id, [])
    assert n == 0
    count = await conn.fetchval(
        "SELECT count(*) FROM recon_assets WHERE job_id = $1",
        job_id,
    )
    assert count == 0
