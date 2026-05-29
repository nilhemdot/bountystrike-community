# SPDX-License-Identifier: AGPL-3.0-or-later

"""FastMCP server for dedup-mcp.

Exposes two MCP tools:
  - check_duplicate   — lookup before oracle invocation; skip if is_dup=True
  - register_finding  — idempotent upsert after oracle validates the finding

Transport: stdio (default FastMCP transport).
Entry point: ``dedup-mcp`` CLI script (see pyproject.toml).

Requires DATABASE_URL env var (postgresql[+asyncpg]://...).
"""

from __future__ import annotations

import asyncio
import os

from mcp.server.fastmcp import FastMCP

from dedup_mcp.embedding import Embedder, OpenAIEmbedder, build_finding_text
from dedup_mcp.fingerprint import compute_fingerprint
from dedup_mcp.store import DedupStore

mcp = FastMCP("dedup-mcp")

_DATABASE_URL: str = os.environ.get("DATABASE_URL", "")
_store: DedupStore | None = None
_embedder: Embedder | None = None
_init_lock = asyncio.Lock()

# Tier thresholds — research/03-verifier-antislop.md §Semantic Dedup.
# Tuned against HackerOne false-duplicate rate; do not relax without
# updating the verifier-antislop ADR.
SEMANTIC_DISPLAY_THRESHOLD = 0.75
SEMANTIC_T2_THRESHOLD = 0.85
SEMANTIC_T3_THRESHOLD = 0.95


async def _get_store() -> DedupStore:
    global _store
    if _store is not None:
        return _store
    async with _init_lock:
        if _store is None:
            if not _DATABASE_URL:
                raise RuntimeError("DATABASE_URL is not set")
            _store = await DedupStore.create(_DATABASE_URL)
    return _store


async def _get_embedder() -> Embedder:
    global _embedder
    if _embedder is None:
        _embedder = OpenAIEmbedder()
    return _embedder


def _classify_tier(similarity: float) -> str:
    """Map similarity → escalation tier.

    >=0.95 → T3 (two-person review)
    >=0.85 → T2 (operator review)
    >=0.75 → display only (no escalation; informational match)
    < 0.75 → no_match
    """
    if similarity >= SEMANTIC_T3_THRESHOLD:
        return "t3"
    if similarity >= SEMANTIC_T2_THRESHOLD:
        return "t2"
    if similarity >= SEMANTIC_DISPLAY_THRESHOLD:
        return "display"
    return "no_match"


# ---------------------------------------------------------------------------
# Testable implementation layer (store injected)
# ---------------------------------------------------------------------------


async def _check_duplicate_impl(
    store: DedupStore,
    platform: str,
    program_handle: str,
    vuln_type: str,
    host: str,
    path: str,
) -> dict:
    fp = compute_fingerprint(platform, program_handle, vuln_type, host, path)
    existing = await store.lookup(fp)
    if existing:
        return {"is_dup": True, "fingerprint_hex": fp, **existing}
    return {"is_dup": False, "fingerprint_hex": fp}


async def _register_finding_impl(
    store: DedupStore,
    platform: str,
    program_handle: str,
    vuln_type: str,
    host: str,
    path: str,
    finding_id: str,
) -> dict:
    fp = compute_fingerprint(platform, program_handle, vuln_type, host, path)
    result = await store.register(fp, platform, program_handle, vuln_type, finding_id)
    return {"fingerprint_hex": fp, **result}


async def _check_semantic_duplicate_impl(
    store: DedupStore,
    embedder: Embedder,
    program_handle: str,
    title: str,
    description: str,
    parameter: str | None,
    threshold: float = SEMANTIC_DISPLAY_THRESHOLD,
    limit: int = 10,
) -> dict:
    """Run a semantic dedup check against prior findings for one program.

    Returns ``tier`` selected from the highest-similarity match:
    ``no_match`` < ``display`` < ``t2`` < ``t3``. Always returns up to
    ``limit`` top matches above ``threshold`` so the operator can review.
    """
    text = build_finding_text(title, description, parameter)
    embedding = await embedder.embed(text)
    matches = await store.semantic_search(
        embedding=embedding,
        program_handle=program_handle,
        threshold=threshold,
        limit=limit,
    )
    if not matches:
        return {"tier": "no_match", "top_similarity": 0.0, "matches": []}
    top = matches[0]
    tier = _classify_tier(top["similarity"])
    return {
        "tier": tier,
        "top_similarity": top["similarity"],
        "matches": matches,
    }


async def _register_embedding_impl(
    store: DedupStore,
    embedder: Embedder,
    finding_id: str,
    title: str,
    description: str,
    parameter: str | None,
) -> dict:
    """Generate + persist the finding embedding column.

    Called by validator-agent on every ``validated`` transition. Idempotent.
    """
    text = build_finding_text(title, description, parameter)
    embedding = await embedder.embed(text)
    await store.store_embedding(finding_id, embedding)
    return {"finding_id": finding_id, "embedding_stored": True, "dim": len(embedding)}


# ---------------------------------------------------------------------------
# MCP tools
# ---------------------------------------------------------------------------


@mcp.tool()
async def check_duplicate(
    platform: str,
    program_handle: str,
    vuln_type: str,
    host: str,
    path: str,
) -> dict:
    """Check whether a finding has already been filed.

    Call before running oracle verification. If ``is_dup`` is True, skip the
    oracle entirely and do not file a new report.

    Args:
        platform: Bug bounty platform handle (e.g. ``hackerone``).
        program_handle: Program slug (e.g. ``acme-corp``).
        vuln_type: Finding type slug (e.g. ``xss``, ``sqli``).
        host: Target hostname (normalised: port 80/443 stripped, lowercased).
        path: Target path (normalised: query/fragment stripped, lowercased).

    Returns:
        ``{is_dup, fingerprint_hex}`` — or ``{is_dup, fingerprint_hex,
        finding_id, first_seen_at}`` when ``is_dup`` is True.
    """
    store = await _get_store()
    return await _check_duplicate_impl(store, platform, program_handle, vuln_type, host, path)


@mcp.tool()
async def register_finding(
    platform: str,
    program_handle: str,
    vuln_type: str,
    host: str,
    path: str,
    finding_id: str,
) -> dict:
    """Register a confirmed finding to prevent duplicate reports.

    Call after oracle validates the finding. Idempotent — if the fingerprint
    already exists, ``registered`` is False and the original ``finding_id`` is
    returned.

    Args:
        platform: Bug bounty platform handle.
        program_handle: Program slug.
        vuln_type: Finding type slug.
        host: Target hostname.
        path: Target path.
        finding_id: UUID string of the newly created finding row.

    Returns:
        ``{registered, fingerprint_hex, finding_id, first_seen_at}``.
    """
    store = await _get_store()
    return await _register_finding_impl(
        store, platform, program_handle, vuln_type, host, path, finding_id
    )


@mcp.tool()
async def check_semantic_duplicate(
    program_handle: str,
    title: str,
    description: str,
    parameter: str | None = None,
    threshold: float = SEMANTIC_DISPLAY_THRESHOLD,
    limit: int = 10,
) -> dict:
    """Semantic-similarity check against prior findings for one program.

    Run AFTER ``check_duplicate`` returns ``is_dup=False``. Embeds
    ``title + description + param`` via OpenAI ``text-embedding-3-large``
    (1536 dims) and queries the ``findings.embedding`` HNSW index for
    cosine matches.

    Tier classification of the highest-similarity hit:
        ≥ 0.95 → ``t3`` (two-person review required before submit)
        ≥ 0.85 → ``t2`` (operator review)
        ≥ 0.75 → ``display`` (show to operator; no escalation)
        otherwise → ``no_match``

    Args:
        program_handle: Program slug (semantic search is per-program).
        title: Report title (short).
        description: Report description (longer narrative).
        parameter: Affected parameter, optional.
        threshold: Similarity floor for matches list (default 0.75).
        limit: Max top matches returned (default 10).

    Returns:
        ``{tier, top_similarity, matches: [{finding_id, cwe, similarity}, ...]}``.
    """
    store = await _get_store()
    embedder = await _get_embedder()
    return await _check_semantic_duplicate_impl(
        store, embedder, program_handle, title, description, parameter, threshold, limit
    )


@mcp.tool()
async def register_embedding(
    finding_id: str,
    title: str,
    description: str,
    parameter: str | None = None,
) -> dict:
    """Generate + persist the embedding column for a validated finding.

    Call after the finding row exists and is in ``validated`` status. Stores
    ``vector(1536)`` from OpenAI ``text-embedding-3-large`` into
    ``findings.embedding`` so subsequent ``check_semantic_duplicate`` calls
    will match against this finding.

    Idempotent: re-calling overwrites the prior embedding (valid after
    title/description edits).

    Args:
        finding_id: UUID string of the findings row.
        title: Report title.
        description: Report description.
        parameter: Affected parameter, optional.

    Returns:
        ``{finding_id, embedding_stored: True, dim: 1536}``.
    """
    store = await _get_store()
    embedder = await _get_embedder()
    return await _register_embedding_impl(
        store, embedder, finding_id, title, description, parameter
    )


def main() -> None:
    """Run the dedup-mcp FastMCP server (stdio transport)."""
    mcp.run()


if __name__ == "__main__":
    main()
