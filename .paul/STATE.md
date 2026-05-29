# Project State

## Project Reference

See: .paul/PROJECT.md (updated 2026-05-29)

**Core value:** Automated bug bounty hunting that produces only verified, non-duplicate findings
**Current focus:** Phase 1 — Community Edition MVP: The Moat

## Current Position

Milestone: v0.1 Community Edition MVP
Phase: 1 of 6 (Community Edition MVP: The Moat) — In Progress (5 of 8 plans complete) — ready to PLAN 01-06
Plan: 01-05 (Scope-diff notification delivery) — LOOP CLOSED (SUMMARY written). Next: PLAN 01-06.
Status: 01-05 APPLIED. All ACs (AC-1..AC-9) verified. Migration 12 applied LIVE vs bs-postgres twice (4104 historical rows backfilled, re-apply idempotent UPDATE 0, NULL count=0, col+idx present — AC-5/AC-6). ScopeNotificationService.deliver_pending shipped (bounded batch=25, 2000-char summary cap, FOR UPDATE SKIP LOCKED, retry-once on transport/429/5xx, secret-URL redaction, fail-open at-least-once, returns {notified,pending}). scope_poll wired (append-only, fail-open, totals+notified+pending). 9/9 new tests pass (AC-1..4,6,7,9); 6/6 federation+ingest regression green; ruff clean on all 6 touched files.
Last activity: 2026-05-29 — 01-05 APPLY complete (3/3 tasks qualified)

Progress:
- Milestone: [███░░░░░░░] ~30% (1 of 6 phases complete + Phase 1 half-done)
- Phase 0: [██████████] 100% (4/4 plans complete)
- Phase 1: [██████▌░░░] ~62% (5 of 8 — 01-01 DB, 01-02 Hatchet, 01-03 Evidence, 01-04 Scope ingestion, 01-05 Notifications)

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
Phase 1 loop (01-04) — COMPLETE:
```
PLAN ──▶ APPLY ──▶ UNIFY
  ✓        ✓        ✓     [Loop closed — federated scope ingestion shipped + verified LIVE (798/4104/4104)]
```
Phase 1 loop (01-05) — COMPLETE:
```
PLAN ──▶ APPLY ──▶ UNIFY
  ✓        ✓        ✓     [Loop closed — scope-diff notification delivery shipped + verified]
```
Note: 01-02 line SPLIT — 01-02 = Hatchet v1 only; 01-03 = evidence store (R2). Downstream +1 (was 7).
Note: 01-04 line SPLIT (2026-05-29) — old single 01-04 (ingestion + RS256 + notifications) → 01-04 = ingestion completion (bbscope+projectdiscovery+scheduled poll+reconcile); 01-05 = scope-diff notification delivery (NEW). Downstream +1 → 8 plans (01-01..01-08). RS256 JWT already built (v5 carryover) → reconcile-only inside 01-04, not a standalone plan.

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
| 2026-05-29: PLAN 01-04 + split. Scope recon found scope_management ~70% pre-built (v5 carryover, untouched by Phase 1): arkadiyt+hackerone clients, jwt_issuer RS256 issuer/validator, 575-line ingest_service w/ detect_scope_changes, normalize ×5 platforms, scope_events diff classes, scope-mcp TS validation, 3 test files. Genuine gaps: (1) bbscope v2 integration MISSING, (2) projectdiscovery integration MISSING, (3) notification DELIVERY missing (events persisted, no channel), (4) no Hatchet scheduled poll task, (5) reconcile vs 01-01 custom-PG schema (scope code predates Phase 1 DB rebuild). 5 concerns → COMPLEX → SPLIT: 01-04 = ingestion completion (bbscope+projectdiscovery+scope_poll task+reconcile, 3 tasks); 01-05 = notification delivery. RS256 already shipped → reconcile-only, not rebuilt. | Phase 1 | Single-concern plans; ingestion isolated from notification delivery. Traps in play: #3 bbscope poll/db, #8 projectdiscovery dist/data.json `programs` key, #2 Hatchet v1 cron, #15 RS256 verify, #10 Bugcrowd cookie |
| 2026-05-29: APPLY/UNIFY 01-04 (federated scope ingestion). All AC-1..AC-5 verified (13/13 scope tests; ruff clean ×6 files). LIVE: worker registered scope-poll; trigger returned {programs:798,scopes:4104,events:4104} into bs-postgres; re-trigger events=0 (idempotent). 5 deviations: (1) generated keys/ RSA-4096 keypair (gitignored PEMs absent → test_scope_jwt) — env reconcile, NOT files_modified; (2) DEFAULT_DATABASE_URL (bountystrike:bountystrike) ≠ live bs-postgres (user `bs`/pw `verify_local_pw_01_01`, 01-01 throwaway) — live trigger needs explicit DATABASE_URL; flag for installer 01-08; (3) live trigger ran sources=["projectdiscovery"] only (bbscope binary not installed→01-08; arkadiyt skipped for determinism; both covered by unit tests); (4) scope_poll per-source commit (reuses committing ingest_*), not single atomic txn — documented; (5) _ingest_federation_program gained `source` param (in-scope helper extension). Doctrine: bbscope v2 = `poll`+`db -p X -o json` (+`--oos`), NOT v1 `h1 -t`; pd- handle namespacing prevents programs-PK collision; bare-target sources reuse per-platform normalizers via per-platform key-shape map; ruff-autofix strips unused imports between edits (land usage with/before import). RS256 confirmed in jwt_issuer (trap #15). | Phase 1 | Scope data foundation complete (3 federated sources + scheduled poll). Open: bbscope/arkadiyt live paths unverified (binary→01-08); DEFAULT_DATABASE_URL creds mismatch; notification delivery → 01-05 |
| 2026-05-29: Enterprise audit on 01-05 (scope-diff notification delivery). Applied 5 must-have + 4 strongly-rec; deferred 3. Verdict: conditionally acceptable (was not-acceptable). Caught 2 release-blockers: (M1) migration must BACKFILL existing rows notified_at=now() — else first run retro-floods the webhook with ~4104 stale 01-04 events (column added NULL on all history); (M2) single limit=200 POST breaks Discord content 2000-char cap AND dribbles backlog 200/6h-poll (~5d to drain fresh DB) → BATCH_SIZE=25 + length-capped summary + drain loop. Also: (M3) SCOPE_WEBHOOK_URL is secret (Slack/Discord embed token) — never log/return/raise full URL, redact to scheme+host; (M4) false "exactly-once" claim → at-least-once (POST-then-commit redelivery window documented); (M5) silent-failure → WARNING w/ status+pending count, return {notified,pending}. Strongly-rec: FOR UPDATE SKIP LOCKED (cron+manual overlap), retry 429/5xx not just transport, call-site fail-open wrap, http(s) scheme validation. Deferred: per-program routing/email (scoped out), metrics→Langfuse (Phase 2/3), HMAC payload sig (Phase 4). Doctrine: feature-add migrations on a populated table must backfill the new delivery-marker as already-done (go-forward-only); outbound webhook URLs are credentials; alerting controls must fail loud + observable; bound payloads to the strictest provider cap (Discord 2000) + drain in-run not across polls. | Phase 1 | Notification delivery audit-defensible; will not retro-flood / leak / silently fail on first deploy |
| 2026-05-29: APPLY 01-05 (scope-diff notification delivery). All ACs verified; 3/3 tasks qualified. 5 deviations: (1) AC-6 backfill verified LIVE vs bs-postgres (4104 rows backfilled, re-apply UPDATE 0, NULL=0) — migration .sql is PG-specific so unit test asserts backfill SEMANTICS portably on SQLite, not the .sql itself; (2) tasks.py gained `import structlog` + module logger (plan snippet said `log.warning` but tasks.py had no logger) — additive, append-only, in-boundary; (3) scope_poll ingest-accumulation loop narrowed from `for key in totals` to explicit ("programs","scopes","events") tuple so the new notified/pending keys stay delivery-authoritative (benign); (4) deliver_pending calls session.rollback() before counting pending on failure — needed to release FOR UPDATE SKIP LOCKED row locks held in the same txn (impl detail beyond plan text); (5) live worker-trigger of scope_poll NOT run — module import of tasks.py needs HATCHET_CLIENT_TOKEN (pre-existing client.py gate, same as 01-04); verified via py_compile + AST wiring-check + 9 unit tests instead. Live end-to-end webhook POST deferred (no token regen + no real webhook endpoint this session). Doctrine: notification service must be dialect-portable (with_for_update(skip_locked=True) no-ops on SQLite, ORM update().where(id.in_()), Python datetime.now(UTC) not SQL now()); FOR UPDATE locks require rollback-before-recount on the fail path; secret webhook URLs redact to scheme+host in every log line. | Phase 1 | Scope-change signal now leaves the DB. Open: live webhook POST + worker-trigger unverified (token+endpoint → 01-08 installer / a live smoke); duplicate-on-crash redelivery window accepted (at-least-once, documented) |
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
Stopped at: 01-05 LOOP CLOSED (APPLY+UNIFY done). Notification delivery shipped + verified (9/9 tests, migration live-applied, ruff clean). SUMMARY written.
Next action: /paul:plan 01-06 (oracles). NOTE: working tree holds UNCOMMITTED 01-04 + 01-05 src + .paul (HEAD=7754096 has 01-04? — 01-04 commit 7754096 IS at HEAD; 01-05 + any 01-04 .paul drift uncommitted). Phase NOT complete: 3 plans remain (01-06 oracles, 01-07 recon, 01-08 installer). transition heuristic (PLAN==SUMMARY count) is a FALSE positive here — future plans unauthored.
Resume file: .paul/phases/01-community-edition-mvp/01-05-SUMMARY.md
01-05 PLAN SHAPE:
- 3 tasks, standard, autonomous. Channel=generic webhook (SCOPE_WEBHOOK_URL, sends both Slack `text` + Discord `content` + events[]); trigger=inline in scope_poll; dedup=scope_changes.notified_at column.
- Task 1: migration 12_phase1_scope_notified.sql (ADD COLUMN IF NOT EXISTS notified_at TIMESTAMPTZ + partial idx WHERE notified_at IS NULL; NO CONCURRENTLY) + ScopeChange ORM notified_at. Additive; DO NOT touch 01_schema.sql.
- Task 2: notification_service.py deliver_pending(session) — select notified_at IS NULL, build Pydantic payload, httpx.AsyncClient POST (timeout 10, retry-once), mark notified_at=now() on 2xx only. FAIL-OPEN (no webhook→0; outage→0, no raise, no mark). Export from services/__init__ + domain __init__.
- Task 3: wire totals["notified"]=await deliver_pending(session) into scope_poll after ingest loop (same session block, in-handler import); new test_scope_notifications.py mock httpx (4 cases AC-1..AC-4; reuse existing scope test fixture).
- BOUNDARIES: don't change detect_scope_changes/scope_events/ingest_*_all/jwt_issuer/01_schema.sql/cron. Webhook only (no SMTP/UI/per-program routing/new deps).
- 01-04 OVERLAP (benign, acknowledged): tasks.py::scope_poll gets delivery call appended (append-only, no restructure).
Resume context:
- Phase 1: 3 of 8 plans done. Remaining: 01-04 (ingestion, PLANNED) → 01-05 notifications → 01-06 oracles → 01-07 recon → 01-08 installer.
- 01-04 KEY FINDING: scope_management is ~70% pre-built (v5 carryover). DO NOT rebuild arkadiyt/hackerone/jwt_issuer/ingest_service/scope_events — EXTEND. New files: integrations/bbscope.py, integrations/projectdiscovery.py. Modify: ingest_service.py (+ingest_bbscope_all/+ingest_projectdiscovery_all), workflows/tasks.py (+scope_poll @hatchet.task), worker.py (register), tests/test_scope_federation.py (new).
- 01-04 federation path: clients emit FederationProgram → _ingest_federation_program upserts → detect_scope_changes diffs (events come free). Mirror ingest_arkadiyt_all.
- 01-04 TRAPS: #3 bbscope v2 `poll`/`db` NOT v1 `h1 -t`; #8 projectdiscovery `dist/data.json` under `programs` key NOT chaos-bugbounty-list.json; #2 Hatchet v1 cron API (verify Context7); #15 jwt_issuer algorithms=["RS256"]; #10 Bugcrowd `_bugcrowd_session`. Intigriti --oos → CanonicalScope in_scope=False.
- 01-04 RECONCILE GATE: scope code predates 01-01 DB rebuild — run test_scope_ingest + test_scope_jwt vs live bs-postgres; fix code to schema (NOT migrations) if drift.
- COMMIT NOTE: 01-01/01-02/01-03 ALL committed (HEAD bacda9b). Working tree clean except untracked .token-savior-cache.json (tool cache — gitignore candidate, not part of plan).
- 01-03 SHIPPED: blob_store.py R2BlobStore._CHECKSUM_CONFIG (botocore Config when_required ×2); evidence_recording_service.py EvidenceRecordingService.record() (advisory-lock SELECT-guard idempotency, blob-PUT-before-commit, jsonb codec self-registered, genesis prev_hash b""); workflows/tasks.py record-evidence @hatchet.task + RecordEvidenceInput (raw_bytes_b64); worker.py registers [heartbeat, record_evidence]; orchestrator.py trigger-record-evidence subcommand (argparse --help). test_evidence_recording.py 4 tests. pyproject moto[server] + integration marker.
- LIVE STATE: bs-postgres + bs-hatchet + bs-hatchet-postgres UP + healthy. Worker STOPPED. bs-postgres volume bountystrike_postgres_data FRESH this session (init scripts re-ran; schema + 3 extensions verified). Hatchet token session-ephemeral at /tmp/bs_hatchet_token (Default tenant 707d0855-80ab-4e1f-a156-f1c4546cbf52) — regen runbook in 01-03-SUMMARY.
- KEY DOCTRINE this session: idempotency w/o UNIQUE = per-finding advisory-lock SELECT-guard; no jsonb codec existed anywhere (HashChainService passes dict→jsonb) → register on conn; aiobotocore needs ThreadedMotoServer not moto mock_aws; PostToolUse ruff-autofix strips unused imports BETWEEN edits (add import only once usage edit lands — bit me twice: botocore Config, argparse).
- UNCOMMITTED: working tree holds 01-03 changes (7 files) + .paul updates. 01-01+01-02 already committed (4c84845). Recommend commit before 01-04.
- HARNESS: NO corruption this session (model Opus 4.8 1M). Strict-sequential held throughout. Headroom (Pith) reported 120%+ near end.

---
*STATE.md — Updated after every significant action*
