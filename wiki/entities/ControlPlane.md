# ControlPlane
**Type:** component
**Summary:** FastAPI + domain-driven orchestrator under `control-plane/src/control_plane/`. Holds the business logic the sub-agents and MCPs depend on: scope-JWT issuance, approval-gate state machine, EV scoring, recon service, evidence hash-chain, and security validation.

## Key Facts
- Layout: `core/` (security validation, path guards, `routing` model cost-tiers, `flags` feature flags, `shared` DDD base classes) + `domains/` + `infrastructure/database.py` (SQLAlchemy 2.0 async, asyncpg).
- Bounded contexts under `domains/`:
  - `scope_management` — `jwt_issuer.py` (RS256 4096-bit, 168h max, JTI revocation), `ingest_service.py` (H1/Arkadiyt scope normalize + upsert), `integrations/hackerone.py`.
  - `approval_gate` — `services.py` (`classify_tier`, T1/T2/T3 transitions), `aggregates.py`, `queue.py` (`enqueue/approve/reject/wait_for_approval`, exp backoff 5s→60s, T3 distinct-actor), `finding_status_cache.py`.
  - `program_ranking` — `scoring_service.py` (EV formula: payout, saturation, ops, fit, cve).
  - `recon` — `service.py` (subfinder → scope_filter → httpx live → hypothesis), `tool_runner.py`, `__main__.py` container entry.
  - `evidence_management` — `blob_store.py` (local/R2/S3), `hash_chain_service.py`.
  - `safety` — kill switch + rate limiting.
- ~6,700 LOC Python across the repo; control-plane tests in `control-plane/tests/` (21 files).

## Connections
- [[Orchestrator]] — drives the domains during a scan
- [[McpServers]] — `ev-mcp` has a workspace dep on control-plane
- [[scope-jwt-trust-boundary]] — `jwt_issuer.py` is the trusted signer
- [[approval-tiers]] — implemented in `domains/approval_gate`
- [[ev-scoring]] — implemented in `domains/program_ranking`

## Sources
- docs/codebase-summary.md — 2026-05-01
- docs/system-architecture.md — 2026-05-01
