# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for the .claude/hooks/pretool_approval_gate.py PreToolUse hook
+ the FindingStatusCache integration in ApprovalGateService.
"""

from __future__ import annotations

import importlib.util
import time
import uuid
from dataclasses import replace
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

import pytest
from control_plane.domains.approval_gate import (
    ApprovalGateService,
    ApprovalRequestStatus,
    FindingStatusCache,
    InMemoryApprovalRequestStore,
    InMemoryFindingStatusCache,
    RedisFindingStatusCache,
)
from control_plane.domains.approval_gate.value_objects import (
    ApprovalContext,
    ApprovalTier,
)

_HOOK_PATH = (
    Path(__file__).resolve().parents[2]
    / ".claude" / "hooks" / "pretool_approval_gate.py"
)

_BASE_CTX = ApprovalContext(
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


def _ctx(**overrides: Any) -> ApprovalContext:
    return replace(_BASE_CTX, **overrides)


def _load_hook_module():
    spec = importlib.util.spec_from_file_location(
        "pretool_approval_gate", _HOOK_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def hook():
    return _load_hook_module()


# ---------------------------------------------------------------------------
# 1. InMemoryFindingStatusCache — TTL + clear semantics
# ---------------------------------------------------------------------------


async def test_in_memory_cache_set_get_roundtrip():
    cache = InMemoryFindingStatusCache()
    fid = uuid.uuid4()
    await cache.set_status(fid, ApprovalRequestStatus.APPROVED, ttl_seconds=300)
    assert await cache.get_status(fid) == ApprovalRequestStatus.APPROVED


async def test_in_memory_cache_get_unknown_returns_none():
    cache = InMemoryFindingStatusCache()
    assert await cache.get_status(uuid.uuid4()) is None


async def test_in_memory_cache_clear_removes_entry():
    cache = InMemoryFindingStatusCache()
    fid = uuid.uuid4()
    await cache.set_status(fid, ApprovalRequestStatus.APPROVED, ttl_seconds=300)
    await cache.clear(fid)
    assert await cache.get_status(fid) is None


async def test_in_memory_cache_rejects_non_positive_ttl():
    cache = InMemoryFindingStatusCache()
    with pytest.raises(ValueError, match="ttl_seconds"):
        await cache.set_status(uuid.uuid4(), ApprovalRequestStatus.APPROVED, 0)


async def test_in_memory_cache_expires_after_ttl(monkeypatch: pytest.MonkeyPatch):
    cache = InMemoryFindingStatusCache()
    fake_now = [0.0]
    monkeypatch.setattr(time, "monotonic", lambda: fake_now[0])

    fid = uuid.uuid4()
    await cache.set_status(fid, ApprovalRequestStatus.APPROVED, ttl_seconds=10)
    fake_now[0] = 9.999
    assert await cache.get_status(fid) == ApprovalRequestStatus.APPROVED
    fake_now[0] = 10.0
    assert await cache.get_status(fid) is None


def test_in_memory_satisfies_protocol():
    assert isinstance(InMemoryFindingStatusCache(), FindingStatusCache)


# ---------------------------------------------------------------------------
# 2. RedisFindingStatusCache — exercises against AsyncMock client
# ---------------------------------------------------------------------------


async def test_redis_cache_set_uses_set_with_ex():
    client = AsyncMock()
    cache = RedisFindingStatusCache(client, key_prefix="bs:approval:finding:")
    fid = uuid.UUID("00000000-0000-0000-0000-000000000001")
    await cache.set_status(fid, ApprovalRequestStatus.APPROVED, ttl_seconds=300)
    client.set.assert_awaited_once_with(
        f"bs:approval:finding:{fid}",
        "approved",
        ex=300,
    )


async def test_redis_cache_get_returns_none_for_missing():
    client = AsyncMock()
    client.get.return_value = None
    cache = RedisFindingStatusCache(client)
    assert await cache.get_status(uuid.uuid4()) is None


async def test_redis_cache_get_decodes_bytes_value():
    client = AsyncMock()
    client.get.return_value = b"approved"
    cache = RedisFindingStatusCache(client)
    assert await cache.get_status(uuid.uuid4()) == ApprovalRequestStatus.APPROVED


async def test_redis_cache_get_returns_none_for_garbage_value():
    client = AsyncMock()
    client.get.return_value = b"garbage_value_not_a_status"
    cache = RedisFindingStatusCache(client)
    assert await cache.get_status(uuid.uuid4()) is None


async def test_redis_cache_clear_calls_delete():
    client = AsyncMock()
    cache = RedisFindingStatusCache(client)
    fid = uuid.uuid4()
    await cache.clear(fid)
    client.delete.assert_awaited_once_with(f"bs:approval:finding:{fid}")


def test_redis_satisfies_protocol():
    assert isinstance(RedisFindingStatusCache(AsyncMock()), FindingStatusCache)


# ---------------------------------------------------------------------------
# 3. ApprovalGateService writes the cache on every state transition
# ---------------------------------------------------------------------------


async def test_service_publishes_t0_approval_on_open():
    cache = InMemoryFindingStatusCache()
    service = ApprovalGateService(InMemoryApprovalRequestStore(), cache)
    fid = uuid.uuid4()
    req = await service.open_request(fid, _ctx(cvss=5.0))
    assert req.tier == ApprovalTier.T0
    assert await cache.get_status(fid) == ApprovalRequestStatus.APPROVED


async def test_service_publishes_pending_on_open_for_higher_tier():
    cache = InMemoryFindingStatusCache()
    service = ApprovalGateService(InMemoryApprovalRequestStore(), cache)
    fid = uuid.uuid4()
    await service.open_request(fid, _ctx(cvss=9.0))   # T2
    assert await cache.get_status(fid) == ApprovalRequestStatus.PENDING


async def test_service_publishes_approved_after_clear():
    cache = InMemoryFindingStatusCache()
    service = ApprovalGateService(InMemoryApprovalRequestStore(), cache)
    fid = uuid.uuid4()
    req = await service.open_request(fid, _ctx(cvss=9.0))
    await service.record_decision(req.id, "operator:alice", True, "lgtm")
    assert await cache.get_status(fid) == ApprovalRequestStatus.APPROVED


async def test_service_publishes_rejected_on_veto():
    cache = InMemoryFindingStatusCache()
    service = ApprovalGateService(InMemoryApprovalRequestStore(), cache)
    fid = uuid.uuid4()
    req = await service.open_request(fid, _ctx(cvss=9.0))
    await service.record_decision(req.id, "operator:alice", False, "out of scope")
    assert await cache.get_status(fid) == ApprovalRequestStatus.REJECTED


async def test_service_works_without_cache():
    """Cache is optional — service must not fail when none is provided."""
    service = ApprovalGateService(InMemoryApprovalRequestStore())
    fid = uuid.uuid4()
    req = await service.open_request(fid, _ctx(cvss=9.0))
    await service.record_decision(req.id, "operator:alice", True, "ok")
    # No assertion — we're proving no exception is raised.


async def test_service_swallows_cache_publish_errors():
    """Cache failures must never break the durable write path."""

    class _Boom:
        async def set_status(self, *args, **kwargs):
            raise RuntimeError("cache down")

        async def get_status(self, finding_id):
            return None

        async def clear(self, finding_id):
            return None

    service = ApprovalGateService(InMemoryApprovalRequestStore(), _Boom())
    # Must not raise — durable store still wins.
    req = await service.open_request(uuid.uuid4(), _ctx(cvss=5.0))
    assert req.status == ApprovalRequestStatus.APPROVED


# ---------------------------------------------------------------------------
# 4. Hook decide() — decision matrix
# ---------------------------------------------------------------------------


def test_hook_non_submission_tool_is_noop(hook, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(hook, "_read_status", lambda _fid: ("approved", ""))
    out = hook.decide({
        "tool_name": "Bash",
        "arguments": {"command": "ls"},
    })
    assert out == {"decision": "allow"}


def test_hook_submission_tool_missing_finding_id_denied(hook, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(hook, "_read_status", lambda _fid: ("approved", ""))
    out = hook.decide({
        "tool_name": "mcp__h1__submit_report",
        "arguments": {},
    })
    assert out["decision"] == "deny"
    assert "finding_id" in out["reason"]


def test_hook_submission_with_no_cache_entry_denied(hook, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(hook, "_read_status", lambda _fid: ("", "no approval on file"))
    out = hook.decide({
        "tool_name": "mcp__bugcrowd__submit_report",
        "arguments": {"finding_id": "f-123"},
    })
    assert out["decision"] == "deny"
    assert "no approval on file" in out["reason"]


def test_hook_submission_with_pending_status_denied(hook, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(hook, "_read_status", lambda _fid: ("pending", ""))
    out = hook.decide({
        "tool_name": "mcp__h1__submit_report",
        "arguments": {"finding_id": "f-123"},
    })
    assert out["decision"] == "deny"
    assert "pending" in out["reason"]


def test_hook_submission_with_rejected_status_denied(hook, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(hook, "_read_status", lambda _fid: ("rejected", ""))
    out = hook.decide({
        "tool_name": "mcp__h1__submit_report",
        "arguments": {"finding_id": "f-123"},
    })
    assert out["decision"] == "deny"
    assert "rejected" in out["reason"]


def test_hook_submission_with_approved_status_allowed(hook, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(hook, "_read_status", lambda _fid: ("approved", ""))
    out = hook.decide({
        "tool_name": "mcp__h1__submit_report",
        "arguments": {"finding_id": "f-123"},
    })
    assert out == {"decision": "allow"}


def test_hook_submission_with_redis_unavailable_denied(hook, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        hook, "_read_status",
        lambda _fid: ("", "redis unavailable: ConnectionError"),
    )
    out = hook.decide({
        "tool_name": "mcp__h1__submit_report",
        "arguments": {"finding_id": "f-123"},
    })
    assert out["decision"] == "deny"
    assert "redis unavailable" in out["reason"]


def test_hook_accepts_request_id_as_fallback(hook, monkeypatch: pytest.MonkeyPatch):
    seen = {}

    def _stub(fid):
        seen["fid"] = fid
        return ("approved", "")

    monkeypatch.setattr(hook, "_read_status", _stub)
    out = hook.decide({
        "tool_name": "mcp__intigriti__submit_report",
        "arguments": {"request_id": "r-456"},
    })
    assert out == {"decision": "allow"}
    assert seen["fid"] == "r-456"


@pytest.mark.parametrize(
    "tool_name,is_submit",
    [
        ("mcp__h1__submit_report", True),
        ("mcp__bugcrowd__submit_finding", True),
        ("mcp__immunefi__submit_disclosure", True),
        ("mcp__intigriti__submit_report", True),
        ("mcp__yeswehack__submit_report", True),
        ("mcp__h1__list_reports", False),
        ("mcp__evidence__put_artifact", False),
        ("Bash", False),
        ("WebFetch", False),
        ("", False),
    ],
)
def test_hook_classifies_submission_tools(hook, tool_name: str, is_submit: bool):
    assert hook._is_submission_tool(tool_name) is is_submit
