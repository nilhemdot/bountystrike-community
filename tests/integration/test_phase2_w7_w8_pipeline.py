"""Phase 2 W7-8 end-to-end orchestration smoke test.

Exercises ``scripts/orchestrator.main`` with mocked Claude Code subagent
subprocesses and a FakeConnection that models the subset of asyncpg surface
the orchestrator uses. Verifies the wiring without needing a live Postgres
or real Claude CLI.

The fake subagents simulate state transitions a real subagent would perform:

* ``recon-agent``  → flips ``scan_jobs.status`` to ``recon_complete`` and
                     inserts a hypothesis finding
* ``scanner-agent``→ flips ``scan_jobs.status`` to ``scan_complete``
* ``exploit-agent``→ either flips finding to ``exploit_pending_validation``
                     or to ``approval_pending_t2`` depending on fixture
* ``validator``    → flips finding to ``validated``
* ``reporter``     → flips finding to ``submitted``
"""

from __future__ import annotations

import contextlib
import importlib
import json
import os
import sys
import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any

import pytest

# Ensure the control-plane package is importable for the queue helpers.
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, os.path.join(ROOT, "control-plane", "src"))
sys.path.insert(0, ROOT)


# ---------------------------------------------------------------------------
# FakeConnection — minimal asyncpg surface for orchestrator + queue
# ---------------------------------------------------------------------------


class FakeOrchestratorDB:
    """In-memory model of scan_jobs + findings + approval_queue."""

    def __init__(self) -> None:
        self.scan_jobs: dict[str, dict[str, Any]] = {}
        self.findings: dict[str, dict[str, Any]] = {}
        self.approval_queue: dict[uuid.UUID, dict[str, Any]] = {}
        self._closed = False

    @asynccontextmanager
    async def transaction(self):
        yield

    async def close(self) -> None:
        self._closed = True

    # ------- execute -----------------------------------------------------

    async def execute(self, sql: str, *args: Any) -> str:
        sql_n = " ".join(sql.split())

        if sql_n.startswith("INSERT INTO scan_jobs"):
            job_id, program_handle, platform, jti = args
            self.scan_jobs[job_id] = {
                "id": job_id,
                "program_handle": program_handle,
                "platform": platform,
                "scope_jwt_jti": jti,
                "status": "queued",
                "started_at": datetime.now(UTC),
                "raw": {},
            }
            return "INSERT 0 1"

        if sql_n.startswith("UPDATE scan_jobs SET status = 'running' WHERE id"):
            (job_id,) = args
            self.scan_jobs[job_id]["status"] = "running"
            return "UPDATE 1"

        if sql_n.startswith("UPDATE scan_jobs SET status = 'running_scan' WHERE id"):
            (job_id,) = args
            self.scan_jobs[job_id]["status"] = "running_scan"
            return "UPDATE 1"

        if sql_n.startswith("INSERT INTO approval_queue"):
            finding_id, tier, poc_text, expires_at = args
            if finding_id in self.approval_queue:
                return "INSERT 0 0"
            self.approval_queue[finding_id] = {
                "finding_id": finding_id,
                "tier": tier,
                "poc_text": poc_text,
                "status": "pending",
                "token": None,
                "requested_at": datetime.now(UTC),
                "approved_at": None,
                "approver_id": None,
                "approver_id_2": None,
                "reason": None,
                "expires_at": expires_at,
            }
            return "INSERT 0 1"

        if "SET status='approved', approver_id=$2" in sql_n:
            finding_id, approver_id, reason, token = args
            row = self.approval_queue[finding_id]
            row["status"] = "approved"
            row["approver_id"] = approver_id
            row["reason"] = reason
            row["token"] = token
            row["approved_at"] = datetime.now(UTC)
            return "UPDATE 1"

        if "SET status='approved', approver_id_2=$2" in sql_n:
            finding_id, approver_id_2, token = args
            row = self.approval_queue[finding_id]
            row["status"] = "approved"
            row["approver_id_2"] = approver_id_2
            row["token"] = token
            row["approved_at"] = datetime.now(UTC)
            return "UPDATE 1"

        if "UPDATE approval_queue SET approver_id=$2, reason=$3" in sql_n:
            finding_id, approver_id, reason = args
            row = self.approval_queue[finding_id]
            row["approver_id"] = approver_id
            row["reason"] = reason
            return "UPDATE 1"

        if sql_n.startswith("UPDATE findings SET status='archived'"):
            (fid,) = args
            self.findings[str(fid)]["status"] = "archived"
            return "UPDATE 1"

        if sql_n.startswith("UPDATE findings SET status='validated'"):
            (fid,) = args
            self.findings[str(fid)]["status"] = "validated"
            return "UPDATE 1"

        raise NotImplementedError(f"FakeOrchestratorDB.execute: {sql_n[:80]}")

    # ------- fetchval ----------------------------------------------------

    async def fetchval(self, sql: str, *args: Any) -> Any:
        sql_n = " ".join(sql.split())
        if sql_n.startswith("SELECT status FROM scan_jobs WHERE id"):
            (job_id,) = args
            return self.scan_jobs[job_id]["status"]
        if "SELECT COUNT(*) FROM findings" in sql_n:
            (job_id,) = args
            return sum(
                1 for f in self.findings.values()
                if f["job_id"] == job_id and f["status"] == "hypothesis"
            )
        # validator-compliance audit total count.
        if "count(*)" in sql_n.lower() and "f.status = 'validated'" in sql_n:
            (program_handle,) = args
            return sum(
                1 for f in self.findings.values()
                if f["status"] == "validated"
                and (program_handle is None or f["program_handle"] == program_handle)
            )
        raise NotImplementedError(f"FakeOrchestratorDB.fetchval: {sql_n[:80]}")

    # ------- fetch -------------------------------------------------------

    async def fetch(self, sql: str, *args: Any) -> list[dict[str, Any]]:
        sql_n = " ".join(sql.split())

        if "WHERE job_id = $1 AND status = 'hypothesis'" in sql_n:
            (job_id,) = args
            return [
                {"id": uuid.UUID(f["id"])}
                for f in self.findings.values()
                if f["job_id"] == job_id and f["status"] == "hypothesis"
            ]

        if "WHERE job_id = $1 AND status = 'approval_pending_t2'" in sql_n:
            (job_id,) = args
            return [
                {"id": uuid.UUID(f["id"])}
                for f in self.findings.values()
                if f["job_id"] == job_id and f["status"] == "approval_pending_t2"
            ]

        # Tier-parametrised query — orchestrator passes status as $2.
        if "WHERE job_id = $1 AND status = $2" in sql_n:
            job_id, status = args
            return [
                {"id": uuid.UUID(f["id"])}
                for f in self.findings.values()
                if f["job_id"] == job_id and f["status"] == status
            ]

        if "WHERE job_id = $1 AND status = 'validated'" in sql_n:
            (job_id,) = args
            return [
                {"id": uuid.UUID(f["id"])}
                for f in self.findings.values()
                if f["job_id"] == job_id and f["status"] == "validated"
            ]

        if "AND status IN ('hypothesis', 'exploit_pending_validation')" in sql_n:
            (job_id,) = args
            return [
                {"id": uuid.UUID(f["id"])}
                for f in self.findings.values()
                if f["job_id"] == job_id
                and f["status"] in ("hypothesis", "exploit_pending_validation")
            ]

        # validator-compliance audit missing-ids query.
        if "LEFT JOIN dedup_fingerprints" in sql_n:
            (program_handle,) = args
            return [
                {"id": uuid.UUID(f["id"])}
                for f in self.findings.values()
                if f["status"] == "validated"
                and (program_handle is None or f["program_handle"] == program_handle)
            ]

        if "GROUP BY status" in sql_n:
            (job_id,) = args
            counts: dict[str, int] = {}
            for f in self.findings.values():
                if f["job_id"] == job_id:
                    counts[f["status"]] = counts.get(f["status"], 0) + 1
            return [{"status": s, "n": n} for s, n in counts.items()]

        raise NotImplementedError(f"FakeOrchestratorDB.fetch: {sql_n[:80]}")

    # ------- fetchrow ----------------------------------------------------

    async def fetchrow(self, sql: str, *args: Any) -> dict[str, Any] | None:
        sql_n = " ".join(sql.split())

        if "FROM findings WHERE id = $1" in sql_n and "raw_finding->'chain_steps'" in sql_n:
            (fid,) = args
            f = self.findings.get(str(fid))
            if f is None:
                return None
            chain = f.get("raw_finding", {}).get("chain_steps")
            return {"chain_steps": chain}

        if "FROM approval_queue WHERE finding_id = $1 FOR UPDATE" in sql_n:
            (fid,) = args
            return self.approval_queue.get(fid)

        if "FROM approval_queue WHERE finding_id = $1" in sql_n:
            (fid,) = args
            return self.approval_queue.get(fid)

        raise NotImplementedError(f"FakeOrchestratorDB.fetchrow: {sql_n[:80]}")


# ---------------------------------------------------------------------------
# Subagent simulators
# ---------------------------------------------------------------------------


class SubagentSimulator:
    """Build a fake _run_agent that mutates the FakeOrchestratorDB."""

    def __init__(
        self,
        db: FakeOrchestratorDB,
        *,
        exploit_outcome: str = "success",
        validator_outcome: str = "validated",
    ) -> None:
        self.db = db
        self.exploit_outcome = exploit_outcome  # "success" | "needs_t2" | "failed"
        self.validator_outcome = validator_outcome  # "validated" | "needs_t3"
        self.calls: list[tuple[str, dict[str, str]]] = []

    async def __call__(
        self,
        agent_type: str,
        env_extras: dict[str, str],
        claude_cmd: str,
        model_id: str | None = None,
    ) -> int:
        self.calls.append((agent_type, dict(env_extras)))
        job_id = env_extras.get("SCAN_JOB_ID", "")

        if agent_type == "recon":
            self.db.scan_jobs[job_id]["status"] = "recon_complete"
            # Insert one hypothesis finding
            fid = str(uuid.uuid4())
            self.db.findings[fid] = {
                "id": fid,
                "job_id": job_id,
                "program_handle": env_extras.get("PROGRAM_HANDLE"),
                "platform": env_extras.get("PLATFORM"),
                "cwe": "CWE-79",
                "url": "https://fixture-acme.test/search",
                "parameter": "q",
                "status": "hypothesis",
                "raw_finding": {},
                "oracle_method": None,
            }
            return 0

        if agent_type == "scanner-agent":
            self.db.scan_jobs[job_id]["status"] = "scan_complete"
            return 0

        if agent_type == "exploit-agent":
            fid = env_extras["FINDING_ID"]
            f = self.db.findings[fid]
            if self.exploit_outcome == "success":
                f["status"] = "exploit_pending_validation"
                f["raw_finding"] = {**f["raw_finding"], "chain_steps": ["step1"]}
            elif self.exploit_outcome == "needs_t2":
                # First call enqueues T2 review; second call (with token) succeeds.
                if env_extras.get("APPROVAL_TOKEN"):
                    f["status"] = "exploit_pending_validation"
                    f["raw_finding"] = {**f["raw_finding"], "chain_steps": ["step1"]}
                else:
                    f["status"] = "approval_pending_t2"
            elif self.exploit_outcome == "failed":
                f["status"] = "exploit_failed_timeout"
            return 0

        if agent_type == "validator":
            fid = env_extras["FINDING_ID"]
            f = self.db.findings[fid]
            if self.validator_outcome == "needs_t3":
                f["status"] = "approval_pending_t3"
            else:
                f["status"] = "validated"
            return 0

        if agent_type == "reporter":
            fid = env_extras["FINDING_ID"]
            f = self.db.findings[fid]
            f["status"] = "submitted"
            return 0

        raise AssertionError(f"unexpected subagent: {agent_type}")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def fake_db() -> FakeOrchestratorDB:
    return FakeOrchestratorDB()


@pytest.fixture
def orchestrator_module(monkeypatch, fake_db):
    """Import scripts/orchestrator.py with asyncpg.connect monkeypatched."""
    # Required env for orchestrator
    monkeypatch.setenv("PROGRAM_HANDLE", "fixture-acme")
    monkeypatch.setenv("PLATFORM", "hackerone")
    monkeypatch.setenv(
        "SCOPE_JWT",
        # 3-segment dummy JWT — orchestrator only base64-decodes the payload
        "header." + _b64({"jti": "test-jti"}) + ".sig",
    )
    monkeypatch.setenv("DATABASE_URL", "postgresql://localhost/fake")
    monkeypatch.setenv("CLAUDE_CMD", "claude")

    # Import (or re-import) the module
    if "scripts.orchestrator" in sys.modules:
        del sys.modules["scripts.orchestrator"]
    mod = importlib.import_module("scripts.orchestrator")

    async def _fake_connect(dsn: str) -> FakeOrchestratorDB:
        return fake_db

    monkeypatch.setattr(mod.asyncpg, "connect", _fake_connect)
    # Speed up _wait_status polling without globally patching asyncio.sleep
    # (we still need real sleep for cooperative tasks like auto_approver to run).
    async def _fast_wait_status(conn, job_id, terminal_states, timeout_seconds):
        # Poll once, immediately — fake DB transitions are synchronous.
        status = await conn.fetchval(
            "SELECT status FROM scan_jobs WHERE id = $1", job_id
        )
        return status if status in terminal_states else "timeout"

    monkeypatch.setattr(mod, "_wait_status", _fast_wait_status)
    return mod


def _b64(payload: dict[str, Any]) -> str:
    import base64

    return base64.urlsafe_b64encode(
        json.dumps(payload).encode()
    ).decode().rstrip("=")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pipeline_runs_recon_only_when_skips_set(
    monkeypatch, fake_db, orchestrator_module
):
    """SKIP_SCANNER + SKIP_EXPLOIT + SKIP_REPORT yields recon→validate path only."""
    monkeypatch.setenv("SKIP_SCANNER", "1")
    monkeypatch.setenv("SKIP_EXPLOIT", "1")
    monkeypatch.setenv("SKIP_REPORT", "1")

    sim = SubagentSimulator(fake_db, exploit_outcome="success")
    monkeypatch.setattr(orchestrator_module, "_run_agent", sim)

    await orchestrator_module.main()

    types = [t for t, _ in sim.calls]
    assert "recon" in types
    assert "scanner-agent" not in types
    assert "exploit-agent" not in types
    assert "validator" in types
    assert "reporter" not in types

    # The hypothesis finding should be validated by validator
    statuses = {f["status"] for f in fake_db.findings.values()}
    assert "validated" in statuses


@pytest.mark.asyncio
async def test_exploit_success_path(monkeypatch, fake_db, orchestrator_module):
    """Exploit-agent flips hypothesis → exploit_pending_validation, validator picks up."""
    monkeypatch.setenv("SKIP_SCANNER", "1")
    monkeypatch.setenv("SKIP_REPORT", "1")

    sim = SubagentSimulator(fake_db, exploit_outcome="success")
    monkeypatch.setattr(orchestrator_module, "_run_agent", sim)

    await orchestrator_module.main()

    types = [t for t, _ in sim.calls]
    assert types.count("exploit-agent") == 1
    assert types.count("validator") == 1

    # Verify the exploit-agent ran first, then the validator
    exploit_idx = types.index("exploit-agent")
    validator_idx = types.index("validator")
    assert exploit_idx < validator_idx

    statuses = {f["status"] for f in fake_db.findings.values()}
    assert "validated" in statuses


@pytest.mark.asyncio
async def test_t2_approval_flow(monkeypatch, fake_db, orchestrator_module):
    """Exploit-agent stalls on approval_pending_t2; orchestrator enqueues + waits."""
    monkeypatch.setenv("SKIP_SCANNER", "1")
    monkeypatch.setenv("SKIP_REPORT", "1")
    monkeypatch.setenv("APPROVAL_TIMEOUT", "30")

    # Tight polling — real asyncio.sleep, but tiny intervals so other tasks run.
    import control_plane.domains.approval_gate.queue as q_mod
    monkeypatch.setattr(q_mod, "_backoff_seconds", lambda _attempt: 0.01)

    sim = SubagentSimulator(fake_db, exploit_outcome="needs_t2")
    monkeypatch.setattr(orchestrator_module, "_run_agent", sim)

    # Auto-approve in the background once the queue row appears.
    import asyncio as aio

    from control_plane.domains.approval_gate import queue_approve

    async def auto_approver() -> None:
        for _ in range(500):
            if fake_db.approval_queue:
                fid = next(iter(fake_db.approval_queue))
                if fake_db.approval_queue[fid]["status"] == "pending":
                    await queue_approve(fake_db, fid, "auto-test", reason="ci")
                    return
            await aio.sleep(0.005)

    approver_task = aio.create_task(auto_approver())
    try:
        await orchestrator_module.main()
    finally:
        if not approver_task.done():
            approver_task.cancel()
            with contextlib.suppress(aio.CancelledError):
                await approver_task

    types = [t for t, _ in sim.calls]
    # exploit-agent ran twice: once unauthorised, once with APPROVAL_TOKEN
    assert types.count("exploit-agent") == 2

    # The second exploit-agent invocation must have APPROVAL_TOKEN in env
    exploit_envs = [env for t, env in sim.calls if t == "exploit-agent"]
    assert "APPROVAL_TOKEN" not in exploit_envs[0]
    assert "APPROVAL_TOKEN" in exploit_envs[1]

    # Validator runs after the second exploit-agent invocation
    assert "validator" in types

    statuses = {f["status"] for f in fake_db.findings.values()}
    assert "validated" in statuses


@pytest.mark.asyncio
async def test_t3_approval_two_actors_promotes_to_validated(
    monkeypatch, fake_db, orchestrator_module
):
    """Validator flips finding to approval_pending_t3 → orchestrator enqueues
    T3 → two distinct operators approve → finding promoted back to validated
    → reporter runs."""
    monkeypatch.setenv("SKIP_SCANNER", "1")
    monkeypatch.setenv("SKIP_EXPLOIT", "1")
    monkeypatch.setenv("APPROVAL_TIMEOUT", "30")

    import control_plane.domains.approval_gate.queue as q_mod
    monkeypatch.setattr(q_mod, "_backoff_seconds", lambda _attempt: 0.01)

    sim = SubagentSimulator(
        fake_db,
        exploit_outcome="success",
        validator_outcome="needs_t3",
    )
    monkeypatch.setattr(orchestrator_module, "_run_agent", sim)

    import asyncio as aio

    from control_plane.domains.approval_gate import queue_approve

    async def t3_auto_approver() -> None:
        for _ in range(500):
            if fake_db.approval_queue:
                fid = next(iter(fake_db.approval_queue))
                row = fake_db.approval_queue[fid]
                if row["status"] == "pending":
                    if row["approver_id"] is None:
                        await queue_approve(fake_db, fid, "op1", reason="t3 first")
                    elif row["approver_id"] != "op2":
                        await queue_approve(fake_db, fid, "op2", reason="t3 second")
                        return
            await aio.sleep(0.005)

    approver_task = aio.create_task(t3_auto_approver())
    try:
        await orchestrator_module.main()
    finally:
        if not approver_task.done():
            approver_task.cancel()
            import contextlib
            with contextlib.suppress(aio.CancelledError):
                await approver_task

    types = [t for t, _ in sim.calls]
    assert "validator" in types
    assert "reporter" in types

    statuses = {f["status"] for f in fake_db.findings.values()}
    # Finding should have been promoted to validated, then submitted by reporter.
    assert "submitted" in statuses

    # Approval queue row finalised approved with both approver fields set.
    fid = next(iter(fake_db.approval_queue))
    qrow = fake_db.approval_queue[fid]
    assert qrow["status"] == "approved"
    assert qrow["approver_id"] == "op1"
    assert qrow["approver_id_2"] == "op2"


@pytest.mark.asyncio
async def test_t3_denial_archives_finding(
    monkeypatch, fake_db, orchestrator_module
):
    """T3 expires/denied → finding flipped to archived, reporter does not run for it."""
    monkeypatch.setenv("SKIP_SCANNER", "1")
    monkeypatch.setenv("SKIP_EXPLOIT", "1")
    monkeypatch.setenv("APPROVAL_TIMEOUT", "1")  # tight timeout — let it expire

    import control_plane.domains.approval_gate.queue as q_mod
    monkeypatch.setattr(q_mod, "_backoff_seconds", lambda _attempt: 0.05)

    sim = SubagentSimulator(
        fake_db,
        exploit_outcome="success",
        validator_outcome="needs_t3",
    )
    monkeypatch.setattr(orchestrator_module, "_run_agent", sim)

    await orchestrator_module.main()

    types = [t for t, _ in sim.calls]
    # Reporter should NOT run for the T3-denied finding (no validated rows
    # remain when the wait times out → empty validated_ids → no reporter).
    assert "validator" in types
    assert "reporter" not in types

    statuses = {f["status"] for f in fake_db.findings.values()}
    assert "archived" in statuses
    assert "submitted" not in statuses


@pytest.mark.asyncio
async def test_recon_failed_aborts(monkeypatch, fake_db, orchestrator_module):
    """If recon ends with recon_failed, the orchestrator aborts via sys.exit."""
    sim = SubagentSimulator(fake_db, exploit_outcome="success")

    async def failing_recon(agent_type, env_extras, claude_cmd, model_id=None):
        if agent_type == "recon":
            fake_db.scan_jobs[env_extras["SCAN_JOB_ID"]]["status"] = "recon_failed"
            return 1
        return await sim(agent_type, env_extras, claude_cmd, model_id=model_id)

    monkeypatch.setattr(orchestrator_module, "_run_agent", failing_recon)
    monkeypatch.setenv("SKIP_SCANNER", "1")
    monkeypatch.setenv("SKIP_EXPLOIT", "1")
    monkeypatch.setenv("SKIP_REPORT", "1")

    with pytest.raises(SystemExit):
        await orchestrator_module.main()


# ---------------------------------------------------------------------------
# Helper-function unit tests
# ---------------------------------------------------------------------------


def test_missing_scanner_binaries_returns_list(orchestrator_module):
    """_missing_scanner_binaries returns names not on PATH."""
    missing = orchestrator_module._missing_scanner_binaries()
    assert isinstance(missing, list)
    # In the dev environment none of these are installed; expect all 6.
    assert all(b in orchestrator_module._SCANNER_BINARIES for b in missing)


def test_flag_parses_truthy(orchestrator_module, monkeypatch):
    monkeypatch.setenv("FOO", "1")
    monkeypatch.setenv("BAR", "TRUE")
    monkeypatch.setenv("BAZ", "yes")
    monkeypatch.setenv("QUX", "no")
    assert orchestrator_module._flag("FOO") is True
    assert orchestrator_module._flag("BAR") is True
    assert orchestrator_module._flag("BAZ") is True
    assert orchestrator_module._flag("QUX") is False
    assert orchestrator_module._flag("MISSING") is False


def test_jwt_jti_extracts_payload(orchestrator_module):
    token = "header." + _b64({"jti": "abc-123"}) + ".sig"
    assert orchestrator_module._jwt_jti(token) == "abc-123"


def test_jwt_jti_returns_unknown_on_garbage(orchestrator_module):
    assert orchestrator_module._jwt_jti("not.a.jwt") == "unknown"
    assert orchestrator_module._jwt_jti("only-one-segment") == "unknown"
