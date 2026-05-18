# Codebase Summary — BountyStrike v5

A file-tree map of the repo, plus the data and tools every contributor needs in one place: dependency inventory, Postgres schema, MCP tool catalogue, and the test surface. Pair this with [`system-architecture.md`](system-architecture.md) for the visual flows and [`code-standards.md`](code-standards.md) for how to add new code.

**Generated:** 2026-05-01 against git HEAD `e9b4b77`. Phase 2 W7-8 sprint closed: 5 new oracle field-validation suites at TPR=1.0/FPR=0.0; T3 approval plumbing wired in orchestrator.

## Top-Level Layout

```
bountystrike-ai5/
├── pyproject.toml          # uv workspace root, ruff config, pytest config
├── uv.lock                 # 478 KB pinned versions
├── .env.example            # 21 env keys
├── .gitignore              # excludes keys/, .env, .swarm/, .claude/projects/
├── README.md               # project quickstart
├── CLAUDE.md               # global behavioral rules
├── control-plane/          # FastAPI orchestrator + DDD domains
├── mcp/                    # 15 MCP servers (14 Python + 1 TypeScript)
├── infra/                  # SQL migrations + docker-compose
├── keys/                   # gitignored RSA scope-JWT keypair
├── scripts/                # CLI entry points
├── docs/                   # this directory + research/ + architecture/
└── .claude/                # settings, hooks, agent specs
```

Total Python source: ~6,700 LOC across ~150 files (excluding tests, .venv, .claude/).

## Workspace Members (`pyproject.toml`)

```toml
[tool.uv.workspace]
members = [
    "control-plane",
    "mcp/oracle-mcp",
    "mcp/evidence-mcp",
    "mcp/dedup-mcp",
    "mcp/kev-mcp",
    "mcp/ev-mcp",
]
```

**Drift to flag:** the filesystem has 14 Python MCP dirs, but only 5 are registered as workspace members. The other 9 (`h1-mcp`, `bugcrowd-mcp`, `intigriti-mcp`, `yeswehack-mcp`, `immunefi-mcp`, `state-mcp`, `sandbox-mcp`, `normalize-mcp`, `politeness-mcp`) are standalone — `uv sync` from root won't install them. Phase 2 cleanup task: register all Python MCPs as workspace members.

`scope-mcp` is a TypeScript / Node project and lives outside the uv workspace entirely.

## Tooling

- **Build:** `uv` with hatchling backend (`[build-system]` per package).
- **Lint:** `ruff` 0.7+, line-length 100, target Python 3.12, rules `E F W I N UP B SIM ASYNC` (see root `pyproject.toml` `[tool.ruff.lint]`).
- **Type-check:** `mypy>=1.13` (control-plane dev dep).
- **Test:** `pytest>=8` + `pytest-asyncio>=0.24` with `asyncio_mode = "auto"`.

## control-plane

`control-plane/` — FastAPI + DDD bounded contexts. Domain-driven layout under `src/control_plane/`.

```
control-plane/src/control_plane/
├── core/
│   ├── security/
│   │   ├── validation.py      # JTI, ProgramHandle, OperatorId patterns; destructive payload denylist
│   │   └── path.py            # path-traversal guard + reports/ prefix enforcement
│   └── shared/                # AggregateRoot, DomainEvent, ValueObject base classes
├── domains/
│   ├── approval_gate/
│   │   ├── services.py        # ApprovalGateService — T1/T2/T3 tier transitions + classify_tier
│   │   ├── aggregates.py      # ApprovalRequest aggregate (pending → approved/rejected/expired)
│   │   ├── value_objects.py   # T0/T1/T2/T3 tier value objects + SLA constants
│   │   ├── queue.py           # enqueue / approve / reject / wait_for_approval (exp backoff 5s→60s, T3 distinct-actor)
│   │   └── finding_status_cache.py    # in-memory or Redis cache for finding lifecycle
│   ├── evidence_management/
│   │   ├── repositories/blob_store.py # abstract BlobStore (local FS / R2 / S3)
│   │   └── services/hash_chain_service.py     # hash-chained audit log validation
│   ├── program_ranking/
│   │   └── services/scoring_service.py        # EV formula (payout, saturation, ops, fit, cve)
│   ├── recon/
│   │   ├── service.py         # ReconService — subfinder → scope_filter → httpx live → hypothesis
│   │   ├── tool_runner.py     # BinaryRunner wrapper (subfinder, httpx, katana CLIs)
│   │   └── __main__.py        # recon-agent container entrypoint
│   ├── safety/                # kill switch + rate limiting
│   └── scope_management/
│       ├── services/jwt_issuer.py     # RS256 4096-bit, 168h max, JTI revocation
│       ├── services/ingest_service.py # H1 / Arkadiyt scope normalization + upsert
│       └── integrations/hackerone.py  # H1 org-assets API client (April 2026 migration)
└── infrastructure/
    └── database.py            # SQLAlchemy 2.0 async ORM, asyncpg engine factory
```

Tests in `control-plane/tests/` (21 files):

| Test file | Coverage |
|---|---|
| `test_antislop_hook.py` | Path/payload validation |
| `test_approval_gate.py`, `test_approval_gate_hook.py` | Tier transitions + Redis state |
| `test_blob_store_factory.py` | Local-vs-R2 selection |
| `test_core_security.py`, `test_core_shared.py` | Validation patterns + DDD base classes |
| `test_evidence_chain.py` | Hash-chained audit log |
| `test_ev_fixture_50.py`, `test_ev_freshness.py`, `test_ev_scoring.py`, `test_ev_writer.py` | EV scoring + freshness decay |
| `test_h1_client.py` | HackerOne API client |
| `test_kill_switch.py` | 3-layer kill switch |
| `test_normalize.py` | CVSS + CWE normalization |
| `test_recon.py`, `test_recon_main.py` | ReconService + tool_runner + container entry |
| `test_scope_ingest.py`, `test_scope_jwt.py` | Scope ingestion + RS256 JWT |
| `test_venice_route_hook.py` | OpenRouter Venice routing |

## MCP Inventory (15 servers)

All Python MCPs use FastMCP stdio transport. Baseline deps: `mcp>=1.0`, `structlog>=24`. Each has `[project.scripts]` entrypoint named after the package.

| MCP | Type | Backend | Tools (selected) | Recent commit |
|---|---|---|---|---|
| **oracle-mcp** | Py | none (stateless) + Playwright + Interactsh | `verify_xss`, `verify_ssrf`, `verify_sqli`, `verify_ssti`, `verify_open_redirect`, `verify_ssrf_imds`, `verify_idor`, `verify_rce` — 7 field-validated TPR=1.0/FPR=0.0 (XSS, SSRF, SSRF→IMDS, IDOR, RCE, SSTI, Open Redirect); SQLi suite pending W9-10 | Phase 2 W7-8 SSRF→IMDS (`e9b4b77`), IDOR (`65fe921`), RCE (`5493eea`), SSTI (`6ef4858`), Open Redirect (`1b6eb64`); Phase 1.1d SSRF (`3d5d52b`), 1.1c XSS (`4e84007`) |
| **evidence-mcp** | Py | **aiosqlite** + R2/local blob | `put_artifact`, `get_artifact`, `append_audit_entry`, `get_audit_chain` | Phase 1 hash-chain advisory lock |
| **dedup-mcp** | Py | asyncpg + pgvector + OpenAI embeddings | `check_duplicate`, `register_finding`, `check_semantic_duplicate`, `register_embedding` | Recall fixture (`3d9e915`) |
| **state-mcp** | Py | asyncpg | `get_finding`, `query_artifacts`, `query_experience_kb`, `update_finding_status` | DSN parse + lock fix (`38dc943`) |
| **ev-mcp** | Py | asyncpg + workspace dep on control-plane | `rank_programs`, `get_program_details` | Freshness tracking |
| **kev-mcp** | Py | httpx + file cache | `kev_get_recent`, `kev_match_program`, `kev_lookup`, `kev_status` | `kev_match_program` (`b7ec4e3`, today) |
| **scope-mcp** | TS | JWT lib | RS256 decode + claims extraction | (Node ecosystem, separate test/) |
| **h1-mcp** | Py | httpx | `submit_report` (HackerOne JSON:API) | API verified (`2e56883`) |
| **bugcrowd-mcp** | Py | httpx | `submit_report` (Bugcrowd JSON:API) | API align (`938d9f3`) |
| **intigriti-mcp** | Py | httpx | `submit_report` (PLACEHOLDER — researcher API is read-only) | API align (`938d9f3`) |
| **yeswehack-mcp** | Py | httpx | `submit_report` (4xx-no-retry) | Retry logic (`fd55aff`) |
| **immunefi-mcp** | Py | httpx | `submit_report` | 3-platform batch (`accafc7`) |
| **politeness-mcp** | Py | (stdlib only) | `check_rate_limit` (per-host token bucket + adaptive backoff) | TOCTOU fix (`c38ff2e`) |
| **sandbox-mcp** | Py | (stdlib only) | `exec_safe` (LocalSubprocessDriver + DockerDriver scaffold) | Scaffold (`b61546d`) — Firecracker deferred |
| **normalize-mcp** | Py | `cvss>=3.0` | CVSS v3.1/v4 + CWE normalization | CWE accuracy (`34bb03c`) |

**429 retry semantics** wired across all 5 platform submitters in `0077e90`.

**Intigriti note:** the researcher API is read-only per [`research/00c-context7-verifications.md`](research/00c-context7-verifications.md). `submit_report` is a placeholder until a relay endpoint or web-UI automation is built.

## infra/sql

Migrations apply alphabetically via Postgres `docker-entrypoint-initdb.d` (mounted in [`infra/docker/docker-compose.yml`](../infra/docker/docker-compose.yml)).

| File | Purpose |
|---|---|
| `00_extensions.sql` | `pgvector`, `pg_trgm`, `pgcrypto` |
| `01_schema.sql` | 11 core tables + `finding_status` ENUM (16 states) + indexes |
| `02_dedup_fingerprints.sql` | `dedup_fingerprints` table + `scan_jobs` columns (`hosts_found`, `endpoints_found`, `completed_at`) |
| `03_audit_log_realign.sql` | `audit_log` column realignment for hash-chain trigger |
| `04_approval_queue.sql` | `approval_queue` table — FK to `findings`, status enum `pending\|approved\|rejected\|expired`, `approver_id` + `approver_id_2` for T3 distinct-actor enforcement, indexed on (status, tier, requested_at). Idempotent. |
| `05_findings_raw_finding.sql` | `findings.raw_finding JSONB DEFAULT '{}'::jsonb` + expression index on `chain_steps` (raw scanner output + post-exploit chain). Round 5 Bug-2 fix. |

### Tables (13 total)

From [`01_schema.sql`](../infra/sql/01_schema.sql), [`02_dedup_fingerprints.sql`](../infra/sql/02_dedup_fingerprints.sql), and [`04_approval_queue.sql`](../infra/sql/04_approval_queue.sql). Migration `05_findings_raw_finding.sql` adds the `raw_finding` JSONB column on `findings` (no new table).

| # | Table | Key columns | Notes |
|---|---|---|---|
| 1 | `programs` | `handle` PK, `platform`, `payout_min/max`, `dup_rate` | federated registry |
| 2 | `scopes` | `id`, `program_handle` FK, `asset_type`, `identifier` (trgm GIN) | normalized assets |
| 3 | `scope_changes` | `event_type`, `old_value/new_value` JSONB, `detected_at` | change-event log |
| 4 | `ev_score_history` | `ev_score`, `f_payout`, `f_saturation`, `f_ops`, `f_fit`, `f_cve` | EV time-series |
| 5 | `scan_jobs` | `id` UUID, `status`, `scope_jwt_jti`, `ev_score`, `completed_at` | orchestrator invocations |
| 6 | `findings` | `id` UUID, `status` (16-ENUM), `embedding` vector(1536) HNSW | candidates → validated |
| 7 | `evidence_artifacts` | `content_hash`, `prev_audit_hash`, `r2_key`, `scope_token_jti` | hash-chained PoC |
| 8 | `audit_log` | `row_hash`, `prev_hash`, `payload` JSONB | tamper-evident |
| 9 | `agent_sessions` | `tokens_in/out`, `cost_usd`, `langfuse_trace_id` | Claude trace anchor |
| 10 | `model_costs` | `model`, `tokens_in/out`, `cost_usd` | per-call cost ledger |
| 11 | `report_submissions` | `finding_id`, `platform`, `submission_id`, `payout_usd` | T3 outbound |
| 12 | `dedup_fingerprints` | `fingerprint_hex` PK, `platform`, `program_handle`, `vuln_type` | cross-session dedup |
| 13 | `approval_queue` | `id` UUID, `finding_id` FK, `tier`, `status` (pending/approved/rejected/expired), `approver_id`, `approver_id_2`, `requested_at` | T1/T2/T3 operator approval workflow |

**`finding_status` ENUM (16 states):**
`hypothesis` → `exploit_attempt` → `exploit_candidate` → `validation_pending` → `validated` → `dedup_check` → `approval_pending_t1/t2/t3` → `approved` → `submitted` → `confirmed` / `rejected` / `duplicate` / `wont_fix` / `archived`.

**Notable indexes:** trgm GIN on `scopes.identifier` (wildcard match), HNSW on `findings.embedding` (`vector_cosine_ops`, `m=16`, `ef_construction=64`).

**Dedup fingerprint:** `sha256(platform || \x00 || program || \x00 || vuln_type || \x00 || host || \x00 || path)`.

## infra/docker

```
infra/docker/
├── docker-compose.yml    # 5 services
├── Caddyfile             # reverse proxy (TLS off in solo mode)
└── Dockerfile.recon      # recon container image — Phase 1.1f GAP, not yet built/pushed
```

`docker-compose.yml` services (network: `bountystrike` bridge):

| Service | Image | Purpose | Health gate |
|---|---|---|---|
| `postgres` | `pgvector/pgvector:pg17` | primary DB; auto-applies `infra/sql/*.sql` | `pg_isready` |
| `redis` | `redis:7-alpine` | kill switch + approval cache (AOF + password) | `redis-cli ping` |
| `hatchet` | `ghcr.io/hatchet-dev/hatchet-engine:latest` | workflow engine | depends on postgres |
| `langfuse` | `langfuse/langfuse:latest` | LLM observability | depends on postgres |
| `caddy` | `caddy:2-alpine` | reverse proxy | depends on hatchet + langfuse |

All passwords sourced from `.env` via `${VAR:?...}` syntax — fail loud on missing secrets.

## scripts/

| Script | Purpose |
|---|---|
| `orchestrator.py` | scan-job orchestrator. Pipeline: `recon → scanner (skippable) → exploit → [T2 enqueue+poll+relaunch] → validator → [T3 enqueue+poll+relaunch] → reporter`. Each phase skippable via env (`SKIP_SCANNER`, `SKIP_EXPLOIT`, `SKIP_REPORT`). Required env: `PROGRAM_HANDLE`, `PLATFORM`, `SCOPE_JWT`, `DATABASE_URL`. Tunables: `MAX_VALIDATORS` (default 5), `MAX_EXPLOITS` (default 3), `MAX_REPORTERS` (default 3), `APPROVAL_TIMEOUT`, `RECON_TIMEOUT`, `SCAN_TIMEOUT`, `TIME_BUDGET_MIN`. |
| `gen_scope_jwt.py` | RS256 keygen + scope-JWT issuance CLI |
| `approve.py` | Operator approval-queue CLI — `list / show / approve / reject` subcommands; talks to `approval_queue` table via asyncpg |
| `run_xss_field_validation.py` | Phase 1.1c fixture harness — 40 cases, TPR=1.0, FPR=0.0 |
| `run_ssrf_field_validation.py` | Phase 1.1d fixture harness — 5-endpoint lab, TPR=1.0, FPR=0.0 |
| `run_ssrf_imds_field_validation.py` | Phase 2 W7-8 — IMDS (169.254.169.254) callback verification, TPR=1.0, FPR=0.0 (`e9b4b77`) |
| `run_idor_field_validation.py` | Phase 2 W7-8 — cross-tenant object-id probe, TPR=1.0, FPR=0.0 (`65fe921`) |
| `run_rce_field_validation.py` | Phase 2 W7-8 — sandboxed payload exec verification, TPR=1.0, FPR=0.0 (`5493eea`) |
| `run_ssti_field_validation.py` | Phase 2 W7-8 — template-engine fingerprint + execution verification, TPR=1.0, FPR=0.0 (`6ef4858`) |
| `run_open_redirect_field_validation.py` | Phase 2 W7-8 — Location-header redirect verification, TPR=1.0, FPR=0.0 (`1b6eb64`) |

## .claude

```
.claude/
├── settings.json                # 4 wired PreToolUse hooks
├── hooks/
│   ├── pretool_killswitch.py    # matcher: * (all) — Layer 2 kill switch
│   ├── pretool_antislop.py      # matcher: ^(Write|Edit|MultiEdit)$
│   ├── pretool_venice_route.py  # matcher: ^mcp__openrouter__openrouter_complete$
│   ├── pretool_approval_gate.py # matcher: ^mcp__[a-z0-9_-]+__submit_
│   ├── pre-task-scope-check.sh
│   └── post-task-scan-complete.sh
└── agents/                       # 9 sub-agent specs (.md)
    ├── recon.md
    ├── cloud-recon-agent.md
    ├── scanner-agent.md
    ├── ai-vuln-hunter.md
    ├── exploit-agent.md
    ├── validator.md
    ├── reporter.md
    ├── scope-guard.md
    └── program-selector.md
```

**Hook wire-schema** corrected in commit `c75c3a9` to emit valid Claude Code wire format.

## Key Dependencies

From `control-plane/pyproject.toml` + `uv.lock`:

| Package | Version (lock) | Type | Purpose |
|---|---|---|---|
| `anthropic` | 0.97.0 | runtime | Claude API client |
| `fastapi` | 0.136.1 | runtime | Internal control-plane HTTP |
| `pydantic` | 2.x | runtime | Validation + JSON schema |
| `pyjwt[crypto]` | 2.x | runtime | RS256 scope JWT signing/verifying |
| `asyncpg` | 0.31.0 | runtime | Async Postgres |
| `sqlalchemy[asyncio]` | 2.x | runtime | Async ORM |
| `pgvector` | 0.3+ | runtime | pgvector Python bindings |
| `httpx` | 0.28.1 | runtime | Async HTTP |
| `aioboto3` | 15.5.0 | runtime | Async R2 / S3 (evidence backend) |
| `redis` | 5.x | runtime | Kill switch L1 + approval cache |
| `structlog` | 24+ | runtime | Structured logging |
| `cryptography` | 47.0.0 | runtime | RSA + AES |
| `uvicorn[standard]` | 0.32+ | runtime | ASGI server |
| `pytest` | 8.x | dev | Test framework |
| `pytest-asyncio` | 0.24+ | dev | asyncio mode auto |
| `ruff` | 0.7+ | dev | Lint |
| `mypy` | 1.13+ | dev | Type-check |
| `respx` | 0.21+ | dev | httpx mock for HTTP tests |

Per-MCP variations:
- **oracle-mcp** adds `playwright>=1.48`, `scipy>=1.13`, `cryptography>=43`.
- **evidence-mcp** uses `aiosqlite>=0.20` (file SQLite, not Postgres).
- **dedup-mcp**, **state-mcp**, **ev-mcp** use `asyncpg>=0.29`.
- **normalize-mcp** uses `cvss>=3.0`.
- **5 platform submitters** (h1, bugcrowd, intigriti, yeswehack, immunefi) only need `mcp` + `httpx` + `structlog`.

## Environment Variables (`.env.example`)

21 keys grouped:

- **Core infra:** `POSTGRES_PASSWORD`, `REDIS_PASSWORD`, `HATCHET_COOKIE_SECRET`, `LANGFUSE_SECRET`, `LANGFUSE_SALT`
- **Redis connection:** `REDIS_HOST=127.0.0.1`, `REDIS_PORT=6379`, `REDIS_DB=0`
- **Kill switch:** `KILL_SWITCH_BACKEND=redis|memory`, `KILL_SWITCH_KEY=bountystrike:killswitch:global`
- **LLM providers:** `ANTHROPIC_API_KEY`, `OPENROUTER_API_KEY` (consumed by `pretool_venice_route.py` for non-Anthropic routing), `OLLAMA_CLOUD_API_KEY` (plumbed forward; not yet consumed)
- **Platform auth:** `H1_API_TOKEN`, `H1_USERNAME`, `BUGCROWD_SESSION_COOKIE`, `INTIGRITI_PAT`, `YESWEHACK_BEARER`
- **Scope JWT:** `SCOPE_JWT_PRIVATE_KEY_PATH=keys/scope_jwt_private.pem`, `SCOPE_JWT_PUBLIC_KEY_PATH=keys/scope_jwt_public.pem`
- **Evidence backend:** `EVIDENCE_BACKEND=local|r2`, `EVIDENCE_ROOT=./evidence`, `R2_BUCKET`, `R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_ENDPOINT_URL`

## See Also

- [`system-architecture.md`](system-architecture.md) — Mermaid diagrams of the data flow
- [`code-standards.md`](code-standards.md) — DDD layout, ruff config, MCP template
- [`research/05-deployment.md`](research/05-deployment.md) — full deployment walk-through
- [`research/04-skills-mcps.md`](research/04-skills-mcps.md) — agent / hook / MCP design rationale
- [`phase1_signoff.md`](phase1_signoff.md) — Phase 1 audit + Round 4 closeout
