# First-Scan Walkthrough — BountyStrike v5

A step-by-step guide to running your first BountyStrike recon scan, from JWT generation through approval queue cleanup. Assumes you have completed the setup steps in the [Alpha Testing Guide](alpha-testing-guide.md) or run `bs init`.

**Estimated time:** 15-30 minutes for your first scan (excluding Docker image pull).

## Prerequisites Checklist

Before starting, verify each item:

- [ ] Docker containers running: `docker compose -f infra/docker/docker-compose.yml ps`
- [ ] `.env` configured with `DATABASE_URL`, `ANTHROPIC_API_KEY`, `SCOPE_JWT`
- [ ] Scope-JWT keypair exists: `keys/scope_jwt_private.pem` and `keys/scope_jwt_public.pem`
- [ ] Postgres reachable: `psql $DATABASE_URL -c "SELECT 1"`

If any check fails, see the [Alpha Testing Guide](alpha-testing-guide.md) §Installation or the [Troubleshooting Guide](troubleshooting-guide.md).

## Step 1 — Generate Your Scope JWT

The scope JWT is your authorization boundary. It tells BountyStrike which targets are in scope and which platform to submit findings to.

### 1a. Generate the Keypair (first time only)

```bash
python scripts/gen_scope_jwt.py keygen --out keys/
```

This creates:
- `keys/scope_jwt_private.pem` — your signing key (**never commit or share**)
- `keys/scope_jwt_public.pem` — the public key MCPs use to validate scope

Both paths are gitignored by default. If the files already exist, skip this step (or pass `--keygen` to force-regenerate).

### 1b. Issue a Scope JWT

```bash
python scripts/gen_scope_jwt.py issue \
  --operator-id <your-operator-id> \
  --program-handle <program-name> \
  --platform hackerone \
  --targets 'wildcard=*.example.com' \
  --out scope.jwt
```

**Parameters:**

| Flag | Description | Example |
|---|---|---|
| `--operator-id` | Your identifier | `alice`, `alice@example.com` |
| `--program-handle` | Platform program slug | `acme-corp` |
| `--platform` | Bug bounty platform | `hackerone`, `bugcrowd`, `intigriti`, `yeswehack` |
| `--targets` | Scope targets (repeatable) | `wildcard=*.example.com`, `host=app.example.com` |
| `--hours` | JWT expiry in hours (max 168) | `24` (default) |
| `--out` | Write JWT to file | `scope.jwt` |

You can pass multiple `--targets` flags:

```bash
python scripts/gen_scope_jwt.py issue \
  --operator-id alice \
  --program-handle acme-corp \
  --platform hackerone \
  --targets 'wildcard=*.acme.com' \
  --targets 'wildcard=*.api.acme.com' \
  --targets 'host=portal.acme.com' \
  --out scope.jwt
```

### 1c. Verify the JWT

Decode the JWT to confirm its claims:

```bash
# Decode without verification (just to inspect claims)
python -c "
import jwt, json
token = open('scope.jwt').read()
claims = jwt.decode(token, options={'verify_signature': False})
print(json.dumps(claims, indent=2))
"
```

Expected output includes:

```json
{
  "iss": "bountystrike-v5-control-plane",
  "sub": "alice",
  "aud": "bountystrike-v5-mcp",
  "scope": {
    "program": "acme-corp",
    "platform": "hackerone",
    "targets": [
      {"type": "wildcard", "value": "*.acme.com"}
    ]
  },
  "iat": 1716700000,
  "exp": 1716786400
}
```

### 1d. Load the JWT into Your Environment

```bash
export SCOPE_JWT=$(cat scope.jwt)
```

For persistence across sessions, add to `.env`:

```bash
SCOPE_JWT=<paste full JWT string here>
```

**Security note:** The JWT contains your scope boundary but is signed — it cannot be modified without the private key. It is safe to store in `.env` but should not be committed to version control.

## Step 2 — Run the Orchestrator

The orchestrator is the top-level pipeline controller. It runs recon, scanning, exploitation, validation, and reporting in sequence.

### 2a. Minimal Run (Recon Only)

For your first scan, start with recon only. This validates scope enforcement, asset discovery, and database writes without triggering exploit agents.

```bash
SCOPE_JWT=$(cat scope.jwt) \
PROGRAM_HANDLE=acme-corp \
PLATFORM=hackerone \
DATABASE_URL=postgresql://bs:$POSTGRES_PASSWORD@localhost:5432/bountystrike \
SKIP_SCANNER=1 \
SKIP_EXPLOIT=1 \
SKIP_REPORT=1 \
python scripts/orchestrator.py
```

**What this does:**
1. Creates a `scan_jobs` row in Postgres (status: `queued` → `running`)
2. Launches the recon-agent subprocess
3. Recon-agent discovers subdomains, ports, and services within JWT scope
4. Writes findings to the `findings` table
5. Orchestrator prints a summary and exits

**Expected output:**

```
[orchestrator] scan_id=<uuid> program=acme-corp platform=hackerone
[orchestrator] phase=recon status=running
[recon-agent] discovering assets for *.acme.com ...
[recon-agent] found 14 subdomains, 31 hosts, 87 services
[orchestrator] phase=recon status=complete findings=87
[orchestrator] summary: recon=87 scanner=0 exploit=0 validated=0 reported=0
```

### 2b. Full Pipeline Run

Once recon works, run the full pipeline:

```bash
SCOPE_JWT=$(cat scope.jwt) \
PROGRAM_HANDLE=acme-corp \
PLATFORM=hackerone \
DATABASE_URL=postgresql://bs:$POSTGRES_PASSWORD@localhost:5432/bountystrike \
python scripts/orchestrator.py
```

This runs all phases in order:

| Phase | What it does | Skippable? |
|---|---|---|
| **Recon** | Subdomain enumeration, port scan, service detection | No |
| **Scanner** | Active vulnerability scanning (Nuclei templates) | `SKIP_SCANNER=1` |
| **Exploit** | Hypothesis generation + exploitation attempts | `SKIP_EXPLOIT=1` |
| **Validator** | Deterministic oracle verification (XSS, SSRF, SQLi, etc.) | No |
| **Reporter** | Approval queue + platform submission | `SKIP_REPORT=1` |

### 2c. Useful Environment Variables

| Variable | Default | Purpose |
|---|---|---|
| `SKIP_SCANNER` | unset | Set to `1` to skip scanner phase |
| `SKIP_EXPLOIT` | unset | Set to `1` to skip exploit phase |
| `SKIP_REPORT` | unset | Set to `1` to skip reporter phase |
| `SKIP_IDOR` | unset | Set to `1` to drop IDOR-candidate findings post-recon |
| `MAX_EXPLOITS` | `3` | Parallel exploit-agent limit |
| `MAX_VALIDATORS` | `5` | Parallel validator-agent limit |
| `RECON_TIMEOUT` | `3600` | Max seconds for recon phase |
| `SCAN_TIMEOUT` | `7200` | Max seconds for scanner phase |
| `APPROVAL_TIMEOUT` | `86400` | Max seconds to wait for T2 approval |

## Step 3 — Interpret the Results

### 3a. Check the Scan Status

```bash
# View the latest scan job
psql $DATABASE_URL -c "
  SELECT id, program_handle, platform, status, started_at, completed_at
  FROM scan_jobs
  ORDER BY created_at DESC
  LIMIT 1;
"
```

Status values: `queued` → `running` → `completed` | `failed` | `paused_approval`

### 3b. View Findings

```bash
# Summary by severity/status
psql $DATABASE_URL -c "
  SELECT status, severity, COUNT(*)
  FROM findings
  GROUP BY status, severity
  ORDER BY severity, status;
"

# Detailed view of validated findings
psql $DATABASE_URL -c "
  SELECT id, title, severity, vuln_type, status, created_at
  FROM findings
  WHERE status = 'validated'
  ORDER BY severity ASC, created_at DESC;
"
```

**Finding statuses:**

| Status | Meaning |
|---|---|
| `pending` | Discovered by recon/scanner, not yet processed |
| `exploit_pending` | Queued for exploit-agent |
| `exploit_running` | Exploit-agent actively testing |
| `validated` | Oracle confirmed the vulnerability |
| `unreproducible` | Oracle could not confirm |
| `approval_pending_t2` | Awaiting T2 human approval (exploit action) |
| `approval_pending_t3` | Awaiting T3 human approval (report submission) |
| `reported` | Submitted to platform |
| `rejected` | Rejected by human approver |

### 3c. View Evidence

Each validated finding has an evidence chain stored in the `evidence_artifacts` table:

```bash
# List evidence for a finding
psql $DATABASE_URL -c "
  SELECT id, artifact_type, hash_chain, created_at
  FROM evidence_artifacts
  WHERE finding_id = '<finding-uuid>'
  ORDER BY created_at;
"
```

Evidence types: `http_request`, `http_response`, `screenshot`, `console_output`, `oracle_verification`.

### 3d. Monitor in Langfuse

Open `http://localhost:3000` to see:

- **Traces** — full agent execution traces per phase
- **Token counts** — LLM usage per agent (cost tracking)
- **Latency** — time spent per agent invocation
- **Scores** — oracle confidence scores on validated findings

Filter by `scan_id` to isolate a single run.

## Step 4 — Approval Queue Usage

When the orchestrator reaches T2 (exploit action) or T3 (report submission) gates, it pauses and waits for human approval. The approval queue is the mechanism for this.

### 4a. List Pending Approvals

```bash
# All pending requests
DATABASE_URL=postgresql://bs:$POSTGRES_PASSWORD@localhost:5432/bountystrike \
  python scripts/approve.py list

# Filter by tier
DATABASE_URL=postgresql://bs:$POSTGRES_PASSWORD@localhost:5432/bountystrike \
  python scripts/approve.py list --tier T3
```

**Example output:**

```
finding_id                             tier age    expires_in   actor
--------------------------------------------------------------------------------
a1b2c3d4-...-f5e6                      T3   2m     86398s
b2c3d4e5-...-a1b2                      T2   5m     86395s
```

### 4b. Inspect a Request

```bash
DATABASE_URL=postgresql://bs:$POSTGRES_PASSWORD@localhost:5432/bountystrike \
  python scripts/approve.py show <finding_id>
```

This prints a JSON object with the finding ID, tier, status, PoC text, approval timestamps, and the `token` field (populated only after final approval).

**Example output:**

```json
{
  "finding_id": "a1b2c3d4-...",
  "tier": "T3",
  "status": "pending",
  "token": null,
  "requested_at": "2026-05-26T18:30:00+00:00",
  "approved_at": null,
  "expires_at": "2026-05-27T18:30:00+00:00",
  "approver_id": null,
  "approver_id_2": null,
  "reason": null,
  "poc_text": "GET /redirect?url=http://evil.example HTTP/1.1\nHost: app.acme.com\n\nHTTP/1.1 302 Location: http://evil.example\n\nImpact: Open redirect allows phishing via trusted domain."
}
```

### 4c. Approve a Request

```bash
# T2 approval (single approver)
DATABASE_URL=postgresql://bs:$POSTGRES_PASSWORD@localhost:5432/bountystrike \
  python scripts/approve.py approve <finding_id> \
    --as <your-operator-id> \
    --reason "Confirmed scope and impact"

# T3 approval — first of two approvers
DATABASE_URL=postgresql://bs:$POSTGRES_PASSWORD@localhost:5432/bountystrike \
  python scripts/approve.py approve <finding_id> \
    --as operator-alice \
    --reason "Verified PoC, ready for submission"
# Output: OK (1/2): first approver recorded for T3 finding <id>

# T3 approval — second approver (completes approval)
DATABASE_URL=postgresql://bs:$POSTGRES_PASSWORD@localhost:5432/bountystrike \
  python scripts/approve.py approve <finding_id> \
    --as operator-bob \
    --reason "Reviewed and confirmed"
# Output: APPROVED finding=<id> token=<approval-token-uuid>
```

**T3 requires two distinct approvers.** The first call records the approver but returns `None` (pending). The second call from a different operator returns the `APPROVAL_TOKEN`, which the orchestrator uses to proceed with platform submission.

### 4d. Reject a Request

```bash
DATABASE_URL=postgresql://bs:$POSTGRES_PASSWORD@localhost:5432/bountystrike \
  python scripts/approve.py reject <finding_id> \
    --as <your-operator-id> \
    --reason "Out of scope — subdomain not covered by JWT claims"
```

Rejected findings are marked `rejected` in the database and will not be submitted to any platform.

### 4e. Resume the Orchestrator

After approval, the orchestrator (which is polling the approval queue) automatically resumes:

```
[orchestrator] approval received for finding=<id> tier=T3 token=<token>
[orchestrator] phase=reporter status=running
[reporter-agent] submitting finding a1b2c3d4-... to hackerone/acme-corp
[orchestrator] phase=reporter status=complete
```

If the orchestrator was not running (e.g., you approved after it exited), re-run it — it will pick up where it left off by scanning for `approval_pending_*` rows.

## Step 5 — Verify the Submission

### 5a. Check the Database

```bash
psql $DATABASE_URL -c "
  SELECT id, title, status, platform_submission_id, reported_at
  FROM findings
  WHERE status = 'reported'
  ORDER BY reported_at DESC;
"
```

### 5b. Check the Platform

Log in to your bug bounty platform (HackerOne, Bugcrowd, etc.) and verify the report appears in the program's submission queue.

### 5c. Check the Audit Log

```bash
psql $DATABASE_URL -c "
  SELECT action, actor, details, created_at
  FROM audit_log
  WHERE finding_id = '<finding-uuid>'
  ORDER BY created_at;
"
```

The audit log is hash-chained and tamper-evident — every action from scan initiation through platform submission is recorded.

## Common First-Scan Issues

| Symptom | Cause | Fix |
|---|---|---|
| `SCOPE_JWT is not set` | JWT not exported | `export SCOPE_JWT=$(cat scope.jwt)` |
| `DATABASE_URL is not set` | Env var missing | Add to `.env` or export inline |
| Recon finds 0 assets | Scope too narrow or DNS failure | Check wildcard in JWT matches target; verify DNS resolution |
| Orchestrator hangs at approval gate | No approver action | Run `approve.py approve` in another terminal |
| `keys/scope_jwt_private.pem not found` | Keypair not generated | Run `gen_scope_jwt.py keygen --out keys/` |
| JWT expired | Default 24h expiry passed | Re-issue with `gen_scope_jwt.py issue` |
| `connection refused` on Postgres | Docker container not running | `docker compose -f infra/docker/docker-compose.yml up -d postgres` |

## Next Steps

After completing your first scan:

1. **Read the docs:**
   - [`alpha-testing-guide.md`](alpha-testing-guide.md) — full alpha testing guide
   - [`configuration-guide.md`](configuration-guide.md) — all environment variables
   - [`testing-guide.md`](testing-guide.md) — running tests and validation harnesses

2. **Try edge cases:**
   - Test scope enforcement with a target outside JWT claims
   - Trigger the kill switch: `docker exec -it bountystrike_redis redis-cli -a $REDIS_PASSWORD SET bountystrike:killswitch:global 1`
   - Run with `SKIP_SCANNER=1` to isolate recon-only behavior

3. **Share feedback:** File issues in the alpha repo or post in `#bountystrike-alpha`.

**Ship it.** 🚀
