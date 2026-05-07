# BountyStrike v5 — Phase 3 Lessons (First Live Run)

**Date:** 2026-05-07
**Phase:** 3 — Solo Deploy, Alpha Hunters, Calibration (Weeks 11-14)
**HEAD commit:** `36bd515 fix(onboard_hunter): all --hosts go to the single program when only one`

## TL;DR

The Phase 3 *pipeline plumbing* (DB schema, recon ingest, JWT issuance,
operator profile, EV scoring, oracle FP view, kill-switch watcher) all
work end-to-end against real bug-bounty targets. The Phase 3 *first
real-finding gate* (5+ submitted, ρ ≥ 0.60, < $0.20/scan) is **not**
closeable with a naive nuclei-against-public-scope strategy because
modern bounty programs are universally WAF-protected at every
in-scope endpoint we touched. This is a strategic finding, not a bug.

The product's actual differentiator — LLM-augmented adaptive scanning
that mimics legitimate browser traffic and bypasses WAF heuristics —
remains untested and is the only credible path to first findings on
the targets a hunter would actually pick.

## What we validated (works in production)

| Layer | Verification |
|---|---|
| `bountystrike_v5` Postgres database | 9 migrations apply cleanly to a fresh DB; 16 tables created |
| `operators` row + skill vector | `nilhem` onboarded via `scripts/onboard_hunter.py` |
| RS256 scope JWT issuance | Three production JWTs minted (shopify, hackerone-security, mariadb); all decode through `ScopeJWTValidator` |
| `--wildcards` flag (new) | Onboarding accepts wildcard scopes such as `*.shopify.com,*.shopify.io` and binds them to the JWT |
| Single-program multi-host (new) | Onboarding routes every `--host` to the one program when `--programs` lists exactly one — fixed mid-run |
| Subfinder + httpx → `recon_assets` persistence | Three scan_jobs persisted with 524 total recon_assets across the three programs |
| `programs` row + EV scoring | New programs ranked correctly via `control_plane.domains.program_ranking` |
| `v_oracle_fp_rate` view | Reachable from production DB; returns zero rows pre-submissions |
| 542 / 542 tests green (control-plane unit + tests/integration with PG) | No regression introduced by the session's changes |

## Live targets attempted

Three programs, three nuclei runs, **5 findings total — all info severity, none submission-worthy**.

| Program | Hosts in JWT | Live | Nuclei findings | Useful? |
|---|---|---|---|---|
| shopify | 4 wildcards (`*.shopify.com`, `*.email.shopify.com`, `*.shopifykloud.com`, `*.shopify.io`) | 515 | 1 (cookies-without-httponly, info) | No |
| hackerone (security) | 7 exact hosts + 2 wildcards | 8 | 1 (azure-domain-tenant, info) | No |
| mariadb | `mariadb.org` exact | 1 | 3 (waf-detect, info) | No |

**Combined finding rate over ~40 minutes of nuclei: ~0.0008 hits/host.**
Cloudflare WAF / Seravo WAF / managed-host filters drop ~99.9% of
template-driven probes.

## What this means for the product

bountystrike-v5's value proposition is *not* a nuclei wrapper. The
architecture documents (`research/01-strategy-architecture.md`,
`research/03-verifier-antislop.md`) bet on three differentiators:

1. **Oracle-mcp deterministic verification** — TPR=1.0/FPR=0.0 oracles
   for XSS / SSRF / RCE / SSTI / IDOR / SQLi / SSRF→IMDS / Open Redirect
   gating any submission. Useless when there are no candidate findings
   to verify.
2. **LLM-augmented adaptive recon and exploit** — recon-agent and
   exploit-agent issue probes that read like legitimate browser
   sessions, parse responses contextually, and chain insights across
   endpoints. This is the layer most likely to traverse modern WAF
   heuristics and is the only one not yet exercised against a live
   target.
3. **Evidence chain + dedup** — irrelevant until findings exist.

The first real gate to clear is therefore *Stage 2 of the graduated
plan* — boot the MCP servers, run `scripts/orchestrator.py` against a
chosen target with `SKIP_REPORT=1`, and verify whether the
recon/scanner subagents produce candidate findings that the oracle
suite then validates. That run will cost LLM tokens (estimated $3-8
per host) and is the next critical experiment.

## Why we stopped before doing it

Three reasons:

* The graduated plan agreed in this session was *naive recon first,
  LLM-orchestrator second*. We finished the naive layer. Spending
  another $8 on the LLM layer with the same target list is fine; it
  just does not need to happen in the same sitting.
* Three nuclei runs without a useful finding is enough evidence that
  template-driven probing is the wrong layer to invest more time in
  for hardened H1 programs. Banking that lesson is the cheap move.
* The session already produced three commits' worth of material to
  ship (CI workflow, telemetry stack, onboarding fixes); cutting now
  keeps the change set reviewable.

## Concrete state at sign-off

* `bountystrike_v5` Postgres DB live on the local Docker stack.
* `operators.nilhem` exists with skill vector `{web:0.85, api:0.7,
  auth:0.6}`.
* Three production scope JWTs minted (each 7 days):
  * `shopify` — `jti=jwt_1778162891_7445cd38f75f04cb`
  * `hackerone:security` — `jti=jwt_1778165613_b4e9b70327009fb1`
  * `hackerone:mariadb` — `jti=jwt_1778173815_7a4efe1489eae078`
* Three `scan_jobs` with `status=recon_complete` and a total of 524
  `recon_assets` rows.
* No `findings` rows. No submissions. No platform interaction.

## Phase 3 exit criteria — current state

Build-plan §10.5:

| # | Criterion | Status |
|---|---|---|
| 1 | confirmed-rate ≥ 70% | Not measurable — 0 submissions |
| 2 | avg scan cost ≤ $0.20 | Not measurable — 0 LLM scan runs |
| 3 | P90 TTV < 4h (P1/P2) | Not measurable — 0 validated findings |
| 4 | EV ρ ≥ 0.60 | Not measurable — `hunt_outcomes` empty |
| 5 | Dedup recall ≥ 0.95 | Met (1.0 on harness, see Phase 2 §10.4) |

Phase 3 cannot close until Stage 2 (LLM-augmented orchestrator run)
produces real findings, those findings get adjudicated by the
program, and the resulting outcome data feeds back into
`hunt_outcomes`.

## Outstanding work

| Item | Owner | Blocker |
|---|---|---|
| Boot MCP servers (oracle-, evidence-, dedup-, sandbox-, scope-, kev-, ev-) and run orchestrator scanner against `mariadb.org` with `SKIP_REPORT=1` | next session | LLM budget (~$8) and time |
| Decide whether to pursue source-code-scope programs (`rails`, `django`, `phabricator`, `concretecms`) — bypasses the WAF problem entirely by switching to static analysis on github URLs | next session | Static analysis path is not yet wired into the orchestrator |
| Stand up Grafana with the bundle from `infra/grafana/` so the panels shipped in `c13b992` actually render | operator | Decision on E1 vs E2 from earlier session |
| Run `scripts/bs kill-switch-watch` as a systemd unit | operator | systemd unit file not yet committed |

## See also

* `docs/changelog.md` §Phase 3 — Calibration
* `docs/research/06-roadmap.md` §Phase 3 — Solo Deploy, Alpha Hunters, Calibration
* `docs/phase1_signoff.md` for the format precedent
