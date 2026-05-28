# Orchestrator
**Type:** component
**Summary:** `scripts/orchestrator.py` — the scan-job entry point. Runs one bounty program through the full pipeline, fanning out parallel sub-agents and pausing at the approval gate.

## Key Facts
- Pipeline: `recon → scanner (skippable) → exploit → [T2 enqueue+poll+relaunch] → validator → [T3 enqueue+poll+relaunch] → reporter`.
- Required env: `PROGRAM_HANDLE`, `PLATFORM`, `SCOPE_JWT`, `DATABASE_URL`.
- Phase skips: `SKIP_SCANNER`, `SKIP_EXPLOIT`, `SKIP_REPORT`.
- Concurrency tunables: `MAX_VALIDATORS` (5), `MAX_EXPLOITS` (3), `MAX_REPORTERS` (3).
- Time/timeout tunables: `APPROVAL_TIMEOUT`, `RECON_TIMEOUT`, `SCAN_TIMEOUT`, `TIME_BUDGET_MIN`.
- Writes `scan_jobs` (queued → complete) and emits a final summary (hypotheses, validated, submitted).

## Connections
- [[SubAgents]] — spawns each phase's agent
- [[ControlPlane]] — calls approval-gate queue + recon service
- [[finding-lifecycle]] — advances findings through the status machine
- [[approval-tiers]] — enqueues T2/T3 and relaunches with the approval token

## Sources
- scripts/orchestrator.py — current
- docs/codebase-summary.md §scripts — 2026-05-01
