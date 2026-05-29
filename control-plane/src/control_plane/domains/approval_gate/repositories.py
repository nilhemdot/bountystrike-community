# SPDX-License-Identifier: AGPL-3.0-or-later

"""Repositories for the approval-gate bounded context.

Production callers will swap :class:`InMemoryApprovalRequestStore` for
a Postgres-backed store with row-level locking. The Protocol is the
seam.
"""

from __future__ import annotations

import uuid
from typing import Protocol, runtime_checkable

from .aggregates import ApprovalRequest


@runtime_checkable
class ApprovalRequestStore(Protocol):
    """Async store for :class:`ApprovalRequest` aggregates."""

    async def save(self, request: ApprovalRequest) -> None: ...
    async def get(self, request_id: uuid.UUID) -> ApprovalRequest | None: ...
    async def list_pending_for_finding(
        self, finding_id: uuid.UUID
    ) -> list[ApprovalRequest]: ...


class InMemoryApprovalRequestStore:
    """Process-local store. Tests + dev only."""

    def __init__(self) -> None:
        self._by_id: dict[uuid.UUID, ApprovalRequest] = {}

    async def save(self, request: ApprovalRequest) -> None:
        self._by_id[request.id] = request

    async def get(self, request_id: uuid.UUID) -> ApprovalRequest | None:
        return self._by_id.get(request_id)

    async def list_pending_for_finding(
        self, finding_id: uuid.UUID
    ) -> list[ApprovalRequest]:
        from .aggregates import ApprovalRequestStatus

        return [
            r for r in self._by_id.values()
            if r.finding_id == finding_id
            and r.status == ApprovalRequestStatus.PENDING
        ]


__all__ = ["ApprovalRequestStore", "InMemoryApprovalRequestStore"]
