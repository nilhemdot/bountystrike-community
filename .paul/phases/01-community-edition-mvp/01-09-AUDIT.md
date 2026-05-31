# Enterprise Plan Audit Report

**Plan:** .paul/phases/01-community-edition-mvp/01-09-PLAN.md
**Audited:** 2026-05-31
**Verdict:** Conditionally acceptable (was not-acceptable as written — live smokes touched a real host path + supply-chain-unsafe image bake)

---

## 1. Executive Verdict
Conditionally acceptable after applied fixes. The plan correctly scopes to a local
Docker stack and reuses 01-08's installer, but as written it (a) could probe an
unauthorized host, (b) baked an unpinned/unverified binary + browser into the worker
image, and (c) mutated the live DB / handled secrets without isolation or redaction.
With the 3 must-haves applied it is approvable for execution (interactive, human-gated).

## 2. What Is Solid
- LOCAL-Docker scope + reuse of install.sh (no remote-host blast radius).
- Moat preserved: WIRES + runs domain code, edits none (oracles stay field-validated).
- No-compose-topology-change boundary (image content only).
- /e2e skill gate before the live pipeline smoke.
- CRLF `.gitattributes` with explicit binary `-text` exclusions (won't LF-mangle keypairs).

## 3. Enterprise Gaps Identified
- M1: recon smoke target authorization — "safe authorized target" underspecified; risk of
  probing a third-party host; the product's core control (scope-JWT egress enforcement)
  was not asserted by the smoke.
- M2: `playwright install chromium` + bbscope `curl` download were unpinned + unverified —
  non-reproducible image + supply-chain exposure in the very component this product hunts.
- M3: smoke seeds/mutates live bs-postgres + handles HATCHET token + secret webhook URL with
  no isolation, cleanup, or redaction.
- S1: chromium presence asserted only on the built image, not the running worker.
- S2: an internet recon target carries authorization ambiguity; a local deliberately-
  vulnerable container removes it and is CI-safe.
- S3: CRLF sweep idempotency + ordering (`.gitattributes` must be staged before renormalize).

## 4. Upgrades Applied to Plan

### Must-Have (Release-Blocking)
| # | Finding | Section | Change |
|---|---------|---------|--------|
| M1 | Recon smoke could touch unauthorized host | new AC-7, Task 3, boundaries | Abort if no valid in-scope JWT; target derived from JWT claims only; assert zero out-of-scope egress; fail loud |
| M2 | Unpinned/unverified image bake | AC-1, Task 1, boundaries | Pin playwright/chromium + bbscope version; verify bbscope sha256 before chmod +x (fail build on mismatch) |
| M3 | Live-DB mutation + secret handling | Task 3, boundaries | Test-data isolation + cleanup + re-runnable; never echo/commit HATCHET token or webhook URL (redact scheme+host) |

### Strongly Recommended
| # | Finding | Section | Change |
|---|---------|---------|--------|
| S1 | Image-only chromium check | AC-1 | Also verify chromium on the RUNNING worker container via docker exec |
| S2 | Internet target ambiguity | AC-7, Task 3 | Prefer a local deliberately-vulnerable container as recon target |
| S3 | CRLF sweep correctness | AC-6, verification | Second run no-op; `.gitattributes` staged before `git add --renormalize` |

### Deferred (Can Safely Defer)
| # | Finding | Rationale |
|---|---------|-----------|
| D1 | Coolify live validation | Remote; explicitly out of local-Docker scope (doc recipe only) |
| D2 | Multi-arch image builds | Local amd64 only for now; cross-arch is a release/Phase-3 concern |
| D3 | Langfuse trace assertions on smokes | Observability is Phase 2/3 |

## 5. Audit & Compliance Readiness
With fixes: the smoke produces defensible evidence (chromium-backed artifact + verifying
hash chain), fails loud on every gate (no silent half-pass), keeps secrets out of logs/
reports, and proves scope-JWT egress enforcement — the auditable centerpiece. Image bake
is now reproducible + integrity-checked. Remaining accountability: human-action checkpoints
(token, webhook sink, scope JWT) are operator-owned and logged.

## 6. Final Release Bar
Before APPLY: load /e2e; local stack up; a LOCAL in-scope target + issued scope JWT;
HATCHET token regenerated; a test webhook sink. Remaining risk if shipped as-is: none
release-blocking once M1–M3 hold; recon is gated to authorized scope, image is pinned +
verified, secrets are redacted. Signable for execution.

---

**Summary:** Applied 3 must-have + 3 strongly-recommended upgrades. Deferred 3 items.
**Plan status:** Updated and ready for APPLY (interactive — autonomous=false).

---
*Audit performed by PAUL Enterprise Audit Workflow*
*Audit template version: 1.0*
