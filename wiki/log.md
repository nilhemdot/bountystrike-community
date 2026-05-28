# Wiki Log

## [2026-05-28] setup | Initial wiki created
Project: BountyStrike v5
Type: brownfield
Stack: Python 3.12 (FastAPI + DDD, uv) · 15 MCP servers · Postgres 17 + pgvector · Redis · Hatchet · Langfuse · R2
Team: solo
Pain points: losing context between sessions; documenting decisions

## [2026-05-28] bootstrap | Wiki bootstrapped from existing codebase
Sources: docs/codebase-summary.md, docs/system-architecture.md (both 2026-05-01 @ e9b4b77), repo structure scan.
Created 5 entity pages (ControlPlane, McpServers, OracleMcp, SubAgents, Orchestrator),
5 concept pages (finding-lifecycle, scope-jwt-trust-boundary, approval-tiers, ev-scoring, kill-switch),
2 decision records (scope-enforced-at-network-not-prompt, deterministic-oracles).
Filled overview.md and index.md.
Noted freshness caveat: base docs predate the Phase 0 truth-in-claims correction and the re-added core/routing matrix — verify specific claims against current code.
