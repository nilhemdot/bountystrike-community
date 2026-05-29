# Enterprise Plan Audit Report

**Plan:** .paul/phases/01-community-edition-mvp/01-05-PLAN.md
**Audited:** 2026-05-29
**Verdict:** Conditionally acceptable (was **not acceptable** as written — two release-blocking defects would make the feature actively harmful on first deploy)

---

## 1. Executive Verdict

As written, the plan would **flood the operator with thousands of stale scope changes** the first time it ran (01-04 already seeded ~4104 `scope_changes` rows before notifications existed, all with `notified_at` NULL after the migration), and its single-payload-of-200 design **breaks Discord's 2000-char `content` cap** while simultaneously **dribbling any real backlog out at 200 events / 6h** (≈5 days to drain a fresh DB). It also claimed **exactly-once** delivery (false — there is an unavoidable POST-then-commit redelivery window) and would **leak the secret-bearing webhook URL** into logs. None of these are hypothetical; each fires on the very first production run.

With the 5 must-have + 4 strongly-recommended upgrades applied, the architecture is sound: bounded-batch drain, go-forward-only backfill, fail-open at-least-once with observable failures, and secret-safe egress. **I would approve the amended plan for APPLY.** I would not have approved the original.

## 2. What Is Solid (Do Not Change)

- **Inline-in-scope_poll + `notified_at` marker** — correct, minimal, no second scheduler; the column is durable and queryable. Right call over a high-water-mark side table.
- **Fail-open posture** — a notification channel must never crash the ingest path that feeds the product. Correctly stated (now hardened at the call site too).
- **Additive migration, 01_schema.sql untouched, no CONCURRENTLY in init path** — consistent with 01-01 doctrine.
- **httpx.AsyncClient, Pydantic payload boundary** — aligns with project async + input-boundary constraints; no new dependency.
- **Boundaries protecting 01-04's diff/ingest path** — this plan only reads the rows 01-04 produces; that separation is correct.

## 3. Enterprise Gaps Identified

| # | Gap | Risk |
|---|-----|------|
| G1 | Post-migration, all historical rows are `notified_at` NULL → first run delivers the entire backlog of pre-feature events | Operator spammed with thousands of stale changes; alerting credibility destroyed on day one |
| G2 | Single POST of `limit=200` events | Discord `content` hard cap = 2000 chars → payload rejected; and a real backlog drains 200/poll = days |
| G3 | "delivered exactly once" claim | False. 2xx-then-commit-failure redelivers. Truth-in-claims violation (project ethos) |
| G4 | Delivery failure is silent | A dead/misconfigured webhook leaves events piling up with no signal; the alerting feature silently stops alerting |
| G5 | `SCOPE_WEBHOOK_URL` logged/echoed | Slack/Discord webhook URLs embed an auth token → credential leak into logs/Hatchet results |
| G6 | No locking on the undelivered SELECT | Cron run + manual trigger overlap → same rows double-sent |
| G7 | Retry only on transport error | 429/5xx (common from Slack/Discord) not retried; 4xx re-POSTed forever every poll |
| G8 | No URL scheme validation | Misconfig (file://, etc.) handled ambiguously |

## 4. Upgrades Applied to Plan

### Must-Have (Release-Blocking)

| # | Finding | Plan Section Modified | Change Applied |
|---|---------|----------------------|----------------|
| M1 | G1: go-forward-only | Task 1 + AC-6 + verify | Migration backfills `UPDATE scope_changes SET notified_at=now() WHERE notified_at IS NULL` after ADD COLUMN; idempotent; post-apply NULL count = 0 |
| M2 | G2: batch + size bound | Task 2 + AC-7 + verification | `BATCH_SIZE=25`/POST, summary capped to Discord 2000-char limit (overflow summarised, detail in `events[]`), drain loop (max_batches) until backlog empty |
| M3 | G5: URL is secret | Task 2 + boundaries + AC-9 + verification | URL never logged/returned/raised — redact to scheme+host; grep-verified |
| M4 | G3: false exactly-once | Task 2 docstring + AC-8 + success_criteria | Re-stated as at-least-once; documented POST-then-commit redelivery window; corrected success claim |
| M5 | G4: silent failure | Task 2 + Task 3 + AC-9 | WARNING log with status + pending count on failure; `deliver_pending` returns `{notified, pending}`; scope_poll surfaces both |

### Strongly Recommended

| # | Finding | Plan Section Modified | Change Applied |
|---|---------|----------------------|----------------|
| S1 | G6: concurrent runs | Task 2 | `SELECT … FOR UPDATE SKIP LOCKED` on undelivered batch |
| S2 | G7: retry policy | Task 2 | Retry once on transport error OR 429/5xx (backoff); 4xx (non-429) = permanent for that batch |
| S3 | call-site fail-open | Task 3 | scope_poll wraps `deliver_pending` in try/except so a delivery/DB error never discards committed ingest totals |
| S4 | G8: scheme validation | Task 2 | Reject non-http(s) `SCOPE_WEBHOOK_URL`; redacted warning + no-op |

### Deferred (Can Safely Defer)

| # | Finding | Rationale for Deferral |
|---|---------|----------------------|
| D1 | Per-program routing / multiple webhooks / email | Already scoped out; single global webhook is the MVP decision |
| D2 | Delivery metrics to Langfuse/Prometheus | Structured log + return-dict counts suffice for MVP; observability stack is Phase 2/3 |
| D3 | HMAC-sign the outbound payload (receiver authenticity) | Enterprise hardening; no receiver verifies signatures yet. Revisit Phase 4 |

## 5. Audit & Compliance Readiness

- **Defensible evidence:** `notified_at` timestamp per row is a durable delivery record; `{notified, pending}` return gives per-run accounting. Adequate.
- **Silent-failure prevention:** Addressed by M5/AC-9 — failure now logs status + backlog and surfaces pending. This was the largest compliance gap; the feature is an alerting control and a control that fails silent is worse than none.
- **Post-incident reconstruction:** `detected_at` (ingest) + `notified_at` (delivery) bracket the event lifecycle. Redelivery (at-least-once) is documented, so duplicate notifications are explainable, not anomalous.
- **Secret handling:** M3 closes the credential-leak path; the boundary forbids any secret in the payload. Consistent with the network-egress-control ethos of the product.
- **Ownership:** Delivery rides scope_poll (already owned); no new orphan surface.

## 6. Final Release Bar

**Must be true before ship (all now encoded in the plan):**
1. Historical rows backfilled as delivered — no retro-flood (AC-6).
2. Bounded batches within provider size caps + full-backlog drain per run (AC-7).
3. At-least-once contract stated honestly; no exactly-once claim (AC-8).
4. Delivery failures logged with backlog + surfaced in return; URL never leaked (AC-9, M3).
5. 01-04 ingestion tests stay green; no new ruff violations.

**Residual risk if shipped as amended:** duplicate notifications in the narrow crash-between-POST-and-commit window (accepted, documented). Single global channel only (by decision). No payload authenticity signature (deferred, D3).

**Sign-off:** With the amendments applied, I would sign my name to this plan for APPLY.

---

**Summary:** Applied 5 must-have + 4 strongly-recommended upgrades. Deferred 3 items.
**Plan status:** Updated and ready for APPLY.

---
*Audit performed by PAUL Enterprise Audit Workflow*
*Audit template version: 1.0*
