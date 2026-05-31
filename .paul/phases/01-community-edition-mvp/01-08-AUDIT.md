# Enterprise Plan Audit Report

**Plan:** .paul/phases/01-community-edition-mvp/01-08-PLAN.md
**Audited:** 2026-05-31
**Verdict:** Conditionally acceptable (was **not acceptable** as written)

---

## 1. Executive Verdict

Conditionally acceptable after remediation. The plan's architecture is right —
ORCHESTRATE pre-built v5 assets into one idempotent command, defer live-deploy +
release to 01-09 — and the split was the correct call. But as written it would
ship an installer for a **security product** that: (a) writes `.env` (API keys,
DB passwords, webhook tokens) **world-readable** under the default umask;
(b) boots the stack on **predictable, source-visible secret defaults** for
hatchet-postgres / langfuse / hatchet-cookie because compose `:-`-defaults them
and the original AC-5 only checked the two no-default vars; (c) could **exit 0 on
a half-up stack** (silent failure on a health-tool deploy); and (d) could imply a
`curl … | sh`-as-root from `--unattended` alone. None acceptable for a tool whose
entire premise is finding exactly these classes of defect. I would not sign the
original; I would sign the remediated plan for APPLY.

## 2. What Is Solid (do not change)

- **The split.** Installer (autonomous, offline-testable) vs live-gates+release
  (needs a host + human checkpoints) is the correct seam; 01-09 UNIFY triggering
  the phase transition is right.
- **ORCHESTRATE-not-build.** Reusing generate_keys.sh (already idempotent, 0600),
  .env.example, health_check.sh, e2e_verify.sh, the 681-line compose — no
  re-implementation. Correct, low-risk.
- **Unattended-auto-gen + never-overwrite secret model.** The right idempotency
  primitive for a re-runnable installer; clobbering POSTGRES_PASSWORD would orphan
  the data volume.
- **Offline test harness with a stub `docker`.** Keeps APPLY infra-free and CI-safe.
- **Boundaries deferring image-bake / live-smoke / release to 01-09.** Clean scope.

## 3. Enterprise Gaps Identified

1. **(M1) World-readable secrets.** Host umask 022 → fresh `.env` is 0644. It
   holds ANTHROPIC/DeepSeek keys, POSTGRES/REDIS passwords, webhook tokens. Nothing
   chmods it. generate_keys.sh protects the private key but not `.env`.
2. **(M2) Predictable-default boot.** Refined compose scan: only POSTGRES_PASSWORD
   and REDIS_PASSWORD are no-default. HATCHET_POSTGRES_PASSWORD, HATCHET_COOKIE_SECRET,
   LANGFUSE_SECRET, LANGFUSE_SALT all carry hardcoded `:-` fallbacks → if `.env`
   omits them the stack runs on source-visible secrets. The original AC-5
   ("no-default parity") was trivially already satisfied and missed this entirely.
   Also: `.gitignore` ignores `.env`/`keys/` but **not** `.env.backup*`, which
   init_wizard.py creates → committable plaintext-secret leak.
3. **(M3) Silent half-up stack.** health_check.sh exits 0/1/2 under `set -e`. A
   naive poll loop either lets `-e` abort on rc 1/2 or, worse, could fall through
   and report success while a service is down.
4. **(M4) Partial-.env / missing-prereq.** No openssl/bash preflight → on a minimal
   host `openssl rand` fails and a `.env` with blank secrets is written, then the
   stack boots with empty passwords. No post-seed `compose config` validation that
   generated values round-trip.
5. **(S1) Implicit curl|sh-as-root.** Auto-installing Docker from `--unattended`
   alone pipes a remote script to a root shell — the exact risk class this product
   hunts.
6. **(S2) No pre-`up` compose validation.** A missing/blank required secret
   surfaces as a mystery container crash, not a loud pre-boot error.
7. **(S3) Unverifiable README one-liner.** A `curl <raw-url> | bash` command 404s
   until the public repo exists (01-09) — ships a broken copy-paste.
8. **(S4) Mixed-state idempotency unspecified.** Operator pre-fills some keys,
   leaves others blank — must fill only blanks, never touch set values.

## 4. Upgrades Applied to Plan

### Must-Have (release-blocking)

| # | Finding | Plan Section Modified | Change Applied |
|---|---------|----------------------|----------------|
| M1 | World-readable `.env` (umask 022 → 0644) | AC-7 (new), Task 2 action, Verification | seed_env chmod 600 .env; no .env.backup* by seed_env; AC-7 asserts 0600 on .env + private key |
| M2 | Predictable compose-baked secret defaults + `.env.backup*` leak | AC-5 (rewritten), Task 2 action+files, Boundaries, frontmatter | seed_env overrides all 4 `:-`-defaulted secrets; .env.example lists them (+HATCHET_POSTGRES_PASSWORD); `.gitignore` += `.env.backup*`; AC-5 asserts seeded ≠ baked default |
| M3 | Silent exit-0 on half-up stack | AC-8 (new), Task 1 bring_up | Capture health rc (no `set -e` abort), treat 1/2 as keep-waiting, timeout → non-zero naming unhealthy svcs, never success banner while down; retries/interval env-overridable |
| M4 | Partial-.env / missing openssl | AC-9 (new), Task 1 preflight (step 0), Task 2 preflight | Preflight openssl/bash before any write; atomic tmp+mv; post-seed `docker compose config -q` round-trip check |

### Strongly Recommended

| # | Finding | Plan Section Modified | Change Applied |
|---|---------|----------------------|----------------|
| S1 | Implicit curl\|sh-as-root | AC-4 (rewritten), Task 1 ensure_docker | Docker auto-install gated behind explicit `--install-docker` AND `--unattended`; else print command + non-zero |
| S2 | No pre-`up` compose validation | Task 1 bring_up, Verification | `compose --env-file .env config -q` before `up -d`; C3 asserts config-before-up ordering |
| S3 | README one-liner 404s pre-release | AC list note, Task 1 README action | Primary = `git clone && bash scripts/install.sh`; curl form deferred to post-release/01-09 |
| S4 | Mixed-state idempotency | AC-10 (new), Task 2 verify, Test C7 | Fill only empty keys; assert pre-set values byte-identical |

### Deferred (can safely defer)

| # | Finding | Rationale for Deferral |
|---|---------|----------------------|
| D1 | Coolify recipe live-validation | Needs a running Coolify instance; docs-recipe only this plan, live deploy = 01-09 |
| D2 | Non-Ubuntu (Alpine/RHEL) install paths | Solo target is Ubuntu/Hetzner; multi-distro = Phase 3 SaaS |
| D3 | Secret rotation / re-key flow | init_wizard.py `--update` already exists; out of installer scope |
| D4 | Harden compose `:-` secret defaults at source | M2 fix (always-override via .env) is sufficient; removing defaults is a separate compose-hardening change, boundary-excluded here |

## 5. Audit & Compliance Readiness

- **Defensible evidence:** offline harness C1–C9 now proves perms (0600),
  no-default-boot, loud failure, preflight, and docker-gate — each a named AC.
- **Silent-failure prevention:** AC-8 converts the health wait from a
  potential success-on-failure into a loud non-zero; AC-9 stops partial-.env writes.
- **Secret hygiene:** 0600 + `.env.backup*` gitignore + override-baked-defaults
  closes the three plaintext-secret exposure paths (disk perms, VCS, predictable
  default). Appropriate for a tool that will be audited.
- **Post-incident reconstruction:** install.sh remains idempotent and stateless;
  a re-run converges, so a failed install is diagnosable and recoverable.
- **Ownership:** single operator-run script; no hidden side effects beyond the
  documented .env/keys/compose.

## 6. Final Release Bar

**Must be true before APPLY ships:** `.env` is 0600; the stack never boots on a
compose-baked default secret; install.sh exits non-zero (no success banner) on any
unhealthy/timeout; openssl/bash preflight blocks partial-.env; Docker auto-install
is opt-in only. All five are now encoded as ACs + test cases.

**Residual risk if shipped as-is (remediated):** Coolify path is doc-only and
unvalidated against a live Coolify (accepted → 01-09); compose still *contains*
the weak `:-` defaults (neutralized by always-override, not removed). Both
documented and bounded.

**Sign-off:** With the four must-haves + four strongly-recommended applied, I
would sign this plan for APPLY.

---

**Summary:** Applied 4 must-have + 4 strongly-recommended upgrades. Deferred 4.
**Plan status:** Updated and ready for APPLY.

---
*Audit performed by PAUL Enterprise Audit Workflow*
*Audit template version: 1.0*
