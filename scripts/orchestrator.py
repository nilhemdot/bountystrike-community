#!/usr/bin/env python3
"""BountyStrike v5 pipeline orchestrator.

Runs one full scan cycle for a single program:
  1. Create scan_jobs row (status=queued)
  2. Launch recon-agent subprocess; wait for recon_complete
  3. Fan out validator-agent per hypothesis finding (MAX_VALIDATORS concurrency)
  4. Print summary

Required environment variables:
    PROGRAM_HANDLE    — e.g. "acme-corp"
    PLATFORM          — e.g. "hackerone"
    SCOPE_JWT         — RS256 scope token
    DATABASE_URL      — postgresql[+asyncpg]://...

Optional:
    ORACLE_MCP_URL    — path/command for oracle-mcp (default: oracle-mcp)
    EVIDENCE_MCP_URL  — path/command for evidence-mcp (default: evidence-mcp)
    DEDUP_MCP_URL     — path/command for dedup-mcp (default: dedup-mcp)
    MAX_VALIDATORS    — parallel validator limit (default: 5)
    RECON_TIMEOUT     — seconds to wait for recon (default: 3600)
    CLAUDE_CMD        — claude CLI binary (default: claude)
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
import sys
import uuid
from datetime import UTC, datetime

import asyncpg


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_required(key: str) -> str:
    val = os.environ.get(key)
    if not val:
        print(f"[orchestrator] ERROR: {key} is not set", file=sys.stderr)
        sys.exit(1)
    return val


def _jwt_jti(scope_jwt: str) -> str:
    try:
        segment = scope_jwt.split(".")[1]
        pad = (4 - len(segment) % 4) % 4
        payload = json.loads(base64.b64decode(segment + "=" * pad).decode())
        return payload.get("jti", "unknown")
    except Exception:
        return "unknown"


def _log(msg: str) -> None:
    ts = datetime.now(UTC).isoformat(timespec="seconds")
    print(f"[orchestrator {ts}] {msg}", flush=True)


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

async def _create_scan_job(
    conn: asyncpg.Connection,
    program_handle: str,
    platform: str,
    scope_jwt_jti: str,
) -> str:
    job_id = str(uuid.uuid4())
    await conn.execute(
        """
        INSERT INTO scan_jobs (id, program_handle, platform, scope_jwt_jti, status, started_at)
        VALUES ($1, $2, $3, $4, 'queued', now())
        """,
        job_id, program_handle, platform, scope_jwt_jti,
    )
    return job_id


async def _wait_recon(
    conn: asyncpg.Connection,
    job_id: str,
    timeout_seconds: int,
) -> str:
    deadline = asyncio.get_event_loop().time() + timeout_seconds
    while asyncio.get_event_loop().time() < deadline:
        status: str | None = await conn.fetchval(
            "SELECT status FROM scan_jobs WHERE id = $1", job_id
        )
        if status in ("recon_complete", "recon_failed"):
            return status
        await asyncio.sleep(10)
    return "timeout"


async def _hypothesis_finding_ids(conn: asyncpg.Connection, job_id: str) -> list[str]:
    rows = await conn.fetch(
        "SELECT id FROM findings WHERE job_id = $1 AND status = 'hypothesis'",
        job_id,
    )
    return [str(r["id"]) for r in rows]


async def _count_by_status(conn: asyncpg.Connection, job_id: str) -> dict[str, int]:
    rows = await conn.fetch(
        "SELECT status, COUNT(*) AS n FROM findings WHERE job_id = $1 GROUP BY status",
        job_id,
    )
    return {r["status"]: r["n"] for r in rows}


# ---------------------------------------------------------------------------
# Agent runner
# ---------------------------------------------------------------------------

async def _run_agent(
    agent_type: str,
    env_extras: dict[str, str],
    claude_cmd: str,
) -> int:
    prompt = (
        f"Run the {agent_type} subagent exactly as specified in "
        f".claude/agents/{agent_type}.md. Follow all steps in the spec."
    )
    env = {**os.environ, **env_extras}
    proc = await asyncio.create_subprocess_exec(
        claude_cmd, "-p", prompt, "--dangerously-skip-permissions",
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    if stderr:
        for line in stderr.decode(errors="replace").splitlines():
            print(f"  [{agent_type}] {line}", file=sys.stderr, flush=True)
    return proc.returncode or 0


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main() -> None:
    program_handle = _get_required("PROGRAM_HANDLE")
    platform       = os.environ.get("PLATFORM", "hackerone")
    scope_jwt      = _get_required("SCOPE_JWT")
    database_url   = _get_required("DATABASE_URL")

    oracle_mcp_url   = os.environ.get("ORACLE_MCP_URL",   "oracle-mcp")
    evidence_mcp_url = os.environ.get("EVIDENCE_MCP_URL", "evidence-mcp")
    dedup_mcp_url    = os.environ.get("DEDUP_MCP_URL",    "dedup-mcp")
    max_validators   = int(os.environ.get("MAX_VALIDATORS", "5"))
    recon_timeout    = int(os.environ.get("RECON_TIMEOUT", "3600"))
    claude_cmd       = os.environ.get("CLAUDE_CMD", "claude")

    dsn = database_url.replace("+asyncpg", "")
    conn: asyncpg.Connection = await asyncpg.connect(dsn)

    try:
        scope_jwt_jti = _jwt_jti(scope_jwt)
        job_id = await _create_scan_job(conn, program_handle, platform, scope_jwt_jti)
        _log(f"scan_job={job_id} program={program_handle} platform={platform}")

        # ── Recon ──────────────────────────────────────────────────────────
        await conn.execute(
            "UPDATE scan_jobs SET status = 'running' WHERE id = $1", job_id
        )
        _log("launching recon-agent")
        recon_rc = await _run_agent(
            "recon",
            {
                "SCOPE_JWT":       scope_jwt,
                "PROGRAM_HANDLE":  program_handle,
                "PLATFORM":        platform,
                "DATABASE_URL":    database_url,
                "SCAN_JOB_ID":     job_id,
                "TASK_STATUS":     "recon_complete",
            },
            claude_cmd,
        )
        if recon_rc != 0:
            _log(f"WARNING: recon-agent exited {recon_rc} — polling DB anyway")

        recon_status = await _wait_recon(conn, job_id, recon_timeout)
        _log(f"recon finished: status={recon_status}")
        if recon_status != "recon_complete":
            _log(f"aborting — recon status={recon_status}")
            sys.exit(1)

        # ── Validate ───────────────────────────────────────────────────────
        finding_ids = await _hypothesis_finding_ids(conn, job_id)
        _log(f"{len(finding_ids)} hypothesis findings")

        if not finding_ids:
            _log("nothing to validate — done")
            return

        semaphore = asyncio.Semaphore(max_validators)
        completed = 0
        failed = 0

        async def _validate_one(finding_id: str) -> None:
            nonlocal completed, failed
            async with semaphore:
                rc = await _run_agent(
                    "validator",
                    {
                        "SCOPE_JWT":        scope_jwt,
                        "PROGRAM_HANDLE":   program_handle,
                        "PLATFORM":         platform,
                        "DATABASE_URL":     database_url,
                        "FINDING_ID":       finding_id,
                        "SCAN_JOB_ID":      job_id,
                        "ORACLE_MCP_URL":   oracle_mcp_url,
                        "EVIDENCE_MCP_URL": evidence_mcp_url,
                        "DEDUP_MCP_URL":    dedup_mcp_url,
                    },
                    claude_cmd,
                )
                if rc == 0:
                    completed += 1
                else:
                    failed += 1
                _log(f"finding={finding_id} rc={rc} ({completed}/{len(finding_ids)} done)")

        await asyncio.gather(*[_validate_one(fid) for fid in finding_ids])

        # ── Summary ────────────────────────────────────────────────────────
        counts = await _count_by_status(conn, job_id)
        _log(
            f"complete — validated={counts.get('validated', 0)} "
            f"duplicate={counts.get('duplicate', 0)} "
            f"archived={counts.get('archived', 0)} "
            f"pending={counts.get('validation_pending', 0)} "
            f"validator_errors={failed}"
        )

    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
