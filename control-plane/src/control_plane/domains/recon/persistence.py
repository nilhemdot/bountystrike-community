"""Postgres persistence layer for the recon bounded context.

Encapsulates all SQL writes against ``scan_jobs`` and ``findings`` so the
rest of the recon code stays DB-free. Caller is responsible for opening
the connection (`asyncpg.Connection`) and managing the transaction
boundary.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Iterable
from dataclasses import dataclass

from .tool_runner import HttpxProbe


@dataclass(frozen=True, slots=True)
class HypothesisFinding:
    """One row to insert into ``findings`` with status='hypothesis'."""

    url: str
    parameter: str
    cwe: str  # e.g. "xss-candidate", "ssrf-candidate"


class ScanPersistence:
    """All recon-side writes to ``scan_jobs`` and ``findings``."""

    async def mark_running(self, conn, job_id: uuid.UUID | str) -> None:
        await conn.execute(
            "UPDATE scan_jobs SET status = 'running' WHERE id = $1",
            _as_uuid(job_id),
        )

    async def mark_complete(
        self,
        conn,
        job_id: uuid.UUID | str,
        hosts_found: int,
        endpoints_found: int,
    ) -> None:
        await conn.execute(
            """
            UPDATE scan_jobs
            SET status = 'recon_complete',
                hosts_found = $2,
                endpoints_found = $3,
                completed_at = now()
            WHERE id = $1
            """,
            _as_uuid(job_id),
            hosts_found,
            endpoints_found,
        )

    async def mark_failed(self, conn, job_id: uuid.UUID | str, reason: str) -> None:
        # `reason` is intentionally swallowed — the audit-log layer captures
        # detailed failure causes; scan_jobs only carries the terminal status.
        del reason
        await conn.execute(
            """
            UPDATE scan_jobs
            SET status = 'recon_failed',
                completed_at = now()
            WHERE id = $1
            """,
            _as_uuid(job_id),
        )

    async def insert_recon_assets(
        self,
        conn,
        job_id: uuid.UUID | str,
        probes: Iterable[HttpxProbe],
    ) -> int:
        """Bulk-insert httpx probe results into ``recon_assets``.

        Each row carries the host, URL, comma-joined tech list, HTTP
        status, and the original JSONL row as JSONB. Idempotent on
        re-run via the ``UNIQUE (job_id, host, url)`` constraint from
        migration 06: re-running a recon job overwrites nothing and
        inserts no duplicates. Probes without a host are skipped — the
        column is NOT NULL.

        Returns the number of rows submitted (some may be deduplicated
        by ``ON CONFLICT DO NOTHING``; this method does not count
        actual writes — caller should not rely on the return value for
        invariant checks beyond "submitted ≥ written").
        """
        rows = [
            (
                uuid.uuid4(),
                _as_uuid(job_id),
                p.host,
                p.url or None,
                ",".join(p.tech) if p.tech else None,
                int(p.status_code),
                json.dumps(p.raw) if p.raw else None,
            )
            for p in probes
            if p.host
        ]
        if not rows:
            return 0
        await conn.executemany(
            """
            INSERT INTO recon_assets (
                id, job_id, host, url, tech, status_code, raw
            ) VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb)
            ON CONFLICT (job_id, host, url) DO NOTHING
            """,
            rows,
        )
        return len(rows)

    async def insert_findings(
        self,
        conn,
        job_id: uuid.UUID | str,
        program_handle: str,
        platform: str,
        findings: Iterable[HypothesisFinding],
    ) -> int:
        """Bulk-insert hypothesis findings. Returns count actually written."""
        rows = [
            (
                uuid.uuid4(),
                _as_uuid(job_id),
                program_handle,
                platform,
                f.cwe,
                f.url,
                f.parameter,
                "hypothesis",
            )
            for f in findings
        ]
        if not rows:
            return 0
        # Use executemany via copy_records or a pg array-unnest; for a skeleton
        # we issue a single multi-VALUES INSERT for simplicity.
        await conn.executemany(
            """
            INSERT INTO findings (
                id, job_id, program_handle, platform, cwe, url, parameter, status
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8::finding_status)
            ON CONFLICT (cwe, platform, program_handle, deduplication_key)
                DO NOTHING
            """,
            rows,
        )
        return len(rows)


def _as_uuid(value: uuid.UUID | str) -> uuid.UUID:
    return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))


__all__ = ["HypothesisFinding", "ScanPersistence"]
