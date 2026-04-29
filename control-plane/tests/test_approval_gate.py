"""Tests for the approval-gate bounded context."""

from __future__ import annotations

import time
import uuid

import pytest

from control_plane.domains.approval_gate import (
    ApprovalContext,
    ApprovalGateService,
    ApprovalRequest,
    ApprovalRequestStatus,
    ApprovalRequestStore,
    ApprovalTier,
    DuplicateApprovalError,
    InMemoryApprovalRequestStore,
    NotApprovableError,
    classify_tier,
)


def _ctx(**overrides) -> ApprovalContext:
    base = dict(
        cvss=5.0,
        similarity=0.10,
        bug_class="xss",
        oracle_verdict="validated",
        evidence_hash_present=True,
        sandbox_execution=False,
        hop_count=1,
        pii_record_count=0,
        platform="hackerone",
        tags=frozenset(),
    )
    base.update(overrides)
    return ApprovalContext(**base)


# ---------------------------------------------------------------------------
# 1. ApprovalTier — required-approvals + SLA
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "tier,n",
    [
        (ApprovalTier.T0, 0),
        (ApprovalTier.T1, 1),
        (ApprovalTier.T2, 1),
        (ApprovalTier.T3, 2),
    ],
)
def test_tier_required_approvals(tier: ApprovalTier, n: int):
    assert tier.required_approvals == n


def test_tier_review_sla_increases_with_severity():
    assert ApprovalTier.T0.review_sla_seconds == 0
    assert ApprovalTier.T1.review_sla_seconds < ApprovalTier.T2.review_sla_seconds
    assert ApprovalTier.T2.review_sla_seconds < ApprovalTier.T3.review_sla_seconds


# ---------------------------------------------------------------------------
# 2. classify_tier — top-down precedence per build-plan §6.3
# ---------------------------------------------------------------------------


def test_classify_t0_typical_validated_finding():
    assert classify_tier(_ctx(cvss=5.5, similarity=0.10)) == ApprovalTier.T0


def test_classify_t0_requires_evidence_hash():
    assert classify_tier(_ctx(evidence_hash_present=False)) == ApprovalTier.T1


def test_classify_t0_requires_validated_verdict():
    assert classify_tier(_ctx(oracle_verdict="unreproducible")) == ApprovalTier.T1


def test_classify_t1_high_severity_band():
    assert classify_tier(_ctx(cvss=7.5)) == ApprovalTier.T1
    assert classify_tier(_ctx(cvss=8.9)) == ApprovalTier.T1


def test_classify_t1_borderline_similarity():
    assert classify_tier(_ctx(cvss=5.0, similarity=0.80)) == ApprovalTier.T1
    assert classify_tier(_ctx(cvss=5.0, similarity=0.84)) == ApprovalTier.T1


def test_classify_t2_critical_cvss():
    assert classify_tier(_ctx(cvss=9.0)) == ApprovalTier.T2
    assert classify_tier(_ctx(cvss=9.4)) == ApprovalTier.T2


def test_classify_t2_sandbox_execution():
    assert classify_tier(_ctx(cvss=5.0, sandbox_execution=True)) == ApprovalTier.T2


def test_classify_t2_flaky_oracle_verdict():
    assert classify_tier(_ctx(cvss=5.0, oracle_verdict="flaky")) == ApprovalTier.T2


def test_classify_t2_first_of_class_tag():
    assert (
        classify_tier(_ctx(cvss=5.0, tags=frozenset({"first_of_class"})))
        == ApprovalTier.T2
    )


def test_classify_t3_severity_threshold():
    assert classify_tier(_ctx(cvss=9.5)) == ApprovalTier.T3
    assert classify_tier(_ctx(cvss=10.0)) == ApprovalTier.T3


def test_classify_t3_novel_chain():
    assert classify_tier(_ctx(hop_count=3)) == ApprovalTier.T3
    assert classify_tier(_ctx(hop_count=5)) == ApprovalTier.T3


def test_classify_t3_credential_theft_class():
    assert classify_tier(_ctx(bug_class="credential-theft")) == ApprovalTier.T3
    assert classify_tier(_ctx(bug_class="account-takeover")) == ApprovalTier.T3


def test_classify_t3_immunefi_smart_contract_critical():
    assert (
        classify_tier(_ctx(platform="immunefi", bug_class="smart-contract-critical"))
        == ApprovalTier.T3
    )


def test_classify_t3_pii_threshold():
    assert (
        classify_tier(_ctx(bug_class="pii-exposure", pii_record_count=11))
        == ApprovalTier.T3
    )
    # 10 or fewer rows is NOT T3 (boundary check).
    assert (
        classify_tier(_ctx(bug_class="pii-exposure", pii_record_count=10))
        != ApprovalTier.T3
    )


def test_classify_smart_contract_outside_immunefi_does_not_trigger_t3():
    """A 'smart-contract-critical' on H1 doesn't auto-T3 — programs vary."""
    assert (
        classify_tier(_ctx(platform="hackerone", bug_class="smart-contract-critical"))
        != ApprovalTier.T3
    )


# ---------------------------------------------------------------------------
# 3. ApprovalRequest aggregate
# ---------------------------------------------------------------------------


def test_request_create_sets_expiry_from_tier_sla():
    req = ApprovalRequest.create(uuid.uuid4(), ApprovalTier.T2, now=1000.0)
    assert req.status == ApprovalRequestStatus.PENDING
    assert req.expires_at == 1000.0 + ApprovalTier.T2.review_sla_seconds


def test_request_is_expired_boundary():
    req = ApprovalRequest.create(uuid.uuid4(), ApprovalTier.T1, now=1000.0)
    deadline = 1000.0 + ApprovalTier.T1.review_sla_seconds
    assert req.is_expired(now=deadline - 0.001) is False
    assert req.is_expired(now=deadline) is True


# ---------------------------------------------------------------------------
# 4. InMemory store
# ---------------------------------------------------------------------------


async def test_store_save_and_get_roundtrip():
    store = InMemoryApprovalRequestStore()
    req = ApprovalRequest.create(uuid.uuid4(), ApprovalTier.T2)
    await store.save(req)
    fetched = await store.get(req.id)
    assert fetched is req


async def test_store_get_missing_returns_none():
    store = InMemoryApprovalRequestStore()
    assert await store.get(uuid.uuid4()) is None


async def test_store_list_pending_for_finding():
    store = InMemoryApprovalRequestStore()
    fid = uuid.uuid4()
    other = uuid.uuid4()
    a = ApprovalRequest.create(fid, ApprovalTier.T2)
    b = ApprovalRequest.create(other, ApprovalTier.T1)
    c = ApprovalRequest.create(fid, ApprovalTier.T3)
    c.status = ApprovalRequestStatus.APPROVED  # not pending — must be filtered
    for r in (a, b, c):
        await store.save(r)
    pending = await store.list_pending_for_finding(fid)
    assert pending == [a]


def test_in_memory_store_satisfies_protocol():
    assert isinstance(InMemoryApprovalRequestStore(), ApprovalRequestStore)


# ---------------------------------------------------------------------------
# 5. Service — happy paths
# ---------------------------------------------------------------------------


async def test_service_opens_request_and_classifies():
    service = ApprovalGateService(InMemoryApprovalRequestStore())
    req = await service.open_request(uuid.uuid4(), _ctx(cvss=9.6))
    assert req.tier == ApprovalTier.T3
    assert req.status == ApprovalRequestStatus.PENDING


async def test_service_t0_request_is_auto_approved_on_open():
    service = ApprovalGateService(InMemoryApprovalRequestStore())
    req = await service.open_request(uuid.uuid4(), _ctx(cvss=4.0))
    assert req.tier == ApprovalTier.T0
    assert req.status == ApprovalRequestStatus.APPROVED


async def test_service_t2_single_approval_clears():
    service = ApprovalGateService(InMemoryApprovalRequestStore())
    req = await service.open_request(uuid.uuid4(), _ctx(cvss=9.0))
    assert req.tier == ApprovalTier.T2

    final = await service.record_decision(
        req.id, actor="operator:alice", approved=True, reason="lgtm"
    )
    assert final.status == ApprovalRequestStatus.APPROVED


async def test_service_t3_requires_two_distinct_approvals():
    service = ApprovalGateService(InMemoryApprovalRequestStore())
    req = await service.open_request(uuid.uuid4(), _ctx(cvss=9.6))
    assert req.tier == ApprovalTier.T3

    after_first = await service.record_decision(
        req.id, actor="operator:alice", approved=True, reason="r1"
    )
    assert after_first.status == ApprovalRequestStatus.PENDING
    assert len(after_first.approvals) == 1

    after_second = await service.record_decision(
        req.id, actor="operator:bob", approved=True, reason="r2"
    )
    assert after_second.status == ApprovalRequestStatus.APPROVED


async def test_service_t3_same_actor_twice_raises_duplicate():
    service = ApprovalGateService(InMemoryApprovalRequestStore())
    req = await service.open_request(uuid.uuid4(), _ctx(cvss=9.6))

    await service.record_decision(
        req.id, actor="operator:alice", approved=True, reason="r1"
    )
    with pytest.raises(DuplicateApprovalError):
        await service.record_decision(
            req.id, actor="operator:alice", approved=True, reason="again"
        )


# ---------------------------------------------------------------------------
# 6. Service — rejection veto + expiry + invariants
# ---------------------------------------------------------------------------


async def test_service_single_rejection_blocks_request():
    service = ApprovalGateService(InMemoryApprovalRequestStore())
    req = await service.open_request(uuid.uuid4(), _ctx(cvss=9.6))

    final = await service.record_decision(
        req.id, actor="operator:alice", approved=False, reason="out of scope"
    )
    assert final.status == ApprovalRequestStatus.REJECTED


async def test_service_decision_on_expired_request_raises(monkeypatch):
    store = InMemoryApprovalRequestStore()
    service = ApprovalGateService(store)
    req = await service.open_request(uuid.uuid4(), _ctx(cvss=9.0))

    # Skip past the SLA. record_decision uses time.time(); patch it.
    fake_now = req.expires_at + 1.0
    monkeypatch.setattr(time, "time", lambda: fake_now)

    with pytest.raises(NotApprovableError, match="expired"):
        await service.record_decision(
            req.id, actor="operator:alice", approved=True, reason="too late"
        )

    persisted = await store.get(req.id)
    assert persisted is not None
    assert persisted.status == ApprovalRequestStatus.EXPIRED


async def test_service_decision_on_already_approved_raises():
    service = ApprovalGateService(InMemoryApprovalRequestStore())
    req = await service.open_request(uuid.uuid4(), _ctx(cvss=9.0))
    await service.record_decision(req.id, "alice", True, "ok")

    with pytest.raises(NotApprovableError):
        await service.record_decision(req.id, "bob", True, "also ok")


async def test_service_decision_on_unknown_request_raises():
    service = ApprovalGateService(InMemoryApprovalRequestStore())
    with pytest.raises(NotApprovableError, match="not found"):
        await service.record_decision(uuid.uuid4(), "alice", True, "ok")


async def test_service_record_decision_requires_non_empty_actor():
    service = ApprovalGateService(InMemoryApprovalRequestStore())
    req = await service.open_request(uuid.uuid4(), _ctx(cvss=9.0))
    with pytest.raises(ValueError, match="actor"):
        await service.record_decision(req.id, "", True, "ok")
    with pytest.raises(ValueError, match="actor"):
        await service.record_decision(req.id, "  ", True, "ok")


async def test_service_record_decision_requires_non_empty_reason():
    service = ApprovalGateService(InMemoryApprovalRequestStore())
    req = await service.open_request(uuid.uuid4(), _ctx(cvss=9.0))
    with pytest.raises(ValueError, match="reason"):
        await service.record_decision(req.id, "alice", True, "")


async def test_service_is_approved_returns_false_for_pending():
    service = ApprovalGateService(InMemoryApprovalRequestStore())
    req = await service.open_request(uuid.uuid4(), _ctx(cvss=9.6))
    assert await service.is_approved(req.id) is False


async def test_service_is_approved_returns_false_for_unknown():
    service = ApprovalGateService(InMemoryApprovalRequestStore())
    assert await service.is_approved(uuid.uuid4()) is False


async def test_service_is_approved_true_for_t0_immediately():
    service = ApprovalGateService(InMemoryApprovalRequestStore())
    req = await service.open_request(uuid.uuid4(), _ctx())
    # _ctx() is a typical T0 candidate
    assert req.tier == ApprovalTier.T0
    assert await service.is_approved(req.id) is True
