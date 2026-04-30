"""Per-finding approval status cache.

The PreToolUse approval-gate hook fires at every `mcp__*__submit_*`
tool call and needs a sub-millisecond read on "is this finding
approved for submission". The aggregate store
(:class:`ApprovalRequestStore`) is the durable record; this cache is a
fast lookup keyed by ``finding_id`` for the hook subprocess.

Service writes the cache on every state transition. Hook reads only.

Cache values are the raw :class:`ApprovalRequestStatus` string of the
*latest* request for the finding — ``approved`` means it's safe to
submit; anything else means deny.
"""

from __future__ import annotations

import time
import uuid
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from control_plane.domains.approval_gate.aggregates import ApprovalRequestStatus

if TYPE_CHECKING:
    from redis.asyncio import Redis as AsyncRedis


_DEFAULT_TTL_SECONDS = 24 * 3600           # match build-plan §6.3 SLAs
_VALID_STATUSES = {s.value for s in ApprovalRequestStatus}


@runtime_checkable
class FindingStatusCache(Protocol):
    """Read/write surface used by the service + the hook (read-only)."""

    async def set_status(
        self,
        finding_id: uuid.UUID,
        status: ApprovalRequestStatus,
        ttl_seconds: int = _DEFAULT_TTL_SECONDS,
    ) -> None: ...

    async def get_status(
        self, finding_id: uuid.UUID
    ) -> ApprovalRequestStatus | None: ...

    async def clear(self, finding_id: uuid.UUID) -> None: ...


class InMemoryFindingStatusCache:
    """Process-local cache. Tests + dev only."""

    def __init__(self) -> None:
        self._by_id: dict[uuid.UUID, tuple[ApprovalRequestStatus, float]] = {}

    async def set_status(
        self,
        finding_id: uuid.UUID,
        status: ApprovalRequestStatus,
        ttl_seconds: int = _DEFAULT_TTL_SECONDS,
    ) -> None:
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")
        self._by_id[finding_id] = (status, time.monotonic() + ttl_seconds)

    async def get_status(
        self, finding_id: uuid.UUID
    ) -> ApprovalRequestStatus | None:
        entry = self._by_id.get(finding_id)
        if entry is None:
            return None
        status, expires_at = entry
        if time.monotonic() >= expires_at:
            self._by_id.pop(finding_id, None)
            return None
        return status

    async def clear(self, finding_id: uuid.UUID) -> None:
        self._by_id.pop(finding_id, None)


class RedisFindingStatusCache:
    """Redis-backed cache. Key namespace: ``bs:approval:finding:{uuid}``."""

    def __init__(
        self,
        client: AsyncRedis,
        key_prefix: str = "bs:approval:finding:",
    ) -> None:
        self._client = client
        self._prefix = key_prefix

    def _key(self, finding_id: uuid.UUID) -> str:
        return f"{self._prefix}{finding_id}"

    async def set_status(
        self,
        finding_id: uuid.UUID,
        status: ApprovalRequestStatus,
        ttl_seconds: int = _DEFAULT_TTL_SECONDS,
    ) -> None:
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")
        await self._client.set(self._key(finding_id), status.value, ex=ttl_seconds)

    async def get_status(
        self, finding_id: uuid.UUID
    ) -> ApprovalRequestStatus | None:
        raw = await self._client.get(self._key(finding_id))
        if raw is None:
            return None
        value = raw.decode() if isinstance(raw, (bytes, bytearray)) else str(raw)
        if value not in _VALID_STATUSES:
            return None
        return ApprovalRequestStatus(value)

    async def clear(self, finding_id: uuid.UUID) -> None:
        await self._client.delete(self._key(finding_id))


__all__ = [
    "FindingStatusCache",
    "InMemoryFindingStatusCache",
    "RedisFindingStatusCache",
]
