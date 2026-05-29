# Project State

## Project Reference

See: .paul/PROJECT.md (updated 2026-05-29)

**Core value:** Automated bug bounty hunting that produces only verified, non-duplicate findings
**Current focus:** Phase 1 — Community Edition MVP: The Moat

## Current Position

Milestone: v0.1 Community Edition MVP
Phase: 1 of 6 (Community Edition MVP: The Moat) — In Progress (3 of ~7 plans complete)
Plan: 01-03 (Evidence store / R2 write path) — COMPLETE (loop closed, all 6 ACs verified live)
Status: 01-01 + 01-02 committed (4c84845). 01-03 SHIPPED + UNIFIED: R2BlobStore checksum-safe (botocore Config when_required); EvidenceRecordingService.record() atomic+idempotent (advisory-lock SELECT-guard, not ON CONFLICT — no UNIQUE on content_hash); Hatchet record-evidence task + orchestrator trigger-record-evidence. 4/4 tests pass (2 unit + 2 integration live PG); live trigger SUCCEEDED + chain verified. 01-03 changes UNCOMMITTED.
Last activity: 2026-05-29 — UNIFY 01-03 (SUMMARY created, loop closed)

Progress:
- Milestone: [███░░░░░░░] ~27% (1 of 6 phases complete + Phase 1 progressing)
- Phase 0: [██████████] 100% (4/4 plans complete)
- Phase 1: [████░░░░░░] ~43% (3 of ~7 plans complete — 01-01 DB, 01-02 Hatchet, 01-03 Evidence)

## Loop Position

Phase 0 loop (00-04) — COMPLETE:
```
PLAN ──▶ APPLY ──▶ UNIFY
  ✓        ✓        ✓     [Loop complete — Phase 0 transition executed]
```

Phase 1 loop (01-01) — COMPLETE:
```
PLAN ──▶ APPLY ──▶ UNIFY
  ✓        ✓        ✓     [Loop closed — DB foundation shipped + verified]
```
Phase 1 loop (01-02) — COMPLETE:
```
PLAN ──▶ APPLY ──▶ UNIFY
  ✓        ✓        ✓     [Loop closed — Hatchet v1 runtime shipped + verified]
```
Phase 1 loop (01-03) — COMPLETE:
```
PLAN ──▶ APPLY ──▶ UNIFY
  ✓        ✓        ✓     [Loop closed — evidence write path shipped + verified live]
```
Note: 01-02 line SPLIT — 01-02 = Hatchet v1 only; 01-03 = evidence store (R2). Downstream +1 (now 7 plans 01-01..01-07).

## Accumulated Context

### Decisions

| Decision | Phase | Impact |
|----------|-------|--------|
| AGPLv3 Community + proprietary Enterprise + Apache 2.0 shared primitives | Init | Governs all licensing and repo layout |
| Deterministic verifier is the moat — no submission without evidence artifact | Init | Shapes Phase 1 scope and oracle TPR=1.0/FPR=0.0 requirement |
| SOC 2 clock must start at Phase 3 launch (Week 19), not enterprise launch | Init | Hard constraint on Phase 3 exit criteria |
| Position as AEV inside Gartner CTEM, not "bug bounty tool" | Init | Shapes Phase 4 marketing, pricing, and competitive framing |
| 2026-05-27: Enterprise audit on 00-01. Applied 3 must-have + 2 strongly-recommended. Verdict: conditionally acceptable → ready | Phase 0 | Plan now enforces full doc coverage, inline provenance, cost-overrun stop |
| 2026-05-27: 00-01 edit scope = v5 plan + research/ + support docs (NOT v6 docs, which hold the corrections as source-of-truth). v5 build plan edited in place despite being superseded, for fact-check consistency | Phase 0 | Stale claims corrected wherever they appear as live assertions; v6 docs left as correction record |
| 2026-05-27: Git committer identity set repo-local (3x3by3@gmail.com / nilhem) to enable baseline commit | Phase 0 | One-time; no global config touched |
| 2026-05-27: Monorepo approach = HYBRID (keep uv workspace, layer pnpm/Turborepo on top; no physical code move). Repo was already a uv workspace, not greenfield | Phase 0 | 00-02 scaffolds license roots + task layer; physical reorg deferred |
| 2026-05-27: Phase 0 split 2→3 plans (00-03 = OpenFeature + custom Unleash provider, separated due to no official Python provider per brief) | Phase 0 | Feature flags own plan |
| 2026-05-27: Audit on 00-02 added license-text integrity (verbatim canonical), LICENSES.md code↔license map, AGPL §13 network-use clause | Phase 0 | License posture audit-defensible before code ships |
| 2026-05-27: Audit on 00-03 — tier-enterprise flag is a config/rollout gate, NOT an authz boundary. Entitlement enforced server-side vs signed plan. Provider: TLS + secrets token + fail-closed on malformed response; context untrusted | Phase 0 | Prevents flag-as-authz privilege-escalation; sets the doctrine for all later tier gating |
| 2026-05-29: Audit on 00-04 — 5 must-have + 6 strongly-rec applied; 4 deferred. Verdict: conditionally acceptable. Caught 2 release-blocking license defects (foreign/.venv AGPL-stamping; AGPL-vs-Apache root collision) + unsound import-ban canary test. Doctrine: SPDX sweep uses six-root ALLOW-LIST (not git-walk+deny), shebang/PEP-263-cookie ordering, byte-equality idempotency proof, canary inside contract source_modules w/ trap-cleanup | Phase 0 | License sweep audit-defensible; import-ban enforcement sound. Residual risk: APPLY must encode allow-list, not regress to git-walk |
| 2026-05-29: Phase 1 split — 01-01 line (5 subsystems) split into 01-01 DB foundation (PG17 custom image pgvector+vectorscale+pg_search) + 01-02 Hatchet v1 + evidence store; downstream plans renumbered +1 (now 6 plans). Matches PAUL 2-3 task sizing | Phase 1 | Single-concern plans; DB foundation isolated from workflow/evidence wiring |
| 2026-05-29: Enterprise audit on 01-01 (DB foundation). Applied 4 must-have + 4 strongly-rec; deferred 3. Verdict: conditionally acceptable (was not-acceptable as written). Caught 2 release-blocking SQL defects — BM25 migration indexed non-existent findings.title/description cols, and used the DEPRECATED `paradedb.create_bm25()` API (current = `CREATE INDEX … USING bm25 … WITH (key_field='id')`, verified Context7). Also: zero version pins despite "reproducible" claim (pinned pgvector 0.8.0 / vectorscale 0.9.0 / pg_search v0.23.x + fixed base tag); Alpine/musl build unverified (added glibc bookworm fallback, AC-1 = empirical gate); incomplete cargo-pgrx invocation (match version + `pgrx init`); CONCURRENTLY in initpath → plain CREATE INDEX (INVALID-index masking); added AC-7 pins, AC-8 idempotency-on-re-apply, AC-3 functional .so smoke. Doctrine: migrations must target verified-existing columns; pg_search uses CREATE INDEX USING bm25 (not legacy CALL); pin all extensions+base; first-boot init = no CONCURRENTLY; verify extensions functionally not by catalog row | Phase 1 | DB foundation audit-defensible + reproducible; plan can now satisfy its own ACs at apply time |
| 2026-05-29: APPLY 01-02 (Hatchet v1). hatchet-lite v0.86.18 + dedicated hatchet-postgres in compose; all 8 ACs verified LIVE (engine healthy, worker registered bs-heartbeat, triggered run returned result/SUCCEEDED). 7 deviations: (1) topology = hatchet-lite Postgres-only (plan said engine+RabbitMQ) — lite uses PG as both store+queue, AC-8 isolation kept, 1 fewer container; (2) replaced a PRE-EXISTING broken `hatchet` service (engine pointed at app DB, no broker, + YAML bug: networks nested under healthcheck); (3) gRPC 7070→7077 (lite default); (4) `uv sync --all-packages` REQUIRED — plain root sync exits 0 but skips workspace-member deps; (5) sdk pin 1.33.6 (PyPI latest; trap #2 floor >=1.33.5; no `__version__` attr — use importlib.metadata); (6) client token session-ephemeral via `hatchet-admin token create --config /config` (path is /config not /hatchet/config) for seeded Default tenant 707d0855-…, NOT committed; (7) healthcheck `/api/ready`. HARNESS NOTE: severe tool-output corruption this session (fabricated/merged results + parallel-cancel cascades); first APPLY pass fabricated success w/ nothing on disk — caught, redone strict-sequential, every claim re-verified against disk/sandbox. | Phase 1 | Durable-execution backbone live. Doctrine: hatchet-lite for solo self-host (PG-only, isolated DB); workspace deps need `uv sync --all-packages`; self-host worker needs HATCHET_CLIENT_TOKEN + TLS_STRATEGY=none; under harness corruption switch to strict-sequential + re-verify on disk. Open: in-container worker token wiring (later plan) |
| 2026-05-29: Enterprise audit on 01-03 (evidence store / R2). Applied 3 must-have + 3 strongly-rec; deferred 2. Verdict: conditionally acceptable (was not-acceptable). Caught release-blockers: (M1) genesis prev_hash claimed 32 zero bytes but migration 03 + HashChainService use b"" 0-byte — plan would fail own chain-verify; (M2) moto cannot reproduce R2 CRC-header rejection so moto round-trip ≠ proof of trap-#5 fix — AC now asserts Config values by introspection; (M3) idempotent re-record skipped dup artifact row but would still append a 2nd audit entry → crashed-task replay could pad/fork the tamper-evident chain (audit append now only on NEW insert). Strongly-rec: scope_token_jti required non-empty (provenance), blob-PUT-before-commit + orphan-blob-acceptable semantics, raw_bytes size cap (Hatchet gRPC ~4 MiB). Deferred: oracle_verdict gating (recording attempts = legit audit trail), aioboto3 pooling (Phase 2). Doctrine: hash-chain genesis = b""; moto proves byte-fidelity not R2-checksum-compat (assert config + deployment smoke); idempotency must cover the audit append not just the row. | Phase 1 | Evidence write path audit-defensible; chain replay-safe |
| 2026-05-29: APPLY/UNIFY 01-03 (evidence store / R2). All 6 ACs verified LIVE (4/4 tests: 2 unit + 2 integration vs bs-postgres; worker registered record-evidence; trigger SUCCEEDED w/ full payload; blob on disk; chain canonical-verifies, genesis=b""). 4 deviations: (1) ON CONFLICT(content_hash) IMPOSSIBLE — no UNIQUE constraint + schema locked → per-finding pg_advisory_xact_lock SELECT-guard keyed (finding_id,content_hash), audit-append only on NEW insert; (2) pyproject.toml edited (NOT in files_modified) — added moto[server]>=5.0 dev dep + registered `integration` marker in control-plane [tool.pytest.ini_options]; (3) moto mock_aws unreliable w/ aiobotocore → ThreadedMotoServer (real HTTP localhost); (4) live trigger ran EVIDENCE_BACKEND=local (no R2 creds; R2 S3 path covered by moto unit test). Doctrine: idempotency w/o UNIQUE = advisory-lock SELECT-guard; service self-registers jsonb codec on acquired conn (HashChainService passes dict→jsonb, no codec existed anywhere); aiobotocore needs ThreadedMotoServer not mock_aws; PostToolUse ruff-autofix STRIPS unused imports between edits — add import only once its usage edit lands. | Phase 1 | Evidence write path live + audit-defensible. Open: evidence-mcp↔control-plane divergence deferred; in-container worker token wiring; pre-existing ruff debt |
| 2026-05-29: APPLY/UNIFY 01-01. Custom bs-postgres:pg17 built + ALL ACs verified live (PG17.10, 3 extensions active, DiskANN+BM25 apply+idempotent). 3 deviations: (1) glibc postgres:17-bookworm base not Alpine — pgrx+ParadeDB are glibc-only (plan-permitted fallback); (2) added `-c shared_preload_libraries=pg_search` to compose command — pg_search BM25 AM requires preload at server start (Context7-verified), absent from Task 2 spec; (3) `ruff check .` not clean — 40 PRE-EXISTING errors all in non-01-01 .py (control-plane/mcp/scripts/tests); 01-01 touched zero .py so introduced none; AC-6 "ruff exits 0" unsatisfiable w/o violating no-domain boundary. pgrx auto-matched to 0.16.1 via cargo metadata. | Phase 1 | DB foundation shipped. Doctrine: pg_search MUST be in shared_preload_libraries; custom PG ext images use glibc base + cargo-pgrx version-match. Open: pre-existing ruff debt needs separate triage (out of 01-01 scope) |

### Deferred Issues

| Issue | Origin | Effort | Revisit |
|-------|--------|--------|---------|
| ~~HackerOne structured_scopes changelog verification~~ **RESOLVED 2026-05-27** via primary source (api.hackerone.com changelog, in docs/bountystrike_v6_phase0-1_technical_brief.md). Only program-level WRITE removed (Apr 7 2026); READ endpoint CURRENT; NEW scope_exclusions endpoint (Apr 11 2026). Phase 1 W1.2 UNBLOCKED: implement structured_scopes READ + scope_exclusions READ + merge; skip program-level WRITE. research/02-routing-ev.md:66-76 migration spec has WRONG date ("April 16" vs actual April 7) + needs scope_exclusions added — fix in a future Phase 1 plan. | Init (v6 plan) | DONE | Closed — see brief |
| DeepSeek pricing correction + cost model rebuild | Init (v6 plan) | S | Phase 0, Day 1 |
| EV decay constants derivation (lambda=0.00065 / mu=0.00963) — regression-fit or hand-tuned? | Init (v6 plan) | M | Phase 0 |

### Blockers/Concerns

| Blocker | Origin | Status |
|---------|--------|--------|
| ~~No container runtime in WSL distro~~ **RESOLVED 2026-05-29** — Docker enabled (`docker info` UP). Custom image built exit 0; all empirical ACs verified live. | APPLY 01-01 (2026-05-29) | CLOSED |

## Session Continuity

Last session: 2026-05-29
Stopped at: 01-03 loop CLOSED (PLAN ✓ APPLY ✓ UNIFY ✓). All 6 ACs verified live. SUMMARY on disk. 01-03 changes UNCOMMITTED.
Next action: /paul:plan for 01-04 (next Phase 1 plan). NOT phase-complete (01-04..01-07 remain) — no transition yet. Consider committing 01-03 first.
Resume file: .paul/phases/01-community-edition-mvp/01-03-SUMMARY.md
Resume context:
- Phase 1: 3 of ~7 plans done. 01-04..01-07 remain (likely: validator/oracle wiring next).
- 01-03 SHIPPED: blob_store.py R2BlobStore._CHECKSUM_CONFIG (botocore Config when_required ×2); evidence_recording_service.py EvidenceRecordingService.record() (advisory-lock SELECT-guard idempotency, blob-PUT-before-commit, jsonb codec self-registered, genesis prev_hash b""); workflows/tasks.py record-evidence @hatchet.task + RecordEvidenceInput (raw_bytes_b64); worker.py registers [heartbeat, record_evidence]; orchestrator.py trigger-record-evidence subcommand (argparse --help). test_evidence_recording.py 4 tests. pyproject moto[server] + integration marker.
- LIVE STATE: bs-postgres + bs-hatchet + bs-hatchet-postgres UP + healthy. Worker STOPPED. bs-postgres volume bountystrike_postgres_data FRESH this session (init scripts re-ran; schema + 3 extensions verified). Hatchet token session-ephemeral at /tmp/bs_hatchet_token (Default tenant 707d0855-80ab-4e1f-a156-f1c4546cbf52) — regen runbook in 01-03-SUMMARY.
- KEY DOCTRINE this session: idempotency w/o UNIQUE = per-finding advisory-lock SELECT-guard; no jsonb codec existed anywhere (HashChainService passes dict→jsonb) → register on conn; aiobotocore needs ThreadedMotoServer not moto mock_aws; PostToolUse ruff-autofix strips unused imports BETWEEN edits (add import only once usage edit lands — bit me twice: botocore Config, argparse).
- UNCOMMITTED: working tree holds 01-03 changes (7 files) + .paul updates. 01-01+01-02 already committed (4c84845). Recommend commit before 01-04.
- HARNESS: NO corruption this session (model Opus 4.8 1M). Strict-sequential held throughout. Headroom (Pith) reported 120%+ near end.

---
*STATE.md — Updated after every significant action*
