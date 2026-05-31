---
phase: 01-community-edition-mvp
plan: 08
type: summary
status: complete
date: 2026-05-31
---

# 01-08 SUMMARY — One-line installer

## Outcome

APPLY complete. All 3 tasks qualified PASS. All 10 acceptance criteria satisfied.
Offline test harness green (26/26 cases C1–C9); `e2e_verify.sh` green (43/43
critical, rc=0; deployment package ready).

## What shipped

- **`scripts/install.sh`** (new) — unattended one-line bootstrap orchestrator.
  `preflight → (ensure_docker) → seed_secrets → ensure_keys → bring_up → print_next_steps`.
  Flags `--no-up`, `--unattended`/`-y`, `--install-docker` (explicit opt-in, only
  honoured with `--unattended`), `--help`. `set -euo pipefail`; SPDX AGPL header;
  REPO_ROOT resolved like generate_keys.sh. Health wait captures `health_check.sh`
  rc without `set -e` aborting; retries/interval overridable via
  `INSTALL_HEALTH_RETRIES`/`INSTALL_HEALTH_INTERVAL`; fails NON-ZERO on timeout
  naming still-down services, never prints success on a half-up stack. `ensure_docker`
  never pipes `curl|sh` implicitly. `ensure_docker`/`bring_up` only on the up path
  (skipped under `--no-up`).
- **`scripts/seed_env.sh`** (new) — non-interactive idempotent secret seeder.
  `cp .env.example→.env` if absent; fills ONLY empty infra secrets
  (POSTGRES/REDIS/HATCHET_COOKIE/HATCHET_POSTGRES/LANGFUSE_SECRET = `openssl rand
  -base64 32`; LANGFUSE_SALT = `-hex 16`); never overwrites a set value; never
  touches BYOK/platform keys. Atomic temp-file rewrite via awk (no `sed -i` —
  base64 has `/ + =`); `chmod 600 .env`. Preflight fails (no openssl) BEFORE any
  write. No `.env.backup*`.
- **`scripts/test_install_e2e.sh`** (new) — pure-bash offline harness. Stub
  `docker`+`curl` shims on PATH (record argv, simulate healthy stack;
  `DOCKER_STUB_MODE=broken` simulates unusable compose). Isolated temp copy of the
  repo — real `.env`/`keys/` never touched. Cases C1–C9 cover AC-1..AC-10.
- **`.env.example`** — added `HATCHET_POSTGRES_PASSWORD=` placeholder (was the
  documented drift: compose `:-hatchet`-defaults it, previously absent). Normalized
  CRLF→LF (was shipped CRLF; trailing `\r` would corrupt every compose value).
- **`.gitignore`** — added `.env.backup*` (init_wizard.py writes incremental
  `.env.backup.N` plaintext-secret files, previously committable).
- **`README.md`** — new "One-line install" section (primary =
  `git clone … && bash scripts/install.sh`; curl|bash noted as post-release).
  Replaced the stale "Phase 1 signed off 2026-05-01 (4/6 PASS…)" status line with
  current Phase-1 status (8/9 plans shipped).
- **`docs/DEPLOYMENT.md`** — added "Deploy via Coolify" recipe subsection
  (register compose as a Coolify resource, paste seeded `.env`, expose caddy 80/443;
  recipe only, no code dependency).

## Acceptance criteria — all PASS

| AC | Result | Evidence |
|----|--------|----------|
| AC-1 fresh unattended provision | PASS | C1: exit 0, .env + 6 secrets non-empty, BYOK blank, keypair present |
| AC-2 idempotent re-run | PASS | C2: .env byte-identical, keypair mtime unchanged |
| AC-3 full run + health wait | PASS | C3: `config -q` before `up -d --build`, banner + scope-JWT cmd printed |
| AC-4 no implicit curl\|sh | PASS | C4: docker unusable → non-zero, get.docker.com msg, curl never called, no up |
| AC-5 no predictable defaults | PASS | C5: all 6 placeholders present; HATCHET_POSTGRES_PASSWORD ≠ baked `hatchet` |
| AC-6 offline harness + package | PASS | harness 26/26; `e2e_verify.sh` rc=0 (43 critical) |
| AC-7 secrets 0600 | PASS | C6: .env 600, private key 600 |
| AC-8 health fails loud | PASS | C8: health stub exit 1 → install non-zero, no banner, timeout message |
| AC-9 preflight before write | PASS | C9: openssl off PATH → seed_env non-zero, .env not created |
| AC-10 mixed-state fill-blanks | PASS | C7: pre-set POSTGRES untouched, blank LANGFUSE_SALT filled |

## Deviations

1. **CRLF defect discovered (release-blocking) — LF normalization of 4 shipped
   scripts.** QUALIFY revealed the repo's shipped helper scripts are CRLF-encoded
   and **non-functional on Linux** (`set: pipefail: invalid option name`, rc=2).
   The plan's recon misread them as working (the compressed/garbled Read hid the
   CRLF). Normalized CRLF→LF (pure line-ending fix, zero logic change):
   - `scripts/health_check.sh`, `scripts/e2e_verify.sh` — not boundary-protected.
   - `scripts/generate_keys.sh` — **boundary-protected** ("reuse as-is; do not
     edit"). Normalized under an explicit, user-approved scoped exception
     (AskUserQuestion 2026-05-31, option "Normalize to LF"). Without it AC-1
     (keypair generated) was unsatisfiable — install.sh's `ensure_keys` calls it.
   - `infra/docker/entrypoint.sh` — **boundary-protected** ("DO NOT CHANGE —
     container first-boot logic stable"). Normalized under a SECOND user-approved
     scoped exception (AskUserQuestion 2026-05-31, option "Normalize now"): it was
     the only remaining AC-6 failure and CRLF leaves the container unable to boot
     (01-09's first live step). Logic byte-identical post-normalization;
     `bash -n` clean.
2. **`.env.example` also CRLF → normalized to LF** as part of the Task-2 reconcile
   (in files_modified). Trailing `\r` on every default line would have corrupted
   compose interpolation at deploy (e.g. `REDIS_HOST=127.0.0.1\r`).
3. **Real `.env` seeded in the working tree during verify.** Running
   `bash scripts/seed_env.sh` against the repo created a real `.env` (mode 0600,
   gitignored — confirmed `git check-ignore`) so `e2e_verify.sh` sections 1/8 could
   validate. Expected installer artifact; not committed.
4. **shellcheck not installed** on this host → skipped (plan said "if available").
   All 3 new scripts pass `bash -n`.

## Boundary status

Honored: docker-compose.yml topology, Dockerfile.*, gen_scope_jwt.py, init_wizard.py
(interactive path intact), 01_schema.sql, oracle/validation/recon/scope code — all
untouched. No live deploy, no parked-gate smokes, no image bake, no git tag/release,
no version bump (pyproject stays 0.1.0), no new Python deps. Coolify = docs only.

Two boundary-protected files (`generate_keys.sh`, `entrypoint.sh`) were CRLF→LF
normalized — both under explicit user approval, both pure line-ending fixes with
identical logic. No compose-default removal (M2 neutralized by always-overriding
via seeded .env, per audit).

## Deferred to 01-09

- Repo-wide CRLF: many other `scripts/*.py` / `*.sh` files remain CRLF (e.g.
  `init_wizard.py`, `cost_audit.py`, `bs`, field-validation runners). Only the
  4 files on the installer's critical path were normalized. A repo-wide LF sweep +
  `.gitattributes` to prevent recurrence is a candidate for 01-09 or a dedicated
  hygiene plan. **(NEW deferred issue — flag at UNIFY.)**
- Live deploy-gate smokes (worker triggers, recon→scan, webhook POST), bbscope +
  chromium image bake, public AGPLv3 release — all 01-09 as planned.

## Next

Run `/paul:unify .paul/phases/01-community-edition-mvp/01-08-PLAN.md` to reconcile
plan vs actual and close the 01-08 loop. Phase 1 → 8/9. (01-09 UNIFY triggers the
Phase 1→2 transition, not 01-08.)
