from __future__ import annotations

from control_plane.core.shared import DomainEvent


class AuditEntryRecorded(DomainEvent):
    """Emitted when a new AuditLogEntry is appended to the chain."""

    finding_id: str
    entry_type: str
    chain_hash_hex: str


__all__ = ["AuditEntryRecorded"]
