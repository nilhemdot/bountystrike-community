"""Real-Postgres integration tests for ``dedup-mcp``.

Existing unit tests in ``mcp/dedup-mcp/tests/test_dedup_mcp.py`` mock
the store, so they never exercise the asyncpg/Postgres path. These
tests run :class:`DedupStore` against a live database with migration
02 applied so spec drift between the embedded ``CREATE TABLE`` in
``store.py`` and ``infra/sql/02_dedup_fingerprints.sql`` surfaces as a
test failure rather than at runtime.

Skipped when ``BS5_PG_TEST_DSN`` is unset so CI without a Postgres
fixture stays green. To run locally::

    BS5_PG_TEST_DSN=postgresql://bs:bspass@127.0.0.1:5432/bountystrike_dryrun \\
        uv run pytest tests/integration/test_dedup_postgres.py -v
"""

from __future__ import annotations

import os
import sys
import uuid

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, "mcp", "dedup-mcp", "src"))

from dedup_mcp.fingerprint import compute_fingerprint  # noqa: E402
from dedup_mcp.server import _register_finding_impl  # noqa: E402
from dedup_mcp.store import DedupStore  # noqa: E402

_DSN = os.environ.get("BS5_PG_TEST_DSN", "").replace("+asyncpg", "")
_skip_if_no_dsn = pytest.mark.skipif(
    not _DSN, reason="BS5_PG_TEST_DSN not set; skipping real-Postgres tests"
)

# Test rows live under this program-handle prefix so cleanup never
# touches non-test rows.
_TEST_PREFIX = "dedup-pg-test-"


@pytest.fixture
async def store():
    if not _DSN:
        pytest.skip("BS5_PG_TEST_DSN not set")
    s = await DedupStore.create(_DSN)
    # Wipe any leftover rows from a prior interrupted run.
    async with s._pool.acquire() as c:
        await c.execute(
            "DELETE FROM dedup_fingerprints WHERE program_handle LIKE $1",
            f"{_TEST_PREFIX}%",
        )
    try:
        yield s
    finally:
        async with s._pool.acquire() as c:
            await c.execute(
                "DELETE FROM dedup_fingerprints WHERE program_handle LIKE $1",
                f"{_TEST_PREFIX}%",
            )
        await s.close()


# ---------------------------------------------------------------------------
# 1. register-new — row lands in dedup_fingerprints with the right shape.
# ---------------------------------------------------------------------------


@_skip_if_no_dsn
@pytest.mark.asyncio
async def test_register_new_persists_row(store: DedupStore) -> None:
    program = f"{_TEST_PREFIX}reg-new"
    fp = compute_fingerprint("hackerone", program, "xss", "example.com", "/search")
    finding_id = str(uuid.uuid4())

    result = await store.register(fp, "hackerone", program, "xss", finding_id)

    assert result["registered"] is True
    assert result["finding_id"] == finding_id

    async with store._pool.acquire() as c:
        row = await c.fetchrow(
            "SELECT fingerprint_hex, platform, program_handle, vuln_type, finding_id "
            "FROM dedup_fingerprints WHERE fingerprint_hex = $1",
            fp,
        )
    assert row is not None
    assert row["fingerprint_hex"] == fp
    assert row["platform"] == "hackerone"
    assert row["program_handle"] == program
    assert row["vuln_type"] == "xss"
    assert row["finding_id"] == finding_id


# ---------------------------------------------------------------------------
# 2. register-idempotent — second call with same fingerprint preserves
#    the original finding_id and reports registered=False.
# ---------------------------------------------------------------------------


@_skip_if_no_dsn
@pytest.mark.asyncio
async def test_register_idempotent_returns_original_finding(store: DedupStore) -> None:
    program = f"{_TEST_PREFIX}idemp"
    fp = compute_fingerprint("hackerone", program, "sqli", "api.example.com", "/users")
    first_id = str(uuid.uuid4())
    second_id = str(uuid.uuid4())

    first = await store.register(fp, "hackerone", program, "sqli", first_id)
    second = await store.register(fp, "hackerone", program, "sqli", second_id)

    assert first["registered"] is True
    assert first["finding_id"] == first_id

    assert second["registered"] is False
    assert second["finding_id"] == first_id  # original wins
    assert second["first_seen_at"] == first["first_seen_at"]

    # Only one row in the table for this fingerprint.
    async with store._pool.acquire() as c:
        count = await c.fetchval(
            "SELECT count(*) FROM dedup_fingerprints WHERE fingerprint_hex = $1",
            fp,
        )
    assert count == 1


# ---------------------------------------------------------------------------
# 3. cross-program distinct — same (vuln_type, host, path) under two
#    different programs must produce two distinct fingerprints + rows.
#    Guards against a fingerprint algorithm regression that drops
#    program_handle from the digest.
# ---------------------------------------------------------------------------


@_skip_if_no_dsn
@pytest.mark.asyncio
async def test_cross_program_same_vuln_yields_distinct_rows(store: DedupStore) -> None:
    prog_a = f"{_TEST_PREFIX}prog-a"
    prog_b = f"{_TEST_PREFIX}prog-b"

    fp_a = compute_fingerprint("hackerone", prog_a, "xss", "shared.example.com", "/q")
    fp_b = compute_fingerprint("hackerone", prog_b, "xss", "shared.example.com", "/q")

    assert fp_a != fp_b, "fingerprint must include program_handle"

    fid_a = str(uuid.uuid4())
    fid_b = str(uuid.uuid4())

    res_a = await store.register(fp_a, "hackerone", prog_a, "xss", fid_a)
    res_b = await store.register(fp_b, "hackerone", prog_b, "xss", fid_b)

    assert res_a["registered"] is True
    assert res_b["registered"] is True
    assert res_a["finding_id"] != res_b["finding_id"]

    async with store._pool.acquire() as c:
        rows = await c.fetch(
            "SELECT program_handle, finding_id FROM dedup_fingerprints "
            "WHERE program_handle IN ($1, $2) ORDER BY program_handle",
            prog_a,
            prog_b,
        )
    assert len(rows) == 2
    assert rows[0]["program_handle"] == prog_a
    assert rows[0]["finding_id"] == fid_a
    assert rows[1]["program_handle"] == prog_b
    assert rows[1]["finding_id"] == fid_b


# ---------------------------------------------------------------------------
# 4. lookup-roundtrip — registered fingerprint hits, unknown misses.
# ---------------------------------------------------------------------------


@_skip_if_no_dsn
@pytest.mark.asyncio
async def test_lookup_roundtrip(store: DedupStore) -> None:
    program = f"{_TEST_PREFIX}lookup"
    fp_hit = compute_fingerprint("hackerone", program, "ssrf", "edge.example.com", "/proxy")
    fp_miss = compute_fingerprint("hackerone", program, "rce", "other.example.com", "/exec")
    finding_id = str(uuid.uuid4())

    await store.register(fp_hit, "hackerone", program, "ssrf", finding_id)

    hit = await store.lookup(fp_hit)
    assert hit is not None
    assert hit["finding_id"] == finding_id
    assert "first_seen_at" in hit

    miss = await store.lookup(fp_miss)
    assert miss is None


# ---------------------------------------------------------------------------
# 5. Server-impl path — _register_finding_impl end-to-end against real PG.
#    Closes the gap between the mocked unit tests and the real call site
#    the validator-agent invokes via MCP.
# ---------------------------------------------------------------------------


@_skip_if_no_dsn
@pytest.mark.asyncio
async def test_register_finding_impl_end_to_end(store: DedupStore) -> None:
    program = f"{_TEST_PREFIX}impl"
    finding_id = str(uuid.uuid4())

    result = await _register_finding_impl(
        store, "hackerone", program, "open_redirect",
        "redir.example.com", "/go", finding_id,
    )

    assert result["registered"] is True
    assert result["finding_id"] == finding_id
    expected_fp = compute_fingerprint(
        "hackerone", program, "open_redirect", "redir.example.com", "/go"
    )
    assert result["fingerprint_hex"] == expected_fp

    async with store._pool.acquire() as c:
        stored_fid = await c.fetchval(
            "SELECT finding_id FROM dedup_fingerprints WHERE fingerprint_hex = $1",
            expected_fp,
        )
    assert stored_fid == finding_id
