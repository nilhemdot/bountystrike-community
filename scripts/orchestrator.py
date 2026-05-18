#!/usr/bin/env python3
"""BountyStrike v5 pipeline orchestrator.

Runs one full scan cycle for a single program:

  1. Create scan_jobs row (status=queued)
  2. Launch recon-agent subprocess; wait for recon_complete
  3. Launch scanner-agent subprocess (skippable); wait for scan_complete
  4. Fan out exploit-agent per hypothesis finding (MAX_EXPLOITS concurrency).
     - On `approval_pending_t2` rows, enqueue + poll the approval queue, then
       re-launch the exploit-agent once with APPROVAL_TOKEN set.
  5. Fan out validator-agent per hypothesis / exploit_pending_validation
     finding (MAX_VALIDATORS concurrency)
  6. Fan out reporter-agent per validated finding (skippable)
  7. Print summary

Required environment variables:
    PROGRAM_HANDLE    — e.g. "acme-corp"
    PLATFORM          — e.g. "hackerone"
    SCOPE_JWT         — RS256 scope token
    DATABASE_URL      — postgresql[+asyncpg]://...

Optional:
    ORACLE_MCP_URL    — path/command for oracle-mcp (default: oracle-mcp)
    EVIDENCE_MCP_URL  — path/command for evidence-mcp (default: evidence-mcp)
    DEDUP_MCP_URL     — path/command for dedup-mcp (default: dedup-mcp)
    SANDBOX_MCP_URL   — path/command for sandbox-mcp (default: sandbox-mcp)
    OPENROUTER_API_KEY — consumed by .claude/hooks/pretool_venice_route.py for non-Anthropic routing
    OLLAMA_CLOUD_API_KEY — plumbed forward for an upcoming Ollama Cloud rewire (not yet consumed)
    MAX_VALIDATORS    — parallel validator limit (default: 5)
    MAX_EXPLOITS      — parallel exploit limit (default: 3)
    MAX_REPORTERS     — parallel reporter limit (default: 3)
    RECON_TIMEOUT     — seconds to wait for recon (default: 3600)
    SCAN_TIMEOUT      — seconds to wait for scanner (default: 7200)
    APPROVAL_TIMEOUT  — seconds to wait for T2 approval (default: 86400)
    SKIP_SCANNER      — set 1/true/yes to skip scanner phase
    SKIP_EXPLOIT      — set 1/true/yes to skip exploit phase
    SKIP_REPORT       — set 1/true/yes to skip reporter phase
    SKIP_IDOR         — set 1/true/yes to drop idor-candidate findings post-recon (Gap-2 mitigation)
    NUCLEI_TEMPLATE_DIR — passed through to scanner-agent
    TIME_BUDGET_MIN   — passed through to scanner-agent
    CLAUDE_CMD        — claude CLI binary (default: claude)
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
import shutil
import sys
import uuid
from datetime import UTC, datetime

import asyncpg

# Hot-path import of the approval queue helpers — keeps the orchestrator the
# single owner of ``approval_queue`` writes; agents don't need DB access.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "control-plane", "src"))
from control_plane.domains.approval_gate import (  # noqa: E402
    ApprovalQueueError,
    ApprovalTier,
    queue_enqueue,
    queue_wait_for_approval,
)
from control_plane.domains.evidence_management.services import (  # noqa: E402
    audit_validator_compliance,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_required(key: str) -> str:
    val = os.environ.get(key)
    if not val:
        print(f"[orchestrator] ERROR: {key} is not set", file=sys.stderr)
        sys.exit(1)
    return val


def _flag(key: str) -> bool:
    return os.environ.get(key, "").lower() in ("1", "true", "yes")


def _exploit_phase_skip_reason(skip_exploit: bool, max_exploits: int) -> str | None:
    """Return human reason to skip the exploit phase, or None to run it.

    ``MAX_EXPLOITS=0`` must short-circuit here: building
    ``asyncio.Semaphore(0)`` and then ``asyncio.gather`` over the hypothesis
    findings deadlocks forever, since every ``_exploit_one`` task blocks on
    ``.acquire()`` waiting for a permit that no other task will ever release.
    """
    if skip_exploit:
        return "SKIP_EXPLOIT set"
    if max_exploits <= 0:
        return "MAX_EXPLOITS=0 (use SKIP_EXPLOIT=1 to silence)"
    return None


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


async def _purge_idor_candidates(conn: asyncpg.Connection, job_id: str) -> int:
    """Delete idor-candidate findings for a job. Returns row count."""
    n = await conn.fetchval(
        "WITH d AS ("
        "  DELETE FROM findings "
        "  WHERE job_id = $1 AND cwe = 'idor-candidate' "
        "  RETURNING 1"
        ") SELECT COUNT(*) FROM d",
        job_id,
    )
    return int(n or 0)


# Scanner-agent shells out to these binaries; orchestrator probes once at
# startup and warns rather than crashing the run.
_SCANNER_BINARIES = ("nuclei", "feroxbuster", "ffuf", "sqlmap", "arjun", "kr")


def _missing_scanner_binaries() -> list[str]:
    return [b for b in _SCANNER_BINARIES if shutil.which(b) is None]


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


async def _wait_status(
    conn: asyncpg.Connection,
    job_id: str,
    terminal_states: tuple[str, ...],
    timeout_seconds: int,
) -> str:
    """Poll ``scan_jobs.status`` until it hits one of ``terminal_states``."""
    deadline = asyncio.get_event_loop().time() + timeout_seconds
    while asyncio.get_event_loop().time() < deadline:
        status: str | None = await conn.fetchval(
            "SELECT status FROM scan_jobs WHERE id = $1", job_id
        )
        if status in terminal_states:
            return status
        await asyncio.sleep(10)
    return "timeout"


async def _hypothesis_finding_ids(conn: asyncpg.Connection, job_id: str) -> list[str]:
    rows = await conn.fetch(
        "SELECT id FROM findings WHERE job_id = $1 AND status = 'hypothesis'",
        job_id,
    )
    return [str(r["id"]) for r in rows]


async def _validatable_finding_ids(conn: asyncpg.Connection, job_id: str) -> list[str]:
    """Findings the validator-agent can claim: hypothesis + exploit_pending_validation."""
    rows = await conn.fetch(
        """
        SELECT id FROM findings
        WHERE job_id = $1
          AND status IN ('hypothesis', 'exploit_pending_validation')
        """,
        job_id,
    )
    return [str(r["id"]) for r in rows]


async def _pending_tier_finding_ids(
    conn: asyncpg.Connection, job_id: str, tier: ApprovalTier
) -> list[str]:
    """Findings parked at ``approval_pending_t2`` / ``approval_pending_t3``."""
    status_col = f"approval_pending_{tier.value.lower()}"
    rows = await conn.fetch(
        "SELECT id FROM findings WHERE job_id = $1 AND status = $2",
        job_id, status_col,
    )
    return [str(r["id"]) for r in rows]


async def _t2_pending_finding_ids(conn: asyncpg.Connection, job_id: str) -> list[str]:
    """Backwards-compat shim — use :func:`_pending_tier_finding_ids` for new code."""
    return await _pending_tier_finding_ids(conn, job_id, ApprovalTier.T2)


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
# Phases
# ---------------------------------------------------------------------------


async def _phase_recon(
    conn: asyncpg.Connection,
    *,
    job_id: str,
    program_handle: str,
    platform: str,
    scope_jwt: str,
    database_url: str,
    claude_cmd: str,
    timeout_seconds: int,
) -> None:
    await conn.execute(
        "UPDATE scan_jobs SET status = 'running' WHERE id = $1", job_id
    )
    _log("launching recon-agent")
    rc = await _run_agent(
        "recon",
        {
            "SCOPE_JWT":      scope_jwt,
            "PROGRAM_HANDLE": program_handle,
            "PLATFORM":       platform,
            "DATABASE_URL":   database_url,
            "SCAN_JOB_ID":    job_id,
            "TASK_STATUS":    "recon_complete",
        },
        claude_cmd,
    )
    if rc != 0:
        _log(f"WARNING: recon-agent exited {rc} — polling DB anyway")

    status = await _wait_status(
        conn, job_id, ("recon_complete", "recon_failed"), timeout_seconds
    )
    _log(f"recon finished: status={status}")
    if status != "recon_complete":
        _log(f"aborting — recon status={status}")
        sys.exit(1)


async def _phase_scanner(
    conn: asyncpg.Connection,
    *,
    job_id: str,
    program_handle: str,
    platform: str,
    scope_jwt: str,
    database_url: str,
    claude_cmd: str,
    timeout_seconds: int,
) -> None:
    if _flag("SKIP_SCANNER"):
        _log("SKIP_SCANNER set — skipping scanner-agent phase")
        return

    missing = _missing_scanner_binaries()
    if missing:
        _log(
            f"WARNING: scanner binaries not on PATH ({', '.join(missing)}); "
            f"skipping scanner phase. Install them or set SKIP_SCANNER=1 to silence."
        )
        return

    await conn.execute(
        "UPDATE scan_jobs SET status = 'running_scan' WHERE id = $1", job_id
    )
    _log("launching scanner-agent")
    env_extras = {
        "SCOPE_JWT":      scope_jwt,
        "PROGRAM_HANDLE": program_handle,
        "PLATFORM":       platform,
        "DATABASE_URL":   database_url,
        "SCAN_JOB_ID":    job_id,
    }
    for passthrough in ("NUCLEI_TEMPLATE_DIR", "TIME_BUDGET_MIN"):
        if passthrough in os.environ:
            env_extras[passthrough] = os.environ[passthrough]

    rc = await _run_agent("scanner-agent", env_extras, claude_cmd)
    if rc != 0:
        _log(f"WARNING: scanner-agent exited {rc} — polling DB anyway")

    status = await _wait_status(
        conn,
        job_id,
        ("scan_complete", "scan_partial", "scan_failed"),
        timeout_seconds,
    )
    if status == "scan_failed":
        _log(f"aborting — scanner status={status}")
        sys.exit(1)
    if status == "scan_partial":
        _log("scanner returned scan_partial — continuing with partial findings")
    else:
        _log(f"scanner finished: status={status}")

    n = await conn.fetchval(
        "SELECT COUNT(*) FROM findings WHERE job_id = $1 AND status = 'hypothesis'",
        job_id,
    )
    _log(f"scanner emitted (cumulative hypothesis count) {n} finding(s)")


async def _exploit_one(
    conn: asyncpg.Connection,
    *,
    finding_id: str,
    job_id: str,
    program_handle: str,
    platform: str,
    scope_jwt: str,
    database_url: str,
    evidence_mcp_url: str,
    dedup_mcp_url: str,
    sandbox_mcp_url: str,
    approval_token: str | None,
    semaphore: asyncio.Semaphore,
    claude_cmd: str,
) -> int:
    async with semaphore:
        env_extras: dict[str, str] = {
            "SCOPE_JWT":         scope_jwt,
            "PROGRAM_HANDLE":    program_handle,
            "PLATFORM":          platform,
            "DATABASE_URL":      database_url,
            "FINDING_ID":        finding_id,
            "SCAN_JOB_ID":       job_id,
            "EVIDENCE_MCP_URL":  evidence_mcp_url,
            "DEDUP_MCP_URL":     dedup_mcp_url,
            "SANDBOX_MCP_URL":   sandbox_mcp_url,
        }
        if approval_token:
            env_extras["APPROVAL_TOKEN"] = approval_token
        # OPENROUTER_API_KEY is the currently consumed routing key
        # (.claude/hooks/pretool_venice_route.py). OLLAMA_CLOUD_API_KEY is plumbed
        # forward in anticipation of the Ollama Cloud rewire.
        for passthrough in ("OPENROUTER_API_KEY", "OLLAMA_CLOUD_API_KEY"):
            if passthrough in os.environ:
                env_extras[passthrough] = os.environ[passthrough]

        rc = await _run_agent("exploit-agent", env_extras, claude_cmd)
        _log(f"exploit-agent finding={finding_id} rc={rc}")
        return rc


async def _enqueue_pending_tier(
    conn: asyncpg.Connection,
    finding_ids: list[str],
    tier: ApprovalTier,
) -> list[str]:
    """Enqueue any rows parked at ``approval_pending_t2`` / ``approval_pending_t3``.

    Returns the list of finding_ids that now have a pending entry in
    ``approval_queue``. Idempotent: an already-enqueued finding is a no-op.
    """
    enqueued: list[str] = []
    for fid_str in finding_ids:
        fid = uuid.UUID(fid_str)
        row = await conn.fetchrow(
            """
            SELECT raw_finding->'chain_steps' AS chain_steps
            FROM findings WHERE id = $1
            """,
            fid,
        )
        poc_text = (
            json.dumps(row["chain_steps"]) if row and row["chain_steps"] else None
        )
        try:
            await queue_enqueue(conn, fid, tier, poc_text=poc_text)
            enqueued.append(fid_str)
        except ApprovalQueueError as exc:
            _log(f"  enqueue skipped finding={fid_str}: {exc}")
    return enqueued


async def _enqueue_pending_t2(
    conn: asyncpg.Connection,
    finding_ids: list[str],
) -> list[str]:
    """Backwards-compat shim — use :func:`_enqueue_pending_tier` for new code."""
    return await _enqueue_pending_tier(conn, finding_ids, ApprovalTier.T2)


async def _wait_token(
    conn: asyncpg.Connection,
    finding_id: str,
    timeout_seconds: float,
) -> str | None:
    """Block until the operator approves the finding via scripts/approve.py."""
    fid = uuid.UUID(finding_id)
    token = await queue_wait_for_approval(conn, fid, timeout_seconds=timeout_seconds)
    return str(token) if token else None


# Legacy alias retained for callers that imported the T2-specific name.
_wait_t2_token = _wait_token


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main() -> None:  # noqa: PLR0912, PLR0915
    program_handle = _get_required("PROGRAM_HANDLE")
    platform       = os.environ.get("PLATFORM", "hackerone")
    scope_jwt      = _get_required("SCOPE_JWT")
    database_url   = _get_required("DATABASE_URL")

    oracle_mcp_url   = os.environ.get("ORACLE_MCP_URL",   "oracle-mcp")
    evidence_mcp_url = os.environ.get("EVIDENCE_MCP_URL", "evidence-mcp")
    dedup_mcp_url    = os.environ.get("DEDUP_MCP_URL",    "dedup-mcp")
    sandbox_mcp_url  = os.environ.get("SANDBOX_MCP_URL",  "sandbox-mcp")

    max_validators   = int(os.environ.get("MAX_VALIDATORS", "5"))
    max_exploits     = int(os.environ.get("MAX_EXPLOITS",   "3"))
    max_reporters    = int(os.environ.get("MAX_REPORTERS",  "3"))
    recon_timeout    = int(os.environ.get("RECON_TIMEOUT",  "3600"))
    scan_timeout     = int(os.environ.get("SCAN_TIMEOUT",   "7200"))
    approval_timeout = int(os.environ.get("APPROVAL_TIMEOUT", str(24 * 3600)))
    claude_cmd       = os.environ.get("CLAUDE_CMD", "claude")

    skip_exploit = _flag("SKIP_EXPLOIT")
    skip_report  = _flag("SKIP_REPORT")
    skip_idor    = _flag("SKIP_IDOR")

    dsn = database_url.replace("+asyncpg", "")
    conn: asyncpg.Connection = await asyncpg.connect(dsn)

    try:
        scope_jwt_jti = _jwt_jti(scope_jwt)
        job_id = await _create_scan_job(conn, program_handle, platform, scope_jwt_jti)
        _log(f"scan_job={job_id} program={program_handle} platform={platform}")

        # ── Recon ──────────────────────────────────────────────────────────
        await _phase_recon(
            conn,
            job_id=job_id,
            program_handle=program_handle,
            platform=platform,
            scope_jwt=scope_jwt,
            database_url=database_url,
            claude_cmd=claude_cmd,
            timeout_seconds=recon_timeout,
        )

        if skip_idor:
            dropped = await _purge_idor_candidates(conn, job_id)
            _log(f"SKIP_IDOR set — dropped {dropped} idor-candidate finding(s) post-recon")

        # ── Scanner ────────────────────────────────────────────────────────
        await _phase_scanner(
            conn,
            job_id=job_id,
            program_handle=program_handle,
            platform=platform,
            scope_jwt=scope_jwt,
            database_url=database_url,
            claude_cmd=claude_cmd,
            timeout_seconds=scan_timeout,
        )

        # ── Exploit ────────────────────────────────────────────────────────
        exploit_skip_reason = _exploit_phase_skip_reason(skip_exploit, max_exploits)
        if exploit_skip_reason is not None:
            _log(f"{exploit_skip_reason} — skipping exploit-agent phase")
        else:
            hypo_ids = await _hypothesis_finding_ids(conn, job_id)
            _log(f"{len(hypo_ids)} hypothesis findings for exploit phase")

            if hypo_ids:
                exp_sem = asyncio.Semaphore(max_exploits)
                await asyncio.gather(*[
                    _exploit_one(
                        conn,
                        finding_id=fid,
                        job_id=job_id,
                        program_handle=program_handle,
                        platform=platform,
                        scope_jwt=scope_jwt,
                        database_url=database_url,
                        evidence_mcp_url=evidence_mcp_url,
                        dedup_mcp_url=dedup_mcp_url,
                        sandbox_mcp_url=sandbox_mcp_url,
                        approval_token=None,
                        semaphore=exp_sem,
                        claude_cmd=claude_cmd,
                    )
                    for fid in hypo_ids
                ])

                # ── T2 approval ────────────────────────────────────────────
                pending_t2 = await _t2_pending_finding_ids(conn, job_id)
                if pending_t2:
                    _log(
                        f"{len(pending_t2)} finding(s) require T2 approval — "
                        f"enqueueing and waiting (timeout={approval_timeout}s). "
                        f"Run `scripts/approve.py list` in another shell."
                    )
                    enqueued = await _enqueue_pending_t2(conn, pending_t2)
                    for fid in enqueued:
                        token = await _wait_t2_token(conn, fid, approval_timeout)
                        if token is None:
                            _log(f"  T2 approval denied/expired for finding={fid}")
                            continue
                        _log(f"  T2 approved finding={fid} — relaunching exploit-agent")
                        await _exploit_one(
                            conn,
                            finding_id=fid,
                            job_id=job_id,
                            program_handle=program_handle,
                            platform=platform,
                            scope_jwt=scope_jwt,
                            database_url=database_url,
                            evidence_mcp_url=evidence_mcp_url,
                            dedup_mcp_url=dedup_mcp_url,
                            sandbox_mcp_url=sandbox_mcp_url,
                            approval_token=token,
                            semaphore=asyncio.Semaphore(1),
                            claude_cmd=claude_cmd,
                        )

        # ── Validate ───────────────────────────────────────────────────────
        finding_ids = await _validatable_finding_ids(conn, job_id)
        _log(f"{len(finding_ids)} finding(s) ready for validation")

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

        # ── T3 approval ────────────────────────────────────────────────────
        # The validator (or a future post-validate classifier) flips
        # high-impact findings to ``approval_pending_t3`` based on CVSS,
        # bug class, hop count, etc (build-plan §6.3). Two distinct
        # operators must approve before the reporter-agent submits.
        pending_t3 = await _pending_tier_finding_ids(conn, job_id, ApprovalTier.T3)
        if pending_t3:
            _log(
                f"{len(pending_t3)} finding(s) require T3 approval — "
                f"enqueueing and waiting (timeout={approval_timeout}s). "
                f"Run `scripts/approve.py list --tier T3` in another shell. "
                f"T3 needs TWO distinct approvers."
            )
            enqueued_t3 = await _enqueue_pending_tier(conn, pending_t3, ApprovalTier.T3)
            for fid in enqueued_t3:
                token = await _wait_token(conn, fid, approval_timeout)
                if token is None:
                    _log(f"  T3 approval denied/expired for finding={fid} → archiving")
                    await conn.execute(
                        "UPDATE findings SET status='archived', updated_at=now() "
                        "WHERE id = $1",
                        uuid.UUID(fid),
                    )
                    continue
                _log(f"  T3 approved finding={fid} → promoting to validated for reporter")
                await conn.execute(
                    "UPDATE findings SET status='validated', updated_at=now() "
                    "WHERE id = $1",
                    uuid.UUID(fid),
                )

        # ── Report ─────────────────────────────────────────────────────────
        if skip_report:
            _log("SKIP_REPORT set — skipping reporter-agent phase")
        else:
            validated_rows = await conn.fetch(
                "SELECT id FROM findings WHERE job_id = $1 AND status = 'validated'",
                job_id,
            )
            validated_ids = [str(r["id"]) for r in validated_rows]
            _log(f"{len(validated_ids)} validated findings to report")

            if validated_ids:
                rep_semaphore = asyncio.Semaphore(max_reporters)
                rep_failed = 0

                async def _report_one(finding_id: str) -> None:
                    nonlocal rep_failed
                    async with rep_semaphore:
                        reporter_env: dict[str, str] = {
                            "SCOPE_JWT":        scope_jwt,
                            "PROGRAM_HANDLE":   program_handle,
                            "PLATFORM":         platform,
                            "DATABASE_URL":     database_url,
                            "FINDING_ID":       finding_id,
                            "EVIDENCE_MCP_URL": evidence_mcp_url,
                        }
                        for tok_var in (
                            "H1_API_TOKEN", "BUGCROWD_API_TOKEN",
                            "IMMUNEFI_API_TOKEN", "REPORTER_MODEL",
                        ):
                            if tok_var in os.environ:
                                reporter_env[tok_var] = os.environ[tok_var]
                        rc = await _run_agent("reporter", reporter_env, claude_cmd)
                        if rc != 0:
                            rep_failed += 1
                        _log(f"reporter finding={finding_id} rc={rc}")

                await asyncio.gather(*[_report_one(fid) for fid in validated_ids])

        # ── Summary ────────────────────────────────────────────────────────
        counts = await _count_by_status(conn, job_id)
        # Validator-spec compliance audit (build-plan §6.3 / Round 12).
        # Logs only — strict CI gates own the build/break decision.
        compliance = await audit_validator_compliance(
            conn, program_handle=program_handle
        )
        compliance_status = (
            "ok"
            if compliance.is_compliant
            else f"{compliance.missing_fingerprint} missing"
        )
        _log(
            f"complete — validated={counts.get('validated', 0)} "
            f"submitted={counts.get('submitted', 0)} "
            f"duplicate={counts.get('duplicate', 0)} "
            f"archived={counts.get('archived', 0)} "
            f"pending={counts.get('validation_pending', 0)} "
            f"approval_pending_t2={counts.get('approval_pending_t2', 0)} "
            f"exploit_pending_validation={counts.get('exploit_pending_validation', 0)} "
            f"validator_errors={failed} "
            f"validator_compliance={compliance_status}"
        )

    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
