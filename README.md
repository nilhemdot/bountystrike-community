# BountyStrike v5

Claude Code-native autonomous bug bounty platform. Recon, exploit hypothesis, deterministic verification, hash-chained evidence, tiered approval, and platform submission — all driven by Claude agents under hard scope-JWT and rate-limit boundaries.

**Status:** **v0.1.0 — Community Edition MVP released** (2026-05-31). Phase 1 complete: DB foundation, Hatchet v1 runtime, hash-chained evidence store, federated scope ingestion, scope-diff notifications, deterministic verifier wiring, recon rate-limiting, one-line installer, and live deploy-gate smokes (bbscope + chromium image bake, worker triggers, recon→scan, webhook POST).

## Release — v0.1.0

[![version](https://img.shields.io/badge/version-0.1.0-blue.svg)](CHANGELOG.md) · AGPL-3.0-or-later

First public Community Edition release. See the full release notes in
[`CHANGELOG.md`](CHANGELOG.md). Licensed under [AGPL-3.0](LICENSE-AGPL) — third-party
license posture in [`LICENSES.md`](LICENSES.md). Self-host in one line:

```bash
bash scripts/install.sh
```

## Highlights

- **Five non-negotiables** (full text in [`docs/project-overview-pdr.md`](docs/project-overview-pdr.md)):
  scope enforcement at the network layer, deterministic verifier independent of the exploiter, hash-chained evidence, T1/T2/T3 human-tier approvals, and per-program EV ranking.
- **8 verification oracles** in [`mcp/oracle-mcp`](mcp/oracle-mcp/): XSS (Playwright DOM observer), SSRF (Interactsh OAST), SQLi (Welch t-test timing), SSTI, IDOR, Open Redirect, RCE, SSRF→IMDS. **7 of 8 field-validated at TPR=1.0, FPR=0.0** (Phase 1 XSS/SSRF + Phase 2 W7-8 SSRF→IMDS, IDOR, RCE, SSTI, Open Redirect). SQLi field-validation suite pending W9-10.
- **15 MCP servers** (14 Python + 1 TypeScript): see [`docs/codebase-summary.md`](docs/codebase-summary.md) §MCP Inventory.
- **9 sub-agent specs** in [`.claude/agents/`](.claude/agents/) (recon, scanner, validator, reporter, scope-guard, exploit, ai-vuln-hunter, cloud-recon, program-selector).
- **4 PreToolUse hooks** wired via [`.claude/settings.json`](.claude/settings.json): kill switch, antislop, openrouter routing, approval gate.
- **Postgres 17 + pgvector** with HNSW vector index + pg_trgm wildcard match. 12 tables, 16-state finding-status ENUM. Schema in [`infra/sql/`](infra/sql/).

## Architecture (one-screen view)

See full diagrams (component graph, data flow, ER, scope-JWT trust boundary, kill-switch layers, finding-status state machine) in [`docs/system-architecture.md`](docs/system-architecture.md).

```
                  ┌─ control-plane (FastAPI + DDD domains) ─┐
operator → JWT →  │   recon  approval_gate  evidence  EV    │ ← Postgres 17
                  │   scope_management   safety   ranking   │   pgvector + pg_trgm
                  └─────────────────────────────────────────┘
                                    │ subprocess / stdio
                  ┌─────────────────┴─────────────────┐
                  ▼                                   ▼
       Claude sub-agents (9)              MCP servers (15)
       recon, scanner, exploit,          oracle, evidence, dedup,
       validator, reporter, etc.          state, ev, kev, scope (TS),
                                          h1/bugcrowd/intigriti/
                                          yeswehack/immunefi,
                                          normalize, politeness, sandbox
```

## One-line install

Take a fresh Ubuntu/Hetzner host from clone → running stack with one command. The
installer is idempotent (safe to re-run) and never overwrites an existing `.env`
or keypair. It auto-generates the infra secrets, generates the RS256 scope keypair,
brings the compose stack up, and waits for healthchecks.

```bash
git clone <repo> bountystrike-ai7 && cd bountystrike-ai7
bash scripts/install.sh --unattended
```

- `--no-up` — provision `.env` + scope keypair only, skip `docker compose up`.
- `--install-docker` — opt-in to auto-install Docker (only with `--unattended`).
  The installer never pipes `curl | sh` to a root shell unless you explicitly ask.

Fill in your BYOK keys (`ANTHROPIC_API_KEY`, `DEEPSEEK_API_KEY`, …) and platform
credentials in `.env` afterwards — the installer leaves those blank for you.

> A hosted `curl … | bash` one-liner will be published with the public AGPLv3
> release; until then use the `git clone` form above.

## Quickstart (solo mode)

Requires Python ≥3.12, Docker, [`uv`](https://docs.astral.sh/uv/), and `openssl` for keygen. Full prerequisites in [`docs/research/05-deployment.md`](docs/research/05-deployment.md).

> **New to BountyStrike?** Run the interactive setup wizard — it walks through environment configuration, API key setup, JWT keypair generation, and a guided first-scan walkthrough:
> ```bash
> scripts/bs init
> ```
> The wizard can be re-run anytime to update configuration: `scripts/bs init --update`.

```bash
# 1. Clone + sync workspace
git clone <repo> bountystrike-v5 && cd bountystrike-v5
uv sync                     # installs control-plane + 5 registered MCPs

# 2. Generate scope-JWT keypair (RS256, 4096-bit)
python scripts/gen_scope_jwt.py keygen --out keys/

# 3. Configure environment
cp .env.example .env        # fill POSTGRES_PASSWORD, REDIS_PASSWORD, ANTHROPIC_API_KEY, etc.

# 4. Bring up Postgres + Redis + Hatchet + Langfuse + Caddy
docker compose -f infra/docker/docker-compose.yml --env-file .env up -d
# Schema migrations auto-apply from infra/sql/*.sql on first boot.

# 5. Issue a scope JWT for one program
python scripts/gen_scope_jwt.py issue \
  --operator-id me \
  --program-handle acme-corp \
  --platform hackerone \
  --targets 'wildcard=*.acme.com' \
  --out scope.jwt

# 6. Run a scan
SCOPE_JWT=$(cat scope.jwt) PROGRAM_HANDLE=acme-corp PLATFORM=hackerone \
  DATABASE_URL=postgresql://bs:$POSTGRES_PASSWORD@localhost:5432/bountystrike \
  python scripts/orchestrator.py
```

## Repository Layout

| Path | Purpose |
|---|---|
| `control-plane/` | FastAPI + DDD domains (recon, scope, approval gate, evidence, EV, safety) |
| `mcp/` | 15 MCP servers (FastMCP stdio + 1 TypeScript) |
| `infra/sql/` | 6 Postgres migrations (extensions, schema, dedup, audit realign, approval queue, raw_finding column) |
| `infra/docker/` | docker-compose.yml, Caddyfile, Dockerfile.recon |
| `keys/` | RS256 scope-JWT keypair (gitignored) |
| `scripts/` | orchestrator, JWT gen, field validation harnesses |
| `docs/` | project-overview, codebase-summary, system-architecture, code-standards, research/, architecture/, phase1_signoff |
| `.claude/` | settings.json, 6 hooks, 9 sub-agent specs |

Full file map in [`docs/codebase-summary.md`](docs/codebase-summary.md).

## Tests

```bash
# Control-plane (21 tests)
uv run --package control-plane pytest control-plane/tests/

# Per-MCP tests
uv run --package oracle-mcp pytest mcp/oracle-mcp/tests/

# Field-validation harnesses (TPR=1.0 / FPR=0.0)
uv run python scripts/run_xss_field_validation.py            # Phase 1.1c
uv run python scripts/run_ssrf_field_validation.py           # Phase 1.1d
uv run python scripts/run_ssrf_imds_field_validation.py      # Phase 2 W7-8
uv run python scripts/run_idor_field_validation.py           # Phase 2 W7-8
uv run python scripts/run_rce_field_validation.py            # Phase 2 W7-8
uv run python scripts/run_ssti_field_validation.py           # Phase 2 W7-8
uv run python scripts/run_open_redirect_field_validation.py  # Phase 2 W7-8

# Operator approval-queue CLI (T1/T2/T3)
uv run python scripts/approve.py list
uv run python scripts/approve.py show <request_id>
uv run python scripts/approve.py approve <request_id> --reason "..."
uv run python scripts/approve.py reject <request_id> --reason "..."
```

Test count: 216 total post-Phase-1; Round 5 added 39 (24 queue unit + 8 orchestration smoke + 7 Postgres integration); Round 6 field-validation suites added per-oracle integration tests on top.

## Node.js Environment Verification

Verified on 2026-05-13 that `mcp/scope-mcp` works with the current local Node toolchain (no `nvm` required for this repo at present).

- `node`: `v22.22.2`
- `npm`: `10.9.7`
- `corepack`: `0.34.6`
- `pnpm`: `10.33.0`

Validation commands run:

```bash
cd mcp/scope-mcp
npm ci
npm run build
npm test
```

Result: build passed, typecheck passed, and tests passed (`32/32`).

## Documentation Map

- [`docs/project-overview-pdr.md`](docs/project-overview-pdr.md) — vision + 5 non-negotiables + scope
- [`docs/codebase-summary.md`](docs/codebase-summary.md) — file inventory, deps, tables, MCP tools
- [`docs/system-architecture.md`](docs/system-architecture.md) — Mermaid diagrams (6+)
- [`docs/code-standards.md`](docs/code-standards.md) — Python style, DDD layout, MCP template, hook authoring
- [`docs/architecture/bountystrike_v5_build_plan.md`](docs/architecture/bountystrike_v5_build_plan.md) — full 20-week spec
- [`docs/research/`](docs/research/) — 9 numbered research notes (libraries, routing, oracles, deployment, roadmap)
- [`docs/signoffs/phase1_signoff.md`](docs/signoffs/phase1_signoff.md) — Phase 1 audit + Round 4 closeout

## Security & Scope Boundary

- **Scope JWT** (RS256, 4096-bit, 168h max): every MCP that touches a target validates the JWT and enforces target/exclusion/rate-limit claims. See `mcp/scope-mcp/` (TypeScript) and [`control-plane/src/control_plane/domains/scope_management/services/jwt_issuer.py`](control-plane/src/control_plane/domains/scope_management/services/jwt_issuer.py).
- **Kill switch** (3 layers): Redis flag (`bountystrike:killswitch:global`) → PreToolUse hook (`pretool_killswitch.py`) → SIGTERM supervisor.
- **Antislop hook**: blocks hallucinated report writes outside `reports/*` prefix.
- **Approval gate**: T1 (LLM review) / T2 (single-human) / T3 (two-person) before any platform submission.

Never commit `.env`, `keys/`, or anything matching the `.gitignore` patterns. Bug-bounty work is authorized testing only — scope JWT enforces this at the network layer.

## License

TBD. Internal/private repo until Phase 4 release decision.
