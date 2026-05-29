# SPDX-License-Identifier: AGPL-3.0-or-later

from __future__ import annotations

from control_plane.core.shared import DomainEvent


class EvidenceArtifactCreated(DomainEvent):
    """Emitted when a new EvidenceArtifact is created."""

    finding_id: str
    platform: str
    program_handle: str
    content_hash_hex: str
    r2_key: str


__all__ = ["EvidenceArtifactCreated"]
