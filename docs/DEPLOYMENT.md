# BountyStrike v5 — Deployment Guide

Complete deployment documentation for BountyStrike v5 Solo Mode — from bare metal / fresh VPS to first scan in under 30 minutes, under $30/month.

**Audience:** Solo bug bounty hunters and independent security researchers — no DevOps background required.

**Architecture Reference:** For diagrams (component graph, data flow, scope-JWT trust boundary, kill-switch layers, finding-status state machine), see [`docs/system-architecture.md`](system-architecture.md).

---

## Table of Contents

1. [Why Solo Mode](#why-solo-mode)
2. [Host Requirements](#host-requirements)
3. [Prerequisites](#prerequisites)
4. [Quick Start — 5 Steps to First Scan](#quick-start--5-steps-to-first-scan)
5. [Configuration Reference](#configuration-reference)
6. [Service Topology](#service-topology)
7. [Scope-JWT Keypair](#scope-jwt-keypair)
8. [Kill Switch Operations](#kill-switch-operations)
9. [Health Checks](#health-checks)
10. [Evidence Backend](#evidence-backend)
11. [Logs & Observability](#logs--observability)
12. [Operator Approval Workflow](#operator-approval-workflow)
13. [Backing Up & Restoring](#backing-up--restoring)
14. [Teardown](#teardown)
15. [Cost Breakdown](#cost-breakdown)
16. [FAQ / Troubleshooting](#faq--troubleshooting)
17. [SaaS Multi-Tenant Preview (Phase 4)](#saas-multi-tenant-preview-phase-4)
18. [See Also](#see-also)

---

## Why Solo Mode

BountyStrike v5 was built for one person with a Docker host — not a security team with a Kubernetes cluster. Every dollar of infra cost comes out of your bounty payouts, so the entire stack is designed to run on a $20-30/month VPS.

**The one-command promise:**

```bash
docker compose -f infra/docker/docker-compose.yml --env-file .env up -d
```

That single command starts the complete platform: Postgres, Redis, workflow engine, observability, reverse proxy, control plane, and all 15 MCP servers. No Terraform, no Helm charts, no managed services.

---

## Host Requirements

### Minimum (Solo Mode)

| Resource | Minimum | Recommended |
|---|---|---|
| CPU | 2 vCPU | 4 vCPU |
| RAM | 4 GB | 8 GB |
| Disk | 20 GB SSD | 50 GB NVMe |
| OS | Ubuntu 24.04 / macOS 14+ | Ubuntu 24.04 |
| Network | Outbound HTTPS | Outbound HTTPS + optional public IP |

### Cost-Minimal VPS Options (2026)

| Provider | Plan | Specs | Price |
|---|---|---|---|
| Hetzner | CX32 | 4 vCPU, 8 GB RAM, 80 GB NVMe | €8.29/mo |
| OVH | VPS Comfort | 4 vCPU, 8 GB RAM, 80 GB SSD | $13.51/mo |
| DigitalOcean | Basic Droplet | 2 vCPU, 4 GB RAM, 80 GB SSD | $24/mo |
| Local/Mac | Mac mini M4 | Apple M4, 16 GB RAM, 526 GB SSD | $0 (existing hardware) |

At 4 vCPU / 8 GB RAM, the complete stack typically idles at ~2.2 GB RAM and 15-20% CPU, leaving ample headroom for concurrent scan workloads.

---

## Prerequisites

### All Platforms

```bash
# Docker (container runtime + compose)
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER  # log out + back in after this

# uv — Python package manager (10-100x faster than pip)
curl -LsSf https://astral.sh/uv/install.sh | sh

# openssl — ships with macOS / Ubuntu; used for key + secret generation
openssl version   # any modern version works
```

### macOS (Homebrew)

```bash
brew install go python@3.12 node@22 docker colima

# Bug bounty reconnaissance tooling (optional but recommended)
brew install subfinder httpx dnsx naabu katana nuclei interactsh
```

### Linux (Ubuntu 24.04)

```bash
sudo apt-get install -y golang nodejs python3.12 docker.io

# Reconstruction toolset (same `go install` block as macOS)
go install github.com/sw33tLie/bbscope@latest
go install -v github.com/projectdiscovery/subfinder/v2/cmd/subfinder@latest
go install -v github.com/projectdiscovery/httpx/cmd/httpx@latest
go install -v github.com/projectdiscovery/dnsx/cmd/dnsx@latest
go install -v github.com/projectdiscovery/naabu/v2/cmd/naabu@latest
go install -v github.com/projectdiscovery/nuclei/v3/cmd/nuclei@latest
go install -v github.com/projectdiscovery/katana/cmd/katana@latest

# Nuclei templates
nuclei -update-templates
```

### Cross-Platform Tools

```bash
# Claude Code CLI
npm install -g @anthropic-ai/claude-code

# Claude Agent SDK
pip install claude-agent-sdk
```

---

## Quick Start — 5 Steps to First Scan

This section is the "under 30 minutes" path. The steps are sequential and annotated with expected time per step on a 100 Mbps connection.

### Step 1: Clone & Build (5 min)

```bash
git clone <repo> bountystrike-v5 && cd bountystrike-v5

# Install Python dependencies via workspace
uv sync --all-packages
```

`uv sync` installs the control-plane and all registered MCPs from the workspace lockfile.

### Step 2: Generate Scope Keypair (10 sec)

```bash
bash scripts/generate_keys.sh
# → keys/scope_jwt_private.pem  (RSA-4096, chmod 600)
# → keys/scope_jwt_public.pem
```

Keys are auto-generated if they don't exist. Use `--force` to regenerate. The `keys/` directory is gitignored.

### Step 3: Configure Environment (2 min)

```bash
cp .env.example .env
# Edit .env and fill at minimum:
#   POSTGRES_PASSWORD    (generate: openssl rand -base64 32)
#   REDIS_PASSWORD       (generate: openssl rand -base64 32)
#   HATCHET_COOKIE_SECRET (generate: openssl rand -hex 32)
#   LANGFUSE_SECRET      (generate: openssl rand -hex 32)
#   LANGFUSE_SALT        (generate: openssl rand -hex 16)
#   ANTHROPIC_API_KEY    (from https://console.anthropic.com/settings/keys)
```

Generate all secrets at once:

```bash
for v in POSTGRES_PASSWORD REDIS_PASSWORD HATCHET_COOKIE_SECRET LANGFUSE_SECRET LANGFUSE_SALT; do
  printf '%s=%s\n' "$v" "$(openssl rand -hex 32)"
done >> .env
```

> **BYOK Philosophy:** Every API key is Bring Your Own Key. BountyStrike never stores or proxies your credentials. You authenticate directly with each provider/ platform.

### Step 4: Start the Stack (3-5 min first boot; <30 sec thereafter)

```bash
docker compose -f infra/docker/docker-compose.yml --env-file .env up -d
```

**First boot only:** Postgres initializes from `infra/sql/*.sql` via `/docker-entrypoint-initdb.d` (30-60s). Hatchet waits for Postgres to become healthy.

**Verify all services are up:**

```bash
bash scripts/health_check.sh --verbose
```

Expected output:

```
BountyStrike v5 — Health Check
================================

✓ postgres: healthy (port 5432)
✓ redis: healthy (port 6379)
✓ hatchet: healthy (gRPC: 7070, HTTP: 8080)
✓ langfuse: healthy (port 3000)
✓ control-plane: healthy (port 8001)
✓ caddy: healthy (ports 80, 443)
✓ mcp-servers: healthy (15/15 running)

All services are healthy
```

### Step 5: First Scan (5-20 min depending on program size)

```bash
# Issue a scope JWT for a HackerOne program
python scripts/gen_scope_jwt.py issue \
  --operator-id me \
  --program-handle example-program \
  --platform hackerone \
  --targets 'wildcard=*.example.com' \
  --out scope.jwt

# Run the orchestrator
SCOPE_JWT=$(cat scope.jwt) \
PROGRAM_HANDLE=example-program \
PLATFORM=hackerone \
DATABASE_URL=postgresql://bs:${POSTGRES_PASSWORD}@localhost:5432/bountystrike \
python scripts/orchestrator.py
```

The orchestrator phases are: **recon → scanner → exploit → T2 approval → validator → T3 approval → reporter**. See [Operator Approval Workflow](#operator-approval-workflow) for T2/T3 gating.

---

## Configuration Reference

Full env var reference (every variable, default, and where it's read) is in [`docs/runbooks/configuration-guide.md`](runbooks/configuration-guide.md). The table below covers the essentials required to stand up solo mode.

### Required Variables

| Variable | How to Generate | Purpose |
|---|---|---|
| `POSTGRES_PASSWORD` | `openssl rand -base64 32` | Postgres user password |
| `REDIS_PASSWORD` | `openssl rand -base64 32` | Redis AUTH / kill switch |
| `HATCHET_COOKIE_SECRET` | `openssl rand -hex 32` | Hatchet auth cookie signing |
| `LANGFUSE_SECRET` | `openssl rand -hex 32` | Langfuse NextAuth secret |
| `LANGFUSE_SALT` | `openssl rand -hex 16` | Langfuse encryption salt |
| `ANTHROPIC_API_KEY` | From Anthropic Console | Claude API access (1M req/mo free tier) |

### Optional but Recommended (BYOK Providers)

| Variable | Provider | Typical Cost |
|---|---|---|
| `DEEPSEEK_API_KEY` | [DeepSeek Console](https://platform.deepseek.com/api_keys) | $0.27/M input tokens |
| `OPENROUTER_API_KEY` | [OpenRouter](https://openrouter.ai/settings/keys) | Pay-as-you-go, 200+ models |
| `XAI_API_KEY` | [xAI Console](https://console.x.ai/) | Optional, creative recon |

### Platform Credentials (set only for platforms you submit to)

| Variable | Platform | How to Get It |
|---|---|---|
| `H1_API_TOKEN` + `H1_USERNAME` | HackerOne | Settings → API Tokens |
| `BUGCROWD_SESSION_COOKIE` | Bugcrowd | Browser DevTools → Cookies |
| `INTIGRITI_PAT` | Intigriti | Profile → API Token |
| `YESWEHACK_BEARER` | YesWeHack | User Settings → API |

### Scanning Tunables

| Variable | Default | Purpose |
|---|---|---|
| `MAX_VALIDATORS` | `5` | Parallel validator agents |
| `MAX_EXPLOITS` | `3` | Parallel exploit agents |
| `MAX_REPORTERS` | `3` | Parallel reporter agents |
| `RECON_TIMEOUT` | — | Recon phase wall-clock cap (minutes) |
| `SCAN_TIMEOUT` | — | Total scan wall-clock cap (minutes) |
| `SKIP_SCANNER` | — | Set to `1` to skip scanner phase |
| `SKIP_EXPLOIT` | — | Set to `1` to skip exploit phase |

> **Fail-loud design:** All required variables use `${VAR:?...}` syntax in `docker-compose.yml`. A missing variable aborts startup with a clear error message — never results in a silent default.

---

## Service Topology (Solo Mode)

```bash
docker compose -f infra/docker/docker-compose.yml ps
```

| Service | Container | Image | Bound Port | Persistence | Health Gate |
|---|---|---|---|---|---|
| `postgres` | `bs-postgres` | `pgvector/pgvector:pg17` | `127.0.0.1:5432` | `postgres_data` vol | `pg_isready` |
| `redis` | `bs-redis` | `redis:7-alpine` | `127.0.0.1:6379` | `redis_data` vol (AOF) | `redis-cli ping` |
| `hatchet` | `bs-hatchet` | `ghcr.io/hatchet-dev/hatchet-engine:latest` | `127.0.0.1:7070` (gRPC), `8080` (HTTP) | `hatchet_data` vol | `depends_on: postgres (healthy)` |
| `langfuse` | `bs-langfuse` | `langfuse/langfuse:latest` | `127.0.0.1:3000` | (Postgres-backed) | `depends_on: postgres (healthy)` |
| `caddy` | `bs-caddy` | `caddy:2-alpine` | `80`, `443` | `caddy_data` vol | `depends_on: hatchet+langfuse` |
| `control-plane` | `bs-control-plane` | (local build) | `127.0.0.1:8001` | — | `depends_on: postgres+redis+hatchet` |
| `mcp-*` (×15) | `bs-mcp-*` | (local builds) | (stdio subprocess) | — | `depends_on: control-plane` |

**Port bindings** default to `127.0.0.1` (local-only). TLS via `caddy` is required for any public exposure.

**Network:** All services share the `bountystrike` bridge network (DNS resolution via container names).

---

## Scope-JWT Keypair

The scope JWT is BountyStrike's network-layer trust anchor. Every MCP that touches a target validates the JWT and enforces target/exclusion/rate-limit claims.

### Auto-Generation

Keys are automatically generated by the entrypoint script if they don't exist:

```bash
# Manual generation (same as what the entrypoint does):
bash scripts/generate_keys.sh
# keys/scope_jwt_private.pem  → exists → skip
# keys/scope_jwt_public.pem   → exists → skip
# Otherwise: generates RSA-4096 keypair, chmod 600 on private key
```

### Issuing a Scope JWT

```bash
python scripts/gen_scope_jwt.py issue \
  --operator-id me \
  --program-handle acme-corp \
  --platform hackerone \
  --targets 'wildcard=*.acme.com' \
  --out scope.jwt
```

The JWT carries: `wildcards`, `exact_hosts`, `ips`, `exclusions.hostnames`, `exclusions.paths`, `rate_limits.default_rps`, per-host overrides, `jti`, `exp` (max 168 hours), `iss`, `sub`. See `mcp/scope-mcp/` for validation logic.

### Rotation

Rotate by regenerating keys and revoking issued JTIs via the `audit_log` table:

```bash
bash scripts/generate_keys.sh --force
# Revoke old JTIs in Postgres:
psql $DATABASE_URL -c "UPDATE scope_jwt_audit SET revoked = true WHERE jti = 'old-jti';"
```

---

## Kill Switch Operations

Three independent layers — each works without the others.

| Layer | Mechanism | Command | Latency |
|---|---|---|---|
| 1 — Redis flag | `SET bountystrike:killswitch:global 1 EX 86400` | `redis-cli -a $REDIS_PASSWORD SET bountystrike:killswitch:global 1 EX 86400` | Instant |
| 2 — PreToolUse hook | `pretool_killswitch.py` checks Redis before every tool call | (automatic, wired in `.claude/settings.json`) | ~1 ms/call |
| 3 — Process supervisor | Kill any in-flight agent process | `docker compose stop` (graceful) / `pkill -f "claude -p"` (immediate) | Kernel-level |

Check kill switch status:

```bash
bash scripts/health_check.sh  # status line shows kill switch state
redis-cli -a $REDIS_PASSWORD GET bountystrike:killswitch:global
# → (nil) = disabled | 1 = active
```

The 24-hour TTL (`EX 86400`) auto-clears the flag so an abandoned kill switch cannot permanently disable the platform.

> **Fail-open behavior:** Layer 1 fails open if Redis is unreachable (the platform keeps running). Layer 3 is the last-resort backstop.

---

## Health Checks

### Quick Status

```bash
bash scripts/health_check.sh
```

### Verbose (per-service detail)

```bash
bash scripts/health_check.sh --verbose
```

### Individual Services

```bash
# Postgres
psql "postgresql://bs:${POSTGRES_PASSWORD}@localhost:5432/bountystrike" -c "SELECT 1"

# Redis
redis-cli -a ${REDIS_PASSWORD} PING
# → PONG

# Hatchet
curl -sf http://localhost:8080/healthz
# → {"status":"ok"}

# Langfuse
curl -sf http://localhost:3000/api/public/health
# → {"status":"ok"}

# Control-plane
curl -sf http://localhost:8001/health
# → {"status":"ok"}
```

### Interpreting Health States

| State | Meaning | Action |
|---|---|---|
| `healthy` | Service is passing its health check | None — operate normally |
| `starting` | Service is initializing (common on first boot) | Wait 30-60s, re-check |
| `unhealthy` | Health check is failing | Check service logs: `docker logs bs-<service>` |
| `not running` | Container is stopped or crashed | Restart: `docker compose restart <service>` |

---

## Evidence Backend

Two backends, configured via `EVIDENCE_BACKEND`:

### Local Filesystem (default — dev / solo)

```env
EVIDENCE_BACKEND=local
EVIDENCE_ROOT=./evidence
```

Data persists in the `./evidence` directory. Back up this directory regularly.

### Cloudflare R2 (recommended for production solo)

```env
EVIDENCE_BACKEND=r2
R2_BUCKET=bountystrike-evidence
R2_ACCOUNT_ID=<your-cloudflare-account-id>
R2_ACCESS_KEY_ID=<your-r2-access-key>
R2_SECRET_ACCESS_KEY=<your-r2-secret>
R2_REGION=auto
# Optional:
# R2_ENDPOINT_URL=https://<custom-endpoint>
```

R2 pricing (2026): $0.015/GB/month storage, $0.36/M Class-B operations. Typical solo usage (10 GB, 1M ops/month): ~$1-3/month.

---

## Logs & Observability

### Structured Logs (All Services)

Every Python service uses `structlog` with JSON-formatted output to stderr. View:

```bash
# All services
docker compose -f infra/docker/docker-compose.yml logs -f

# Single service
docker compose -f infra/docker/docker-compose.yml logs -f control-plane

# Last 100 lines
docker compose -f infra/docker/docker-compose.yml logs --tail=100 postgres
```

**Log rotation** is configured via the `json-file` driver: `max-size: 10m`, `max-file: 3` (~30 MB max per container).

### Langfuse (LLM Observability)

Access at `http://localhost:3000`. Every Claude trace lands here with token count and cost. The `agent_sessions.langfuse_trace_id` column is the join key.

### Audit Log (Tamper-Evident)

The `audit_log` Postgres table stores a hash-chained log of every state-changing action. Query:

```bash
psql $DATABASE_URL -c "SELECT * FROM audit_log ORDER BY created_at DESC LIMIT 20;"
```

### Postgres System Info

```bash
# Tables + extensions
psql $DATABASE_URL -c "\dt" -c "\dx"
# Expected: 12+ tables, pgvector + pg_trgm + pgcrypto
```

---

## Operator Approval Workflow

T2 (single-human) and T3 (two-person) approvals gate platform submission. Manage them via `scripts/approve.py`:

```bash
# List pending requests
uv run python scripts/approve.py list

# Inspect a request
uv run python scripts/approve.py show <request_id>

# Approve
uv run python scripts/approve.py approve <request_id> --reason "Confirmed working"

# Reject
uv run python scripts/approve.py reject <request_id> --reason "Repro failed"
```

> **T3 requires two distinct approvers.** The first `approve` call marks the request as half-approved (returns `None`). The second call by a different operator returns the APPROVAL_TOKEN that unlocks submission.

---

## Backing Up & Restoring

### Postgres Dump

```bash
# Full dump
docker exec bs-postgres pg_dump -U bs -d bountystrike > backup_$(date +%Y%m%d_%H%M%S).sql

# Restore
psql $DATABASE_URL < backup_20260526.sql
```

### Evidence Directory (Local Backend)

```bash
# Create incremental backup
rsync -av --delete ./evidence/ /mnt/backup/bountystrike-evidence/

# Restore
rsync -av /mnt/backup/bountystrike-evidence/ ./evidence/
```

### Docker Volumes

```bash
# List volumes
docker volume ls | grep bountystrike

# Back up a volume
docker run --rm -v bountystrike_postgres_data:/data -v $(pwd):/backup alpine \
  tar czf /backup/postgres_data.tar.gz -C /data .

# Restore a volume (DESTRUCTIVE: removes existing data first)
docker volume rm bountystrike_postgres_data
docker run --rm -v bountystrike_postgres_data:/data -v $(pwd):/backup alpine \
  tar xzf /backup/postgres_data.tar.gz -C /data
```

---

## Teardown

```bash
# Stop all services (keep data)
docker compose -f infra/docker/docker-compose.yml down

# Stop and DESTROY all data (Postgres, Redis, Hatchet, Caddy, evidence)
docker compose -f infra/docker/docker-compose.yml down -v
```

> `down -v` is **irreversible**. Postgres data, evidence blobs (if using local backend), and Redis kill-switch state are permanently deleted.

---

## Cost Breakdown

Target: **under $30/month** all-in for solo mode.

### Infrastructure

| Item | Cost | Notes |
|---|---|---|
| VPS (Hetzner CX32: 4 vCPU, 8 GB) | €8.29/mo | Or use existing hardware: $0 |
| Docker + all containers | $0 | Everything runs locally |
| Cloudflare R2 (10 GB, 1M ops) | ~$1-3/mo | Only if `EVIDENCE_BACKEND=r2` |
| Caddy + Cloudflare Tunnel | $0 | Free tier covers this |
| Domain (optional) | ~$1/mo | e.g., Namecheap |
| **Infra subtotal** | **$9-13/mo** | |

### LLM API (BYOK)

| Provider | Cost | Notes |
|---|---|---|
| Anthropic Claude | $0 (free tier) | 1M req/month free; Sonnet 4.6 / Opus 4.7 |
| DeepSeek V4-Flash | ~$5-15/mo | Primary model; $0.27/M input tokens |
| OpenRouter | ~$2-10/mo | Pay-as-you-go fallback |
| **LLM subtotal** | **$7-25/mo** | Scales with scan volume |

### Total

| Scenario | Monthly Cost |
|---|---|
| Minimal (existing Mac + free tiers) | **$0-5/mo** |
| VPS + light scanning | **$15-25/mo** |
| VPS + heavy scanning | **$25-35/mo** |

No SaaS markup. No seat licenses. No surprises. Your bounty payouts are the business model.

---

## FAQ / Troubleshooting

### `docker compose up -d` fails with "variable X is missing a value"

**Cause:** A required environment variable is not set in `.env`.  
**Fix:** Open `.env`, find the empty variable, and set it. For secrets: `openssl rand -hex 32`.

### Postgres takes a long time to start on first boot

**Cause:** The database is being initialized from `infra/sql/*.sql` scripts in `/docker-entrypoint-initdb.d`.  
**Fix:** This is normal. Wait 30-60 seconds and re-run `bash scripts/health_check.sh`. On subsequent boots, Postgres starts instantly.

### Hatchet shows "unhealthy" or "depends_on condition not met"

**Cause:** Hatchet waits for Postgres to report `healthy`.  
**Fix:** Check Postgres logs: `docker logs bs-postgres`. Common causes: wrong `POSTGRES_PASSWORD`, disk full, or port conflict.

### Redis refuses connections

**Cause:** `REDIS_PASSWORD` was changed after the container was created — the container still uses the old password.  
**Fix:** `docker compose down -v && docker compose up -d` (recreates the container with the new password). Data loss in Redis is acceptable (rebuildable from Postgres).

### MCP servers are not starting

**Cause:** The control-plane container may not be healthy yet (MCP servers depend on it via the compose dependency chain).  
**Fix:** Wait for `bs-control-plane` to show `healthy`: `docker compose ps`. If it stays unhealthy, check its logs: `docker logs bs-control-plane`.

### "Permission denied" on `keys/scope_jwt_private.pem`

**Cause:** The private key was generated with incorrect file permissions.  
**Fix:** `chmod 600 keys/scope_jwt_private.pem`

### Scans are hanging / timing out

**Cause:** Possible causes include: missing platform API tokens, scope JWT has expired (168h max TTL), Anthropic rate limits hit, or target program is unreachable.  
**Fix:**  
1. Check scope JWT expiry: `python scripts/gen_scope_jwt.py decode --jwt $(cat scope.jwt)`  
2. Check API key validity: attempt a minimal Claude API call.  
3. Check `MAX_VALIDATORS` / `MAX_EXPLOIT` parallelism settings.

### How do I re-apply schema migrations without losing data?

**Cause:** The `docker-entrypoint-initdb.d` scripts only run on *first* boot (empty volume).  
**Fix:** Apply migrations manually:  
```bash
psql $DATABASE_URL -f infra/sql/schema.sql
psql $DATABASE_URL -f infra/sql/seed_weights.sql
```

### How do I completely reset the stack?

```bash
docker compose -f infra/docker/docker-compose.yml down -v
bash scripts/generate_keys.sh --force
docker compose -f infra/docker/docker-compose.yml --env-file .env up -d
```

### How do I update to a new version?

```bash
git pull
docker compose -f infra/docker/docker-compose.yml --env-file .env up -d --build
# --build flag rebuilds images from updated Dockerfiles
```

---

## SaaS Multi-Tenant Preview (Phase 4)

Summarized for forward planning. Solo mode is the only supported deployment today.

| Concern | Solo Mode | SaaS (Phase 4) |
|---|---|---|
| Sandbox | Local subprocess + Docker | Firecracker microVM per scan, scope-bound network namespace |
| Workflow Engine | Hatchet (self-hosted) | Temporal Cloud |
| LLM Routing | Direct BYOK | LiteLLM proxy with per-tenant token budgets |
| Scope Enforcement | RS256 JWT | RS256 JWT + per-tenant isolation |
| TLS | Optional (Caddy) | Mandatory (Caddy + cert-manager) |
| Database | Docker Postgres 17 | Managed Postgres (Hetzner) + read replicas |
| Evidence Store | Local FS or R2 | Cloudflare R2 (mandatory) |
| Tenancy | Single operator | Multi-tenant with Postgres RLS |

### SaaS Tier Pricing (Phase 4)

| Tier | Price | Scans | Concurrent | Programs |
|---|---|---|---|---|
| Hacker | $19/mo | 50 | 1 | 5 |
| Pro | $79/mo | 200 | 3 | 20 |
| Team | $299/mo | 1000 | 10 | 50 |
| Enterprise | $2,000+/mo | Unlimited | Dedicated | Unlimited, on-prem option |

Full SaaS architecture: [`docs/research/05-deployment.md`](research/05-deployment.md) §SaaS Multi-Tenant Architecture.

---

## See Also

| Document | What It Covers |
|---|---|
| [`README.md`](../README.md) | Project overview, architecture diagram, quickstart |
| [`docs/runbooks/configuration-guide.md`](runboards/configuration-guide.md) | Every env var with default, purpose, and where it's read |
| [`docs/runbooks/deployment-guide.md`](runboards/deployment-guide.md) | Detailed solo-mode bring-up (supplements this file) |
| [`docs/runbooks/testing-guide.md`](runboards/testing-guide.md) | Pytest config, fixtures, field-validation harnesses |
| [`docs/system-architecture.md`](system-architecture.md) | Mermaid diagrams: component graph, data flow, ER, trust boundaries |
| [`docs/codebase-summary.md`](codebase-summary.md) | Full file inventory, dependencies, table schema, MCP tools |
| [`docs/research/05-deployment.md`](research/05-deployment.md) | Full deployment rationale from the build plan |
| [`docs/project-overview-pdr.md`](project-overview-pdr.md) | Vision, 5 non-negotiables, scope |
