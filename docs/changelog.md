# Changelog — BountyStrike v5

Generated from `git log --oneline --no-merges`. Grouped by Conventional-Commits-ish prefix (`feat`, `fix`, `fix(security)`, `perf`, `test`, `docs`, `chore`, `refactor`, `ci`). Phase tags from commit subjects.

**Snapshot:** 2026-05-07. 80+ commits in the visible history. Phase 0 → Phase 1 (signed off 2026-05-01) → Phase 2 W7-8 closed → Phase 2 W9-10 closed → Phase 3 calibration scaffolding shipped → Phase 3 first live run captured in [`phase3_lessons.md`](signoffs/phase3_lessons.md).

For phase-level rollups see [`phase1_signoff.md`](signoffs/phase1_signoff.md), [`phase3_lessons.md`](signoffs/phase3_lessons.md), and [`research/06-roadmap.md`](research/06-roadmap.md).

## Phase 3 — Calibration (telemetry shipped, first live run captured 2026-05-07)

Operator-side scaffolding now committed (was uncommitted at the 2026-05-02 snapshot):

- Domain repository: `program_ranking/repositories/hunt_outcome_repository.py`
- Domain VO: `program_ranking/value_objects/hunt_outcome.py`
- Service: `program_ranking/services/calibration_service.py`
- Migration `infra/sql/07_phase3_calibration.sql`, `infra/sql/08_phase3_oracle_fp.sql`
- Operator scripts: `scripts/cost_audit.py`, `scripts/metrics.py`, `scripts/onboard_hunter.py`, `scripts/reconcile_hunt_outcomes.py`, `scripts/kill_switch_watch.py`, `scripts/bs`
- Grafana provisioning bundle: `infra/grafana/`
- CI: `.github/workflows/integration-pg.yml` (Postgres + pgvector matrix)
- Integration tests: `tests/integration/test_dedup_recall_phase3.py`, `tests/integration/test_migration_07_phase3.py`, `tests/integration/test_kill_switch_watch.py`
- Unit test: `control-plane/tests/test_calibration_service.py`

First live run (2026-05-07): one alpha hunter onboarded against three real H1 programs (shopify, hackerone-self, mariadb); recon pipeline persisted 524 assets; nuclei-against-WAF produced no submission-worthy findings. Lessons in [`phase3_lessons.md`](signoffs/phase3_lessons.md).

## Phase 2 — W7-W10

### Phase 2 W9-10 (in flight)

```
8d2601c perf(infra): split Dockerfile.recon dep-sync from source layer
f5a50c1 test(safety): 100-scan OOS audit for Phase 2 §10.4 #5
98dbdd6 perf(dedup): batch OpenAI embeddings in recall runner
5f79070 fix(test): rebase ev fixture freshness timestamps relative to now
b8c9e1e fix(ci): pin setup-uv to v8.1.0 in r2-smoke
92d2ada fix(infra): split CGO per-binary in Dockerfile.recon
fd19d69 feat(phase1): 1.1f-deploy live R2 round-trip — close 1.1f code-side
caad67c feat(infra): 1.1e-deploy recon image CI — ghcr.io via OIDC
bbbd13a feat(phase2): orchestrator wires validator-compliance audit into summary
6b0bb87 feat(phase2): validator-spec compliance audit
b00ce35 chore: add pyrightconfig.json for control-plane and MCP servers
f13ae8e chore: gitignore learn/ ECC skill artifacts
c865622 docs: add project README, PDR, codebase summary, system architecture, code standards
f25f307 chore(hooks): suggest tmux for long-running Bash commands
3eb5eda chore: remove unused claude-flow MCP server and config
412402a feat(phase2): semantic dedup live-Postgres coverage
ed8bf83 feat(phase2): recon-assets emit — close recon→scanner contract
d2c3765 feat(phase2): dedup-prod live-Postgres integration coverage
86bd793 feat(phase2): F2 schema-vs-spec contract test + migration 06 drift fixes
f62316c feat(phase2): Layer-3 kill-switch enforcer + §10.4 <5s SLA test
```

### Phase 2 W7-8 (closed 2026-05-01)

Five new oracle field-validation suites (TPR=1.0 / FPR=0.0) + T3 approval plumbing:

```
e9b4b77 feat(phase2): SSRF→IMDS field-validation suite — TPR=1.0 FPR=0.0
65fe921 feat(phase2): IDOR field-validation suite — TPR=1.0 FPR=0.0
5493eea feat(phase2): RCE field-validation suite — TPR=1.0 FPR=0.0
6ef4858 feat(phase2): SSTI field-validation suite — TPR=1.0 FPR=0.0
1b6eb64 feat(phase2): Open Redirect field-validation suite — TPR=1.0 FPR=0.0
3fbe009 feat(phase2): SQLi field-validation suite — TPR=1.0 FPR=0.0
7001be1 feat(phase2): T3 approval plumbing in orchestrator
636b576 feat(phase2): wire exploit + T2/T3 approval queue
b7ec4e3 feat: kev-mcp `kev_match_program` — tech-stack ↔ KEV cross-reference
```

## Phase 1 (signed off 2026-05-01)

```
e6b285e docs: phase1 signoff Round 4 — close 1.1c + 1.1d (TPR=1.0, FPR=0.0)
c75c3a9 fix: PreToolUse hooks emit valid Claude Code wire schema
1c07cfb chore: add ruflo runtime/data files to .gitignore
e5371b9 chore: configure ruflo/claude-flow environment
38dc943 fix: state-mcp DSN parse + lock distinction + leak tests; cvss double-round; body-shape value asserts
0077e90 feat: 429 retry with Retry-After honor across all 5 platform MCPs
34bb03c fix: normalize CWE accuracy + ywh extra passthrough + state-mcp LIKE escape
c38ff2e fix(security): politeness TOCTOU + sandbox OOM + strict bool gate
068d1a6 fix(security): platform-MCP SSRF + base_url + body-leak hardening
bf11566 docs: 00c — context7 verifications (h1 + bugcrowd + intigriti + firecracker)
3d9e915 feat: dedup recall fixture — Phase 2 §10.4 last exit criterion (recall=1.0)
2e56883 fix: h1-mcp — verified against /websites/api_hackerone, add structured_scope_id
938d9f3 fix: bugcrowd + intigriti — align with real APIs (context7-verified)
accafc7 feat: bugcrowd-mcp + intigriti-mcp + immunefi-mcp — 3 platform submitters
1d824be feat: wire 4 PreToolUse hooks via .claude/settings.json
b1a44bf feat: h1-mcp — HackerOne report submission with retry + JSON:API body
3d5d52b feat: Phase 1.1d — SSRF field validation suite (TPR=1.0, FPR=0.0)
4e84007 feat: Phase 1.1c — XSS field validation suite (TPR=1.0, FPR=0.0)
fd55aff feat: yeswehack-mcp — report submission with retry + 4xx-no-retry semantics
b61546d feat: sandbox-mcp — protocol + LocalSubprocessDriver + DockerDriver scaffold
81539eb feat: state-mcp — finding/artifact queries + experience KB + status writes
30fbeff feat: normalize-mcp — CVSS v3.1/v4 scoring + CWE normalisation
98b81fa feat: politeness-mcp — per-host token bucket + adaptive backoff
9eb35ab feat: anti-slop PreToolUse hook — reject reports/*.md slop
bb72ad2 feat: dedup-mcp semantic tier — pgvector cosine + 4-tier classify
afa9f59 feat: 6 subagent specs — complete 9/9 roster
d276b40 feat: approval-gate hook integration — Phase 2 build-plan §6.3
1ab199e feat: Venice/Hermes routing hook — Phase 2 build-plan §10.4
8313a53 feat: ev-mcp — EV-ranked program scoring (build-plan §4.5)
437c429 feat: kev-mcp — CISA KEV + EPSS v4 lookup (build-plan §4.7)
1bb6469 feat: T0-T3 approval gates — Phase 2 build-plan §6.3
623f14f feat: kill switch — Phase 2 build-plan §6.6 three-layer safety
c234ae8 feat: BlobStore composition root — Phase 1.1f code-side closeout
9511905 feat: recon container — Phase 1.1e GAP-deploy closeout
e47cfd9 feat: Phase 1 sign-off remediation — schema, concurrency, harness, R2
67305be feat: wire reporter-agent into orchestrator pipeline
913c1c9 feat: reporter-agent + gen_scope_jwt + fix recon schema
75587a9 feat: migration 02 + pipeline orchestrator
155f18b docs: validator-agent subagent spec — MCP orchestration glue
6271df9 feat: dedup-mcp FastMCP server — pre-oracle finding deduplication
1b6df2d feat: Phase 2 — evidence-mcp FastMCP server
d4bd2da test: Phase 1.0b — EV formula validation over 50 synthetic programs
6de3c59 feat: Phase 1 — 8 deterministic oracles + evidence chain + recon agent
f1654e9 refactor: apply v3 DDD + security patterns to bountystrike-v5
```

## Phase 0 — Scaffolding

```
88ef4e2 feat: Phase 0b/c/d/e — infra, scope-mcp, scope ingest, EV engine
7065766 feat: Phase 0a+0f scaffold — repo tree, uv workspace, RS256 scope JWT
```

## Grouped Highlights

### Security hardening

- `c38ff2e` politeness TOCTOU + sandbox OOM + strict bool gate
- `068d1a6` platform-MCP SSRF + base_url + body-leak hardening
- `1d824be` wire 4 PreToolUse hooks via `.claude/settings.json`
- `c75c3a9` PreToolUse hooks emit valid Claude Code wire schema

### Oracle accuracy gates (TPR=1.0 / FPR=0.0)

| Oracle | Commit | Phase |
|---|---|---|
| XSS | `4e84007` | 1.1c |
| SSRF | `3d5d52b` | 1.1d |
| SSRF→IMDS | `e9b4b77` | 2 W7-8 |
| IDOR | `65fe921` | 2 W7-8 |
| RCE | `5493eea` | 2 W7-8 |
| SSTI | `6ef4858` | 2 W7-8 |
| Open Redirect | `1b6eb64` | 2 W7-8 |
| SQLi | `3fbe009` | 2 W7-8 |

### Approval lifecycle

- `1bb6469` T0-T3 gates (build-plan §6.3)
- `d276b40` approval-gate hook integration
- `636b576` wire exploit + T2/T3 approval queue
- `7001be1` T3 approval plumbing in orchestrator (two distinct actors)

### Kill switch (3-layer)

- `623f14f` initial three-layer scaffold
- `f62316c` Layer-3 enforcer + §10.4 <5s SLA test

### Storage / persistence

- `75587a9` migration 02 + pipeline orchestrator
- `86bd793` F2 schema-vs-spec contract test + migration 06 drift fixes
- `bb72ad2` dedup-mcp semantic tier — pgvector cosine + 4-tier classify
- `3d9e915` dedup recall fixture (recall=1.0)
- `412402a` semantic dedup live-Postgres coverage
- `d2c3765` dedup-prod live-Postgres integration coverage
- (Phase 3 in-flight) `infra/sql/07_phase3_calibration.sql` — calibration tables

### CI / infra

- `caad67c` recon image CI — ghcr.io via OIDC
- `fd19d69` 1.1f-deploy live R2 round-trip
- `b8c9e1e` pin setup-uv to v8.1.0 in r2-smoke
- `92d2ada` CGO per-binary split in Dockerfile.recon
- `8d2601c` Dockerfile.recon dep-sync layer split

## Conventions

- Subject ≤ 72 chars, imperative
- Type prefixes: `feat`, `fix`, `fix(security)`, `perf`, `test`, `docs`, `chore`, `refactor`, `ci`
- Phase tags: `Phase 1.1c`, `Phase 2 W7-8`, `Phase 2 §10.4`, etc.
- Body explains *why* if non-obvious
- Co-Author trailer omitted globally per `~/.claude/settings.json`

Never `--amend` after pushing. Never `--no-verify`.

## See Also

- [`phase1_signoff.md`](signoffs/phase1_signoff.md) — Phase 1 audit + Round 4 closeout
- [`research/06-roadmap.md`](research/06-roadmap.md) — phase exit criteria + risk register
