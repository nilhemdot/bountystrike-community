# Configuration Guide — BountyStrike v5

Every environment variable used by the stack, where it's read, what it controls, and the safe default. Copy [`.env.example`](../.env.example) to `.env` and fill the required ones; this doc explains why each exists.

**Conventions.**
- Variables marked **REQUIRED** must be set or the docker-compose stack / orchestrator refuses to start (the `${VAR:?...}` syntax in `docker-compose.yml` and `_get_required` in `orchestrator.py`).
- Variables marked **optional** have a working default.
- Secrets (any *_PASSWORD, *_KEY, *_TOKEN, *_COOKIE, *_PAT, *_BEARER) must NEVER land in git. `.env` is gitignored; `.env.example` is the template.

## Core Infrastructure

| Variable | Required? | Default | Purpose |
|---|---|---|---|
| `POSTGRES_PASSWORD` | **REQUIRED** | — | Postgres superuser password. Consumed by docker-compose `postgres` service and every Postgres-touching MCP via `DATABASE_URL`. |
| `REDIS_PASSWORD` | **REQUIRED** | — | Redis AUTH password. Consumed by `redis` service + kill-switch + approval cache. |
| `HATCHET_COOKIE_SECRET` | **REQUIRED** | — | Hatchet auth-cookie signing secret. Generate with `openssl rand -hex 32`. |
| `LANGFUSE_SECRET` | **REQUIRED** | — | Langfuse `NEXTAUTH_SECRET`. Generate with `openssl rand -hex 32`. |
| `LANGFUSE_SALT` | **REQUIRED** | — | Langfuse password salt. Generate with `openssl rand -hex 16`. |

Generate all five at once:

```bash
for v in POSTGRES_PASSWORD REDIS_PASSWORD HATCHET_COOKIE_SECRET LANGFUSE_SECRET LANGFUSE_SALT; do
  printf '%s=%s\n' "$v" "$(openssl rand -hex 32)"
done >> .env
```

## Redis Connection

| Variable | Default | Purpose |
|---|---|---|
| `REDIS_HOST` | `127.0.0.1` | Where the kill-switch + approval cache reads/writes |
| `REDIS_PORT` | `6379` | — |
| `REDIS_DB` | `0` | Logical DB number |

## Kill Switch

| Variable | Default | Purpose |
|---|---|---|
| `KILL_SWITCH_BACKEND` | `redis` | `redis` (prod) or `memory` (tests). Memory backend has no cross-process visibility — never set it in prod. |
| `KILL_SWITCH_KEY` | `bountystrike:killswitch:global` | Redis key for the global kill flag. |

To trip the switch:

```bash
redis-cli -a $REDIS_PASSWORD SET bountystrike:killswitch:global 1 EX 86400
```

PreToolUse hook `pretool_killswitch.py` reads this on every tool call. Fail-open if Redis is unreachable; Layer 3 (process supervisor) is the backstop.

## LLM Providers

| Variable | Required? | Purpose |
|---|---|---|
| `ANTHROPIC_API_KEY` | **REQUIRED** for Claude tasks | All Sonnet/Opus/Haiku calls |
| `OPENROUTER_API_KEY` | optional | Venice / DeepSeek / WhiteRabbitNeo / Pentest-R1 routing. Consumed by `pretool_venice_route.py` for non-Anthropic routing today. |
| `OLLAMA_CLOUD_API_KEY` | optional (forward-compat) | Plumbed via orchestrator passthrough in anticipation of an Ollama Cloud rewire of `pretool_venice_route.py`. Not consumed by the current routing hook. |

The model-routing matrix (16 task types × 4 cost tiers) is in [`research/02-routing-ev.md`](research/02-routing-ev.md). Bulk triage on DeepSeek (`$0.14/M`); deep reasoning on Opus (`$5/M`); security-specialist tasks on Tier-S (Pentest-R1, WhiteRabbitNeo).

## Bug Bounty Platform Auth

Each platform submitter MCP needs its own credential. All optional individually — set only the platforms you intend to submit to.

| Variable | Used by | Purpose |
|---|---|---|
| `H1_API_TOKEN` | `mcp/h1-mcp` | HackerOne JSON:API token |
| `H1_USERNAME` | `mcp/h1-mcp` | HackerOne username (paired with token in HTTP Basic) |
| `BUGCROWD_SESSION_COOKIE` | `mcp/bugcrowd-mcp` | Bugcrowd auth cookie |
| `INTIGRITI_PAT` | `mcp/intigriti-mcp` | Personal access token (researcher API is **read-only**; submission is a placeholder until a relay endpoint exists) |
| `YESWEHACK_BEARER` | `mcp/yeswehack-mcp` | Bearer token |
| (Immunefi cred — TBD) | `mcp/immunefi-mcp` | (set per-program submission flow) |

429 retry semantics (`Retry-After` honored, no retry on other 4xx) are wired across all 5 (commit `0077e90`, `fd55aff`).

## Scope JWT

| Variable | Default | Purpose |
|---|---|---|
| `SCOPE_JWT_PRIVATE_KEY_PATH` | `keys/scope_jwt_private.pem` | RS256 signing key (4096-bit). gitignored. |
| `SCOPE_JWT_PUBLIC_KEY_PATH` | `keys/scope_jwt_public.pem` | Verification key (committed to repo if you wish, but `keys/` is gitignored by default). |

Generate via:

```bash
python scripts/gen_scope_jwt.py keygen --out keys/
```

## Evidence Backend

| Variable | Default | Purpose |
|---|---|---|
| `EVIDENCE_BACKEND` | `local` | `local` (filesystem) or `r2` (Cloudflare R2). |
| `EVIDENCE_ROOT` | `./evidence` | Used when `EVIDENCE_BACKEND=local`. |
| `R2_BUCKET` | — | R2 bucket name (when `EVIDENCE_BACKEND=r2`). |
| `R2_ACCOUNT_ID` | — | Cloudflare account ID. |
| `R2_ACCESS_KEY_ID` | — | R2 access key. |
| `R2_SECRET_ACCESS_KEY` | — | R2 secret. |
| `R2_ENDPOINT_URL` | derived | Override the auto-derived `https://${R2_ACCOUNT_ID}.r2.cloudflarestorage.com`. |
| `R2_REGION` | `auto` | R2 ignores this; boto3 requires *something*. |

Selection logic lives in [`control-plane/src/control_plane/domains/evidence_management/repositories/blob_store.py`](../control-plane/src/control_plane/domains/evidence_management/repositories/blob_store.py). The `r2-smoke` CI workflow (commit `b8c9e1e`) exercises the live round-trip.

## OAST Callback Infrastructure

| Variable | Required? | Purpose |
|---|---|---|
| `INTERACTSH_SERVER_URL` | optional | If hosting your own Interactsh; otherwise leave blank to use the public server (rate-limited). |
| `INTERACTSH_AUTH` | optional | Auth header for self-hosted Interactsh. |
| `BURP_COLLABORATOR_URL` | optional | Burp Collaborator (Pro / Enterprise) for SSRF callback verification. |

OAST is consumed by `oracle-mcp` (`verify_ssrf`, `verify_ssrf_imds`, etc.).

## Database (Application)

| Variable | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | derived from `POSTGRES_PASSWORD` | Connection string used by `control_plane.infrastructure.database.get_database_url()` and every Postgres-touching MCP. Format: `postgresql+asyncpg://bs:$POSTGRES_PASSWORD@localhost:5432/bountystrike`. |

## Orchestrator (`scripts/orchestrator.py`)

| Variable | Required? | Default | Purpose |
|---|---|---|---|
| `PROGRAM_HANDLE` | **REQUIRED** | — | The program slug to scan (matches `programs.handle`). |
| `PLATFORM` | **REQUIRED** | — | `hackerone`, `bugcrowd`, `intigriti`, `yeswehack`, `immunefi`. |
| `SCOPE_JWT` | **REQUIRED** | — | The signed scope JWT (typically `$(cat scope.jwt)`). |
| `DATABASE_URL` | **REQUIRED** | — | App Postgres URL. |
| `MAX_VALIDATORS` | optional | `5` | Parallel validator-agent subprocesses. |
| `MAX_EXPLOITS` | optional | `3` | Parallel exploit-agent subprocesses. |
| `MAX_REPORTERS` | optional | `3` | Parallel reporter-agent subprocesses. |
| `APPROVAL_TIMEOUT` | optional | (minutes) | T2 / T3 wait-for-approval cap. |
| `RECON_TIMEOUT` | optional | (minutes) | Recon-phase cap. |
| `SCAN_TIMEOUT` | optional | (minutes) | Scanner-phase cap. |
| `TIME_BUDGET_MIN` | optional | — | Total scan wall-clock budget. |
| `SKIP_SCANNER` | optional | unset | Set to `1` to skip the scanner phase. |
| `SKIP_EXPLOIT` | optional | unset | Set to `1` to skip the exploit phase. |
| `SKIP_REPORT` | optional | unset | Set to `1` to skip the reporter phase (validate-only run). |

## Phase 3 Calibration / Cost Audit (in-flight)

| Variable | Used by | Purpose |
|---|---|---|
| (See `scripts/cost_audit.py`, `scripts/metrics.py`, `scripts/onboard_hunter.py`, `scripts/reconcile_hunt_outcomes.py`) | new Phase 3 scaffolding | EV calibration loop, hunter onboarding, hunt-outcome reconcile. Specific env vars depend on script — read each script's `_get_required` block. |

## Sub-Agent / Skill Knobs

These are read by `.claude/agents/*.md` specs and the harness:

| Variable | Purpose |
|---|---|
| `MAX_THINKING_TOKENS` | Cap extended-thinking budget. Default 31999; set lower for cost. |
| `KILL_SWITCH_BACKEND=memory` | Use in-process backend in tests so a Redis instance isn't required. |

## Lookups by File

When you need to know "where does this env var get read?":

```bash
grep -rn 'os\.environ' control-plane/src scripts/ mcp/ \
  --include='*.py' | grep -v '\.venv\|__pycache__'
```

For docker-compose variables: search [`infra/docker/docker-compose.yml`](../infra/docker/docker-compose.yml) for `${VAR}` references.

## Validation

The orchestrator + every docker-compose service uses fail-loud patterns. Missing required env aborts startup with a clear error:

```
[orchestrator] ERROR: PROGRAM_HANDLE is not set
```

```
error while interpolating services.postgres.environment.POSTGRES_PASSWORD:
required variable POSTGRES_PASSWORD is missing a value: POSTGRES_PASSWORD must be set in .env
```

Do not silence these errors with empty defaults — fix the missing env.

## See Also

- [`.env.example`](../.env.example) — the template
- [`deployment-guide.md`](deployment-guide.md) — solo-mode bring-up
- [`research/02-routing-ev.md`](research/02-routing-ev.md) §Cost Guardrails — model routing cost tiers
