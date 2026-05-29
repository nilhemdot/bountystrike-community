# Alpha Testing Guide — BountyStrike v5

Welcome to the BountyStrike v5 Alpha! This guide will help you get started with testing the autonomous bug bounty platform powered by Claude Code. Your feedback during this phase is critical to shaping the product.

**Alpha Focus:** Core workflow validation — recon, exploit hypothesis, verification, and report generation. We're testing the autonomous agent coordination, scope enforcement, and approval workflows in real-world conditions.

**Timeline:** Alpha runs through 2026-06-30. Beta begins Q3 2026.

## What You're Testing

BountyStrike v5 is a Claude Code-native platform that autonomously:

1. **Recon** — discovers assets within scope-JWT boundaries
2. **Scan & Exploit** — generates vulnerability hypotheses and attempts exploitation
3. **Verify** — validates findings with deterministic oracles (XSS, SSRF, SQLi, RCE, etc.)
4. **Approve** — gates risky actions through T1/T2/T3 human approval tiers
5. **Report** — submits verified findings to HackerOne, Bugcrowd, Intigriti, YesWeHack

**Key Features:**
- 8 verification oracles (7 field-validated at TPR=1.0/FPR=0.0)
- Scope-JWT enforced at network layer
- Hash-chained tamper-evident evidence
- 3-layer kill switch (Redis flag → PreToolUse hook → process supervisor)
- Tiered human approval before platform submission

## Prerequisites

| Requirement | Min Version | Notes |
|---|---|---|
| Python | 3.12+ | Required for control-plane and MCP servers |
| `uv` | 0.4+ | Workspace sync and dependency management |
| Docker + Compose | 24+ | Brings up Postgres, Redis, Hatchet, Langfuse, Caddy |
| `openssl` | any modern | For RS256 scope-JWT keypair generation |
| Disk space | 10 GB+ | Postgres + Redis + evidence storage |
| RAM | 8 GB+ | Recommended for smooth operation |

**API Keys (obtain before starting):**
- **Anthropic API key** (required) — powers Claude agents
- **HackerOne / Bugcrowd / Intigriti / YesWeHack credentials** (optional) — for live report submission testing

**Supported Platforms:**
- Linux (Ubuntu 22.04+, Debian 12+)
- macOS 13+ (Intel or Apple Silicon)
- Windows 10/11 with WSL2

## Installation

### 1. Clone the Repository

```bash
git clone <provided-alpha-repo-url> bountystrike-v5-alpha
cd bountystrike-v5-alpha
```

You will receive a private repository link via email with your alpha invitation.

### 2. Install Dependencies

```bash
# Install uv if you don't have it
curl -LsSf https://astral.sh/uv/install.sh | sh

# Sync workspace (installs control-plane + 5 registered MCPs)
uv sync --all-packages
```

**Note:** `uv sync --all-packages` installs all workspace members. The base `uv sync` only installs the control-plane. Some unregistered MCPs require manual `cd <mcp-dir> && uv sync` until registration completes (tracked in Phase 2).

### 3. Generate Scope-JWT Keypair

```bash
python scripts/gen_scope_jwt.py keygen --out keys/
```

This creates:
- `keys/scope_jwt_private.pem` (gitignored, 4096-bit RSA)
- `keys/scope_jwt_public.pem` (checked into version control)

The private key signs scope JWTs; the public key validates them in MCPs. **Keep the private key secure** — it's your authorization boundary.

### 4. Configure Environment

```bash
cp .env.example .env
```

Open `.env` and fill in the required values:

```bash
# Required
POSTGRES_PASSWORD=<strong-password>
REDIS_PASSWORD=<strong-password>
HATCHET_COOKIE_SECRET=<random-32-char-string>
LANGFUSE_SECRET=<random-string>
LANGFUSE_SALT=<random-string>
ANTHROPIC_API_KEY=<your-anthropic-key>

# Optional (for live platform testing)
HACKERONE_API_TOKEN=<your-h1-token>
BUGCROWD_API_KEY=<your-bugcrowd-key>
INTIGRITI_API_TOKEN=<your-intigriti-token>
YESWEHACK_API_KEY=<your-ywh-key>

# Evidence storage (default: local filesystem)
EVIDENCE_BACKEND=local
EVIDENCE_ROOT=./evidence

# Optional: Cloudflare R2 for production-like testing
# EVIDENCE_BACKEND=r2
# R2_BUCKET=...
# R2_ACCOUNT_ID=...
# R2_ACCESS_KEY_ID=...
# R2_SECRET_ACCESS_KEY=...
```

See [`configuration-guide.md`](configuration-guide.md) for the full reference.

### 5. Start Services

```bash
docker compose -f infra/docker/docker-compose.yml --env-file .env up -d
```

This brings up:
- **Postgres 17** (with pgvector, pg_trgm, pgcrypto)
- **Redis 7** (AOF persistence for kill switch state)
- **Hatchet** (workflow orchestration)
- **Langfuse** (LLM observability — token counts, traces, costs)
- **Caddy** (reverse proxy, TLS termination)

Verify all services are healthy:

```bash
docker compose -f infra/docker/docker-compose.yml ps
# All should show "healthy" status
```

Schema migrations from `infra/sql/*.sql` auto-apply on first boot.

## First-Time Setup with `bs init`

**Note:** The `bs init` CLI wizard is the new onboarding experience being introduced in this alpha. It simplifies the manual steps above.

### Using `bs init` (Recommended)

```bash
# Interactive setup wizard
uv run bs init
```

The wizard will:
1. Check prerequisites (Python, Docker, uv, openssl)
2. Generate scope-JWT keypair if missing
3. Guide you through `.env` configuration
4. Start Docker services
5. Validate database connectivity
6. Issue your first scope JWT
7. Run a health check scan

**Wizard prompts:**
- **Operator ID:** Your identifier (e.g., `alice`, `bob@example.com`)
- **API Keys:** Anthropic API key (required), platform credentials (optional)
- **Target Program:** HackerOne handle or Bugcrowd slug for your first test
- **Scope Targets:** Wildcards (e.g., `*.example.com`), exact hosts, IPs

The wizard validates each step and provides troubleshooting guidance if checks fail.

### Manual Setup (Fallback)

If `bs init` fails or you prefer manual control, follow the Installation section above step-by-step.

## Your First Scan

Once setup completes, run your first scan:

```bash
# Issue a scope JWT for a specific program
python scripts/gen_scope_jwt.py issue \
  --operator-id <your-id> \
  --program-handle <program-name> \
  --platform hackerone \
  --targets 'wildcard=*.example.com' \
  --out scope.jwt

# Run the orchestrator
SCOPE_JWT=$(cat scope.jwt) \
PROGRAM_HANDLE=<program-name> \
PLATFORM=hackerone \
DATABASE_URL=postgresql://bs:$POSTGRES_PASSWORD@localhost:5432/bountystrike \
python scripts/orchestrator.py
```

The orchestrator runs through phases:
1. **Recon** — subdomain enumeration, port scanning, service detection
2. **Scanner** (optional, skip with `SKIP_SCANNER=1`) — active scanning
3. **Exploit** — hypothesis generation and exploitation attempts
4. **Validator** — deterministic oracle verification
5. **Reporter** — approval queue and platform submission

## Approval Workflow

When the orchestrator reaches T2 or T3 approval gates, it pauses and waits for operator action.

```bash
# List pending approvals
python scripts/approve.py list

# View details of a specific request
python scripts/approve.py show <request_id>

# Approve a request
python scripts/approve.py approve <request_id> --reason "Verified scope and impact"

# Reject a request
python scripts/approve.py reject <request_id> --reason "Out of scope — subdomain not in JWT"
```

**T3 (report submission) requires two distinct approvers.** The first approval returns `None` (pending); the second returns the `APPROVAL_TOKEN`.

## Observability

Monitor your scans:

- **Langfuse UI:** `http://localhost:3000` — LLM traces, token counts, costs per agent session
- **Postgres logs:** `docker logs bountystrike_postgres` — query performance, migrations
- **Redis status:** `docker exec -it bountystrike_redis redis-cli -a $REDIS_PASSWORD PING`
- **Audit log:** Query `audit_log` table in Postgres — hash-chained tamper-evident record

## What to Test

### Priority 1 — Core Workflow
- [ ] Run `bs init` on a fresh install — does the wizard complete successfully?
- [ ] Issue a scope JWT for a real bug bounty program (or test target)
- [ ] Run a full scan with `orchestrator.py`
- [ ] Approve/reject requests via `approve.py`
- [ ] Verify findings in Langfuse — are traces complete? Are token counts reasonable?

### Priority 2 — Edge Cases
- [ ] Test scope enforcement — try a target outside JWT claims (should be blocked)
- [ ] Trigger the kill switch — `redis-cli SET bountystrike:killswitch:global 1`
- [ ] Test with multiple programs concurrently
- [ ] Test approval workflow with invalid JWT (expired, wrong signature)

### Priority 3 — Integrations
- [ ] Submit a verified finding to HackerOne (use a test program)
- [ ] Test R2 evidence backend (if you have Cloudflare R2 access)
- [ ] Run field-validation harnesses:
  ```bash
  uv run python scripts/run_xss_field_validation.py
  uv run python scripts/run_ssrf_field_validation.py
  uv run python scripts/run_idor_field_validation.py
  ```

### Known Issues (Alpha)
- **SQLi oracle not yet field-validated** — timing analysis can have false positives on high-latency targets
- **9 MCPs not registered** — require manual `uv sync` per directory (h1, bugcrowd, intigriti, yeswehack, immunefi, state, sandbox, normalize, politeness)
- **T3 approval UI pending** — CLI-only for now, web UI coming in Beta
- **No multi-tenancy** — solo mode only, SaaS deployment in Phase 4

## Troubleshooting

### Services won't start
```bash
# Check logs
docker compose -f infra/docker/docker-compose.yml logs

# Reset volumes (destroys data)
docker compose -f infra/docker/docker-compose.yml down -v
docker compose -f infra/docker/docker-compose.yml up -d
```

### `bs init` fails at prerequisite check
- Ensure Docker is running: `docker ps`
- Verify uv version: `uv --version` (must be 0.4+)
- Check Python: `python --version` (must be 3.12+)

### JWT validation errors
- Check expiration: JWTs have max 168h (7 day) lifetime
- Verify keypair: `ls -la keys/` should show both `.pem` files
- Regenerate if needed: `python scripts/gen_scope_jwt.py keygen --out keys/`

### Orchestrator hangs at approval gate
- Check approval queue: `python scripts/approve.py list`
- Ensure `DATABASE_URL` is set correctly
- Verify Postgres is reachable: `psql $DATABASE_URL -c "SELECT 1"`

## Feedback Channels

We need your input! Please report:

- **Bugs / Crashes:** File issues in the alpha repo (GitHub Issues)
- **UX Friction:** Where did you get stuck? What was confusing?
- **Performance:** Scan times, memory usage, API costs
- **Feature Requests:** What's missing for your workflow?

### How to Submit Feedback

**1. GitHub Discussions** (preferred for feedback, questions, and suggestions)
- → **https://github.com/bountystrike/bountystrike-v5/discussions**
- Use the "Alpha Feedback" category for testing observations
- Use "Q&A" for setup help and how-to questions
- Use "Ideas" for feature requests and workflow improvements
- The team monitors discussions daily during the alpha period

**2. GitHub Issues** (for reproducible bugs only)
- Go to `<repo-url>/issues`
- Use the "Alpha Bug Report" template
- Tag with `alpha`, `bug`, and the component (`cli`, `orchestrator`, `mcp`, `docs`)
- Include: operator ID, timestamp, logs, and steps to reproduce

**3. Email** (for sensitive feedback or private programs)
- Send to: `alpha-feedback@bountystrike.example` (replace with actual)
- Include: operator ID, timestamp, logs (if applicable)

**4. Weekly Office Hours** (live Q&A)
- Thursdays 3-4 PM UTC via Zoom
- Link provided in alpha invitation email
- No recording — safe space for questions

**5. Slack Channel** (alpha cohort community)
- `#bountystrike-alpha` in the provided workspace
- Quick questions, tips, cohort coordination

### What We're Looking For

- **Critical:** Does `bs init` guide you successfully from zero to first scan?
- **High:** Are approval workflows intuitive? Do you trust the evidence chain?
- **Medium:** How's the performance? Are costs reasonable? (<$30/month target)
- **Nice-to-have:** Documentation clarity, error messages, CLI ergonomics

## Next Steps

After you've completed your first scan:

1. **Read the docs:**
   - [`deployment-guide.md`](deployment-guide.md) — full solo-mode deployment
   - [`configuration-guide.md`](configuration-guide.md) — all env vars
   - [`../system-architecture.md`](../system-architecture.md) — architecture diagrams
   - [`../code-standards.md`](../code-standards.md) — contributing guide (if you want to hack on it)

2. **Test edge cases:** See "What to Test" above.

3. **Share results:** Post findings in GitHub Issues or `#bountystrike-alpha`.

4. **Join office hours:** Meet the team, ask questions, see demos.

## Alpha Timeline

| Milestone | Date | Focus |
|---|---|---|
| Alpha kickoff | 2026-05-26 | Onboarding, `bs init` validation |
| Mid-alpha checkpoint | 2026-06-15 | Core workflow feedback, stability |
| Alpha closeout | 2026-06-30 | Final bugs, readiness for Beta |
| Beta begins | 2026-07-15 | Multi-tenant prep, SaaS architecture |

Thank you for being part of the BountyStrike v5 Alpha. Your testing helps us build a platform that scales autonomous security research without compromising safety or ethics.

**Ship it.** 🚀
