# Enterprise Plan Audit Report

**Plan:** .paul/phases/01-community-edition-mvp/01-07-PLAN.md
**Audited:** 2026-05-31
**Verdict:** Conditionally acceptable (was NOT acceptable as written — silent-drop of real findings)

---

## 1. Executive Verdict
Not acceptable as originally written: AC-5 dropped xss-candidates on rate-limit
exhaustion by returning `probe→False`, which downstream reads as "unreflected →
discard". For a platform whose entire value proposition is *verified, non-missed
findings*, our own throttle silently burying a real bug is a release-blocker.
With the 4 applied fixes (fail-open keep+warn, hostname-only bucket key, rps
clamp, limiter-call fail-open wrap) the plan is conditionally acceptable and
ready for APPLY.

## 2. What Is Solid
- WIRE-not-build posture (consume tested TokenBucketLimiter + ScopeFilter; don't
  edit bucket.py) — correct, mirrors 01-06.
- acquire-before / report-after placed INSIDE the prober (only site with the
  status code) — right layering.
- Backward-compat via `limiter=None` default preserves existing recon tests.
- Tight blast radius: 5 files, no tasks.py/worker.py/orchestrator.py churn.

## 3. Enterprise Gaps Identified
- Silent-failure: rate-limited probe indistinguishable from genuine "not vuln".
- Bucket-key correctness: `hostname or url` fallback shards buckets per-URL,
  silently defeating per-host throttling exactly when hostname parsing fails.
- Crash surface: unclamped per-host rps from an untrusted JWT field; unwrapped
  limiter calls on the recon hot path.

## 4. Upgrades Applied to Plan

### Must-Have (Release-Blocking)
| # | Finding | Section | Change |
|---|---------|---------|--------|
| M1 | Throttle skip silently drops real candidate | AC-5, Task 1, Task 3, boundaries | Fail-open: granted=False → probe returns True (keep) + `recon.politeness.probe_skipped` WARNING; oracle stays sole gate |
| M2 | `hostname or url` fallback defeats per-host bucketing | Task 1 | Key on `(urlparse(url).hostname or "_nohost").lower()`, never the URL |

### Strongly Recommended
| # | Finding | Section | Change |
|---|---------|---------|--------|
| S1 | Untrusted relaxed_hosts rps can exceed ceiling / crash acquire | Task 1, AC-7, Task 3 | `rps = min(rps, MAX_RPS_CEILING)` before acquire |
| S2 | Limiter error could crash recon pipeline | Task 1, boundaries | Wrap acquire/report fail-open (warn + fall through to ungated GET) |

### Deferred (Can Safely Defer)
| # | Finding | Rationale |
|---|---------|-----------|
| D1 | Skip-rate metrics → Langfuse | Observability is Phase 2/3 |
| D2 | Binary-stage (subfinder/httpx/katana) per-host bucketing | Out of "token-bucket only" scope; binaries self-limit via -rate-limit flag |
| D3 | Persisting a "probe_skipped" marker on the finding row | Schema change; out of no-migration scope |

## 5. Audit & Compliance Readiness
Post-fix: skipped probes leave a WARNING audit trail (reconstructable); no real
finding is dropped by our throttle; per-host politeness is provably enforced
(hostname-keyed); untrusted JWT cannot crash recon. Deterministic offline tests
prove each path.

## 6. Final Release Bar
Ship-ready once Task 3 proves AC-5 fail-open (keep+warn, GET not called), M2
bucket-key, AC-7 clamp, and AC-6 regression. Residual (accepted): under sustained
backoff the oracle sees more candidates (fail-open trade) — correct for a
verified-only platform. Signable with the four fixes applied.

---

**Summary:** Applied 2 must-have + 2 strongly-recommended upgrades. Deferred 3.
**Plan status:** Updated and ready for APPLY.

---
*Audit performed by PAUL Enterprise Audit Workflow*
*Audit template version: 1.0*
