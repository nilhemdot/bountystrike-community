from __future__ import annotations

import uuid

from control_plane.domains.evidence_management.aggregates import AuditLogEntry


class HashChainService:
    """Stateless service — manages the hash chain for audit log entries."""

    async def get_latest_chain_hash(self, finding_id: uuid.UUID, conn) -> bytes:
        """Return prev_hash for the next audit entry. Returns b'' for genesis."""
        result = await conn.fetchval(
            "SELECT chain_hash FROM audit_log WHERE finding_id = $1 ORDER BY created_at DESC LIMIT 1",
            finding_id,
        )
        return result or b""

    async def append_entry(
        self,
        finding_id: uuid.UUID,
        entry_type: str,
        payload: dict,
        conn,
    ) -> AuditLogEntry:
        """Get latest hash, create entry, persist it, return the entry."""
        prev_hash = await self.get_latest_chain_hash(finding_id, conn)
        entry = AuditLogEntry.create(
            finding_id=finding_id,
            entry_type=entry_type,
            payload=payload,
            prev_hash=prev_hash,
        )
        await conn.execute(
            """
            INSERT INTO audit_log (id, finding_id, entry_type, payload, prev_hash, chain_hash, created_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            """,
            entry.id,
            entry.finding_id,
            entry.entry_type,
            entry.payload,  # production conn must register a JSONB codec or pre-serialize
            entry.prev_hash,
            entry.chain_hash,
            entry.created_at,
        )
        return entry


__all__ = ["HashChainService"]
