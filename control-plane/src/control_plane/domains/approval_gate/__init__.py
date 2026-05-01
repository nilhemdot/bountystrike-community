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
from .finding_status_cache import (
    FindingStatusCache,
    InMemoryFindingStatusCache,
    RedisFindingStatusCache,
)
from .queue import (
    ApprovalQueueError,
    QueueEntry,
    approve as queue_approve,
    enqueue as queue_enqueue,
    get as queue_get,
    list_pending as queue_list_pending,
    reject as queue_reject,
    wait_for_approval as queue_wait_for_approval,
)
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
    "ApprovalQueueError",
    "ApprovalRequest",
    "ApprovalRequestStatus",
    "ApprovalRequestStore",
    "ApprovalTier",
    "DuplicateApprovalError",
    "FindingStatusCache",
    "InMemoryApprovalRequestStore",
    "InMemoryFindingStatusCache",
    "NotApprovableError",
    "QueueEntry",
    "RedisFindingStatusCache",
    "classify_tier",
    "queue_approve",
    "queue_enqueue",
    "queue_get",
    "queue_list_pending",
    "queue_reject",
    "queue_wait_for_approval",
]
