# SPDX-License-Identifier: AGPL-3.0-or-later

"""Aggregates for the approval-gate bounded context."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import StrEnum

from .value_objects import ApprovalDecision, ApprovalTier


class ApprovalRequestStatus(StrEnum):
    """Lifecycle state of an :class:`ApprovalRequest`."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"


@dataclass(slots=True)
class ApprovalRequest:
    """Aggregate root — the audit-bearing record of one tier review.

    Mutability: the aggregate is mutated only by :class:`ApprovalGateService`.
    Direct edits to ``decisions`` / ``status`` outside the service bypass
    the audit-log invariants enforced there.
    """

    id: uuid.UUID
    finding_id: uuid.UUID
    tier: ApprovalTier
    status: ApprovalRequestStatus
    created_at: float
    expires_at: float
    decisions: list[ApprovalDecision] = field(default_factory=list)

    @classmethod
    def create(
        cls,
        finding_id: uuid.UUID,
        tier: ApprovalTier,
        now: float | None = None,
    ) -> ApprovalRequest:
        """Factory — sets ``created_at`` and ``expires_at`` from the tier SLA."""
        t = now if now is not None else time.time()
        return cls(
            id=uuid.uuid4(),
            finding_id=finding_id,
            tier=tier,
            status=ApprovalRequestStatus.PENDING,
            created_at=t,
            expires_at=t + tier.review_sla_seconds,
        )

    @property
    def approvals(self) -> list[ApprovalDecision]:
        return [d for d in self.decisions if d.approved]

    @property
    def rejections(self) -> list[ApprovalDecision]:
        return [d for d in self.decisions if not d.approved]

    def is_expired(self, now: float | None = None) -> bool:
        return (now if now is not None else time.time()) >= self.expires_at


__all__ = ["ApprovalRequest", "ApprovalRequestStatus"]
