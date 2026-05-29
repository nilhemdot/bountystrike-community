---
phase: 01-community-edition-mvp
plan: 01
subsystem: database
tags: [postgres17, pgvector, pgvectorscale, vectorscale, pg_search, paradedb, diskann, bm25, docker, cargo-pgrx]
requires:
  - phase: 00-truth-in-claims-foundation
    provides: hybrid monorepo + AGPL/Apache license roots + infra/sql baseline schema
provides:
  - custom bs-postgres:pg17 image (vector + vectorscale + pg_search)
  - DiskANN index migration (10_phase1_vectorscale_indexes.sql)
  - BM25 index migration (11_phase1_paradedb_search.sql, current USING bm25 API)
  - database-patterns.md Phase 1 extension-traps reference
affects: [01-02 hatchet-evidence-store, semantic-dedup, triage-ranking]
tech-stack:
  added: [pgvector 0.8.0, vectorscale 0.9.0, pg_search 0.23.5, cargo-pgrx 0.16.1]
  patterns: [custom-pg-image-multistage-build, glibc-base-for-pgrx, shared_preload_libraries=pg_search]
key-files:
  created: [infra/docker/Dockerfile.postgres-bs, infra/sql/10_phase1_vectorscale_indexes.sql, infra/sql/11_phase1_paradedb_search.sql]
  modified: [infra/docker/docker-compose.yml, infra/sql/00_extensions.sql, docs/learnings/database-patterns.md]
key-decisions:
  - "glibc postgres:17-bookworm base, not Alpine/musl (pgrx + ParadeDB glibc-only)"
  - "shared_preload_libraries=pg_search added to compose command (pg_search hard requirement)"
  - "pre-existing ruff debt is out of 01-01 scope (touched zero .py)"
patterns-established:
  - "Custom PG extension images: pin all + match cargo-pgrx to crate pgrx via cargo metadata"
  - "First-boot init migrations: plain CREATE INDEX IF NOT EXISTS, never CONCURRENTLY"
duration: ~25min
completed: 2026-05-29
---

# 01-01 SUMMARY — DB Foundation (PG17 + pgvector + vectorscale + pg_search)

**Executed:** 2026-05-29 | **Status:** COMPLETE (all 4 tasks; all ACs empirically verified)
**Loop:** PLAN ✓ → APPLY ✓ → UNIFY ○

## Outcome

Custom `bs-postgres:pg17` image builds and runs with all three extensions
active in a single `docker compose up -d postgres` cycle. Phase 1 DiskANN +
BM25 migrations apply cleanly and idempotently on first boot. Zero regression
to existing schema.

## Resolved pinned versions

| Component | Pin | Notes |
|-----------|-----|-------|
| Postgres base | `postgres:17-bookworm` → **17.10 (Debian 17.10-1.pgdg12+1)** | glibc, NOT Alpine (see deviation) |
| pgvector | **v0.8.0** | built from source at tag (`make install`) |
| vectorscale (pgvectorscale) | **0.9.0** | built from source via cargo-pgrx; pgrx auto-matched to **0.16.1** via `cargo metadata` |
| pg_search (ParadeDB) | **v0.23.5** | prebuilt `.deb`: `postgresql-17-pg-search_0.23.5-1PARADEDB-bookworm_amd64.deb` |
| Image | `bs-postgres:pg17` | id `a5207bc9f2c0`, 837MB, manifest `sha256:a5207bc9…` |

Base-image RepoDigest not captured locally (image present without digest ref);
the resolved server_version **17.10** is recorded above as the concrete pin
proof. A future hardening item can pin `FROM ...@sha256:<digest>` after a
`docker pull postgres:17-bookworm` on the build host.

## Deviations from plan

1. **glibc bookworm base, NOT Alpine/musl** (plan-permitted fallback, AC-1/AC-4,
   audit G4). pgvectorscale (Rust/pgrx) documents only glibc targets and ParadeDB
   ships `.deb` only for glibc distros. Going straight to bookworm avoided a
   near-certain musl build failure. Recorded as the intended fallback path.
2. **Added `-c shared_preload_libraries=pg_search` to docker-compose postgres
   `command:`** — NOT in the plan's Task 2 spec, but pg_search's BM25 index AM +
   background worker require the shared library at server start (verified
   Context7 /paradedb/paradedb §self-hosted/extension). Without it AC-3/AC-4 fail.
   Justified spec-gap fix within Task 2's own file; no other service touched.
3. **`uv run ruff check .` is NOT clean (40 pre-existing errors)** — all in
   pre-existing `.py` files (control-plane/, mcp/, scripts/, tests/). This plan
   touched **zero** `.py` files (only `.md`/`.sql`/Dockerfile/`.yml`), so it
   introduced **no new** violations and made **no** `control_plane/domains/`
   changes (boundary §585 honored, AC-6 §632 satisfied). The literal AC-6
   "ruff exits 0" is unsatisfiable without violating the no-domain-edits
   boundary. **Flagged for UNIFY / user:** pre-existing ruff debt is out of
   01-01 scope.

## BM25 / DiskANN confirmation

- BM25 uses the **current `CREATE INDEX … USING bm25 (id,url,parameter,cwe,oracle_method) WITH (key_field='id')`** API — NOT `paradedb.create_bm25()` (audit G2).
- BM25 indexes only **existing** findings columns; no `title`/`description` (audit G1 — verified against 01_schema.sql).
- Extension name is **`vectorscale`**, not `pgvectorscale`, everywhere in `infra/sql/` (`grep -rn pgvectorscale infra/sql/` empty — CLAUDE.md #17).
- DiskANN init uses plain `CREATE INDEX IF NOT EXISTS` (no CONCURRENTLY in init path, audit G6).

## docker-compose change (before → after)

```yaml
# before
postgres:
  image: pgvector/pgvector:pg17
# after
postgres:
  build: {context: ../.., dockerfile: infra/docker/Dockerfile.postgres-bs}
  image: bs-postgres:pg17
  command: [ ... existing tuning ..., -c, shared_preload_libraries=pg_search ]
```

## Files

**New:** `infra/docker/Dockerfile.postgres-bs`, `infra/sql/10_phase1_vectorscale_indexes.sql`, `infra/sql/11_phase1_paradedb_search.sql`
**Modified:** `infra/docker/docker-compose.yml`, `infra/sql/00_extensions.sql`, `docs/learnings/database-patterns.md`

## AC results (all empirically verified against live container)

| AC | Result |
|----|--------|
| AC-1 image builds + 3 extensions installable | ✓ (build exit 0) |
| AC-2 compose build stanza + valid config | ✓ |
| AC-3 vector+vectorscale+pg_search active | ✓ (3 rows) |
| AC-4 DiskANN + BM25 migrations apply | ✓ (both indexes present) |
| AC-5 PG17 + tables (programs/scopes/findings/evidence_artifacts/audit_log) intact | ✓ (17.10, 5 tables) |
| AC-6 no domain changes / ruff | ◐ no-domain ✓; ruff has pre-existing debt (deviation 3) |
| AC-7 all versions pinned, pin-gate clean | ✓ |
| AC-8 idempotent re-apply | ✓ (NOTICE skip, exit 0) |
| G8 functional smoke (diskann + bm25 query) | ✓ (both exit 0) |

## Traps encoded in database-patterns.md

9-item "Phase 1 — Extension Traps" section: vectorscale name, ParadeDB image
drop, custom-image build order, boto3/R2 (for 01-02), DiskANN no-CONCURRENTLY,
BM25 current API, pg_search preload requirement, no title/description columns,
pin-everything + cargo-pgrx version-match.

## Handoff note for 01-02

- Hatchet v1 task API (`@hatchet.task()`, `aio_` async prefix, Pydantic inputs).
- R2 evidence wiring: `aioboto3` + pin `boto3 < 1.36` (or `request_checksum_calculation="when_required"`).
- A throwaway `infra/docker/.env` was created for local verification (gitignored); real secrets needed for deploy.
- Pre-existing ruff debt (40 errors) should be triaged separately — not a 01-01 regression.
