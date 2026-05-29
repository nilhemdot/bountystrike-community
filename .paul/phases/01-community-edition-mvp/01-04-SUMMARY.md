# 01-04 SUMMARY — Federated scope ingestion completion

**Status:** APPLY complete — all AC-1..AC-5 verified (unit + LIVE vs bs-postgres).
**Date:** 2026-05-29

## What shipped

Completed federated scope ingestion: added the two missing sources (bbscope v2
authenticated, projectdiscovery VDP) alongside the arkadiyt baseline, driven by
a scheduled Hatchet `scope_poll` task, and reconciled the v5-carryover scope
code against the 01-01 custom-PG schema.

### Files
- **NEW** `integrations/bbscope.py` — `BbscopeClient` over bbscope v2 `poll`/`db`
  (trap #3), injectable subprocess `runner`, `BbscopeScopeRow` Pydantic model,
  groups rows into the shared `FederationProgram` shape. Intigriti `--oos` rows
  carry `in_scope=False`. BYOK creds from env (`H1_API_TOKEN`/`H1_USERNAME`,
  `BUGCROWD_SESSION_COOKIE` = `_bugcrowd_session` trap #10, `INTIGRITI_PAT`,
  `YESWEHACK_BEARER`).
- **NEW** `integrations/projectdiscovery.py` — `ProjectDiscoveryClient` fetching
  `dist/data.json` `programs` key (trap #8). Chaos-list filename never referenced.
- **MOD** `services/ingest_service.py` — `ingest_bbscope_all` +
  `ingest_projectdiscovery_all` + `_normalize_projectdiscovery` + `_pd_handle`
  (pd- namespaced). `_ingest_federation_program` gained a `source` param so
  bbscope/projectdiscovery events are tagged correctly (was hardcoded "arkadiyt").
- **MOD** `workflows/tasks.py` — `scope_poll` `@hatchet.task` (`on_crons=["17 */6 * * *"]`,
  `execution_timeout="15m"`, `ScopePollInput(sources=[...])`); lazy in-handler imports.
- **MOD** `workflows/worker.py` — registers `scope_poll`.
- **NEW** `tests/test_scope_federation.py` — 5 tests (bbscope+oos, projectdiscovery,
  no-chaos-filename, combined, idempotency).

## Acceptance criteria
- **AC-1** bbscope v2 auth ingest + OOS → `in_scope=False` — PASS (test + sandbox).
- **AC-2** projectdiscovery `dist/data.json` `programs` key, no chaos filename — PASS.
- **AC-3** scheduled poll drives sources + emits diff events + returns counts — PASS
  LIVE: worker registered `scope-poll`; trigger returned `{programs:798, scopes:4104, events:4104}`, SUCCEEDED.
- **AC-4** reconcile — `test_scope_ingest` + `test_scope_jwt` green (8 passed); `jwt_issuer`
  confirmed `algorithms=["RS256"]`; live upsert works on custom-PG schema (no drift).
- **AC-5** idempotent re-ingest → 0 new rows, 0 events — PASS (unit + LIVE re-trigger: events=0, rows stable).

Final: ruff clean on all 6 files; 13/13 scope tests pass.

## Deviations / notes
1. **keys/ generated** (NOT in files_modified) — `test_scope_jwt` errored on missing
   `keys/scope_jwt_*.pem` (gitignored secrets, absent locally). Generated a 4096-bit
   RSA keypair at repo-root `keys/` — env reconcile, no code/migration change.
2. **Live DSN** — `DEFAULT_DATABASE_URL` (bountystrike:bountystrike) does NOT match
   bs-postgres (user `bs` / pw `verify_local_pw_01_01`, a 01-01 throwaway). Live trigger
   needed explicit `DATABASE_URL` env. Pre-existing 01-01 artifact; flag for installer (01-08).
3. **Live trigger source** — used `sources=["projectdiscovery"]` only: bbscope binary not
   installed (deferred to 01-08); arkadiyt skipped for determinism. bbscope + arkadiyt
   paths covered by unit tests.
4. **Per-source commit, not single atomic txn** — `scope_poll` reuses existing `ingest_*_all`
   which each `session.commit()`. Mid-run failure leaves prior sources committed; next poll
   reconciles. Documented in the task docstring.
5. **`_ingest_federation_program` source param** — minimal in-scope extension of the shared
   helper; `ingest_arkadiyt_all` unaffected (default "arkadiyt").

## Doctrine
- bbscope v2 = `poll` (refresh local DB) + `db -p <platform> -o json` (+`--oos` for exclusions);
  NOT v1 `h1 -t`. Exact flags confirmed against `bbscope --help` at install (01-08); argv
  builders isolated, parsing canned-JSON tested.
- projectdiscovery programs live in `dist/data.json` under `programs`; pd- handle namespacing
  prevents `programs` PK collision with auth-platform handles.
- PostToolUse ruff-autofix strips unused imports BETWEEN edits — land usage before/with the
  import, or add import last (bit us once on `BbscopeClient`).
- Bare-target federation sources reuse existing per-platform normalizers by shaping each
  target into the dict-shape that normalizer reads (key map per platform).

## Boundaries respected
jwt_issuer (verify-only, RS256 confirmed), scope-mcp TS, 01-01 migrations/schema,
scope_events.py — all untouched. No notification delivery (correctly deferred to 01-05).
No Platform enum member added (projectdiscovery upserts via `platform` string).
