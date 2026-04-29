from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime

from control_plane.core.shared import AggregateRoot
from control_plane.domains.evidence_management.events import AuditEntryRecorded


class AuditLogEntry(AggregateRoot[uuid.UUID]):
    """Hash-chained audit record for a finding."""

    def __init__(
        self,
        entry_id: uuid.UUID,
        finding_id: uuid.UUID,
        entry_type: str,
        payload: dict,
        prev_hash: bytes,
        chain_hash: bytes,
        created_at: datetime,
    ) -> None:
        super().__init__(entry_id)
        self.finding_id = finding_id
        self.entry_type = entry_type
        self.payload = payload
        self.prev_hash = prev_hash
        self.chain_hash = chain_hash
        self.created_at = created_at

    @classmethod
    def create(
        cls,
        finding_id: uuid.UUID,
        entry_type: str,
        payload: dict,
        prev_hash: bytes,
    ) -> AuditLogEntry:
        """Factory — computes chain_hash = SHA-256(prev_hash || payload_bytes)."""
        entry_id = uuid.uuid4()
        payload_bytes = json.dumps(payload, sort_keys=True, default=str).encode()
        chain_hash = hashlib.sha256(prev_hash + payload_bytes).digest()
        created_at = datetime.now(UTC)

        entry = cls(
            entry_id=entry_id,
            finding_id=finding_id,
            entry_type=entry_type,
            payload=payload,
            prev_hash=prev_hash,
            chain_hash=chain_hash,
            created_at=created_at,
        )
        entry._record_event(
            AuditEntryRecorded(
                aggregate_id=str(entry_id),
                finding_id=str(finding_id),
                entry_type=entry_type,
                chain_hash_hex=chain_hash.hex(),
            )
        )
        return entry


__all__ = ["AuditLogEntry"]
