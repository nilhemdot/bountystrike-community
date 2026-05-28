# Finding Lifecycle
**Definition:** The `finding_status` ENUM (16 states) in `infra/sql/01_schema.sql` that every candidate vulnerability moves through, from recon hypothesis to confirmed/rejected.
**Why it matters:** It is the single source of truth for where a finding is; orchestrator phases, oracle verdicts, and approval tiers are all gated on it.

## How it works
`hypothesis → exploit_attempt → exploit_candidate → validation_pending → validated → dedup_check → approval_pending_t1|t2|t3 → approved → submitted → confirmed | rejected | duplicate | wont_fix | archived`. Oracle verdicts drive `validation_pending → validated` (TPR=1.0 path) or `→ rejected` (FPR=0.0 path); dedup-mcp drives `dedup_check → duplicate` vs. an approval tier; the approval gate drives `approval_pending_t* → approved | rejected`. Status updates use an optimistic lock via state-mcp.

## Related
- [[OracleMcp]] — produces the validated/rejected verdict
- [[approval-tiers]] — the t1/t2/t3 branch
- [[deterministic-oracles]] — why validated/rejected is trustworthy
- [[McpServers]] — dedup-mcp + state-mcp drive transitions

## Sources
- infra/sql/01_schema.sql — current
- docs/system-architecture.md §6 — 2026-05-01
