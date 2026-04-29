"""Approval gate bounded context — build-plan §6.3 evidence tiers.

Computes the approval tier (T0-T3) for a validated finding from its
context (CVSS, similarity, bug class, oracle verdict, exploit chain
shape) and tracks the resulting :class:`ApprovalRequest` through the
state machine ``pending → approved | rejected | expired``.

Public surface:

* :class:`ApprovalTier` — enum (T0, T1, T2, T3).
* :class:`ApprovalContext` — input bundle for classification.
* :func:`classify_tier` — pure function ``context → tier``.
* :class:`ApprovalRequest` — aggregate root with the approvals list.
* :class:`ApprovalRequestStore` — Protocol; InMemory impl ships.
* :class:`ApprovalGateService` — operator-facing verbs.
"""

from __future__ import annotations

from .aggregates import ApprovalRequest, ApprovalRequestStatus
from .repositories import ApprovalRequestStore, InMemoryApprovalRequestStore
from .services import (
    ApprovalGateService,
    DuplicateApprovalError,
    NotApprovableError,
    classify_tier,
)
from .value_objects import (
    ApprovalContext,
    ApprovalDecision,
    ApprovalTier,
)

__all__ = [
    "ApprovalContext",
    "ApprovalDecision",
    "ApprovalGateService",
    "ApprovalRequest",
    "ApprovalRequestStatus",
    "ApprovalRequestStore",
    "ApprovalTier",
    "DuplicateApprovalError",
    "InMemoryApprovalRequestStore",
    "NotApprovableError",
    "classify_tier",
]
