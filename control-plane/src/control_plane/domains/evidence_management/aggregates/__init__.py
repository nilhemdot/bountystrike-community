# SPDX-License-Identifier: AGPL-3.0-or-later

"""Aggregates for the evidence_management bounded context."""

from __future__ import annotations

from .audit_log_entry import AuditLogEntry
from .evidence_artifact import EvidenceArtifact

__all__ = ["AuditLogEntry", "EvidenceArtifact"]
