---
phase: 01-community-edition-mvp
plan: 05
subsystem: scope_management
tags: [webhook, notifications, httpx, postgres, scope-diff, hatchet, structlog]

requires:
  - phase: 01-04
    provides: detect_scope_changes → scope_changes rows + scope_poll task
  - phase: 01-01
    provides: bs-postgres custom PG17 image + scope_changes table
provides:
  - scope_changes.notified_at delivery high-water mark (migration 12)
  - ScopeNotificationService.deliver_pending (bounded-batch webhook drain)
  - scope_poll wired to deliver new events per poll run (notified+pending totals)
affects: [01-08 installer (SCOPE_WEBHOOK_URL env + live worker token), Phase 2 observability]

tech-stack:
  added: []
  patterns:
    - "Dialect-portable async delivery: with_for_update(skip_locked) no-ops on SQLite; ORM update().where(id.in_()); Python datetime.now(UTC) not SQL now()"
    - "Secret-bearing egress URL redacted to scheme+host in every log line"
    - "Fail-open at-least-once: mark delivered only after 2xx; rollback-before-recount on fail path to release FOR UPDATE locks"

key-files:
  created:
    - infra/sql/12_phase1_scope_notified.sql
    - control-plane/src/control_plane/domains/scope_management/services/notification_service.py
    - control-plane/tests/test_scope_notifications.py
  modified:
    - control-plane/src/control_plane/infrastructure/database.py
    - control-plane/src/control_plane/workflows/tasks.py
    - control-plane/src/control_plane/domains/scope_management/services/__init__.py
    - control-plane/src/control_plane/domains/scope_management/__init__.py

key-decisions:
  - "Go-forward-only: migration backfills 4104 historical rows notified_at=now() so first run never retro-floods the webhook"
  - "Bounded batch (25) + 2000-char summary cap + drain loop — Discord content cap safe, no 200/6h dribble"
  - "At-least-once (not exactly-once): documented POST-then-commit redelivery window"
  - "Live worker-trigger deferred — tasks.py import needs HATCHET_CLIENT_TOKEN (pre-existing client.py gate); verified via py_compile + AST + 9 unit tests"

patterns-established:
  - "Outbound notification services read secret URL at call-time (12-factor + test monkeypatch), validate http(s) scheme, redact in logs"
  - "Feature-add migrations on a populated table backfill the new delivery-marker as already-done"

duration: ~45min
started: 2026-05-29T22:20:00Z
completed: 2026-05-29T23:05:00Z
---

# Phase 1 Plan 05: Scope-Diff Notification Delivery Summary

**scope_changes diff events now leave the DB — a generic outbound webhook (Slack/Discord/JSON) receives bounded-batch POSTs of new scope changes per scope_poll run, marked delivered via a notified_at high-water mark; first deploy backfilled 4104 historical rows so no retro-flood.**

## Performance

| Metric | Value |
|--------|-------|
| Duration | ~45 min |
| Started | 2026-05-29T22:20:00Z |
| Completed | 2026-05-29T23:05:00Z |
| Tasks | 3 completed (3 qualified PASS) |
| Files modified | 7 (3 created, 4 modified) |

## Acceptance Criteria Results

| Criterion | Status | Notes |
|-----------|--------|-------|
| AC-1: New events delivered to webhook | Pass | test_ac1 — 2 rows POSTed, both in events[], text==content, marked notified_at |
| AC-2: Delivery failure leaves rows redeliverable | Pass | test_ac2 (500 + transport error) — notified=0, rows NULL, no raise, retry-once observed |
| AC-3: No-op when webhook unconfigured | Pass | test_ac3 (unset + file:// scheme) — POST never called, pending surfaced |
| AC-4: Already-delivered rows never re-sent | Pass | test_ac4 — only NULL row in payload, notified=1 |
| AC-5: Migration additive + idempotent | Pass | LIVE bs-postgres: apply ×2, col+idx present, re-apply UPDATE 0 |
| AC-6: Pre-existing events NOT retro-delivered | Pass | LIVE: UPDATE 4104 backfill, post-apply NULL count=0; semantics also unit-tested |
| AC-7: Batch + payload-size bounds | Pass | test_ac7 — 30 rows → 2 POSTs [25,5], each ≤2000 chars, drained pending=0 |
| AC-8: At-least-once, documented redelivery | Pass | Docstring + module contract; mark only after 2xx |
| AC-9: Failure observable, never silent | Pass | test_ac9 — WARNING logged w/ pending=2; secret token absent from logs |

## Accomplishments

- Closed the 01-04 gap: scope-change signal now reaches the operator, not just Postgres.
- Migration 12 verified LIVE against bs-postgres (4104 rows backfilled, idempotent on re-apply).
- ScopeNotificationService: bounded-batch drain, FOR UPDATE SKIP LOCKED, retry-once on transport/429/5xx, secret-redacted observability, fail-open at-least-once.
- 9/9 new tests + 6/6 regression (federation+ingest) green; ruff clean on all touched files.

## Files Created/Modified

| File | Change | Purpose |
|------|--------|---------|
| `infra/sql/12_phase1_scope_notified.sql` | Created | ADD COLUMN notified_at + backfill UPDATE + partial undelivered index |
| `.../scope_management/services/notification_service.py` | Created | deliver_pending + ScopeNotificationPayload + redaction/summary helpers |
| `control-plane/tests/test_scope_notifications.py` | Created | 9 tests (AC-1..4, AC-6, AC-7, AC-9) |
| `.../infrastructure/database.py` | Modified | ScopeChange.notified_at Mapped column |
| `.../workflows/tasks.py` | Modified | scope_poll delivery wiring (fail-open) + structlog logger |
| `.../scope_management/services/__init__.py` | Modified | export deliver_pending, ScopeNotificationPayload |
| `.../scope_management/__init__.py` | Modified | re-export deliver_pending, ScopeNotificationPayload |

## Decisions Made

| Decision | Rationale | Impact |
|----------|-----------|--------|
| AC-6 backfill verified LIVE; unit test asserts semantics on SQLite | Migration .sql is PG-specific (ALTER IF NOT EXISTS / partial idx) — can't run on SQLite | Live PG is the AC-5/AC-6 proof; SQLite test guards the go-forward UPDATE logic |
| tasks.py +structlog logger | Plan snippet referenced `log.warning`; tasks.py had no logger | Additive, append-only, in-boundary |
| ingest-accumulation loop narrowed to explicit (programs,scopes,events) | Keep new notified/pending keys delivery-authoritative | Benign |
| deliver_pending rollback before recounting pending on fail | Release FOR UPDATE SKIP LOCKED row locks held in same txn | Impl detail beyond plan text; correct lock hygiene |

## Deviations from Plan

### Summary

| Type | Count | Impact |
|------|-------|--------|
| Auto-fixed | 1 | ruff SIM113 (manual counter → enumerate) |
| Scope additions | 2 | structlog logger in tasks.py; rollback-before-recount — both essential |
| Deferred | 1 | Live worker-trigger / real webhook POST |

**Total impact:** Essential fixes + correct lock hygiene; no scope creep.

### Deferred Items

- Live end-to-end webhook POST + scope_poll worker-trigger NOT run this session: `tasks.py` import requires `HATCHET_CLIENT_TOKEN` (pre-existing client.py gate, same condition as 01-04). Verified via py_compile + AST wiring-check + 9 unit tests. Live smoke belongs with 01-08 installer (token regen + SCOPE_WEBHOOK_URL endpoint).

## Issues Encountered

| Issue | Resolution |
|-------|------------|
| `import control_plane.workflows.tasks` raised ClientConfig "Token must be set" | Pre-existing hatchet client gate, not a regression. py_compile + AST + unit tests substitute for live import |

## Next Phase Readiness

**Ready:**
- scope_changes notification channel live; notified_at marker durable + queryable.
- scope_poll returns {programs, scopes, events, notified, pending}.

**Concerns:**
- Live webhook delivery + worker-trigger unverified (token + real endpoint).
- Duplicate-on-crash redelivery window accepted (at-least-once, documented).

**Blockers:** None.

---
*Phase: 01-community-edition-mvp, Plan: 05*
*Completed: 2026-05-29*
