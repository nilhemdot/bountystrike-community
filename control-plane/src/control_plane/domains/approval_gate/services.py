"""Services for the approval-gate bounded context.

The :func:`classify_tier` function is the canonical mapping from a
:class:`ApprovalContext` to the required :class:`ApprovalTier`.
:class:`ApprovalGateService` wraps the request lifecycle (create →
record approvals/rejections → resolve).
"""

from __future__ import annotations

import time
import uuid

import structlog

from .aggregates import ApprovalRequest, ApprovalRequestStatus
from .finding_status_cache import FindingStatusCache
from .repositories import ApprovalRequestStore
from .value_objects import (
    CREDENTIAL_THEFT_BUG_CLASSES,
    PII_BUG_CLASSES,
    SMART_CONTRACT_CRITICAL_BUG_CLASSES,
    ApprovalContext,
    ApprovalDecision,
    ApprovalTier,
)

log = structlog.get_logger("approval_gate")


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class NotApprovableError(Exception):
    """Raised when an approval/rejection is attempted on a non-pending request."""


class DuplicateApprovalError(Exception):
    """Raised when the same actor tries to vote twice on the same request.

    Per build-plan §6.3: T3 requires *distinct* actors. The same operator
    voting twice is an audit-log integrity violation, not progress.
    """


# ---------------------------------------------------------------------------
# Tier classification (pure function — no I/O)
# ---------------------------------------------------------------------------


def classify_tier(context: ApprovalContext) -> ApprovalTier:
    """Map a finding's context to its build-plan §6.3 tier.

    Evaluated top-down — first matching tier wins. Strictly conservative:
    when in doubt, escalate to the higher tier.
    """
    # ----------- T3 — two-person review (highest scrutiny) -------------
    if context.cvss >= 9.5:
        return ApprovalTier.T3
    if context.hop_count >= 3:
        return ApprovalTier.T3
    if context.bug_class in CREDENTIAL_THEFT_BUG_CLASSES:
        return ApprovalTier.T3
    if context.platform.lower() == "immunefi" and context.bug_class in SMART_CONTRACT_CRITICAL_BUG_CLASSES:
        return ApprovalTier.T3
    if context.bug_class in PII_BUG_CLASSES and context.pii_record_count > 10:
        return ApprovalTier.T3

    # ----------- T2 — single operator review --------------------------
    if context.cvss >= 9.0:
        return ApprovalTier.T2
    if context.sandbox_execution:
        return ApprovalTier.T2
    if context.oracle_verdict == "flaky":
        return ApprovalTier.T2
    if "first_of_class" in context.tags:
        return ApprovalTier.T2

    # ----------- T1 — coordinator (LLM) review ------------------------
    if 7.0 <= context.cvss < 9.0:
        return ApprovalTier.T1
    if 0.75 <= context.similarity < 0.85:
        return ApprovalTier.T1

    # ----------- T0 — auto-advance ------------------------------------
    if (
        context.oracle_verdict == "validated"
        and context.evidence_hash_present
        and context.similarity < 0.85
        and context.cvss >= 4.0
    ):
        return ApprovalTier.T0

    # Doesn't meet T0 entry — escalate to T1 by default. The build-plan
    # phrasing assumes every validated finding lands in some tier; the
    # safest bucket for an under-confident validated finding is the
    # coordinator review.
    return ApprovalTier.T1


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class ApprovalGateService:
    """Operator-facing API for the approval lifecycle.

    Args:
        store: Durable record of the approval requests.
        status_cache: Optional fast cache keyed by ``finding_id`` so the
            PreToolUse hook (a separate process) can answer
            "is this finding cleared for submission?" in <1ms. Service
            writes the cache on every state transition; hook reads only.
    """

    def __init__(
        self,
        store: ApprovalRequestStore,
        status_cache: FindingStatusCache | None = None,
    ) -> None:
        self._store = store
        self._cache = status_cache

    async def _publish_status(
        self,
        finding_id: uuid.UUID,
        status: ApprovalRequestStatus,
    ) -> None:
        """Best-effort cache update — never fail the request on cache errors."""
        if self._cache is None:
            return
        try:
            await self._cache.set_status(finding_id, status)
        except Exception as exc:  # noqa: BLE001 — cache is opportunistic
            log.warning(
                "approval.cache.publish_failed",
                finding_id=str(finding_id),
                status=status.value,
                error=str(exc),
            )

    async def open_request(
        self,
        finding_id: uuid.UUID,
        context: ApprovalContext,
    ) -> ApprovalRequest:
        """Classify and persist a pending :class:`ApprovalRequest`.

        T0 requests are persisted with status APPROVED immediately —
        the build-plan §6.3 design says T0 auto-advances; the record is
        kept for the audit log.
        """
        tier = classify_tier(context)
        request = ApprovalRequest.create(finding_id=finding_id, tier=tier)
        if tier == ApprovalTier.T0:
            request.status = ApprovalRequestStatus.APPROVED
        await self._store.save(request)
        await self._publish_status(finding_id, request.status)
        log.info(
            "approval.opened",
            request_id=str(request.id),
            finding_id=str(finding_id),
            tier=tier.value,
            cvss=context.cvss,
            similarity=context.similarity,
            verdict=context.oracle_verdict,
        )
        return request

    async def record_decision(
        self,
        request_id: uuid.UUID,
        actor: str,
        approved: bool,
        reason: str,
    ) -> ApprovalRequest:
        """Record one operator's decision on a pending request.

        Promotes the request to ``APPROVED`` once distinct-actor
        approvals reach the tier requirement, or to ``REJECTED`` on the
        first rejection (a single rejection blocks the request — the
        build-plan §6.3 design treats rejection as a hard veto).
        """
        if not actor or not actor.strip():
            raise ValueError("actor must be non-empty")
        if not reason or not reason.strip():
            raise ValueError("reason must be non-empty")

        request = await self._store.get(request_id)
        if request is None:
            raise NotApprovableError(f"approval request {request_id} not found")

        # Drift the status to EXPIRED if the SLA elapsed before any
        # operator decision — saves a separate sweeper job for the
        # common path.
        now = time.time()
        if (
            request.status == ApprovalRequestStatus.PENDING
            and request.is_expired(now)
        ):
            request.status = ApprovalRequestStatus.EXPIRED
            await self._store.save(request)

        if request.status != ApprovalRequestStatus.PENDING:
            raise NotApprovableError(
                f"approval request {request_id} is {request.status.value}; "
                f"only PENDING requests accept decisions"
            )

        if any(d.actor == actor for d in request.decisions):
            raise DuplicateApprovalError(
                f"actor {actor!r} already voted on request {request_id}"
            )

        request.decisions.append(
            ApprovalDecision(
                actor=actor,
                approved=approved,
                reason=reason,
                timestamp=now,
            )
        )

        if not approved:
            request.status = ApprovalRequestStatus.REJECTED
            log.warning(
                "approval.rejected",
                request_id=str(request.id),
                actor=actor,
                reason=reason,
            )
        elif len(request.approvals) >= request.tier.required_approvals:
            request.status = ApprovalRequestStatus.APPROVED
            log.info(
                "approval.granted",
                request_id=str(request.id),
                tier=request.tier.value,
                approvals=len(request.approvals),
            )
        else:
            log.info(
                "approval.pending",
                request_id=str(request.id),
                tier=request.tier.value,
                approvals=len(request.approvals),
                required=request.tier.required_approvals,
            )

        await self._store.save(request)
        await self._publish_status(request.finding_id, request.status)
        return request

    async def is_approved(self, request_id: uuid.UUID) -> bool:
        """Cheap read for the submission hook."""
        request = await self._store.get(request_id)
        return (
            request is not None
            and request.status == ApprovalRequestStatus.APPROVED
        )


__all__ = [
    "ApprovalGateService",
    "DuplicateApprovalError",
    "NotApprovableError",
    "classify_tier",
]
