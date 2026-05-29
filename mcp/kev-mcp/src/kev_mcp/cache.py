# SPDX-License-Identifier: AGPL-3.0-or-later

"""TTL-bounded in-memory cache for the KEV catalog.

The catalog updates daily on the CISA side; refresh hourly is plenty.
Cache is per-process; a multi-replica deployment that wants a shared
cache should swap the impl for one backed by Redis without changing
the server tools.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import structlog

from .loader import CisaKevLoader, KevEntry

log = structlog.get_logger("kev_mcp.cache")

DEFAULT_TTL_SECONDS = 3600.0          # 1 hour
DEFAULT_REFRESH_DEADLINE = 60.0       # max time we'll wait on a refresh


@dataclass(slots=True)
class _Snapshot:
    entries: list[KevEntry]
    by_cve: dict[str, KevEntry]
    fetched_at: float


class KevCache:
    """Lazy-loaded TTL cache around :class:`CisaKevLoader`."""

    def __init__(
        self,
        loader: CisaKevLoader,
        ttl_seconds: float = DEFAULT_TTL_SECONDS,
        clock=time.monotonic,
    ) -> None:
        self._loader = loader
        self._ttl = ttl_seconds
        self._clock = clock
        self._snapshot: _Snapshot | None = None

    @property
    def snapshot(self) -> _Snapshot | None:
        return self._snapshot

    async def get_entries(self) -> list[KevEntry]:
        await self._refresh_if_stale()
        assert self._snapshot is not None
        return self._snapshot.entries

    async def lookup(self, cve_id: str) -> KevEntry | None:
        if not cve_id:
            return None
        await self._refresh_if_stale()
        assert self._snapshot is not None
        return self._snapshot.by_cve.get(cve_id.strip().upper())

    async def force_refresh(self) -> None:
        entries = await self._loader.fetch()
        self._snapshot = _Snapshot(
            entries=entries,
            by_cve={e.cve_id.upper(): e for e in entries},
            fetched_at=self._clock(),
        )
        log.info("kev.cache.refreshed", entries=len(entries))

    async def _refresh_if_stale(self) -> None:
        if self._snapshot is None:
            await self.force_refresh()
            return
        age = self._clock() - self._snapshot.fetched_at
        if age >= self._ttl:
            await self.force_refresh()


__all__ = ["DEFAULT_REFRESH_DEADLINE", "DEFAULT_TTL_SECONDS", "KevCache"]
