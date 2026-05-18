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

Status updated 2026-05-13. §3 + §4 closed this session.

| # | Item | Owner | Status / Blocker |
|---|---|---|---|
| 1 | Boot MCP servers and run orchestrator against `mariadb.org` with `SKIP_REPORT=1` | next session | Open — ~$8 LLM budget. Now framed as Path B under the Path-C decision below. See `docs/stage2_boot_runbook.md` for the operator-ready checklist. |
| 2 | Decide whether to pursue source-code-scope programs (`rails`, `django`, `phabricator`, `concretecms`) | next session | **Decided 2026-05-13 — Path C (hybrid).** See "Decision: Path C" below. Static-agent scaffold parked in `docs/static_agent_scaffold.md` and triggered only if Stage 2 returns 0 hypothesis findings. |
| 3 | Stand up Grafana with the bundle from `infra/grafana/` so panels shipped in `c13b992` render | operator | **Done 2026-05-13.** v4 compose (`/home/nilhem/bountystrike-ai/infra/docker-compose.yml`) now bind-mounts v5 provisioning; grafana relocated to host port 3010 (3000 occupied by hermes-agent WhatsApp bridge). Datasource `BountyStrike-PG → postgres:5432/bountystrike_v5` provisioned; Phase 3 Exit dashboard visible in the "BountyStrike" folder. v4 compose edit lives in v4 working tree — operator commits in v4 repo. |
| 4 | Run `scripts/bs kill-switch-watch` as a systemd unit | operator | **Done 2026-05-13** — commit `e46c409`. Unit at `infra/systemd/bountystrike-kill-switch-watch.service`; `systemd-analyze verify` exit 0; install instructions inline in the unit header. |

Also committed this session: `6a02349` — `.mcp.json` registers 15 MCP servers + 9 platform/utility `uv.lock` files; unblocks Stage-2 boot.

### 2026-05-13 — Stage-2 prep: FP root-cause fix + runbook gap closed

Two commits land defensive work before the Path B Stage-2 run:

- `beb85cf feat(recon): reflection probe drops unreflected xss-candidate at source` — adds a `ReflectionProber` Protocol injected into `ReconService`. Every `xss-candidate` row gets a single GET with a high-entropy sentinel before INSERT; rows that don't reflect into the response body are dropped. Closes 3 FP classes documented in operator memory (`mariadb /download/`, WordPress `?ver=`, WordPress REST routes) at the recon emission path. 7 new tests, 36/36 + 461/461 green. Scanner-agent's direct INSERT path is unaffected — but its xss-candidate emitters (nuclei CVE templates, arjun) already reflection-check internally, so coverage is high.
- `0ca68ae docs(phase3): Stage-2 runbook — sandbox driver preflight + MAX_EXPLOITS=0 default` — Stage-2 audit (vs `mcp/sandbox-mcp/` source + Firecracker reference docs) found every production sandbox driver is GAP-deploy: `local` is dev-only, `docker` returns `Verdict.ERROR` without an unimplemented egress-gate sidecar, `firecracker` driver doesn't exist. Runbook now (a) preflights `SANDBOX_DRIVER` explicitly, (b) defaults `MAX_EXPLOITS=0` so the Path B run exercises recon + scanner-agent (the actual Phase-3 differentiator) without burning Venice/Hermes spend on exploit-agent invocations that will crash at step 6, (c) records the expected terminal status distribution so a clean run is distinguishable from a regression.

Net effect: Path B is now safe to fire on operator's schedule — the run won't waste budget on a broken sandbox stack and the dominant FP class (recon fallthrough heuristic) no longer pollutes the findings table.

## Decision: Path C — Hybrid (recorded 2026-05-13)

§1 (dynamic Stage 2) and §2 (static-analysis path) are not independent. §2's answer depends on §1's data. Single hypothesis test with branching follow-up:

**Hypothesis:** LLM-driven recon+exploit agents (Stage 2) bypass the WAF wall that nuclei-template probing could not on the three programs tested 2026-05-07.

**Path B (run first):** `scripts/orchestrator.py SKIP_REPORT=1` against `mariadb.org` with the existing scope JWT. ~$8, ~30–90 min.

**Decision rule:**
- ≥1 hypothesis finding → continue dynamic; defer static-agent indefinitely
- 0 findings on a WAF target → commit to Path A; start `static-agent` scaffold next sprint

Either outcome populates `hunt_outcomes` and unblocks ρ measurement.

**Rationale:** Building Path A without Path B's evidence is speculative generality. Path B costs $8 to falsify the cheaper hypothesis first; Path A costs 1–2 sprints of engineering. Cheap evidence before expensive code.

**Reference:** Karpathy guideline §2 (simplicity first) and §4 (verifiable goal per path) drove the framing.

## Stage-2 first run (2026-05-17) — 128 hypothesis findings, Path B chosen

- **Job:** `170457c4-e218-4fc4-9128-e49aeeddc917`, program `mariadb`/hackerone, scope `*.mariadb.org`
- **Wall clock:** 51.7 min (recon 46 min, exploit-phase deadlock detected ~5 min in)
- **Cost:** $0.00 vs $10 budget (recon used deterministic binaries; LLM exploit-phase never spent)
- **Status histogram:** hypothesis=128, no validated/rejected (exploit phase aborted before LLM execution)
- **CWE breakdown:** open-redirect-candidate=100, xss-candidate=28
- **Hosts (all in-scope):** jira.mariadb.org=89, mariadb.org=37, git.mariadb.org=2
- **SKIP_IDOR=1** dropped 46 idor-candidate rows post-recon (Gap-2 mitigation worked as designed)
- **filter-unreflected** ran on 28 xss-candidates → 0 dropped, 28 kept (Gap-1 mitigation, no false positives this run)
- **Gap-3/Gap-4** status: deferred (MAX_EXPLOITS=0 attempt deadlocked before sandbox-driver gap could surface)

**Decision rule satisfied:** ≥1 hypothesis on a WAF-shielded target → **commit to Path B (dynamic).** Defer static-agent scaffold.

### Bug surfaced — `scripts/orchestrator.py:506` `MAX_EXPLOITS=0` deadlocks

`asyncio.Semaphore(max_exploits)` with `max_exploits=0` produces a semaphore with zero permits; the subsequent `asyncio.gather(*[_exploit_one(...)])` blocks all 128 tasks forever waiting on `.acquire()`. The runbook and Stage-2 plan both recommend `MAX_EXPLOITS=0` as the lever for skipping exploit work; the working lever is `SKIP_EXPLOIT=1`, which short-circuits at line 499 before reaching the semaphore.

**Workaround:** export `SKIP_EXPLOIT=1` instead of `MAX_EXPLOITS=0`.
**Permanent fix (next sprint):** treat `max_exploits=0` as equivalent to `skip_exploit=True` at line 499, or guard with `if max_exploits == 0 or not hypo_ids: skip exploit-loop`.

### Plan-deviations applied during this run (root-cause fixes, not workarounds)

- `.env` line 10: DB `bountystrike_v5 → bountystrike` (compose + init SQL + code defaults all use `bountystrike`; `_v5` suffix was aspirational and never actualized)
- `.env` line 10: password `bspass → ${POSTGRES_PASSWORD}` (role password set on volume init to long value, hardcoded `bspass` never worked over TCP)
- Pre-flight: ran `scripts/bs seed-programs` (860 programs, 49090 scopes) — original plan assumed programs were already seeded
- Runbook drift: references `bs_postgres` (underscore) container — live v5 container is `bs-postgres` (dash). Underscore name belongs to old `bountystrike-ai` v4 repo.
- Plan called `uv run python scripts/bs ...`; `scripts/bs` is bash, correct form is direct `scripts/bs ...`

### Next-sprint inputs

1. Patch `MAX_EXPLOITS=0` deadlock; re-run Stage-2 to validate the cleanup path actually runs an LLM exploit attempt
2. Validate the 100 open-redirect-candidate findings — needs `verify_open_redirect` oracle pass (Gap-1 only covers xss reflection)
3. Update `docs/stage2_boot_runbook.md` to fix the underscore→dash container-name drift and the `MAX_EXPLOITS=0` recommendation
4. Pick a second WAF-shielded program from EV ranking, repeat Stage-2 for ρ-measurement progress (target: 5 submissions)

## See also

* `docs/changelog.md` §Phase 3 — Calibration
* `docs/research/06-roadmap.md` §Phase 3 — Solo Deploy, Alpha Hunters, Calibration
* `docs/phase1_signoff.md` for the format precedent
* `docs/stage2_boot_runbook.md` — operator runbook for Path B
* `docs/static_agent_scaffold.md` — Path A scaffold (triggered only if Path B yields 0 findings)
