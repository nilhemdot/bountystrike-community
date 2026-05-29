# BountyStrike v5 — Infra (Phase 0b)

Solo-mode Docker Compose stack: Postgres 17 + pgvector, Redis 7, Hatchet, Langfuse, Caddy.

Reference: `docs/research/05-deployment.md`.

## Layout

```
infra/
  sql/
    00_extensions.sql              # vector, pg_trgm, pgcrypto
    01_schema.sql                  # 11 core tables + finding_status ENUM + HNSW index
    02_dedup_fingerprints.sql      # dedup_fingerprints table + scan_jobs.completed_at
    03_audit_log_realign.sql       # audit_log per-finding hash-chained shape
    04_approval_queue.sql          # T2/T3 operator approval queue (Phase 2 W7-8)
    05_findings_raw_finding.sql    # findings.raw_finding JSONB column + chain_steps index
  docker/
    docker-compose.yml     # 5 services + 5 named volumes
    Caddyfile              # local dev reverse proxy (TLS off)
  README.md                # this file
```

## Prerequisites

- Docker Engine 25+ with Compose v2
- A populated `.env` at the repo root (copy `.env.example`, fill in 21 keys)
- For Postgres password / Redis password / Hatchet cookie / Langfuse secrets, generate with:
  ```bash
  openssl rand -base64 32
  ```

## Start the stack

```bash
# from repo root
docker compose -f infra/docker/docker-compose.yml --env-file .env up -d
```

Postgres init scripts (`infra/sql/*.sql`) auto-run **on first boot only** (when `postgres_data`
volume is empty). To re-run schema after schema edits:

```bash
docker compose -f infra/docker/docker-compose.yml down
docker volume rm bountystrike_postgres_data
docker compose -f infra/docker/docker-compose.yml --env-file .env up -d postgres
```

## Manual schema apply (when DB already exists)

```bash
psql "postgresql://bs:${POSTGRES_PASSWORD}@localhost:5432/bountystrike" \
  -f infra/sql/00_extensions.sql \
  -f infra/sql/01_schema.sql
```

## Health checks

| Service   | Probe                                                         |
|-----------|---------------------------------------------------------------|
| postgres  | `docker exec bs-postgres pg_isready -U bs -d bountystrike`    |
| redis     | `docker exec bs-redis redis-cli -a "$REDIS_PASSWORD" ping`    |
| hatchet   | `curl http://localhost:8080/healthz`                          |
| langfuse  | `curl http://localhost:3000/api/public/health`                |
| caddy     | `curl http://localhost/`                                      |

`docker compose ps` shows healthcheck status next to each container.

## Verify pgvector + tables loaded

```bash
psql "postgresql://bs:${POSTGRES_PASSWORD}@localhost:5432/bountystrike" \
  -c "SELECT extname, extversion FROM pg_extension WHERE extname IN ('vector','pg_trgm','pgcrypto');"

psql "postgresql://bs:${POSTGRES_PASSWORD}@localhost:5432/bountystrike" \
  -c "\dt"
```

Expected: 11 tables (`agent_sessions, audit_log, evidence_artifacts, ev_score_history,
findings, model_costs, programs, report_submissions, scan_jobs, scope_changes, scopes`).

## Kill switch operational notes

Three layers (research/03 §Kill Switch):

```bash
# Layer 1 — Redis flag (instant, ~10ms, 24h TTL auto-clear)
docker exec bs-redis redis-cli -a "$REDIS_PASSWORD" \
  SET bs:killswitch:global halt_all EX 86400

# Check
docker exec bs-redis redis-cli -a "$REDIS_PASSWORD" GET bs:killswitch:global

# Clear
docker exec bs-redis redis-cli -a "$REDIS_PASSWORD" DEL bs:killswitch:global

# Layer 2 — PreToolUse hook (Phase 1+: pretool_scope_guard.py reads Layer 1 flag)
# Layer 3 — Process supervisor (last resort)
pkill -SIGTERM -f "claude -p"   # graceful
pkill -SIGKILL -f "claude -p"   # immediate
```

## Tear down (data-preserving)

```bash
docker compose -f infra/docker/docker-compose.yml down
```

## Tear down (purge volumes — DESTRUCTIVE)

```bash
docker compose -f infra/docker/docker-compose.yml down -v
```

## What's NOT in Phase 0b

Deferred to Phase 1+ (per research/01-strategy-architecture.md):

- Firecracker / microsandbox VM pool
- pgvectorscale (DiskANN) — only needed at >500K vectors
- ParadeDB / pg_search BM25
- Hash-chain trigger on `audit_log` (placeholder comment in `01_schema.sql`)
- Sigstore Rekor anchoring
- Postgres RLS policies (SaaS multi-tenant only)
- LiteLLM proxy, NATS JetStream, Temporal Cloud
