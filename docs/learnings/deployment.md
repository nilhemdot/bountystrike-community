# deployment.md — Deployment & Infrastructure

## Local Dev Stack

```bash
docker compose -f infra/docker-compose.yml up -d
# Services: Postgres 17 (pgvector), Redis 7, Hatchet, Langfuse
```

Required env vars (see `.env.example` for all 21):
```
DATABASE_URL=postgresql+asyncpg://...
REDIS_URL=redis://localhost:6379
ANTHROPIC_API_KEY=...
OPENAI_API_KEY=...           # dedup-mcp embeddings
INTERACTSH_SERVER=...
INTERACTSH_TOKEN=...
SCOPE_JWT_PUBLIC_KEY=...     # RS256 public key path
```

## Keys Setup

```bash
bash scripts/generate_keys.sh   # creates keys/ dir with RS256 keypair
# keys/ is gitignored — never commit
```

## Health Check

```bash
bash scripts/health_check.sh
# Checks: Postgres conn, Redis conn, Anthropic API, scope JWT validity
```

## Postgres Migrations

```bash
# Apply in order
psql $DATABASE_URL -f infra/migrations/01_schema.sql
psql $DATABASE_URL -f infra/migrations/02_dedup_fingerprints.sql
psql $DATABASE_URL -f infra/migrations/03_...sql
psql $DATABASE_URL -f infra/migrations/04_approval_queue.sql
psql $DATABASE_URL -f infra/migrations/05_findings_raw_finding.sql
```

## Kill Switch

```bash
# Halt all agent activity immediately
redis-cli SET KILL_SWITCH 1

# Resume
redis-cli DEL KILL_SWITCH

# Watch mode (auto-halt on anomaly)
python scripts/kill_switch_watch.py
```

## Cost Monitoring

```bash
python scripts/cost_audit.py        # per-model cost breakdown
bash scripts/cost_report.sh         # summary report
```

## Langfuse Traces

LLM traces sent to Langfuse (running in Docker). Access at `http://localhost:3000` (default Langfuse port). Use for debugging agent reasoning and prompt token costs.

## Hatchet Workflow Engine

Background job orchestration for long-running hunt workflows. Access dashboard at `http://localhost:8888` (default Hatchet port).
