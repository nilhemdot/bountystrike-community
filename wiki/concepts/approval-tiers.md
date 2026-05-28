# Approval Tiers
**Definition:** A tiered human-in-the-loop gate (T0/T1/T2/T3) in `domains/approval_gate` that a finding must clear before a report is submitted, with severity-scaled review rigor.
**Why it matters:** Keeps a human accountable for outbound action; high-impact or novel findings cannot auto-submit.

## How it works
`classify_tier` assigns a tier by impact: T1 = LLM review (low impact); T2 = single human (CVSS>7, limited PII); T3 = two distinct human actors, 30-min SLA (CVSS>9, novel chain, PII>10, sandbox exec). `queue.py` handles `enqueue/approve/reject/wait_for_approval` with exponential backoff (5s→60s); the `approval_queue` table enforces T3 distinct-actor via `approver_id` + `approver_id_2`. The operator drives it with `scripts/approve.py` (`list/show/approve/reject`). The orchestrator enqueues, polls, then relaunches the agent with the returned approval token. A PreToolUse hook (`pretool_approval_gate.py`) blocks any `mcp__*__submit_*` call lacking approval.

## Related
- [[finding-lifecycle]] — the `approval_pending_t*` states
- [[Orchestrator]] — enqueue + poll + relaunch loop
- [[ControlPlane]] — domain implementation
- [[kill-switch]] — the other safety gate on tool calls

## Sources
- docs/system-architecture.md §2 — 2026-05-01
- infra/sql/04_approval_queue.sql — current
