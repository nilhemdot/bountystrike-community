"""FastMCP server for evidence artifact storage and hash-chained audit logs.

Exposes four MCP tools:
  - put_artifact      — store a finding artifact and return its content key
  - get_artifact      — retrieve an artifact by R2 key
  - append_audit_entry — append a hash-chained audit log entry for a finding
  - get_audit_chain   — retrieve the complete audit chain for a finding

Transport: stdio (default FastMCP transport).
Entry point: ``evidence-mcp`` CLI script (see pyproject.toml).
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import os
import uuid
from datetime import UTC, datetime
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from evidence_mcp.store import AuditStore, BlobStore

# ---------------------------------------------------------------------------
# Environment config — read once at import time
# ---------------------------------------------------------------------------

EVIDENCE_ROOT = Path(os.environ.get("EVIDENCE_ROOT", "/tmp/evidence-mcp/blobs"))
EVIDENCE_DB = Path(os.environ.get("EVIDENCE_DB", "/tmp/evidence-mcp/audit.db"))

# ---------------------------------------------------------------------------
# Shared state
# ---------------------------------------------------------------------------

blob_store = BlobStore(EVIDENCE_ROOT)
audit_store = AuditStore(EVIDENCE_DB)

_initialized = False
_init_lock = asyncio.Lock()

# Per-finding append serialization. SQLite has no advisory locks and our
# AuditStore methods open fresh connections per call, so the read-prev/
# write-new pair is non-atomic across separate calls. Without this lock,
# two concurrent append_audit_entry callers for the same finding_id would
# each read the same prev_hash and fork the chain. In-process scope is
# sufficient — evidence-mcp is a single-process stdio server. Multi-process
# deployments must use control-plane HashChainService (Postgres advisory
# lock) instead.
_finding_locks: dict[str, asyncio.Lock] = {}
_finding_locks_mutex = asyncio.Lock()


async def _get_finding_lock(finding_id: str) -> asyncio.Lock:
    """Return the per-finding append lock, creating it on first use."""
    async with _finding_locks_mutex:
        lock = _finding_locks.get(finding_id)
        if lock is None:
            lock = asyncio.Lock()
            _finding_locks[finding_id] = lock
        return lock


async def _ensure_initialized() -> None:
    """Initialize AuditStore exactly once, even under concurrent callers."""
    global _initialized
    if _initialized:
        return
    async with _init_lock:
        if not _initialized:
            await audit_store.initialize()
            _initialized = True


# ---------------------------------------------------------------------------
# Inline domain helpers (self-contained; no imports from control-plane)
# ---------------------------------------------------------------------------


def _content_hash_hex(raw_bytes: bytes) -> str:
    return hashlib.sha256(raw_bytes).hexdigest()


def _r2_key(platform: str, program_handle: str, finding_id: str, sha256_hex: str) -> str:
    return f"{platform}/{program_handle}/{finding_id}/{sha256_hex}"


def _chain_hash(prev_hash: bytes, payload: dict) -> bytes:
    payload_bytes = json.dumps(payload, sort_keys=True, default=str).encode()
    return hashlib.sha256(prev_hash + payload_bytes).digest()


def _validate_key_component(value: str, field_name: str) -> None:
    """Reject components that contain '..' or '/' — they are unsafe in r2 keys."""
    if ".." in value or "/" in value:
        raise ValueError(f"Invalid {field_name}: contains unsafe characters: {value!r}")


# ---------------------------------------------------------------------------
# FastMCP server
# ---------------------------------------------------------------------------

mcp = FastMCP("evidence-mcp")


@mcp.tool()
async def put_artifact(
    finding_id: str,
    platform: str,
    program_handle: str,
    raw_bytes_b64: str,
    oracle_verdict: str,
    oracle_method: str,
) -> dict:
    """Store a finding artifact and return its content-addressed key.

    The artifact is stored under a SHA-256-derived key so identical bytes
    written twice produce the same key (idempotent).

    Args:
        finding_id: UUID string identifying the finding.
        platform: Bug bounty platform name (e.g. "hackerone").
        program_handle: Platform program handle (e.g. "acme-corp").
        raw_bytes_b64: Base64-encoded artifact bytes.
        oracle_verdict: Oracle verdict string (e.g. "validated").
        oracle_method: Oracle method used (e.g. "sqli_timing_welch").

    Returns:
        dict with keys ``artifact_id``, ``r2_key``, ``content_hash_hex``;
        or ``{"error": "invalid_r2_key"}`` if any component is unsafe.
    """
    await _ensure_initialized()

    # Validate components before building the key.
    try:
        _validate_key_component(platform, "platform")
        _validate_key_component(program_handle, "program_handle")
        _validate_key_component(finding_id, "finding_id")
    except ValueError:
        return {"error": "invalid_r2_key"}

    raw_bytes = base64.b64decode(raw_bytes_b64)
    sha256_hex = _content_hash_hex(raw_bytes)
    key = _r2_key(platform, program_handle, finding_id, sha256_hex)

    await blob_store.put(key, raw_bytes)

    artifact_id = str(uuid.uuid4())
    return {
        "artifact_id": artifact_id,
        "r2_key": key,
        "content_hash_hex": sha256_hex,
    }


@mcp.tool()
async def get_artifact(r2_key: str) -> dict:
    """Retrieve an artifact by its R2 key.

    Args:
        r2_key: The content-addressed key returned by ``put_artifact``.

    Returns:
        dict with keys ``r2_key`` and ``raw_bytes_b64`` on success;
        or ``{"error": "not_found"}`` if the artifact does not exist;
        or ``{"error": "invalid_r2_key"}`` if the key contains unsafe components.
    """
    await _ensure_initialized()

    # Validate each segment of the r2_key.
    segments = r2_key.split("/")
    for segment in segments:
        if not segment or segment == "..":
            return {"error": "invalid_r2_key"}

    data = await blob_store.get(r2_key)
    if data is None:
        return {"error": "not_found"}

    return {
        "r2_key": r2_key,
        "raw_bytes_b64": base64.b64encode(data).decode(),
    }


@mcp.tool()
async def append_audit_entry(
    finding_id: str,
    entry_type: str,
    payload: dict,
) -> dict:
    """Append a hash-chained audit log entry for a finding.

    Each entry's chain_hash is sha256(prev_chain_hash || payload_json_bytes)
    where payload_json_bytes = json.dumps(payload, sort_keys=True, default=str).encode().
    The genesis entry uses prev_hash = b''.

    Args:
        finding_id: UUID string identifying the finding.
        entry_type: Category label for this entry (e.g. "oracle_result").
        payload: Free-form JSON-serialisable dict containing entry details.

    Returns:
        dict with keys ``entry_id``, ``finding_id``, ``entry_type``,
        ``chain_hash_hex``, and ``created_at``.
    """
    await _ensure_initialized()

    lock = await _get_finding_lock(finding_id)
    async with lock:
        prev_hash = await audit_store.get_latest_chain_hash(finding_id)
        chain_hash_bytes = _chain_hash(prev_hash, payload)
        payload_json = json.dumps(payload, sort_keys=True, default=str)
        entry_id = str(uuid.uuid4())
        created_at = datetime.now(UTC).isoformat()

        await audit_store.append(
            id=entry_id,
            finding_id=finding_id,
            entry_type=entry_type,
            payload=payload_json,
            prev_hash=prev_hash,
            chain_hash=chain_hash_bytes,
            created_at=created_at,
        )

    return {
        "entry_id": entry_id,
        "finding_id": finding_id,
        "entry_type": entry_type,
        "chain_hash_hex": chain_hash_bytes.hex(),
        "created_at": created_at,
    }


@mcp.tool()
async def get_audit_chain(finding_id: str) -> dict:
    """Retrieve the complete hash-chained audit log for a finding.

    Args:
        finding_id: UUID string identifying the finding.

    Returns:
        dict with keys ``finding_id`` and ``entries`` (list of entry dicts,
        each containing ``entry_id``, ``entry_type``, ``payload``,
        ``chain_hash_hex``, ``created_at``).
    """
    await _ensure_initialized()

    raw_entries = await audit_store.get_chain(finding_id)
    entries = [
        {
            "entry_id": e["id"],
            "entry_type": e["entry_type"],
            "payload": e["payload_json"],
            "chain_hash_hex": e["chain_hash_hex"],
            "created_at": e["created_at"],
        }
        for e in raw_entries
    ]
    return {"finding_id": finding_id, "entries": entries}


def main() -> None:
    """Run the evidence-mcp FastMCP server (stdio transport)."""
    mcp.run()


if __name__ == "__main__":
    main()
