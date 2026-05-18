# BountyStrike v5 — Documentation

Reader-routed index. Pick the persona that matches your task; the entry doc links onward to whatever else you need.

## I want to...

### Run the system → `runbooks/`

1. [`runbooks/deployment-guide.md`](runbooks/deployment-guide.md) — solo-mode bring-up (docker-compose, env, scope JWT).
2. [`runbooks/configuration-guide.md`](runbooks/configuration-guide.md) — every env var with default + purpose.
3. [`runbooks/testing-guide.md`](runbooks/testing-guide.md) — pytest config, fixtures, field-validation harnesses.
4. [`runbooks/stage2_boot_runbook.md`](runbooks/stage2_boot_runbook.md) — Phase 3 Path B operator checklist.

### Understand the system → `architecture/` + root

1. [`project-overview-pdr.md`](project-overview-pdr.md) — 1-page vision, 5 non-negotiables, success metrics.
2. [`codebase-summary.md`](codebase-summary.md) — file inventory, workspace members, MCP catalogue.
3. [`system-architecture.md`](system-architecture.md) — Mermaid diagrams (component graph, data flow, ER, scope-JWT, kill-switch, finding state machine).
4. [`code-standards.md`](code-standards.md) — DDD layout, ruff/mypy config, MCP template, hook authoring.
5. [`api-reference.md`](api-reference.md) — MCP tool inventory (15 servers).
6. [`architecture/bountystrike_v5_build_plan.md`](architecture/bountystrike_v5_build_plan.md) — full 20-week master spec (4525 LOC, source of truth).

### Audit / investigate → `audits/`

Completed investigations with verdicts. Open these to answer "did we look at X, what did we find?".

- [`audits/validator_agent_contract_audit_2026-05-13.md`](audits/validator_agent_contract_audit_2026-05-13.md) — recon/scanner gaps vs validator-agent contract.
- [`audits/bspass-credential-audit.md`](audits/bspass-credential-audit.md) — stale `bspass` placeholder in `.mcp.json`.
- [`audits/ollama-route-rewire.md`](audits/ollama-route-rewire.md) — A4 verdict to archive `pretool_venice_route.py`.

### Track phase progress → `signoffs/` + `changelog.md`

- [`signoffs/phase1_signoff.md`](signoffs/phase1_signoff.md) — Phase 1 exit-criteria audit (Rounds 1–6).
- [`signoffs/phase3_lessons.md`](signoffs/phase3_lessons.md) — first live-run outcomes (2026-05-07) + Path C decision.
- [`changelog.md`](changelog.md) — git-log rollup grouped by Conventional Commits prefix.

### Deep-dive on plan extracts → `research/`

Topic-indexed extracts of the master build plan. See [`research/README.md`](research/README.md) before treating these as standalone.

### Design contingencies → `spikes/`

Parked design contingencies, not active work.

- [`spikes/static_agent_scaffold.md`](spikes/static_agent_scaffold.md) — Phase 3 Path A; triggered only if Path B yields 0 findings.

## Directory map

```
docs/
├── README.md                    # this file
├── project-overview-pdr.md      # entry strategic doc
├── codebase-summary.md          # file inventory
├── system-architecture.md       # visual flows
├── code-standards.md            # style + conventions
├── api-reference.md             # MCP tool catalogue
├── changelog.md                 # git history rollup
├── architecture/                # master build plan
├── audits/                      # completed investigations
├── runbooks/                    # operational checklists
├── signoffs/                    # phase gates + lessons
├── spikes/                      # parked design contingencies
└── research/                    # plan extracts (see research/README.md)
```
