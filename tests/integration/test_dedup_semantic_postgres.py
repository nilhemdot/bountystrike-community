"""Real-Postgres integration tests for ``dedup-mcp`` semantic search.

Round 9 closed the structural-fingerprint live-PG gap; this round
closes the semantic-search live-PG gap. Existing unit tests in
``mcp/dedup-mcp/tests/test_semantic_dedup.py`` mock the store, so
they never exercise the pgvector ``<=>`` operator or the HNSW index.
These tests run :meth:`DedupStore.semantic_search` against a live
database with migrations 00-06 applied.

Skipped when ``BS5_PG_TEST_DSN`` is unset so CI without a Postgres
fixture stays green. To run locally::

    BS5_PG_TEST_DSN=postgresql://bs:bspass@127.0.0.1:5432/bountystrike_dryrun \\
        uv run pytest tests/integration/test_dedup_semantic_postgres.py -v

Embeddings are constructed deterministically (unit vectors with
controlled cosine to ``e_0``) so similarity assertions are exact
modulo float32 noise from pgvector's internal storage.
"""

from __future__ import annotations

import math
import os
import sys
import uuid

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, "mcp", "dedup-mcp", "src"))

from dedup_mcp.store import DedupStore  # noqa: E402

_DSN = os.environ.get("BS5_PG_TEST_DSN", "").replace("+asyncpg", "")
_skip_if_no_dsn = pytest.mark.skipif(
    not _DSN, reason="BS5_PG_TEST_DSN not set; skipping real-Postgres tests"
)

_TEST_PREFIX = "semantic-pg-test-"
_DIMS = 1536  # findings.embedding is vector(1536)
_FLOAT_TOL = 1e-4  # pgvector stores float32; allow float64↔32 noise


def _unit_vec(cos_to_e0: float, dims: int = _DIMS) -> list[float]:
    """Return a unit vector whose cosine similarity to ``e_0`` equals
    *cos_to_e0*. Only the first two components are non-zero so
    similarity computations stay easy to reason about."""
    if not -1.0 <= cos_to_e0 <= 1.0:
        raise ValueError("cos_to_e0 must be in [-1, 1]")
    sin = math.sqrt(max(0.0, 1.0 - cos_to_e0 * cos_to_e0))
    v = [0.0] * dims
    v[0] = cos_to_e0
    v[1] = sin
    return v


_QUERY_VEC = _unit_vec(1.0)  # the query — aligned with e_0


@pytest.fixture
async def store():
    if not _DSN:
        pytest.skip("BS5_PG_TEST_DSN not set")
    s = await DedupStore.create(_DSN)
    # Programs row is required because findings.program_handle FKs
    # programs(handle); without it the seed INSERTs fail.
    async with s._pool.acquire() as c:
        for suffix in ("a", "b"):
            await c.execute(
                """
                INSERT INTO programs (handle, platform, name)
                VALUES ($1, 'hackerone', $1)
                ON CONFLICT DO NOTHING
                """,
                f"{_TEST_PREFIX}{suffix}",
            )
        await c.execute(
            "DELETE FROM findings WHERE program_handle LIKE $1",
            f"{_TEST_PREFIX}%",
        )
    try:
        yield s
    finally:
        async with s._pool.acquire() as c:
            await c.execute(
                "DELETE FROM findings WHERE program_handle LIKE $1",
                f"{_TEST_PREFIX}%",
            )
        await s.close()


async def _seed_finding(
    store: DedupStore,
    program: str,
    cwe: str,
    status: str,
    embedding: list[float],
) -> uuid.UUID:
    finding_id = uuid.uuid4()
    async with store._pool.acquire() as c:
        await c.execute(
            """
            INSERT INTO findings (id, program_handle, platform, cwe, status)
            VALUES ($1, $2, 'hackerone', $3, $4::finding_status)
            """,
            finding_id,
            program,
            cwe,
            status,
        )
    await store.store_embedding(str(finding_id), embedding)
    return finding_id


# ---------------------------------------------------------------------------
# 1. Basic exact match — same embedding → similarity ≈ 1.0
# ---------------------------------------------------------------------------


@_skip_if_no_dsn
@pytest.mark.asyncio
async def test_semantic_search_exact_match_returns_similarity_one(
    store: DedupStore,
) -> None:
    program = f"{_TEST_PREFIX}a"
    fid = await _seed_finding(store, program, "CWE-79", "validated", _QUERY_VEC)

    matches = await store.semantic_search(
        embedding=_QUERY_VEC,
        program_handle=program,
        threshold=0.5,
        limit=10,
    )
    assert len(matches) == 1
    assert matches[0]["finding_id"] == str(fid)
    assert matches[0]["cwe"] == "CWE-79"
    assert abs(matches[0]["similarity"] - 1.0) < _FLOAT_TOL


# ---------------------------------------------------------------------------
# 2. Threshold floor — raising the threshold prunes lower-similarity hits.
# ---------------------------------------------------------------------------


@_skip_if_no_dsn
@pytest.mark.asyncio
async def test_semantic_search_threshold_filters_low_similarity(
    store: DedupStore,
) -> None:
    program = f"{_TEST_PREFIX}a"
    fid_high = await _seed_finding(store, program, "CWE-79", "validated", _unit_vec(1.0))
    fid_mid = await _seed_finding(store, program, "CWE-89", "validated", _unit_vec(0.80))

    # Default-style display threshold (0.75) → both rows in.
    relaxed = await store.semantic_search(
        embedding=_QUERY_VEC, program_handle=program, threshold=0.75, limit=10
    )
    relaxed_ids = {m["finding_id"] for m in relaxed}
    assert relaxed_ids == {str(fid_high), str(fid_mid)}

    # Tight T3-style threshold (0.95) → only the exact match survives.
    tight = await store.semantic_search(
        embedding=_QUERY_VEC, program_handle=program, threshold=0.95, limit=10
    )
    tight_ids = {m["finding_id"] for m in tight}
    assert tight_ids == {str(fid_high)}


# ---------------------------------------------------------------------------
# 3. Cross-program isolation — semantic_search scopes to a single program.
# ---------------------------------------------------------------------------


@_skip_if_no_dsn
@pytest.mark.asyncio
async def test_semantic_search_isolated_by_program_handle(
    store: DedupStore,
) -> None:
    program_a = f"{_TEST_PREFIX}a"
    program_b = f"{_TEST_PREFIX}b"

    fid_a = await _seed_finding(store, program_a, "CWE-79", "validated", _QUERY_VEC)
    await _seed_finding(store, program_b, "CWE-79", "validated", _QUERY_VEC)

    matches = await store.semantic_search(
        embedding=_QUERY_VEC, program_handle=program_a, threshold=0.5, limit=10
    )
    assert len(matches) == 1
    assert matches[0]["finding_id"] == str(fid_a)


# ---------------------------------------------------------------------------
# 4. Excluded statuses — archived/rejected/duplicate hidden by default.
# ---------------------------------------------------------------------------


@_skip_if_no_dsn
@pytest.mark.asyncio
async def test_semantic_search_excludes_archived_rejected_duplicate(
    store: DedupStore,
) -> None:
    program = f"{_TEST_PREFIX}a"
    fid_validated = await _seed_finding(
        store, program, "CWE-79", "validated", _QUERY_VEC
    )
    await _seed_finding(store, program, "CWE-79", "archived", _QUERY_VEC)
    await _seed_finding(store, program, "CWE-79", "rejected", _QUERY_VEC)
    await _seed_finding(store, program, "CWE-79", "duplicate", _QUERY_VEC)

    # Default exclude — archived/rejected/duplicate all suppressed.
    default = await store.semantic_search(
        embedding=_QUERY_VEC, program_handle=program, threshold=0.5, limit=10
    )
    assert {m["finding_id"] for m in default} == {str(fid_validated)}

    # Override — pass empty exclusions, every status returns.
    relaxed = await store.semantic_search(
        embedding=_QUERY_VEC,
        program_handle=program,
        threshold=0.5,
        limit=10,
        exclude_statuses=(),
    )
    assert len(relaxed) == 4


# ---------------------------------------------------------------------------
# 5. No match below threshold — orthogonal vector returns empty list.
# ---------------------------------------------------------------------------


@_skip_if_no_dsn
@pytest.mark.asyncio
async def test_semantic_search_orthogonal_vector_returns_empty(
    store: DedupStore,
) -> None:
    program = f"{_TEST_PREFIX}a"
    # Seed at e_1 — orthogonal to the e_0 query.
    await _seed_finding(store, program, "CWE-79", "validated", _unit_vec(0.0))

    matches = await store.semantic_search(
        embedding=_QUERY_VEC, program_handle=program, threshold=0.5, limit=10
    )
    assert matches == []
