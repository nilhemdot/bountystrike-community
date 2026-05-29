# Deployment Guide — BountyStrike v5

How to bring up a working BountyStrike v5 stack in solo mode and what the SaaS deployment changes from that baseline. Pair this with [`research/05-deployment.md`](../research/05-deployment.md) for the full walk-through and rationale; this file is the operational quick reference.

**Scope:** solo mode (single host, docker-compose) is the supported deployment today. SaaS multi-tenant (Phase 4) is summarized but not yet operationally complete.

## Prerequisites

| Requirement | Min version | Why |
|---|---|---|
| Python | 3.12 | `pyproject.toml` `requires-python = ">=3.12"` |
| `uv` | 0.4+ | workspace sync; `uv lock` is the lockfile |
| Docker + Compose | 24+ | brings up Postgres / Redis / Hatchet / Langfuse / Caddy |
| `openssl` | any modern | RS256 4096-bit scope-JWT keypair |
| Disk (solo) | 10 GB+ | Postgres + Redis AOF + evidence blobs |

Optional but commonly needed:

- **Cloudflare R2 account** if `EVIDENCE_BACKEND=r2` (otherwise local FS).
- **Anthropic API key** + **Ollama Cloud API key** for Claude + non-Anthropic routing.
- **Per-platform credentials** (HackerOne, Bugcrowd, Intigriti, YesWeHack) for `submit_report` MCPs.

## Solo Mode — Single Host

The reference runtime. One docker-compose stack, BYOK, designed for `<$30/month` ops cost.

### 1. Sync workspace

```bash
git clone <repo> bountystrike-v5 && cd bountystrike-v5
uv sync --all-packages    # installs control-plane + 5 registered MCPs
```

`uv sync` from root (without `--all-packages`) only installs the workspace control-plane. The 9 unregistered MCPs (h1, bugcrowd, intigriti, yeswehack, immunefi, state, sandbox, normalize, politeness) need explicit `uv sync` per directory until they are registered. See [`code-standards.md`](../code-standards.md) §MCP Server Template.

### 2. Generate scope-JWT keypair

```bash
python scripts/gen_scope_jwt.py keygen --out keys/
# produces keys/scope_jwt_private.pem (gitignored)
#          keys/scope_jwt_public.pem
```

Keys are 4096-bit RSA. The private key is gitignored; rotate by regenerating and revoking issued JTIs via the audit log.

### 3. Configure `.env`

```bash
cp .env.example .env
# Edit .env — fill at minimum:
#   POSTGRES_PASSWORD, REDIS_PASSWORD, HATCHET_COOKIE_SECRET,
#   LANGFUSE_SECRET, LANGFUSE_SALT, ANTHROPIC_API_KEY
```

Full env reference: [`configuration-guide.md`](configuration-guide.md).

### 4. Bring up the stack

```bash
docker compose -f infra/docker/docker-compose.yml --env-file .env up -d
```

Services come up in dependency order: postgres → (hatchet, langfuse) → caddy. Redis is independent. Schema migrations in `infra/sql/*.sql` auto-apply via `docker-entrypoint-initdb.d` on **first boot only** — `docker volume rm bountystrike_postgres_data` to re-run them.

Verify:

```bash
docker compose -f infra/docker/docker-compose.yml ps
# All services should be healthy.

# DB sanity
psql "postgresql://bs:${POSTGRES_PASSWORD}@localhost:5432/bountystrike" \
  -c "\dt" -c "\dx"     # 13 tables, pgvector + pg_trgm + pgcrypto
```

### 5. Issue a scope JWT

```bash
python scripts/gen_scope_jwt.py issue \
  --operator-id me \
  --program-handle acme-corp \
  --platform hackerone \
  --targets 'wildcard=*.acme.com' \
  --out scope.jwt
```

The JWT carries: `wildcards`, `exact_hosts`, `ips`, `exclusions.hostnames`, `exclusions.paths`, `rate_limits.default_rps`, per-host overrides, `jti`, `exp` (max 168h), `iss`, `sub`. See [`mcp/scope-mcp/`](../mcp/scope-mcp/) for validation logic.

### 6. Run a scan

```bash
SCOPE_JWT=$(cat scope.jwt) \
PROGRAM_HANDLE=acme-corp \
PLATFORM=hackerone \
DATABASE_URL=postgresql://bs:$POSTGRES_PASSWORD@localhost:5432/bountystrike \
python scripts/orchestrator.py
```

Phases: recon → scanner (skippable) → exploit → T2 approval → validator → T3 approval → reporter. Tunables (env): `MAX_VALIDATORS` (5), `MAX_EXPLOITS` (3), `MAX_REPORTERS` (3), `APPROVAL_TIMEOUT`, `RECON_TIMEOUT`, `SCAN_TIMEOUT`, `TIME_BUDGET_MIN`, `SKIP_SCANNER`, `SKIP_EXPLOIT`, `SKIP_REPORT`. Full list in [`configuration-guide.md`](configuration-guide.md).

### 7. Operator approval CLI

T2 / T3 approvals require operator action via [`scripts/approve.py`](../scripts/approve.py):

```bash
python scripts/approve.py list                   # all pending
python scripts/approve.py show <request_id>      # detail
python scripts/approve.py approve <request_id> --reason "..."
python scripts/approve.py reject  <request_id> --reason "..."
```

T3 requires **two distinct approvers**: first call returns `None` (still pending), second call by a different operator returns the APPROVAL_TOKEN.

## Service Topology (Solo Mode)

| Service | Image | Bound port | Persistence | Health gate |
|---|---|---|---|---|
| `postgres` | `pgvector/pgvector:pg17` | `127.0.0.1:5432` | `postgres_data` volume | `pg_isready` |
| `redis` | `redis:7-alpine` | `127.0.0.1:6379` | `redis_data` volume (AOF) | `redis-cli ping` |
| `hatchet` | `ghcr.io/hatchet-dev/hatchet-engine:latest` | `127.0.0.1:7070` (gRPC), `8080` (HTTP) | `hatchet_data` volume | depends on postgres |
| `langfuse` | `langfuse/langfuse:latest` | `127.0.0.1:3000` | (Postgres-backed) | depends on postgres |
| `caddy` | `caddy:2-alpine` | `80`, `443` | `caddy_data`, `caddy_config` | depends on hatchet+langfuse |

All ports bind to `127.0.0.1` by default — the stack is local-only until you flip TLS on in [`infra/docker/Caddyfile`](../infra/docker/Caddyfile).

## Scope-JWT Trust Boundary

The JWT is the legal artifact. Every MCP that touches a target validates it. Phase 2+ adds an iptables egress allowlist inside a Firecracker microVM derived from JWT claims — the prompt cannot override the netfilter table. Diagram: [`system-architecture.md`](../system-architecture.md) §Scope-JWT Trust Boundary.

## Recon container image

Phase 1.1f-deploy closed the recon container build (commit `fd19d69`). The image is built via CI on push (`caad67c` — GHCR via OIDC) and pulled by the recon-agent at run time.

```bash
# CI builds and pushes:
ghcr.io/<org>/bountystrike-v5/recon:<sha>

# Subprocess wrapper invokes it from control-plane/src/control_plane/domains/recon/__main__.py
```

`Dockerfile.recon` was split into a dep-sync layer + source layer (commit `8d2601c`) to keep rebuild cost low; CGO is per-binary split (`92d2ada`).

## Kill Switch

Three layers, independent. See [`system-architecture.md`](../system-architecture.md) §Kill-Switch Layers.

```bash
# Layer 1 — Redis flag (instant, ~10 ms)
redis-cli -a $REDIS_PASSWORD SET bountystrike:killswitch:global 1 EX 86400

# Layer 2 — wired PreToolUse hook checks Redis on every tool call.
# Layer 3 — process supervisor: docker stop, systemctl stop, pkill.
```

Layer 1 fail-open if Redis unreachable — Layer 3 is the backstop.

## Evidence Backend

Two backends, `EVIDENCE_BACKEND=local|r2`:

```bash
# Local FS (default — dev / solo)
EVIDENCE_BACKEND=local
EVIDENCE_ROOT=./evidence

# Cloudflare R2 (recommended for prod solo)
EVIDENCE_BACKEND=r2
R2_BUCKET=...
R2_ACCOUNT_ID=...
R2_ACCESS_KEY_ID=...
R2_SECRET_ACCESS_KEY=...
R2_REGION=auto
# Optional override:
R2_ENDPOINT_URL=...
```

## Logs and Observability

- **Langfuse** at `http://localhost:3000` — every Claude trace lands here with token + cost. `agent_sessions.langfuse_trace_id` is the join key.
- **structlog** on every Python service, JSON-formatted to stderr.
- **`audit_log`** Postgres table — hash-chained tamper-evident log of every state-changing action.

## Rollback / Teardown

```bash
# Stop without losing data
docker compose -f infra/docker/docker-compose.yml down

# Stop and DESTROY volumes (postgres, redis, hatchet, caddy state)
docker compose -f infra/docker/docker-compose.yml down -v
```

`down -v` is irreversible. Postgres data, evidence blobs (if `EVIDENCE_BACKEND=local`), and Redis kill-switch state are gone.

## SaaS Mode (Phase 4 — not yet operational)

Summarized for forward planning. Differences from solo mode:

| Concern | Solo | SaaS |
|---|---|---|
| Sandbox | local subprocess + Docker scaffold | Firecracker microVM per scan, scope-bound netns |
| Workflow | Hatchet self-hosted | Temporal Cloud |
| LLM routing | direct Anthropic + OpenRouter | LiteLLM proxy with per-tenant cost ceilings |
| TLS | optional (Caddy) | mandatory (Caddy + cert-manager) |
| Scope | single operator | per-tenant signed JWT with operator-id binding |
| DB | docker-compose Postgres | managed Postgres |
| Evidence | local FS or R2 | R2 (mandatory) |

Full SaaS plan: [`research/05-deployment.md`](../research/05-deployment.md) §SaaS Mode.

## See Also

- [`configuration-guide.md`](configuration-guide.md) — every env var, with default and purpose
- [`testing-guide.md`](testing-guide.md) — pytest config, fixtures, field-validation harnesses
- [`research/05-deployment.md`](../research/05-deployment.md) — full deployment rationale
- [`system-architecture.md`](../system-architecture.md) — visual flows
