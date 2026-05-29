# Enterprise Plan Audit Report

**Plan:** .paul/phases/01-community-edition-mvp/01-01-PLAN.md
**Audited:** 2026-05-29
**Verdict:** Conditionally acceptable (was: not-acceptable as written — two release-blocking defects would have produced a build/migration that fails at apply time; both remediated in place)

---

## 1. Executive Verdict

As written, the plan would **fail at apply time** for two independent, deterministic reasons:

1. **The BM25 migration targets columns that do not exist.** `infra/sql/01_schema.sql` defines `findings(id, job_id, program_handle, platform, cwe, url, parameter, status, evidence_hash, oracle_method, validator_model, deduplication_key, embedding, created_at, updated_at)`. There is **no `title` and no `description` column.** Task 3's `11_phase1_paradedb_search.sql` indexes `title` and `description`. The migration raises `column "title" does not exist` and AC-4 can never pass.

2. **The BM25 migration uses the deprecated ParadeDB API.** The plan calls `paradedb.create_bm25(..., paradedb.field(...), paradedb.tokenizer(...))` and the verify step greps for the auto-suffixed index name `findings_bm25_bm25_index`. ParadeDB's maintainers state plainly (Context7, `/paradedb/paradedb`): *"Avoid using legacy docs as syntax has changed dramatically."* The current API is `CREATE INDEX <name> ON <table> USING bm25 (<cols>) WITH (key_field='id')`. Latest release is **v0.23.5**, not the plan's "0.14.x." The `CALL`-based function and its index-naming convention no longer exist in a current pg_search build, so the migration fails regardless of defect #1.

Beyond those, the plan **pins nothing** — pgvector "e.g. v0.8.0", vectorscale "e.g. 0.6.0", ParadeDB "e.g. 0.14.x" are illustrative examples, not binding pins. A plan whose stated purpose is "a single, **reproducible** Postgres image" cannot ship with floating example tags. Two of the three example tags are already stale (vectorscale latest 0.9.0; ParadeDB latest v0.23.5).

Would I approve this for production accountable? **No, as written.** With the must-have and strongly-recommended fixes applied (below), **yes, conditionally** — the conditions being that APPLY honours the pinned versions and the schema-column decision, and that the Alpine/musl build feasibility is proven by AC-1 actually building (not merely asserted).

## 2. What Is Solid

- **The split rationale and scope discipline.** Carving the 5-subsystem ROADMAP line into 01-01 (DB foundation) + 01-02 (Hatchet/R2) is correct PAUL sizing and keeps a single concern auditable. The `<boundaries>` block is unusually disciplined — it freezes Phase 0 artifacts, domain logic, existing SQL files (00–09), and pyproject pins explicitly. Do not weaken it.
- **The `vectorscale` (not `pgvectorscale`) extension-name handling is correct** and verified against the timescale README and CLAUDE.md trap #17. The `CASCADE` on `CREATE EXTENSION vectorscale` is correct (it depends on `vector`). The negative test (`! grep -q pgvectorscale` in SQL CREATE statements) is a sound guard.
- **The DiskANN index parameters are valid.** `num_neighbors=64` (default 50, range 10–1000) and `search_list_size=100` (default 100) are in-range per the upstream README/Context7. The HNSW-coexistence-then-DiskANN-at-scale narrative is accurate.
- **Custom-image rationale is correct.** ParadeDB did drop pgvectorscale from its bundle (trap #18); a custom image is the right call and the `build:` stanza approach with `image: bs-postgres:pg17` is sound.
- **`docker compose config --quiet` as a YAML-validity gate** is the right verification primitive.

## 3. Enterprise Gaps Identified

**G1 (release-blocking) — BM25 indexes non-existent columns.** See §1.1. The `findings` table has no `title`/`description`. The plan must either (a) index columns that exist and are meaningful for keyword triage (`cwe`, `url`, `parameter`, `oracle_method`), or (b) add `title`/`description` columns — but adding columns mutates the frozen schema and crosses into out-of-scope territory. The audit chooses (a): index existing text columns. This keeps the schema frozen per `<boundaries>`.

**G2 (release-blocking) — deprecated ParadeDB API + wrong index-name assumption.** See §1.2. Must migrate to `CREATE INDEX ... USING bm25 (...) WITH (key_field='id')`. The idempotency guard must check the *actual* index name we choose (`idx_findings_bm25`), not the legacy `_bm25_index` suffix. Verify-step grep must change from `create_bm25` to `USING bm25`.

**G3 (release-blocking) — no version pins; "reproducible" claim is false.** pgvector, vectorscale, ParadeDB are all "e.g." examples. A reproducible image requires concrete pins. Audit pins: **pgvectorscale 0.9.0, ParadeDB pg_search 0.23.x (v0.23.5 head), pgvector 0.8.0** — with the explicit instruction that APPLY confirm the exact tag against the upstream release page at build time and record it in the SUMMARY. Base image must be pinned by digest or at minimum a fixed `postgres:17-alpine` patch tag, not a moving major tag.

**G4 (release-blocking risk) — Alpine/musl build feasibility is unverified yet asserted as MUST.** Upstream timescale/pgvectorscale documents glibc Docker images and source builds; it does **not** list Alpine/musl as a supported target, and pg_search (tantivy/Rust) under musl is likewise unverified. The plan's own `<output>` anticipates "Alpine build complexity → Ubuntu base." Mandating `postgres:17-alpine` as a hard MUST while the toolchain support is unknown is a latent build failure. Fix: keep Alpine as the *preferred* base but add an explicit **glibc fallback contingency** (`postgres:17-bookworm`/Debian) that AC-1 may fall back to, with the deviation recorded. The success criterion is "all three extensions load," not "the base is Alpine."

**G5 (strongly-rec) — `cargo pgrx install` invocation is incomplete and will not build.** Upstream requires installing the *matching* `cargo-pgrx` version (`cargo install --locked cargo-pgrx --version <pgrx-version-from-Cargo.lock>`) and running `cargo pgrx init --pg17 $(which pg_config)` before `cargo pgrx install`. The plan's `cargo pgrx install --release --pg-config $(which pg_config)` skips both and will fail with a pgrx-version mismatch or uninitialized-pgrx error.

**G6 (strongly-rec) — `CREATE INDEX CONCURRENTLY` in the init path is the wrong tool and can leave INVALID indexes.** On first-boot `/docker-entrypoint-initdb.d`, the table is empty — CONCURRENTLY buys nothing and cannot run inside a transaction block (which the init runner may impose). If interrupted it leaves an INVALID index that `IF NOT EXISTS` will then *skip*, masking the failure permanently. For a first-boot migration, use plain `CREATE INDEX IF NOT EXISTS`. If CONCURRENTLY is retained for a live-apply path, add an INVALID-index detection + `REINDEX`/drop-and-rebuild recovery note.

**G7 (strongly-rec) — no apply-failure / non-idempotency evidence.** AC-4 asserts "exit 0 with no ERROR lines" but never re-runs the migrations to prove idempotency. A migration that passes once but errors on re-apply is a silent operational landmine (initdb only runs on first boot, so re-apply is the realistic operator action). Add an AC that runs both SQL files **twice** and asserts the second run is also clean.

**G8 (strongly-rec) — extension/library load is verified by name only, not by function.** AC-3 checks `pg_extension` rows but never proves the shared libraries actually *work*. A `.so` can register its catalog row yet fail at first index build (musl symbol mismatch, ABI skew). Add a smoke assertion that actually builds one DiskANN and one BM25 index and runs a trivial query against each — proving the libraries are functionally loaded, not just catalogued.

**G9 (can-defer) — DiskANN storage_layout / SBQ not specified for 1536-dim.** For 1536-dim vectors, `storage_layout='memory_optimized'` with 2-bit SBQ is the upstream-recommended default and yields ~16× compression; the plan omits it (defaults apply). Acceptable to defer — the default auto-selects sensibly — but should be captured as a tuning note.

**G10 (can-defer) — no image-provenance/SBOM step.** The custom image has no cosign/SBOM hook. The plan correctly scopes CI out (`.github/workflows/` frozen), and PROJECT.md already commits to Sigstore/SLSA L3 globally. Safe to defer to the CI-hardening follow-up the plan names.

**G11 (can-defer) — pgvector source-vs-Alpine-package ambiguity.** Task 1 offers "Alpine package OR build from source" without deciding. Minor; the build will resolve it. Pin the chosen path in SUMMARY.

## 4. Upgrades Applied to Plan

### Must-Have (Release-Blocking)

| # | Finding | Plan Section Modified | Change Applied |
|---|---------|----------------------|----------------|
| 1 | BM25 indexes non-existent `title`/`description` columns (G1) | Task 3 action + AC-4 + verification | Rewrote `11_phase1_paradedb_search.sql` spec to index existing `findings` text columns (`url`, `parameter`, `cwe`, `oracle_method`) with `key_field='id'`; added explicit note that `findings` has no title/description and the schema stays frozen |
| 2 | Deprecated ParadeDB `create_bm25` API + wrong index name (G2) | Task 3 action, Task 3 verify, AC-4 | Replaced `CALL paradedb.create_bm25(...)` with current `CREATE INDEX idx_findings_bm25 ... USING bm25 (...) WITH (key_field='id')`; idempotency via `IF NOT EXISTS`; verify greps `USING bm25` not `create_bm25`; AC-4 checks `bm25` access method by index `idx_findings_bm25` |
| 3 | No version pins — "reproducible" claim false (G3) | frontmatter-adjacent objective note + Task 1 action + new AC-7 | Added explicit pins: pgvector 0.8.0, pgvectorscale 0.9.0, ParadeDB pg_search 0.23.x; base image pinned to a fixed `postgres:17-alpine` patch tag (no moving major); APPLY must record exact resolved tags + digest in SUMMARY; added AC-7 asserting no `:latest` / unpinned `e.g.` tags remain in the Dockerfile |
| 4 | Alpine/musl build feasibility unverified but mandated (G4) | Task 1 action + AC-1 | Demoted Alpine from hard-MUST to preferred-with-glibc-fallback (`postgres:17-bookworm`); success = "all three extensions load," base recorded as a deviation if fallback used; AC-1 now the empirical feasibility gate |

### Strongly Recommended

| # | Finding | Plan Section Modified | Change Applied |
|---|---------|----------------------|----------------|
| 5 | Incomplete `cargo pgrx` invocation (G5) | Task 1 action | Added `cargo install --locked cargo-pgrx --version <pinned-pgrx-from-Cargo.lock>` + `cargo pgrx init --pg17 $(which pg_config)` before `cargo pgrx install --release`; noted pgrx-version-match requirement |
| 6 | CONCURRENTLY wrong for init path; INVALID-index masking (G6) | Task 3 action (10_ file) + verification | Switched DiskANN migration to plain `CREATE INDEX IF NOT EXISTS` (first-boot, empty table); added comment + verification note on INVALID-index detection if CONCURRENTLY is ever used in a live path |
| 7 | No idempotency / re-apply evidence (G7) | new AC-8 | Added AC-8: both 10_ and 11_ SQL files run twice; second run must also exit 0 with no ERROR; byte-identical index set after both runs |
| 8 | Extensions verified by name, not function (G8) | AC-3 (extended) + Task 3 verify | Added functional smoke: build one DiskANN + one BM25 index and run a trivial query against each, proving `.so` libraries load functionally (catches musl/ABI skew) |

### Deferred (Can Safely Defer)

| # | Finding | Rationale for Deferral |
|---|---------|----------------------|
| 9 | DiskANN `storage_layout`/SBQ tuning for 1536-dim (G9) | Upstream defaults auto-select sensibly (2-bit SBQ < 900 dims, else 1-bit); a tuning note in database-patterns.md is sufficient. Captured as a learnings note, not a blocking change. |
| 10 | Image provenance / cosign / SBOM (G10) | Plan explicitly freezes `.github/workflows/` and names CI hardening as a follow-up; PROJECT.md already commits to SLSA L3 globally. No new risk introduced by this plan. |
| 11 | pgvector source-vs-package path undecided (G11) | Cosmetic; build resolves it deterministically once a pin is chosen. APPLY records the chosen path in SUMMARY. |

## 5. Audit & Compliance Readiness

- **Defensible evidence:** After fixes, AC-1 proves the image builds, AC-3 proves extensions load *functionally* (not just by catalog row), AC-7 proves no floating tags, AC-8 proves idempotency. This is a defensible chain. Before fixes, the plan would have produced a green checkmark on AC-4 that was impossible to actually satisfy — a false audit signal.
- **Silent-failure prevention:** G6 (INVALID-index masking by `IF NOT EXISTS`) and G8 (name-only extension check) were the two silent-failure vectors; both are now closed. The "no ERROR lines" assertion is now backed by a re-run.
- **Post-incident reconstruction:** SUMMARY now must record exact resolved extension tags + base-image digest + chosen base (Alpine vs glibc fallback). Without G3's pinning, a future "it built last month" incident would be unreconstructable.
- **Ownership:** Single-concern plan, clear `<boundaries>`, no cross-domain blast radius. Acceptable.
- **Would fail a real audit before fixes** on: reproducibility (floating tags), and a verification criterion (AC-4) that cannot be met by the artifact it audits. Both remediated.

## 6. Final Release Bar

**Must be true before this plan ships (post-APPLY):**
- AC-1 actually builds the image (Alpine or recorded glibc fallback) — this is the real feasibility proof, not an assertion.
- The BM25 index targets existing columns and uses the `USING bm25` API; AC-4 passes against the real schema.
- All three extensions load *and function* (AC-3 smoke), proving no musl/ABI breakage.
- Exact extension tags + base digest recorded in SUMMARY (reproducibility).
- Re-running the migrations is clean (AC-8 idempotency).

**Remaining risk if shipped as-is (with fixes applied):** The Alpine/musl build may still fail at APPLY; the glibc fallback is the documented escape hatch, so this is a known-and-handled risk, not an unknown. SBQ tuning is left at defaults (acceptable for solo-mode scale <500K vectors). ParadeDB minor-version churn (0.23.x is fast-moving) means the pin must be re-confirmed at build time.

**Would I sign my name?** With the four must-have and four strongly-recommended fixes applied and AC-1/AC-3/AC-4/AC-8 actually passing at APPLY: **yes.** Without them: no — the artifact could not satisfy its own acceptance criteria.

---

**Summary:** Applied 4 must-have + 4 strongly-recommended upgrades. Deferred 3 items.
**Plan status:** Updated and ready for APPLY (conditionally acceptable; conditions are empirical — AC-1/AC-3/AC-4/AC-8 must pass at apply time).

---
*Audit performed by PAUL Enterprise Audit Workflow*
*Audit template version: 1.0*
