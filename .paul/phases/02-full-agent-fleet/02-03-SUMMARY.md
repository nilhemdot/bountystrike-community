---
phase: 02-full-agent-fleet
plan: 03
subsystem: agents
tags: [exploit-agent, docker-sandbox, egress-gate, postgres-enum, iptables, orchestrator]

requires:
  - phase: 02-02
    provides: DockerDriver substrate + bs5-egress-gate sidecar + bs5/sandbox-runtime image
provides:
  - exploit-agent spec reconciled to the docker sandbox substrate (no Firecracker in run path)
  - finding_status enum: exploit_failed_oos / _timeout / _crash (migration 13)
  - orchestrator _exploit_one SANDBOX_DRIVER=docker + BS_EGRESS_GATE_URL handoff
  - register-before-start static-IP fix (DockerDriver._reserve_ip + gate IPAMConfig fallback)
  - one-shot live dry-run runner (exploit_dryrun.py + exploit_dryrun_netns.sh)
affects: [02-04 ai-vuln-hunter/reporter, 02-05 anti-slop/killswitch]

tech-stack:
  added: []
  patterns:
    - "register-before-start egress gating via pinned --ip (IPAMConfig readable pre-start)"
    - "netns wrapper: run host-driver work in a --network host container to reach a host-net sidecar (WSL/docker-desktop)"

key-files:
  created: [infra/sql/13_phase2_exploit_failed_status.sql, scripts/exploit_dryrun.py, scripts/exploit_dryrun_netns.sh, tests/test_exploit_one_wiring.py]
  modified: [.claude/agents/exploit-agent.md, scripts/orchestrator.py, tests/integration/test_schema_vs_spec_contract.py, mcp/sandbox-mcp/src/sandbox_mcp/drivers/docker.py, infra/sandbox/egress-gate/egress_gate.py]

key-decisions:
  - "Verdict map lives in the agent spec (Step 6); runner mirrors it to prove the FSM handoff without the LLM subprocess"
  - "Fix the register-before-start 409 in the driver (option B) rather than accept on 02-02 proof"

patterns-established:
  - "Bridge IPs bind at docker start; any pre-start firewall keyed by container IP must pin --ip at create"

duration: ~90min
started: 2026-06-01T00:05:00Z
completed: 2026-06-01T01:30:00Z
---

# Phase 2 Plan 03: Exploit-Agent Wiring Summary

**Wired exploit-agent onto the 02-02 docker sandbox: added the exploit_failed_* enum, reconciled the spec (Firecracker→docker, result.verdict, +6 MCP grants), injected the SANDBOX_DRIVER handoff, and proved the full success/denied FSM handoff live — fixing a register-before-start gate defect the live runner uncovered.**

## Performance

| Metric | Value |
|--------|-------|
| Duration | ~90 min |
| Tasks | 3 auto + 1 human-verify |
| Files modified | 9 (4 new, 5 modified) |

## Acceptance Criteria Results

| Criterion | Status | Notes |
|-----------|--------|-------|
| AC-1: enum has exploit_failed_oos/timeout/crash | Pass | migration 13 applied live + idempotent; cast-valid; contract test green |
| AC-2: spec on docker substrate (no Firecracker run-path) | Pass | 1 Firecracker mention = Phase-3 deferral note only |
| AC-3: spec reads result.verdict; +6 mcp grants | Pass | static asserts in test_exploit_one_wiring.py |
| AC-4: orchestrator hands SANDBOX_DRIVER=docker + gate URL | Pass | hermetic env-capture tests |
| AC-5: sandbox fail-closed on unreachable gate | Pass | fired live during first dry-run |
| AC-6: exploit→sandbox→FSM handoff (success + denied) | Pass | live: ALLOWED→exploit_pending_validation, DENIED→exploit_failed_oos |

## Verification

- `pytest tests/test_exploit_one_wiring.py mcp/sandbox-mcp/tests/test_docker_driver.py test_sandbox_mcp.py` → 44 passed
- live `exploit_dryrun_netns.sh`: `ALLOWED verdict=success→exploit_pending_validation` · `DENIED verdict=egress_blocked→exploit_failed_oos` · rows cleaned · no orphan sandbox containers
- ruff clean on all touched files

## Deviations from Plan

| Type | Count | Impact |
|------|-------|--------|
| Auto-fixed | 1 | Driver/gate defect — essential, security-preserving |
| Scope additions | 1 | netns wrapper (env-specific test harness) |
| Deferred | 1 | Logged below |

**1. register-before-start 409 (driver/gate defect)** — Found during T4. The driver registers the PoC container with the gate (which `docker inspect`s for its IP) *before* `docker start`, but bridge IPs bind at start → gate 409 "no network IP yet" → verdict=error. Fix: `DockerDriver._reserve_ip` pins a deterministic in-subnet `--ip` at create (hash(run_id)+attempt-retry on clash); gate `_container_ip` reads `IPAMConfig.IPv4Address` (populated at create) before `.IPAddress`, validating each token as IPv4. Preserves fail-closed (iptables before payload). Gate image rebuilt. Files: `drivers/docker.py`, `egress-gate/egress_gate.py`. Verified by the green live dry-run. **Beyond original files_modified** — a real bug the hermetic 02-02 path missed.

**2. netns wrapper (scope addition)** — `exploit_dryrun_netns.sh`. WSL/docker-desktop puts the host-net gate in the docker-VM netns; the host driver process can't reach `localhost:9090`. Wrapper runs the runner in a `--network host` container (shares the gate+pg loopback) with docker.sock + host docker CLI mounted. Documents the production-faithful path.

**Deferred:** Add a hermetic `_reserve_ip` regression test (determinism + in-subnet + attempt-shift) and a gate IPAMConfig-fallback unit test — the fix is live-proven but not yet unit-pinned. (origin: T4)

## Issues Encountered

| Issue | Resolution |
|-------|------------|
| DENIED command exited 0 (`; echo done` masked curl failure) → driver scored success | Changed to `curl -fsS` with no trailing echo so the blocked connection propagates non-zero → CRASH+blocked → egress_blocked |

## Next Phase Readiness

**Ready:** exploit-agent fully wired onto the live docker substrate; full hypothesis→exploit_pending_validation / exploit_failed_oos FSM proven end-to-end. 02-04 (ai-vuln-hunter/cloud-recon/reporter) can build on a working exploit lane.

**Concerns:** `_reserve_ip`/gate fallback live-proven but lacking dedicated unit tests (deferred above). netns wrapper is WSL-specific; native-Linux operators run the driver host-side directly.

**Blockers:** None.

---
*Phase: 02-full-agent-fleet, Plan: 03*
*Completed: 2026-06-01*
