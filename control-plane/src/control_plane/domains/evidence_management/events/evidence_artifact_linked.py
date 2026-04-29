from __future__ import annotations

from control_plane.core.shared import DomainEvent


class EvidenceArtifactLinked(DomainEvent):
    """Emitted when an EvidenceArtifact is attached to a finding."""

    finding_id: str
    artifact_id: str


__all__ = ["EvidenceArtifactLinked"]
