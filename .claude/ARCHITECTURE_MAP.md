# ARCHITECTURE_MAP.md — BountyStrike v5

## Directory Layout

```
bountystrike-ai7/
├── CLAUDE.md                          # behavioral rules (this session loads this)
├── pyproject.toml                     # uv workspace root + ruff + pytest config
├── uv.lock                            # pinned deps
├── .env.example                       # 21 required env keys
├── control-plane/                     # FastAPI orchestrator
│   └── src/control_plane/
│       ├── core/security/             # JWT validation, path guards
│       ├── domains/                   # DDD bounded contexts
│       │   ├── recon/
│       │   ├── approval_gate/
│       │   ├── evidence_management/
│       │   ├── program_ranking/
│       │   ├── safety/
│       │   └── scope_management/
│       └── infrastructure/
│           └── database.py            # SQLAlchemy 2.0 async sessions
├── mcp/                               # 15 MCP servers
│   ├── oracle-mcp/                    # 8 verifiers + Playwright + scipy
│   ├── evidence-mcp/                  # aiosqlite + R2/local blob
│   ├── dedup-mcp/                     # asyncpg + pgvector + OpenAI
│   ├── state-mcp/                     # asyncpg finding state machine
│   ├── ev-mcp/                        # expected value ranking
│   ├── kev-mcp/                       # CISA KEV + EPSS
│   ├── scope-mcp/                     # TypeScript — JWT validate
│   ├── h1-mcp/                        # HackerOne API
│   ├── bugcrowd-mcp/                  # Bugcrowd API
│   ├── intigriti-mcp/                 # Intigriti (placeholder)
│   ├── yeswehack-mcp/                 # YesWeHack API
│   ├── immunefi-mcp/                  # Immunefi API
│   ├── politeness-mcp/                # token bucket rate limiter
│   ├── sandbox-mcp/                   # local + Docker execution
│   └── normalize-mcp/                 # CVSS + CWE normalization
├── infra/
│   ├── docker-compose.yml             # Postgres 17, Redis 7, Hatchet, Langfuse
│   └── migrations/                    # SQL migration files
├── scripts/                           # CLI entry points
│   ├── orchestrator.py                # main hunt driver
│   ├── approve.py                     # T3 manual approval
│   ├── gen_scope_jwt.py               # issue RS256 scope JWT
│   ├── health_check.sh
│   ├── cost_audit.py
│   └── run_*_field_validation.py      # oracle test suites (8 files)
├── tests/
│   ├── *.py                           # unit tests (no live services)
│   └── integration/                   # live Postgres/Redis/R2 tests
├── .claude/
│   ├── agents/                        # 9 sub-agent markdown specs
│   ├── hooks/                         # pretool_killswitch.py, pretool_antislop.py, pretool_approval_gate.py
│   ├── settings.json
│   ├── COMMON_MISTAKES.md
│   ├── QUICK_START.md
│   ├── ARCHITECTURE_MAP.md (this file)
│   ├── completions/                   # NEVER auto-load
│   └── sessions/                      # NEVER auto-load
└── docs/
    ├── INDEX.md                       # master navigation
    ├── system-architecture.md         # Mermaid diagrams
    ├── codebase-summary.md            # file map + schema
    ├── code-standards.md              # how to add new code
    ├── learnings/                     # topic-specific, load on demand
    └── archive/                       # NEVER auto-load
```

## Finding Status State Machine

`hypothesis` -> `validated` -> `reported` -> `accepted` | `duplicate` | `rejected`

Kill-switch hook checks Redis flag before every tool call and blocks if set.

## Key Postgres Tables (13 total)

`programs`, `recon_assets`, `findings`, `findings_raw_finding` (JSONB), `evidence`, `dedup_fingerprints`, `approval_queue`, `hunt_sessions`, `scope_jwts`, `cost_ledger`, `kev_cache`, `ev_scores`, `politeness_tokens`

## Agent -> MCP Dependencies

| Agent | Key MCPs |
|-------|---------|
| recon-agent | scope-mcp, state-mcp, politeness-mcp |
| scanner-agent | oracle-mcp, sandbox-mcp, state-mcp |
| exploit-agent | sandbox-mcp, oracle-mcp, evidence-mcp |
| validator-agent | oracle-mcp, dedup-mcp, evidence-mcp, normalize-mcp |
| reporter-agent | h1-mcp / bugcrowd-mcp / etc., evidence-mcp |
| scope-guard | scope-mcp |
| program-selector | ev-mcp, kev-mcp |
