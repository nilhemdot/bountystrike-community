# SPDX-License-Identifier: AGPL-3.0-or-later

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from control_plane.core.shared import AggregateRoot
from control_plane.domains.evidence_management.events import EvidenceArtifactCreated
from control_plane.domains.evidence_management.value_objects import (
    ContentHash,
    OracleData,
    R2Key,
)


class EvidenceArtifact(AggregateRoot[uuid.UUID]):
    """Content-addressable finding evidence."""

    def __init__(
        self,
        artifact_id: uuid.UUID,
        finding_id: uuid.UUID,
        platform: str,
        program_handle: str,
        content_hash: ContentHash,
        oracle_data: OracleData,
        r2_key: R2Key,
        created_at: datetime,
    ) -> None:
        super().__init__(artifact_id)
        self.finding_id = finding_id
        self.platform = platform
        self.program_handle = program_handle
        self.content_hash = content_hash
        self.oracle_data = oracle_data
        self.r2_key = r2_key
        self.created_at = created_at

    @classmethod
    def create(
        cls,
        finding_id: uuid.UUID,
        platform: str,
        program_handle: str,
        raw_bytes: bytes,
        oracle_data: OracleData,
    ) -> EvidenceArtifact:
        """Factory — computes hashes, builds R2 key, records creation event."""
        artifact_id = uuid.uuid4()
        content_hash = ContentHash.from_bytes(raw_bytes)
        r2_key = R2Key.compute(platform, program_handle, finding_id, content_hash)
        created_at = datetime.now(UTC)

        artifact = cls(
            artifact_id=artifact_id,
            finding_id=finding_id,
            platform=platform,
            program_handle=program_handle,
            content_hash=content_hash,
            oracle_data=oracle_data,
            r2_key=r2_key,
            created_at=created_at,
        )
        artifact._record_event(
            EvidenceArtifactCreated(
                aggregate_id=str(artifact_id),
                finding_id=str(finding_id),
                platform=platform,
                program_handle=program_handle,
                content_hash_hex=content_hash.hex,
                r2_key=r2_key.key,
            )
        )
        return artifact


__all__ = ["EvidenceArtifact"]
