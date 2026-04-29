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

from dedup_mcp.fingerprint import compute_fingerprint
from dedup_mcp.store import DedupStore

mcp = FastMCP("dedup-mcp")

_DATABASE_URL: str = os.environ.get("DATABASE_URL", "")
_store: DedupStore | None = None
_init_lock = asyncio.Lock()


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


def main() -> None:
    """Run the dedup-mcp FastMCP server (stdio transport)."""
    mcp.run()


if __name__ == "__main__":
    main()
