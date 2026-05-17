"""Real-Postgres integration test for the orchestrator's SKIP_IDOR purge.

Gap-2 mitigation per ``docs/audits/validator_agent_contract_audit_2026-05-13.md``:
recon emits ``idor-candidate`` findings without session credentials, so the
validator-agent would land them at ``validation_pending`` 100% of the time.
``scripts/orchestrator.py:_purge_idor_candidates`` drops those rows between
recon and scanner when ``SKIP_IDOR=1`` is set, giving the Stage-2 boot run
one fewer ambiguous status terminal.

Skipped when ``BS5_PG_TEST_DSN`` is unset so CI without a Postgres
fixture stays green. To run locally::

    BS5_PG_TEST_DSN=postgresql://bs:bspass@127.0.0.1:5432/bountystrike_dryrun \\
        uv run pytest tests/integration/test_orchestrator_skip_idor.py -v
"""

from __future__ import annotations

import importlib.util
import os
import sys
import uuid

import asyncpg
import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))

# ``scripts/`` is not a package and ``orchestrator.py`` has heavy module-level
# imports (control-plane domains, asyncpg). Load it via importlib so we can
# call the helper directly without invoking the orchestrator's CLI entry.
sys.path.insert(0, os.path.join(REPO_ROOT, "control-plane", "src"))
_spec = importlib.util.spec_from_file_location(
    "orchestrator_module", os.path.join(REPO_ROOT, "scripts", "orchestrator.py")
)
assert _spec is not None and _spec.loader is not None
_orch = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_orch)
_purge_idor_candidates = _orch._purge_idor_candidates


_DSN = os.environ.get("BS5_PG_TEST_DSN", "").replace("+asyncpg", "")
_skip_if_no_dsn = pytest.mark.skipif(
    not _DSN, reason="BS5_PG_TEST_DSN not set; skipping real-Postgres tests"
)

_TEST_PREFIX = "skip-idor-test-"


@pytest.fixture
async def pg_conn():
    if not _DSN:
        pytest.skip("BS5_PG_TEST_DSN not set")
    conn = await asyncpg.connect(_DSN)
    await conn.execute(
        "DELETE FROM findings WHERE program_handle LIKE $1", f"{_TEST_PREFIX}%"
    )
    await conn.execute(
        "DELETE FROM scan_jobs WHERE program_handle LIKE $1", f"{_TEST_PREFIX}%"
    )
    try:
        yield conn
    finally:
        await conn.execute(
            "DELETE FROM findings WHERE program_handle LIKE $1", f"{_TEST_PREFIX}%"
        )
        await conn.execute(
            "DELETE FROM scan_jobs WHERE program_handle LIKE $1", f"{_TEST_PREFIX}%"
        )
        await conn.close()


async def _create_scan_job(conn: asyncpg.Connection, suffix: str) -> str:
    job_id = str(uuid.uuid4())
    await conn.execute(
        "INSERT INTO scan_jobs (id, program_handle, platform, scope_jwt_jti, status) "
        "VALUES ($1, $2, 'hackerone', 'test-jti', 'recon_complete')",
        job_id, f"{_TEST_PREFIX}{suffix}",
    )
    return job_id


async def _insert_finding(
    conn: asyncpg.Connection, job_id: str, program: str, cwe: str, dedup: str
) -> None:
    await conn.execute(
        "INSERT INTO findings "
        "(id, job_id, program_handle, platform, cwe, url, parameter, status, deduplication_key) "
        "VALUES (gen_random_uuid(), $1, $2, 'hackerone', $3, "
        "'https://example.test/?p=1', 'p', 'hypothesis', $4)",
        job_id, program, cwe, dedup,
    )


@_skip_if_no_dsn
@pytest.mark.asyncio
async def test_purge_drops_idor_candidate_rows(pg_conn: asyncpg.Connection) -> None:
    job_id = await _create_scan_job(pg_conn, "drops")
    program = f"{_TEST_PREFIX}drops"
    await _insert_finding(pg_conn, job_id, program, "idor-candidate", "dedup-1")
    await _insert_finding(pg_conn, job_id, program, "idor-candidate", "dedup-2")

    dropped = await _purge_idor_candidates(pg_conn, job_id)

    assert dropped == 2
    remaining = await pg_conn.fetchval(
        "SELECT COUNT(*) FROM findings WHERE job_id=$1 AND cwe='idor-candidate'",
        job_id,
    )
    assert remaining == 0


@_skip_if_no_dsn
@pytest.mark.asyncio
async def test_purge_leaves_other_cwes_alone(pg_conn: asyncpg.Connection) -> None:
    job_id = await _create_scan_job(pg_conn, "spares")
    program = f"{_TEST_PREFIX}spares"
    await _insert_finding(pg_conn, job_id, program, "xss-candidate", "dedup-x")
    await _insert_finding(pg_conn, job_id, program, "ssrf-candidate", "dedup-s")

    dropped = await _purge_idor_candidates(pg_conn, job_id)

    assert dropped == 0
    remaining = await pg_conn.fetchval(
        "SELECT COUNT(*) FROM findings WHERE job_id=$1", job_id
    )
    assert remaining == 2


@_skip_if_no_dsn
@pytest.mark.asyncio
async def test_purge_is_scoped_to_job_id(pg_conn: asyncpg.Connection) -> None:
    job_a = await _create_scan_job(pg_conn, "scope-a")
    job_b = await _create_scan_job(pg_conn, "scope-b")
    await _insert_finding(pg_conn, job_a, f"{_TEST_PREFIX}scope-a", "idor-candidate", "a-1")
    await _insert_finding(pg_conn, job_b, f"{_TEST_PREFIX}scope-b", "idor-candidate", "b-1")

    dropped = await _purge_idor_candidates(pg_conn, job_a)

    assert dropped == 1
    surviving_b = await pg_conn.fetchval(
        "SELECT COUNT(*) FROM findings WHERE job_id=$1 AND cwe='idor-candidate'",
        job_b,
    )
    assert surviving_b == 1
