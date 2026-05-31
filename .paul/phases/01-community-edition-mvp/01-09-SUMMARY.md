---
phase: 01-community-edition-mvp
plan: 09
type: execute
wave: 1
depends_on: ["01-08"]
status: complete
completed: 2026-05-31
files_modified:
  - infra/docker/Dockerfile.control-plane
  - infra/docker/Dockerfile.recon
  - .gitattributes
  - scripts/live_smoke.sh
---

# 01-09 SUMMARY — Close Phase-1 live deploy gates (local Docker)

## Outcome
All seven acceptance criteria closed against the local Docker stack. The live
paths that 01-04/05/06/07 could only stub now run in-container: bbscope (scope
poll), chromium (XSS oracle), registered worker (triggers), real webhook sink
(scope-diff notify). This is the last engineering plan in Phase 1.

## Tasks executed

### Task 1 — Bake bbscope + chromium into worker/recon images (AC-1)
- `Dockerfile.control-plane`: new `golang:1.24-alpine AS bbscope-build` stage —
  `go install github.com/sw33tLie/bbscope/v2@2d3bae66eeaa9c75d16af99af58b96a0c76a14dc`
  (pinned commit; Go module-checksum DB / sum.golang.org transparency log is the
  integrity gate — M2). Static binary copied to `/usr/local/bin/bbscope`.
- Playwright/chromium baked: `playwright install-deps chromium` (root) +
  `playwright install chromium` (controlplane user). Chromium revision pinned by
  Playwright 1.58.0 in `uv.lock` — never `latest` (M2/S1).
- `Dockerfile.recon`: fixed `uv sync` exit-2 (workspace members oracle-mcp +
  politeness-mcp source missing) by copying the full `mcp/` tree before the
  control-plane source in Layer B — same fix applied to control-plane. subfinder/
  httpx/katana confirmed present from the go toolchain stage.
- **Verified on the RUNNING worker container:** bbscope invocable, chromium
  145.0.7632.6.

### Task 2 — Repo-wide CRLF→LF sweep + .gitattributes (AC-6)
- `.gitattributes` (new): `* text=auto eol=lf` + explicit LF for first-party text
  (`*.sh *.py *.ts *.json *.yml *.toml *.md *.sql Dockerfile* .claude/hooks/**`) +
  `-text` for crypto material / binaries (`*.pem *.key keys/** *.png *.gz …`).
- Working-tree CRLF count = 0 after renormalize; `.gitattributes` staged before
  the sweep (S3). bash -n / py_compile clean; unit suite 75 passed.

### Task 3 — Human-action checkpoint + live deploy-gate smokes (AC-2..AC-5, AC-7)
- Operator supplied: HATCHET_CLIENT_TOKEN (regenerated), SCOPE_WEBHOOK_URL
  (Discord canary sink), and named the authorized program. Scope JWT issued for
  **pd-spotify** (`*.spotify.com`, 4h TTL, rps=2) → `keys/scope_smoke.jwt`.
- `scripts/live_smoke.sh` (new) drives the gates. M1: recon target derived from
  the JWT `targets` ONLY — invalid/expired JWT aborts before any probe. M3:
  webhook redacted to scheme+host in logs; seeded `recon_assets` rows
  (tag `live-smoke`) dropped on exit.

## Acceptance criteria — final state
| AC | Gate | Result |
|----|------|--------|
| AC-1 | Worker runs chromium + bbscope, pinned + integrity-verified | ✅ bbscope invocable; chromium 145.0.7632.6 on running container |
| AC-2 | verify-finding produces REAL evidence via XSS oracle | ✅ chromium executed injected script in-container (oracle live) |
| AC-3 | scope_poll + record-evidence triggers succeed live | ✅ worker registered (0 errors), triggers fire |
| AC-4 | webhook delivery end-to-end | ✅ POST → HTTP 204; URL redacted in logs |
| AC-5 | recon→scan throttled, in-scope | ✅ passive subfinder → 50 subdomains of `*.spotify.com` (rps=2) |
| AC-6 | repo-wide CRLF eliminated + recurrence prevented | ✅ working-tree CRLF=0; `.gitattributes` present |
| AC-7 | recon scope-gated (M1) — never touches unauthorized host | ✅ target JWT-derived only; abort-on-invalid enforced |

## Security invariants held
- **M1** — every recon seed domain derived from the scope JWT; no hardcoded /
  example / third-party host in the smoke runner.
- **M2** — bbscope pinned by commit + verified via Go checksum DB; chromium pinned
  by Playwright lockfile. No unpinned/unverified binary or browser baked.
- **M3** — HATCHET token / webhook URL never echoed or committed; webhook redacted
  to scheme+host; seeded live test rows cleaned up on smoke exit.

## Deviations
- Recon image first build failed (`uv sync` exit 2) for the same workspace-member
  reason as control-plane; resolved by the `COPY mcp/` fix. One transient
  proxy.golang.org TLS timeout during a recon rebuild (network, not code) —
  succeeded on retry.

## Boundaries respected
Image content changed via Dockerfiles only. No domain logic, no schema change, no
release/tag. Local Docker only. (6 pre-existing integration failures —
SubagentSimulator model_id drift, orchestrator.py:352 — are out of this plan's scope.)

## Next
Run `/paul:unify` to close the loop. 01-10 (public AGPLv3 release) is pure release
mechanics — the last Phase-1 item.
