# Part 9 — Deployment Modes (Solo + SaaS Multi-Tenant)

Source: bountystrike_v5_build_plan.md lines 2674-3218.

## Solo Mode Setup

### Design Constraints
- Single operator on Mac mini M4 or Linux laptop (16GB RAM min, 512GB NVMe).
- Target: under $30/month infra; bounty payouts the only meaningful income line.
- Postgres in Docker (no RDS), Hatchet (no Temporal Cloud), microsandbox/Firecracker locally (no E2B), DeepSeek V4-Flash primary, BYOK Anthropic via 1M free tier, Caddy + ngrok/Cloudflare Tunnel, R2 for blobs.

### Prerequisites — macOS (Homebrew)
```bash
brew install go python@3.12 node@22 rust docker colima
brew install subfinder httpx dnsx naabu katana nuclei interactsh
```

### Prerequisites — Linux (Ubuntu 24.04)
```bash
sudo apt-get install -y golang nodejs python3.12 docker.io
# then run the same `go install` block as macOS
```

### Tool Install Commands (cross-platform)
```bash
# uv — fastest Python installer
curl -LsSf https://astral.sh/uv/install.sh | sh

# Claude Code CLI
npm install -g @anthropic-ai/claude-code

# Claude Agent SDK
pip install claude-agent-sdk

# bbscope v2 (scope ingestion)
go install github.com/sw33tLie/bbscope@latest

# ProjectDiscovery toolset
go install -v github.com/projectdiscovery/subfinder/v2/cmd/subfinder@latest
go install -v github.com/projectdiscovery/httpx/cmd/httpx@latest
go install -v github.com/projectdiscovery/dnsx/cmd/dnsx@latest
go install -v github.com/projectdiscovery/naabu/v2/cmd/naabu@latest
go install -v github.com/projectdiscovery/nuclei/v3/cmd/nuclei@latest
go install -v github.com/projectdiscovery/katana/cmd/katana@latest

# Nuclei templates
nuclei -update-templates
```

### First Launch Sequence
```bash
# 1. Generate scope JWT keypair
mkdir -p keys
openssl genrsa -out keys/scope_jwt_rs256_private.pem 4096
openssl rsa -in keys/scope_jwt_rs256_private.pem \
  -pubout -out keys/scope_jwt_rs256_public.pem

# 2. Boot core services first
docker compose up -d postgres redis hatchet

# 3. Run schema + weight seed migrations
sleep 10
psql postgresql://bs:${POSTGRES_PASSWORD}@localhost:5432/bountystrike \
  < infra/sql/schema.sql
psql postgresql://bs:${POSTGRES_PASSWORD}@localhost:5432/bountystrike \
  < infra/sql/seed_weights.sql

# 4. Bring up full stack
docker compose up -d

# 5. Health checks
curl http://localhost:8080/healthz                   # Hatchet
curl http://localhost:3000/api/public/health         # Langfuse

# 6. Register Hatchet workflows
cd workers && python register_workflows.py

# 7. Initial scope ingest (manual)
python -m bountystrike.workers.scope_ingest --platform all --initial

# 8. Verify scope loaded
psql postgresql://bs:${POSTGRES_PASSWORD}@localhost:5432/bountystrike \
  -c "SELECT platform, count(*) FROM programs GROUP BY platform;"

# 9. First scan
bountystrike scan --program hackerone/target-program --profile solo_aggressive
```

## docker-compose.yml

File: `docker-compose.yml` (solo mode), version `3.9`. Five services + three named volumes.

### Services
| Service | Image | Purpose | Ports |
|---|---|---|---|
| `postgres` | `pgvector/pgvector:pg17` | Primary DB; pgvector + pgvectorscale + ParadeDB | 5432 |
| `redis` | `redis:8.0-alpine` | Kill switch flag + session cache; AOF + password | 6379 |
| `hatchet` | `ghcr.io/hatchet-dev/hatchet-engine:latest` | Workflow engine (Postgres-backed) | 7070 (gRPC), 8080 (HTTP) |
| `langfuse` | `langfuse/langfuse:latest` | Self-hosted LLM observability | 3000 |
| `caddy` | `caddy:2-alpine` | HTTPS reverse proxy + LetsEncrypt | 80, 443 |

### Notable wiring
- Postgres has a healthcheck (`pg_isready`) gating Hatchet + Langfuse via `depends_on: condition: service_healthy`.
- Postgres mounts `./infra/sql/init.sql` into `/docker-entrypoint-initdb.d/init.sql` for first-boot bootstrap.
- Redis runs with `--appendonly yes --requirepass ${REDIS_PASSWORD}`.
- Hatchet env: `DATABASE_URL`, `SERVER_GRPC_PORT=7070`, `SERVER_PORT=8080`, `SERVER_AUTH_COOKIE_SECRETS`.
- Langfuse env: `DATABASE_URL`, `NEXTAUTH_SECRET`, `NEXTAUTH_URL=http://localhost:3000`, `SALT`.
- Caddy mounts `./infra/Caddyfile` and persists `caddy_data`; depends on `hatchet` + `langfuse`.

### Volumes
`postgres_data`, `redis_data`, `caddy_data` (named, default driver).

## .env Template (`.env.local`)

| Key | Purpose |
|---|---|
| `POSTGRES_PASSWORD` | Postgres `bs` user password (`openssl rand -base64 32`) |
| `REDIS_PASSWORD` | Redis `requirepass` for kill switch / cache |
| `HATCHET_COOKIE_SECRET` | Hatchet web auth cookie HMAC secret |
| `LANGFUSE_SECRET` | NextAuth secret for Langfuse self-hosted |
| `LANGFUSE_SALT` | Langfuse encryption salt |
| `ANTHROPIC_API_KEY` | BYOK Claude (1M req/month free tier) for Sonnet 4.6 / Opus 4.7 |
| `H1_API_TOKEN` | HackerOne API token (scope, submission, triage) |
| `H1_USERNAME` | HackerOne account username (paired with API token) |
| `BUGCROWD_SESSION_COOKIE` | Bugcrowd session cookie — refresh monthly |
| `INTIGRITI_PAT` | Intigriti personal access token |
| `YESWEHACK_BEARER` | YesWeHack bearer token |
| `SCOPE_JWT_PRIVATE_KEY_PATH` | Path to RS256 private key (`./keys/scope_jwt_rs256_private.pem`) |
| `SCOPE_JWT_PUBLIC_KEY_PATH` | Path to RS256 public key (`./keys/scope_jwt_rs256_public.pem`) |
| `R2_BUCKET` | Cloudflare R2 bucket name (e.g. `bountystrike-evidence`) |
| `R2_ACCOUNT_ID` | Cloudflare account ID for R2 API |
| `R2_ACCESS_KEY_ID` | R2 S3-compatible access key |
| `R2_SECRET_ACCESS_KEY` | R2 S3-compatible secret |
| `INTERACTSH_SERVER_URL` | OAST callback server (default `https://oast.pro`) |
| `INTERACTSH_AUTH` | Interactsh auth token for self-hosted/SaaS server |
| `BURP_COLLABORATOR_URL` | Optional Burp Collaborator (Pro license) — `https://burpcollaborator.net` |

## JWT Keypair Setup

Scope JWTs are RS256-signed; the private key signs CIDR allowlists, the public key is baked into Firecracker VM images and used by the PreToolUse hook.

```bash
mkdir -p keys
openssl genrsa -out keys/scope_jwt_rs256_private.pem 4096
openssl rsa -in keys/scope_jwt_rs256_private.pem \
  -pubout -out keys/scope_jwt_rs256_public.pem
```

Paths are referenced by `SCOPE_JWT_PRIVATE_KEY_PATH` / `SCOPE_JWT_PUBLIC_KEY_PATH` in `.env`. Same keys feed the SaaS VM init scripts (Section 9.2.4).

## Initial Scope Ingest Flow

1. Wait for Postgres healthcheck, then apply `infra/sql/schema.sql` and `infra/sql/seed_weights.sql` via `psql`.
2. `docker compose up -d` to bring up the rest of the stack.
3. Register all Hatchet workflows: `cd workers && python register_workflows.py`.
4. Cross-platform scope ingester: `python -m bountystrike.workers.scope_ingest --platform all --initial` — pulls programs from H1, Bugcrowd, Intigriti, YesWeHack using the `.env` tokens.
5. Verify: `SELECT platform, count(*) FROM programs GROUP BY platform;`.
6. First scan: `bountystrike scan --program hackerone/target-program --profile solo_aggressive`.

## Kill Switch Ops

Three independent layers (Section 9.1.5) — each works without the others.

| Layer | Mechanism | Latency | Notes |
|---|---|---|---|
| 1 — Redis flag | `redis-cli SET bountystrike:killswitch:global 1 EX 86400` | Instant, no LLM | 24h TTL auto-clears so an abandoned kill switch can't permanently brick the platform |
| 2 — PreToolUse hook | `pretool_scope_guard.py` checks Redis flag before every tool call | ~1ms per call | Embedded in the hook chain; denies tool calls when flag is set |
| 3 — Process supervisor | `pkill -SIGTERM -f "claude -p"` (graceful) or `pkill -SIGKILL -f "claude -p"` (immediate) | Kernel-level | Last-resort, kills any in-flight agent process |

Status: `bountystrike status --killswitch`.

## SaaS Multi-Tenant Architecture

### Design Priorities
1. Hard tenant isolation at the data plane — Postgres RLS so queries can never cross tenants even with app bugs.
2. Per-job Firecracker microVMs — no shared FS between scan jobs; blast radius = one job's egress allowlist.
3. Signed scope JWTs validated at the network layer inside the VM — bypass-proof against LLM prompt injection.
4. Temporal Cloud for durable orchestration — multi-week scans survive server failures.
5. LiteLLM proxy enforces per-tenant monthly token budgets and per-scan cost ceilings.

### Component Map
- Edge: Cloudflare (DNS + WAF + R2).
- Frontend: Next.js 16 on Cloudflare Pages — triage rooms, evidence viewer, EV dashboard, collab WS via Durable Objects.
- Control plane: Go API (Chi + WorkOS AuthKit + RS256 scope JWTs) — endpoints `/api/v1/programs|scans|findings|submit`.
- MCP gateway: per-tenant MCP server with RS256-validated tokens.
- Orchestration: Temporal Cloud, namespace-per-tenant `{tenant-id}.bountystrike`. Workflows: `ScanWorkflow`, `ScopeIngestWorkflow`, `EVRankingWorkflow`, `TriageWorkflow`, `ReportWorkflow`. Workers: K8s (EKS/GKE), 2-20 replicas.
- Agent workers: Claude Agent SDK — `recon-agent`, `scanner-agent`, `exploit-agent`, `validator`, `reporter`.
- Job sandbox: Firecracker microVM pool — per-job VM, 1 vCPU/512MB, scope-JWT IPs only, tap0 iptables enforced, max 30min TTL.
- Event bus: NATS JetStream — `scope_changed`, `kev_alert`, `finding_created`, `killswitch`.
- Model routing: LiteLLM proxy — Anthropic BYOK, OpenRouter, xAI, DeepSeek, self-hosted; emits to Langfuse Cloud + Prometheus.
- Storage: Hetzner AX-52 Postgres 17 primary (1TB NVMe) + 2 AX-32 read replicas, PgBouncer (max 100/tenant), pgvector + ParadeDB BM25, Turbopuffer when tenant > 5M vectors. R2 hot blobs, SeaweedFS Hetzner cold archive (>90d).
- Observability: Langfuse Cloud (LLM traces), Grafana Cloud LGTM, Honeycomb (agent reasoning traces), Sentry Business, OpenTelemetry SDK across all services.

### Tier Pricing
| Tier | Price | Allowance | Per-scan amortized |
|---|---|---|---|
| Hacker | $19/mo | 50 scans, 1 concurrent, 5 programs | $0.38 |
| Pro | $79/mo | 200 scans, 3 concurrent, 20 programs, API access | $0.40 |
| Team | $299/mo | 1000 scans, 10 concurrent, 50 programs, Slack | $0.30 |
| Enterprise | $2,000+/mo | Unlimited, dedicated VMs, on-prem option, SOC 2, SLA | Custom |

### Tenant Isolation — Postgres RLS
```sql
ALTER TABLE scans ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON scans
  USING (tenant_id = current_setting('app.tenant_id')::uuid)
  WITH CHECK (tenant_id = current_setting('app.tenant_id')::uuid);

-- Set per request via PgBouncer:
SET app.tenant_id = '{{tenant_uuid}}';
```

### Compliance Hooks
- EU CRA (effective 2026-09-11): T+24h Early Warning to ENISA SRP / national CSIRT, T+72h Vulnerability Notification (CVSS v4 + affected versions + mitigations), T+14d (exploited) / T+1m (severe incident) Final Report. Operator may add detail but cannot block submission.
- ISO 29147 / 30111 / Project Zero: 90-day disclosure timer per finding (`DisclosureTimer` class), daily Hatchet/Temporal task escalates: `WARNING` <=14d, `URGENT` <=7d, `OVERDUE` <=0d. Auto-disclosure remains human-gated.

## VM Egress Allowlist (iptables flow)

Runs as PID 1 inside each Firecracker microVM, before the scan workload starts. Even if an LLM is prompt-injected into trying out-of-scope IPs, the kernel drops the packet — agent gets a connection timeout, not an app-layer error (invisible + bypass-proof).

```bash
#!/bin/sh
SCOPE_JWT=$(curl -s http://169.254.169.254/latest/user-data | jq -r '.scope_jwt')

# 1. Validate JWT against public key baked into VM image
jwt_validate "$SCOPE_JWT" /etc/bountystrike/scope_jwt_public.pem || {
  echo "FATAL: Invalid scope JWT. Refusing to start scan."
  exit 1
}

# 2. Extract claims
ALLOWED_CIDRS=$(jwt_decode_field "$SCOPE_JWT" "allowed_cidrs")
DNS_SERVERS=$(jwt_decode_field "$SCOPE_JWT" "allowed_dns")
INTERACTSH_HOST=$(jwt_decode_field "$SCOPE_JWT" "interactsh_host")

# 3. Default-deny + minimal allowlist
iptables -P OUTPUT DROP
iptables -A OUTPUT -m state --state ESTABLISHED,RELATED -j ACCEPT
iptables -A OUTPUT -d $DNS_SERVERS    -p udp --dport 53  -j ACCEPT
iptables -A OUTPUT -d $INTERACTSH_HOST -p tcp --dport 443 -j ACCEPT

# 4. Append every scope CIDR
for cidr in $ALLOWED_CIDRS; do
  iptables -A OUTPUT -d "$cidr" -j ACCEPT
done

echo "Egress policy programmed. Authorized CIDRs: $ALLOWED_CIDRS"
```

Flow summary:
1. Go control plane signs a scope JWT (allowed CIDRs, DNS servers, interactsh host) with the RS256 private key.
2. JWT is injected into VM metadata at boot (`http://169.254.169.254/latest/user-data`).
3. Init script fetches it, validates against the public key baked into the VM image — fails closed.
4. Decodes claims, sets `OUTPUT` policy to `DROP`, allows established/related, allows DNS (UDP/53), allows interactsh OAST host (TCP/443), then appends an `ACCEPT` rule per scope CIDR.
5. Scan workload starts. Anything outside the allowlist times out at the kernel.

### Observability SLOs (Section 9.2.6)
1. Confirmed-rate trend (7d/30d MA) — must stay >70%.
2. Time-to-validate per bug class — target <4h for P1/P2.
3. Cost per confirmed finding — <$5 solo, <$15 SaaS.
4. False positive rate per model routing decision.
5. Scope violation attempts (PreToolUse deny rate) — prompt injection canary.
6. Temporal queue depth.
7. BYOK utilization vs free tier.

## Context7 Docs Pulled

Context7 access for Hatchet, uv, and Docker Compose was attempted via `mcp__context7__resolve-library-id` but denied by the harness (permission error on every call). No external docs were merged into this summary; all content is sourced from the build plan itself (Part 9, lines 2674-3218). To unlock Context7 enrichment in a future pass, the user needs to grant the `mcp__context7__resolve-library-id` and `mcp__context7__query-docs` permissions.
