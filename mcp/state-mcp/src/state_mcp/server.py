# SPDX-License-Identifier: AGPL-3.0-or-later

"""FastMCP server for state-mcp.

Exposes four MCP tools:
  - get_finding(finding_id)               — single finding row
  - query_artifacts(finding_id)           — evidence_artifacts for a finding
  - query_experience_kb(cwe, product?, version?)
                                          — prior validated exploits matching CWE / tech
  - update_finding_status(finding_id, new_status, expected_current_status?)
                                          — optimistic-lock state transition

Transport: stdio (default FastMCP transport).
Entry point: ``state-mcp`` CLI script (see pyproject.toml).

Requires ``DATABASE_URL`` env var (postgresql[+asyncpg]://...).
"""

from __future__ import annotations

import asyncio
import os

from mcp.server.fastmcp import FastMCP

from state_mcp.store import StateStore

mcp = FastMCP("state-mcp")

_DATABASE_URL: str = os.environ.get("DATABASE_URL", "")
_store: StateStore | None = None
_init_lock = asyncio.Lock()


async def _get_store() -> StateStore:
    global _store
    if _store is not None:
        return _store
    async with _init_lock:
        if _store is None:
            if not _DATABASE_URL:
                raise RuntimeError("DATABASE_URL is not set")
            _store = await StateStore.create(_DATABASE_URL)
    return _store


# ---------------------------------------------------------------------------
# Testable implementation layer (store injected)
# ---------------------------------------------------------------------------


async def _get_finding_impl(store: StateStore, finding_id: str) -> dict:
    row = await store.get_finding(finding_id)
    if row is None:
        return {"found": False, "finding_id": finding_id}
    return {"found": True, **row}


async def _query_artifacts_impl(store: StateStore, finding_id: str) -> dict:
    rows = await store.query_artifacts(finding_id)
    return {"finding_id": finding_id, "count": len(rows), "artifacts": rows}


async def _query_experience_kb_impl(
    store: StateStore,
    cwe: str,
    product: str | None,
    version: str | None,
    limit: int,
) -> dict:
    rows = await store.query_experience_kb(cwe, product, version, limit)
    return {
        "cwe": cwe,
        "product": product,
        "version": version,
        "count": len(rows),
        "matches": rows,
    }


async def _update_finding_status_impl(
    store: StateStore,
    finding_id: str,
    new_status: str,
    expected_current_status: str | None,
) -> dict:
    return await store.update_finding_status(
        finding_id, new_status, expected_current_status
    )


# ---------------------------------------------------------------------------
# MCP tools
# ---------------------------------------------------------------------------


@mcp.tool()
async def get_finding(finding_id: str) -> dict:
    """Read one ``findings`` row by UUID.

    Returns ``{found, ...columns}`` — ``found`` is False when no row exists.
    """
    store = await _get_store()
    return await _get_finding_impl(store, finding_id)


@mcp.tool()
async def query_artifacts(finding_id: str) -> dict:
    """List all evidence artifacts for a finding, oldest first.

    Returns ``{finding_id, count, artifacts}``. Each artifact carries
    ``content_hash``, ``r2_key``, and the ``oracle_data`` JSONB blob the
    validator persisted.
    """
    store = await _get_store()
    return await _query_artifacts_impl(store, finding_id)


@mcp.tool()
async def query_experience_kb(
    cwe: str,
    product: str | None = None,
    version: str | None = None,
    limit: int = 10,
) -> dict:
    """Look up prior validated exploits matching a CWE / tech-triple.

    Used by exploit-agent (build-plan §2.3.6 chain detection) to reuse a
    known-good PoC template before generating one. Restricts to terminal
    statuses ``validated`` / ``confirmed`` / ``submitted``; rejected
    chains are excluded.

    Args:
        cwe: Canonical CWE-ID (``CWE-79``). Use normalize-mcp first if
            the upstream value is a slug.
        product: Optional product name substring (e.g. ``wordpress``).
        version: Optional version substring; ignored unless ``product``
            is also set.
        limit: Max rows returned (default 10).
    """
    store = await _get_store()
    return await _query_experience_kb_impl(store, cwe, product, version, limit)


@mcp.tool()
async def update_finding_status(
    finding_id: str,
    new_status: str,
    expected_current_status: str | None = None,
) -> dict:
    """Transition a finding's ``status`` column.

    When ``expected_current_status`` is supplied, the UPDATE acts as an
    optimistic lock: returns ``updated=False`` if some other agent
    already changed the row. Used by validator-agent's claim step.

    Args:
        finding_id: UUID string of the findings row.
        new_status: Target status; must be a value of the
            ``finding_status`` enum.
        expected_current_status: Optional pre-condition.

    Returns:
        ``{updated, finding_id, status}``.
    """
    store = await _get_store()
    return await _update_finding_status_impl(
        store, finding_id, new_status, expected_current_status
    )


def main() -> None:
    """Run the state-mcp FastMCP server (stdio transport)."""
    mcp.run()


if __name__ == "__main__":
    main()
