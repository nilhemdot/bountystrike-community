# Troubleshooting Guide — BountyStrike v5

Common issues, their root causes, and step-by-step fixes. Scan the **Symptom** column for your error, then follow the fix. If your issue isn't listed, check [GitHub Issues](../..) or ask in `#bountystrike-alpha`.

**How to read this guide.**
- Every section is ordered from most to least frequent.
- Each entry follows the pattern: **Symptom** → **Cause** → **Fix** → **Verify**.
- Commands assume you are at the repo root with `.env` loaded.

## Environment Variables

### `ERROR: POSTGRES_PASSWORD must be set in .env`

**Symptom.** Docker compose refuses to start:

```
error while interpolating services.postgres.environment.POSTGRES_PASSWORD:
required variable POSTGRES_PASSWORD is missing a value
```

**Cause.** `.env` is missing, or the variable is commented out / has no value.

**Fix.**

```bash
# Check if .env exists
ls -la .env

# If missing, copy the template
cp .env.example .env

# Edit and fill the required values
# At minimum: POSTGRES_PASSWORD, REDIS_PASSWORD, HATCHET_COOKIE_SECRET,
#   LANGFUSE_SECRET, LANGFUSE_SALT
```

Generate all five secrets at once:

```bash
for v in POSTGRES_PASSWORD REDIS_PASSWORD HATCHET_COOKIE_SECRET LANGFUSE_SECRET LANGFUSE_SALT; do
  printf '%s=%s\n' "$v" "$(openssl rand -hex 32)"
done >> .env
```

**Verify.**

```bash
docker compose -f infra/docker/docker-compose.yml --env-file .env config
# Should print the resolved config without errors.
```

---

### `[orchestrator] ERROR: PROGRAM_HANDLE is not set`

**Symptom.** Orchestrator exits immediately on startup.

**Cause.** `PROGRAM_HANDLE` is not exported in the shell or present in `.env`.

**Fix.**

```bash
# Option A: export inline
export PROGRAM_HANDLE=acme-corp

# Option B: add to .env (persists across sessions)
echo 'PROGRAM_HANDLE=acme-corp' >> .env
```

**Verify.**

```bash
echo $PROGRAM_HANDLE
# Should print the program handle.
```

---

### `[orchestrator] ERROR: SCOPE_JWT is not set`

**Symptom.** Orchestrator exits before the recon phase.

**Cause.** The scope JWT has not been generated or exported.

**Fix.**

```bash
# Generate the keypair (first time only)
python scripts/gen_scope_jwt.py keygen --out keys/

# Issue a JWT
python scripts/gen_scope_jwt.py issue \
  --operator-id <your-id> \
  --program-handle <program-name> \
  --platform hackerone \
  --targets 'wildcard=*.example.com' \
  --out scope.jwt

# Export it
export SCOPE_JWT=$(cat scope.jwt)
```

**Verify.**

```bash
python -c "
import jwt, json
token = open('scope.jwt').read()
claims = jwt.decode(token, options={'verify_signature': False})
print(json.dumps(claims['scope'], indent=2))
"
# Should print the program, platform, and targets.
```

---

### `ANTHROPIC_API_KEY` not recognized

**Symptom.** LLM calls fail with `401 Unauthorized` or `AuthenticationError`.

**Cause.** The key is missing from `.env`, expired, or has insufficient credits.

**Fix.**

```bash
# Check if the key is set
grep ANTHROPIC_API_KEY .env

# If missing or wrong, add the correct key:
# ANTHROPIC_API_KEY=sk-ant-...
```

Verify the key works:

```bash
curl -s https://api.anthropic.com/v1/messages \
  -H "x-api-key: $ANTHROPIC_API_KEY" \
  -H "anthropic-version: 2023-06-01" \
  -H "content-type: application/json" \
  -d '{"model":"claude-sonnet-4-20250514","max_tokens":16,"messages":[{"role":"user","content":"ping"}]}' \
  | python -c "import sys,json; d=json.load(sys.stdin); print(d.get('error','OK'))"
# Should print nothing or a valid response (not an auth error).
```

---

### Platform API key errors (HackerOne, Bugcrowd, etc.)

**Symptom.** Report submission fails with `401` or `403`.

**Cause.** The platform credential is missing, expired, or lacks submission scope.

**Fix.** Check the relevant variable in `.env`:

| Platform | Variable | Format |
|---|---|---|
| HackerOne | `H1_API_TOKEN` + `H1_USERNAME` | JSON:API token + username (HTTP Basic) |
| Bugcrowd | `BUGCROWD_SESSION_COOKIE` | Session cookie from browser |
| Intigriti | `INTIGRITI_PAT` | Personal access token |
| YesWeHack | `YESWEHACK_BEARER` | Bearer token |

**Verify.** Test the credential outside BountyStrike:

```bash
# HackerOne example
curl -s -u "$H1_USERNAME:$H1_API_TOKEN" \
  "https://api.hackerone.com/v1/me/programs" | python -m json.tool | head
```

---

## Database Connection

### `connection refused` on `localhost:5432`

**Symptom.** Orchestrator or `psql` cannot connect to Postgres.

**Cause.** The `postgres` container is not running, or the port is occupied.

**Fix.**

```bash
# Check container status
docker compose -f infra/docker/docker-compose.yml ps postgres

# If not running, start it
docker compose -f infra/docker/docker-compose.yml up -d postgres

# Wait for healthy status (up to 60s)
docker compose -f infra/docker/docker-compose.yml ps postgres
# Should show "healthy"
```

If the port is occupied by a local Postgres:

```bash
# Check what's using 5432
# Linux:
ss -tlnp | grep 5432
# macOS:
lsof -i :5432

# Option A: stop the local Postgres
sudo systemctl stop postgresql

# Option B: change the docker-compose port mapping
# Edit infra/docker/docker-compose.yml:
#   ports: ["127.0.0.1:5433:5432"]
# Then update DATABASE_URL accordingly.
```

**Verify.**

```bash
psql "postgresql://bs:${POSTGRES_PASSWORD}@localhost:5432/bountystrike" -c "SELECT 1"
# Should print ?column? | 1
```

---

### `DATABASE_URL` format errors

**Symptom.** `InvalidURL` or `password authentication failed for user "bs"`.

**Cause.** The connection string is malformed or the password contains special characters that aren't URL-encoded.

**Fix.** The expected format is:

```
postgresql+asyncpg://bs:<POSTGRES_PASSWORD>@localhost:5432/bountystrike
```

If the password contains `@`, `#`, `/`, or other special characters, URL-encode them:

```python
# Quick check
import urllib.parse
password = "p@ss/w#rd"
encoded = urllib.parse.quote(password)
print(f"postgresql+asyncpg://bs:{encoded}@localhost:5432/bountystrike")
```

**Verify.**

```bash
# Test with psql (uses the non-asyncpg dialect)
psql "postgresql://bs:${POSTGRES_PASSWORD}@localhost:5432/bountystrike" -c "\dt"
# Should list 13 tables.
```

---

### `relation "scan_jobs" does not exist`

**Symptom.** Orchestrator or `cost_audit.py` fails with a missing table error.

**Cause.** SQL migrations in `infra/sql/*.sql` have not been applied. This happens on first boot or after `docker volume rm`.

**Fix.**

```bash
# Check if tables exist
psql "$DATABASE_URL" -c "\dt"

# If empty, the init scripts should run on next container start.
# Force re-initialization:
docker compose -f infra/docker/docker-compose.yml down -v postgres
docker compose -f infra/docker/docker-compose.yml up -d postgres

# Watch the logs for migration output
docker logs bs-postgres 2>&1 | grep -i "init\|create\|migration"
```

**Verify.**

```bash
psql "$DATABASE_URL" -c "\dt"
# Should list 13 tables including scan_jobs, findings, audit_log.
```

---

### `pgvector` extension missing

**Symptom.** `ERROR: extension "pgvector" does not exist`.

**Cause.** The `pgvector/pgvector:pg17` image was not used, or the extension wasn't created.

**Fix.**

```bash
# Verify the correct image is running
docker inspect bs-postgres --format='{{.Config.Image}}'
# Should print: pgvector/pgvector:pg17

# If wrong image, fix in docker-compose.yml and recreate:
docker compose -f infra/docker/docker-compose.yml down -v postgres
docker compose -f infra/docker/docker-compose.yml up -d postgres
```

**Verify.**

```bash
psql "$DATABASE_URL" -c "\dx"
# Should list pgvector among the installed extensions.
```

---

## JWT Errors

### `ExpiredSignatureError` / JWT expired

**Symptom.** Scope validation fails with "Signature has expired".

**Cause.** The JWT's `exp` claim has passed. Default expiry is 24 hours; maximum is 168 hours (7 days).

**Fix.** Re-issue the JWT:

```bash
python scripts/gen_scope_jwt.py issue \
  --operator-id <your-id> \
  --program-handle <program-name> \
  --platform hackerone \
  --targets 'wildcard=*.example.com' \
  --hours 168 \
  --out scope.jwt

export SCOPE_JWT=$(cat scope.jwt)
```

**Verify.**

```bash
python -c "
import jwt, json
from datetime import datetime, UTC
token = open('scope.jwt').read()
claims = jwt.decode(token, options={'verify_signature': False})
exp = datetime.fromtimestamp(claims['exp'], UTC)
print(f'expires: {exp.isoformat()}')
print(f'remaining: {exp - datetime.now(UTC)}')
"
```

---

### `InvalidSignatureError` / wrong key

**Symptom.** `jwt.exceptions.InvalidSignatureError: Signature verification failed`.

**Cause.** The JWT was signed with a different private key than the public key MCPs are using. This happens after regenerating the keypair without re-issuing the JWT.

**Fix.**

```bash
# Regenerate keys (if needed)
python scripts/gen_scope_jwt.py keygen --out keys/

# Re-issue the JWT with the new key
python scripts/gen_scope_jwt.py issue \
  --operator-id <your-id> \
  --program-handle <program-name> \
  --platform hackerone \
  --targets 'wildcard=*.example.com' \
  --out scope.jwt

export SCOPE_JWT=$(cat scope.jwt)
```

**Verify.**

```bash
# Decode and check the issuer
python -c "
import jwt, json
token = open('scope.jwt').read()
claims = jwt.decode(token, options={'verify_signature': False})
print(f'iss: {claims[\"iss\"]}')
print(f'sub: {claims[\"sub\"]}')
print(f'program: {claims[\"program_handle\"]}')
"
```

---

### `keys/scope_jwt_private.pem not found`

**Symptom.** `gen_scope_jwt.py` or scope-mcp cannot find the private key.

**Cause.** The keypair has not been generated, or the `keys/` directory is missing.

**Fix.**

```bash
# Generate the keypair
python scripts/gen_scope_jwt.py keygen --out keys/

# Verify both files exist
ls -la keys/scope_jwt_private.pem keys/scope_jwt_public.pem
```

**Verify.**

```bash
# Check the key is valid RSA
openssl rsa -in keys/scope_jwt_private.pem -check -noout
# Should print: RSA key ok
```

---

### JWT scope validation fails (target out of scope)

**Symptom.** Recon agent reports "target out of scope" for a host you expected to be in scope.

**Cause.** The target doesn't match any wildcard or exact host in the JWT's `targets` claim.

**Fix.** Decode the JWT and verify the targets:

```bash
python -c "
import jwt, json
token = open('scope.jwt').read()
claims = jwt.decode(token, options={'verify_signature': False})
print(json.dumps(claims['targets'], indent=2))
"
```

Re-issue with the correct targets:

```bash
python scripts/gen_scope_jwt.py issue \
  --operator-id <your-id> \
  --program-handle <program-name> \
  --platform hackerone \
  --targets 'wildcard=*.example.com' \
  --targets 'host=specific.example.com' \
  --out scope.jwt
```

---

## Docker Problems

### Port conflicts (5432, 6379, 3000, 7070, 8080)

**Symptom.** `Bind for 0.0.0.0:5432 failed: port is already allocated`.

**Cause.** Another process or Docker container is using the same port.

**Fix.**

```bash
# Find the conflicting process
docker ps --format "table {{.Names}}\t{{.Ports}}" | grep -E "5432|6379|3000"

# Option A: stop the conflicting container
docker stop <conflicting-container>

# Option B: remap the port in docker-compose.yml
# Change: ports: ["127.0.0.1:5432:5432"]
# To:     ports: ["127.0.0.1:5433:5432"]
# Then update DATABASE_URL to use port 5433.
```

**Verify.**

```bash
docker compose -f infra/docker/docker-compose.yml ps
# All containers should be running.
```

---

### Containers unhealthy after startup

**Symptom.** `docker compose ps` shows `unhealthy` for one or more services.

**Cause.** Usually a dependency issue (e.g., Hatchet waiting for Postgres) or a resource constraint.

**Fix.**

```bash
# Check logs for the unhealthy service
docker logs bs-postgres
docker logs bs-redis
docker logs bs-hatchet
docker logs bs-langfuse

# Common fix: restart the stack
docker compose -f infra/docker/docker-compose.yml restart

# If persistent, recreate:
docker compose -f infra/docker/docker-compose.yml down
docker compose -f infra/docker/docker-compose.yml up -d
```

**Verify.**

```bash
docker compose -f infra/docker/docker-compose.yml ps
# All should show "healthy" within 60 seconds.
```

---

### `docker compose` not found

**Symptom.** `docker: 'compose' is not a docker command`.

**Cause.** Docker Compose V2 plugin is not installed, or you're using an old Docker version.

**Fix.**

```bash
# Check Docker version
docker --version
# Need 24+

# On Linux, install the plugin:
sudo apt-get install docker-compose-plugin

# Or use the standalone (legacy):
docker-compose -f infra/docker/docker-compose.yml up -d
```

---

### Volume data corruption after crash

**Symptom.** Postgres fails to start with `database system was not properly shut down`.

**Cause.** The container was killed without a graceful shutdown.

**Fix.**

```bash
# Postgres should auto-recover on restart. If it doesn't:
docker compose -f infra/docker/docker-compose.yml down
docker compose -f infra/docker/docker-compose.yml up -d postgres

# If still failing, reset the volume (DESTROYS DATA):
docker compose -f infra/docker/docker-compose.yml down -v postgres
docker compose -f infra/docker/docker-compose.yml up -d postgres
```

**Verify.**

```bash
docker logs bs-postgres 2>&1 | tail -5
# Should show "database system is ready to accept connections".
```

---

### Disk space exhaustion

**Symptom.** Containers fail to start, or evidence writes fail with `No space left on device`.

**Cause.** Docker volumes, evidence blobs, or logs have consumed available disk.

**Fix.**

```bash
# Check Docker disk usage
docker system df

# Prune unused images and volumes
docker system prune -a --volumes

# Check evidence directory size
du -sh evidence/

# Rotate Docker logs (already capped at 10MB × 3 files per container
# via the logging config in docker-compose.yml, but verify):
docker inspect bs-postgres --format='{{.HostConfig.LogConfig}}'
```

---

## Orchestrator & Pipeline

### Orchestrator hangs at approval gate

**Symptom.** Orchestrator output pauses at `phase=reporter status=paused_approval` and never resumes.

**Cause.** The orchestrator is waiting for T2 or T3 human approval that hasn't been given.

**Fix.**

```bash
# In another terminal, list pending approvals
DATABASE_URL=postgresql://bs:$POSTGRES_PASSWORD@localhost:5432/bountystrike \
  python scripts/approve.py list

# Approve a request
DATABASE_URL=postgresql://bs:$POSTGRES_PASSWORD@localhost:5432/bountystrike \
  python scripts/approve.py approve <finding_id> \
    --as <your-operator-id> \
    --reason "Verified scope and impact"
```

**Verify.** The orchestrator should resume within seconds of approval.

---

### Orchestrator exits with `SKIP_*` but still runs the phase

**Symptom.** Setting `SKIP_SCANNER=1` doesn't skip the scanner phase.

**Cause.** The variable is not exported, or the value is not `1`.

**Fix.**

```bash
# Verify the variable is set
echo $SKIP_SCANNER
# Should print: 1

# If not set, export it:
export SKIP_SCANNER=1
```

---

### Recon finds 0 assets

**Symptom.** `[recon-agent] found 0 subdomains, 0 hosts, 0 services`.

**Cause.** The JWT scope doesn't match any resolvable targets, or DNS resolution is failing.

**Fix.**

```bash
# Verify the JWT targets
python -c "
import jwt, json
token = open('scope.jwt').read()
claims = jwt.decode(token, options={'verify_signature': False})
print(json.dumps(claims['targets'], indent=2))
"

# Test DNS resolution of a target
nslookup app.example.com
dig app.example.com

# If DNS works but recon doesn't, check the wildcard format:
# Use: wildcard=*.example.com  (not: *.example.com without the key)
```

---

### `ModuleNotFoundError` when running scripts

**Symptom.** `ModuleNotFoundError: No module named 'asyncpg'` (or similar).

**Cause.** The workspace hasn't been synced, or the wrong Python is being used.

**Fix.**

```bash
# Sync the workspace
uv sync --all-packages

# Run scripts through uv
uv run python scripts/orchestrator.py

# Or activate the venv manually
source .venv/bin/activate  # Linux/macOS
# .venv\Scripts\activate   # Windows
```

---

## Cost Estimation

### Checking per-scan LLM costs

Use [`scripts/cost_audit.py`](../scripts/cost_audit.py) to audit spend against the Phase 3 target of **<$0.20 per scan**.

```bash
# Last 7 days (default)
DATABASE_URL=postgresql://bs:$POSTGRES_PASSWORD@localhost:5432/bountystrike \
  uv run python scripts/cost_audit.py

# Last 30 days
DATABASE_URL=postgresql://bs:$POSTGRES_PASSWORD@localhost:5432/bountystrike \
  uv run python scripts/cost_audit.py --since 30

# Single job with per-model breakdown
DATABASE_URL=postgresql://bs:$POSTGRES_PASSWORD@localhost:5432/bountystrike \
  uv run python scripts/cost_audit.py --job <scan_job_uuid>
```

**Example output:**

```
started_at             scan_job_id                            program              operator     cost    !  models
--------------------------------------------------------------------------------------------------------------
2026-05-26T18:30:00    a1b2c3d4-...-f5e6                       acme-corp            alice        $0.1423      3
2026-05-25T12:00:00    b2c3d4e5-...-a1b2                       acme-corp            alice        $0.2105  !   4
--------------------------------------------------------------------------------------------------------------
jobs=2  total=$0.3528  avg=$0.1764  budget=$0.20  breaches=1
```

- `!` marks scans that exceeded the $0.20 budget.
- `models` column shows the number of distinct LLM models used.

### Reducing costs

If scans consistently exceed budget:

1. **Lower `MAX_THINKING_TOKENS`** — caps extended-thinking budget (default 31999):
   ```bash
   echo 'MAX_THINKING_TOKENS=8000' >> .env
   ```

2. **Skip expensive phases** during development:
   ```bash
   SKIP_SCANNER=1 SKIP_EXPLOIT=1  # recon + validate only
   ```

3. **Reduce parallelism** — fewer concurrent agents means fewer concurrent LLM calls:
   ```bash
   MAX_VALIDATORS=2 MAX_EXPLOITS=1
   ```

4. **Check Langfuse** at `http://localhost:3000` for per-agent token usage. Look for agents with disproportionately high token counts.

### Estimating monthly solo-mode costs

The solo-mode target is **<$30/month**. Rough breakdown:

| Component | Estimated monthly cost |
|---|---|
| LLM calls (Anthropic) | $15–25 (at ~$0.20/scan, ~5 scans/week) |
| VPS / hosting | $5–10 (if self-hosting Docker) |
| Cloudflare R2 (optional) | <$1 (evidence storage, <5 GB) |
| **Total** | **$20–36** |

Run `cost_audit.py` weekly to track actual spend against this estimate.

---

## Kill Switch Won't Engage

**Symptom.** Setting the Redis kill flag doesn't stop the agents.

**Cause.** `KILL_SWITCH_BACKEND` is set to `memory` (test mode) instead of `redis`, or Redis is unreachable.

**Fix.**

```bash
# Check the backend
grep KILL_SWITCH_BACKEND .env
# Should be: KILL_SWITCH_BACKEND=redis

# Trip the switch
docker exec -it bs-redis redis-cli -a $REDIS_PASSWORD SET bountystrike:killswitch:global 1 EX 86400

# Verify the flag is set
docker exec -it bs-redis redis-cli -a $REDIS_PASSWORD GET bountystrike:killswitch:global
# Should print: 1
```

If Redis is unreachable, use Layer 3 (process supervisor):

```bash
# Stop all containers immediately
docker compose -f infra/docker/docker-compose.yml stop

# Or kill a specific agent process
pkill -f orchestrator
```

---

## Quick Diagnostics

Run this checklist when nothing else works:

```bash
# 1. All services healthy?
docker compose -f infra/docker/docker-compose.yml ps

# 2. .env loaded?
grep -E "^(POSTGRES_PASSWORD|REDIS_PASSWORD|ANTHROPIC_API_KEY|SCOPE_JWT|DATABASE_URL)=" .env

# 3. Database reachable?
psql "$DATABASE_URL" -c "SELECT 1"

# 4. Redis reachable?
docker exec -it bs-redis redis-cli -a $REDIS_PASSWORD PING

# 5. JWT valid?
python -c "
import jwt, json
from datetime import datetime, UTC
token = open('scope.jwt').read()
claims = jwt.decode(token, options={'verify_signature': False})
exp = datetime.fromtimestamp(claims['exp'], UTC)
assert exp > datetime.now(UTC), 'JWT EXPIRED'
print(f'OK — expires {exp.isoformat()}')
print(f'program: {claims[\"program_handle\"]}')
print(f'targets: {json.dumps(claims[\"targets\"], indent=2)}')
"

# 6. Langfuse accessible?
curl -s -o /dev/null -w "%{http_code}" http://localhost:3000
# Should print: 200
```

## See Also

- [`configuration-guide.md`](configuration-guide.md) — full env var reference
- [`deployment-guide.md`](deployment-guide.md) — solo-mode bring-up
- [`alpha-testing-guide.md`](alpha-testing-guide.md) — getting started
- [`first-scan-walkthrough.md`](first-scan-walkthrough.md) — step-by-step first scan
- [`testing-guide.md`](testing-guide.md) — running tests and validation harnesses
