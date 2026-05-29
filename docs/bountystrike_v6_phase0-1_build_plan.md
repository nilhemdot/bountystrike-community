# BountyStrike v6 — Phase 0 & Phase 1 Implementation-Ready Technical Brief

**Prepared for:** Evan Nil, DEVOPSEC lead, BountyStrike v6 (HexStrike-AI integrated)
**Date:** May 21, 2026
**Purpose:** Feed an atomized, dependency-ordered, machine-executable task graph for one-shot Claude Code autonomous execution from empty repo → AGPLv3 Community Edition release.

---

## TL;DR
- **HackerOne `structured_scopes` is NOT fully deprecated.** Per the official api.hackerone.com changelog (April 7, 2026): "Removed documentation of the obsolete endpoints to create, update and archive structured scopes on the program level. Assets are managed via the organization asset management endpoints." Only **program-level WRITE** is removed. The READ endpoint `GET /v1/hackers/programs/{handle}/structured_scopes` is still current (last revised 2026-01-16); a NEW `GET /v1/hackers/programs/{handle}/scope_exclusions` was added April 11, 2026.
- **DeepSeek pricing in the v6 plan's "Correction #1" is itself wrong.** Per api-docs.deepseek.com/quick_start/pricing (May 21, 2026): `deepseek-chat` and `deepseek-reasoner` are now aliases for `deepseek-v4-flash`, priced **$0.14 cache-miss input / $0.0028 cache-hit input / $0.28 output per 1M tokens** (cache-hit reduced to 1/10 of launch price on 2026-04-26, per the same page).
- **The full toolchain is verified and ready.** Critical TRAINING-DATA TRAPS to encode in CLAUDE.md: `claude-code-sdk → claude-agent-sdk` rename; Hatchet v1 SDK (1.33.5+) breaking API; bbscope v1→v2 subcommand restructure; boto3 1.36.0 R2 checksum incompatibility; LiteLLM 1.82.7/1.82.8 supply-chain incident on March 24, 2026 at 10:39 UTC (use v1.86.1 stable).

---

## TRACK A — Claude Code Autonomous Execution Conventions

### A.1 Subagent `.claude/agents/*.md` (current Claude Code v2.1.89+)

YAML frontmatter + Markdown body.

```markdown
---
name: recon-agent
description: "MUST BE USED for subdomain enumeration, port scanning, and asset discovery. Invokes subfinder/dnsx/httpx/naabu/katana via recon-mcp."
model: claude-haiku-4-5
tools: Read, Bash, Grep, Glob, mcp__recon__subfinder, mcp__recon__httpx
color: blue
---
You are a politeness-first recon subagent. Token-bucket rate limits are enforced by recon-mcp...
```

**Frontmatter fields (verified):** `name`, `description`, `model`, `tools` (comma-separated; markdown form does NOT use `allowed-tools`), `color` (blue/green/red/yellow/purple/orange/pink/cyan — undocumented but accepted), optional `skills` (list), `disable-model-invocation` (true → only via explicit `/agentname`).

**Identity:** comes ONLY from `name`. Subdirectory path doesn't affect identification. Duplicate names within one scope = one silently dropped.

**Precedence:** Managed (org settings) > Project (`.claude/agents/`) > User (`~/.claude/agents/`) > Plugin. Plugin subagents CANNOT use `hooks`, `mcpServers`, or `permissionMode` (security restriction).

**SDK / JSON form** (via `--agents` flag or `AgentDefinition` Python class): uses `prompt` (instead of markdown body), `tools`, `disallowedTools`, `model`, `permissionMode`, `mcpServers`, `hooks`, `maxTurns`, `skills`, `initialPrompt`, `memory`, `effort`, `background`, `isolation`, `color`.

**TRAP:** Older guides use `allowed-tools` in markdown frontmatter. Current syntax is just `tools:` in markdown; `allowedTools`/`allowed_tools` are SDK-only.

### A.2 Hooks (`.claude/settings.json`) — the April 2026 `defer` decision

**12+ events** as of March 2026: `SessionStart`, `SessionEnd`, `Setup` (v2.1.10+), `UserPromptSubmit`, `PreToolUse`, `PermissionRequest` (v2.0.45+), `PostToolUse`, `PostToolUseFailure`, `Stop`, `StopFailure`, `SubagentStart`, `SubagentStop`, `PreCompact`, `Notification`, `Elicitation` (v2.1.76+), `ElicitationResult` (v2.1.76+).

**Handler types:** `command` (shell), `http` (POST), `prompt` (single-turn Claude eval), `agent` (full agent exploration). `async: true` for non-blocking (released January 2026).

**`defer` (v2.1.89+):** PreToolUse `permissionDecision` accepts `"allow"|"deny"|"ask"|"defer"`. `defer` is honored ONLY in non-interactive `claude -p` subprocess mode. It lets the parent process (e.g., Agent SDK app, custom UI) pause Claude at a tool call, gather input through its own interface, and resume via `--resume`. In interactive sessions, `defer` is logged as a warning and ignored. `--resume` restores the deferred permission mode (except `plan` and `bypassPermissions`). If the deferred tool is unavailable at resume time (e.g., MCP server not connected): exit with `stop_reason: "tool_deferred_unavailable"`, `is_error: true`; the `deferred_tool_use` payload is still included for identification.

**Stdin JSON shape (read by hook):**
```json
{"session_id":"...","transcript_path":"...","tool_name":"Bash",
 "tool_input":{"command":"..."}, "tool_use_id":"...", "stop_hook_active":false}
```

**Stdout JSON (PreToolUse current format):**
```json
{"hookSpecificOutput": {
  "hookEventName": "PreToolUse",
  "permissionDecision": "allow|deny|ask|defer",
  "permissionDecisionReason": "...",
  "updatedInput": {"command": "modified"},
  "additionalContext": "..."
}}
```
DEPRECATED form (still works, auto-mapped): top-level `decision: "approve"|"block"` + `reason` → `allow`/`deny`. **PostToolUse and Stop still use the top-level form.**

Exit codes: `0` = success/proceed (read JSON if any); `2` = blocking error (stderr → Claude); other non-zero = non-blocking, stderr → user only. Env vars: `$CLAUDE_PROJECT_DIR`, `$CLAUDE_SESSION_ID` (v2.1.9+).

Example:
```json
{"hooks": {
  "PreToolUse": [{"matcher": "Bash",
    "hooks": [{"type": "command", "command": "$CLAUDE_PROJECT_DIR/.claude/hooks/scope-gate.py"}]}],
  "PostToolUse": [{"matcher": "Write|Edit|MultiEdit",
    "hooks": [{"type": "command", "command": "ruff format $CLAUDE_TOOL_INPUT_FILE_PATH", "async": true}]}]
}}
```

### A.3 Slash commands & A.4 Skills

`.claude/commands/*.md` with frontmatter + body; `$ARGUMENTS` placeholder is replaced with text after the slash command.

**2026 SHIFT (per official docs):** commands have been merged into skills. A file at `.claude/commands/review.md` and a skill at `.claude/skills/review/SKILL.md` both create `/review` and behave identically. Skills give more control (auto-invocation, forking into subagents, supporting files) and take precedence if both exist. New skill flags: `context: fork` (turns the skill into a subagent at runtime), `disable-model-invocation: true` (only runs via explicit `/skillname`). Subagent frontmatter `skills:` field pre-loads listed skills' full content into the subagent's context at startup.

### A.5 MCP server registration

Two transports: `stdio` (subprocess, default when `command` is set) and `http`/`streamable-http` (when `url` is set). MCP tool names exposed to Claude become `mcp__<server>__<tool>`.

```json
{"mcpServers": {
  "recon": {"command": "python", "args": ["-m", "bountystrike.mcp.recon"],
            "env": {"RECON_RATE_LIMIT_RPS": "2"}},
  "scope": {"type": "http", "url": "http://localhost:8765/mcp",
            "headers": {"Authorization": "Bearer ${SCOPE_TOKEN}"}}
}}
```

### A.6 Claude Agent SDK (Python) — current API

**Package:** `claude-agent-sdk` on PyPI, Python 3.10+. **TRAP:** the older `claude-code-sdk` is DEPRECATED; class renamed `ClaudeCodeOptions → ClaudeAgentOptions`. Agent SDK credits launch June 15, 2026 — subscription users get a dedicated monthly SDK credit pool.

```python
import anyio
from claude_agent_sdk import query, ClaudeAgentOptions, AgentDefinition, HookMatcher

async def main():
    options = ClaudeAgentOptions(
        system_prompt="...",
        allowed_tools=["Read","Edit","Bash","Agent"],   # AUTO-APPROVE list; "Agent" needed for subagent spawn
        disallowed_tools=["WebFetch"],                   # hard block
        permission_mode="acceptEdits",                   # default|acceptEdits|plan|bypassPermissions
        cwd="/repo", max_turns=50,
        model="claude-sonnet-4-6-20260315",
        mcp_servers={"recon": {...}},
        agents={"recon-agent": AgentDefinition(
            description="Subdomain enumeration",
            prompt="You are...",
            tools=["Read","Bash","mcp__recon__subfinder"],
            model="claude-haiku-4-5")},
        hooks={"PreToolUse": [HookMatcher(matcher="Bash", hooks=[my_python_hook])]},
        setting_sources=["user","project","local"],     # MUST set to load .claude/ files; default None
        resume=session_id, betas=[],                    # context-1m beta RETIRED 2026-04-30
    )
    async for msg in query(prompt="...", options=options):
        print(msg)

anyio.run(main)
```

**TRAPS:**
- Use `anyio.run`, not `asyncio.run` (SDK's async layer is built on anyio)
- `setting_sources` defaults to `None` (no filesystem load) — must explicitly opt in to load `.claude/` files
- 1M context beta retired April 30, 2026 — use Sonnet 4.6 or Opus 4.6 (1M at standard pricing, no beta header)
- `ClaudeSDKClient` for multi-turn; `query()` is stateless per call — use `resume=session_id` for continuity

### A.7 Multi-step one-shot best practices

1. **TodoWrite spine.** Top-level CLAUDE.md instructs lead agent to read `tasks/manifest.yaml`, populate TodoWrite with all task IDs, mark each in_progress → completed as executed.
2. **Plan mode first.** Start session with `--permission-mode plan`; switch to `acceptEdits` after the manifest is reviewed.
3. **One task = one PR-sized unit.** Each task has unique `id`, explicit `depends_on:` list, `files:` manifest (created/modified), `acceptance:` field (command whose exit 0 = complete).
4. **Subagent boundary = isolation boundary.** Spawn fresh subagent for any broad search/read so parent context stays clean. Subagents return only a summary.
5. **Stop hook = completion gate.** Use a Stop hook that checks TodoWrite state and exits 2 (forcing Claude to continue) until all tasks are `completed`. Guard against infinite loops with `stop_hook_active` check.
6. **Idempotency:** every task script begins with a "skip if acceptance test already passes" check. Re-running the whole graph is a no-op once green.

### A.8 CLAUDE.md precedence
1. `~/.claude/CLAUDE.md` (user-wide)
2. `<repo>/CLAUDE.md` (project root)
3. `<repo>/<subdir>/CLAUDE.md` (nested; loaded when working in that dir)
4. `.claude/CLAUDE.local.md` (gitignored personal overrides)

Best practice: keep < 500 lines, use H2 sections, embed exact commands (`pnpm install`, not "install deps"), include "Constraints" section listing forbidden actions, list methodology files (deterministic-verifier doctrine, scope-enforcement doctrine).

---

## TRACK B — Foundation Toolchain (Phase 0 + Phase 1.1)

### B.1 Monorepo: pnpm workspaces + Turborepo 2.x

**Versions:** `turbo@^2.9.0` (latest stable is v2.9.12 per github.com/vercel/turborepo/releases; v2.7 added composable config and Devtools, v2.9 added Agent Skill), `pnpm@9.x`, Node 18+.

**TRAP:** Turborepo 1.x used `pipeline:`; 2.x uses `tasks:`. Old `pipeline:` still parses but is deprecated.

`pnpm-workspace.yaml`:
```yaml
packages:
  - "packages/core/*"        # bountystrike-core, Apache-2.0
  - "packages/community/*"   # bountystrike-community, AGPL-3.0
  - "packages/enterprise/*"  # bountystrike-enterprise, proprietary
  - "apps/*"
```

`turbo.json`:
```json
{"$schema": "https://turbo.build/schema.json",
 "tasks": {
   "build": {"dependsOn": ["^build"], "outputs": ["dist/**",".next/**","!.next/cache/**"]},
   "test":  {"dependsOn": ["build"]},
   "lint":  {},
   "dev":   {"cache": false, "persistent": true}}}
```

Per-package LICENSE files at workspace root (`packages/core/<pkg>/LICENSE` = Apache 2.0, `packages/community/<pkg>/LICENSE` = AGPL-3.0). Root LICENSE = manifest pointing to per-package licenses. License header automation: Google's `addlicense` or PostToolUse hook.

### B.2 OpenFeature + Unleash

`pip install openfeature-sdk` (Python). **Gap: no official OpenFeature → Unleash Python provider** (0% Python coverage per devcycle.com OpenFeature comparison; GitHub issue Unleash/unleash#3912 still open). Options: (1) implement custom `AbstractProvider` (signature documented at openfeature.dev/docs/reference/technologies/server/python), (2) use `flagd` as eval-layer intermediary, (3) use `go-feature-flag` (82% coverage, OpenFeature-native).

Self-host Unleash:
```bash
git clone https://github.com/Unleash/unleash.git && cd unleash
docker compose up -d
# Admin UI at http://localhost:4242, default creds admin/unleash4all
```
For SaaS: wire LaunchDarkly provider.

### B.3 Postgres 17 + pgvector + pgvectorscale + ParadeDB pg_search

**Versions:** PostgreSQL 17/18, pgvector 0.8.1+, pgvectorscale 0.9.0 (March 2026: `CREATE INDEX CONCURRENTLY` for DiskANN), pg_search current.

**CO-EXISTENCE GOTCHA:** ParadeDB removed pgvectorscale from its own bundle in a recent release. The three CAN coexist but require a custom image. Community reference: `oaklight/vectorsearch` on Docker Hub (Postgres 17 + pgvector 0.8.0 + pg_search + pgvectorscale with bootstrap.sh).

**Install SQL (verified, in order):**
```sql
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS vectorscale CASCADE;   -- TRAP: registered name is "vectorscale", NOT "pgvectorscale"
CREATE EXTENSION IF NOT EXISTS pg_search;             -- ParadeDB BM25
```

DiskANN index:
```sql
CREATE INDEX CONCURRENTLY idx_emb_diskann
ON documents USING diskann (embedding vector_cosine_ops)
WITH (storage_layout = memory_optimized);
```
Ops: `<=>` (cosine, `vector_cosine_ops`), `<->` (L2, `vector_l2_ops`), `<#>` (inner product). Per Timescale (now TigerData) vendor benchmarks published at github.com/timescale/pgvectorscale and tigerdata.com/blog/pgvector-vs-pinecone: "On a benchmark dataset of 50 million Cohere embeddings with 768 dimensions each, PostgreSQL with pgvector and pgvectorscale achieves 28x lower p95 latency and 16x higher query throughput compared to Pinecone's storage optimized (s1) index for approximate nearest neighbor queries at 99% recall, all at 75% less cost when self-hosted on AWS EC2." Note: these are vendor-produced benchmarks.

ParadeDB BM25:
```sql
CREATE INDEX idx_bm25 ON reports USING bm25 (id, body) WITH (key_field='id');
SELECT id, body FROM reports WHERE body @@@ 'xss reflected';
```

### B.4 Hatchet single-binary self-host

**Python SDK:** `hatchet-sdk==1.33.5+` on PyPI (marked alpha). Python 3.10–3.13.

Single-binary install:
```bash
curl -fsSL https://install.hatchet.run/install.sh | bash
hatchet --version
```
Or docker-compose hatchet-lite (verified primary source, docs.hatchet.run/self-hosting/hatchet-lite):
```yaml
services:
  postgres:
    image: postgres:15.6
    environment: {POSTGRES_USER: hatchet, POSTGRES_PASSWORD: hatchet, POSTGRES_DB: hatchet}
    healthcheck: {test: ["CMD-SHELL", "pg_isready -d hatchet -U hatchet"]}
  hatchet-lite:
    image: ghcr.io/hatchet-dev/hatchet/hatchet-lite:latest
    ports: ["8888:8888", "7077:7077"]
    depends_on: {postgres: {condition: service_healthy}}
    environment:
      DATABASE_URL: "postgresql://hatchet:hatchet@postgres:5432/hatchet?sslmode=disable"
      SERVER_GRPC_BIND_ADDRESS: "0.0.0.0"
      SERVER_GRPC_INSECURE: "t"
      SERVER_GRPC_BROADCAST_ADDRESS: localhost:7077
```
UI at `localhost:8888`, default creds `admin@example.com` / `Admin123!!`.

**Python worker v1 API:**
```python
from hatchet_sdk import Context, EmptyModel, Hatchet
hatchet = Hatchet()

@hatchet.task()
def verify_xss(input: EmptyModel, ctx: Context) -> dict:
    return {"verified": True}

def main():
    worker = hatchet.worker("verifier-worker", workflows=[verify_xss])
    worker.start()
```

**TRAP:** Hatchet v0 used `@hatchet.workflow` (class-based), TypedDict inputs, nested `hatchet.aio`, static `Client.from_environment()` — **all deprecated in v1.** V1 uses `@hatchet.task()` (function-based), Pydantic models, `aio_` prefix for async, Pydantic Settings for `ClientConfig`. Optional Postgres queue via `SERVER_TASKQUEUE_KIND=postgres` (default RabbitMQ).

### B.5 LiteLLM proxy

**Pin: `ghcr.io/berriai/litellm:v1.86.1` — current signed stable image as of May 2026 per github.com/BerriAI/litellm/releases (v1.87.0-rc.1 also available as release candidate).**

**SECURITY:** Versions 1.82.7 and 1.82.8 were affected by a supply-chain incident that occurred on March 24, 2026 at 10:39 UTC. Per docs.litellm.ai/blog/security-townhall-updates: "On March 24, 2026 at 10:39 UTC, LiteLLM v1.82.7 was pushed to PyPI. Version v1.82.8 was published soon after. Those packages were live for about 40 minutes before being quarantined by PyPI." Never use 1.82.7/1.82.8.

docker-compose with Postgres for virtual keys + budgets:
```yaml
services:
  db:
    image: postgres:16
    environment: {POSTGRES_USER: litellm, POSTGRES_PASSWORD: litellm, POSTGRES_DB: litellm}
    volumes: [litellm_pg:/var/lib/postgresql/data]
  litellm:
    image: ghcr.io/berriai/litellm:v1.86.1
    ports: ["4000:4000"]
    volumes: [./config.yaml:/app/config.yaml]
    command: ["--config", "/app/config.yaml", "--detailed_debug"]
    environment:
      LITELLM_MASTER_KEY: sk-${LITELLM_MASTER_KEY}
      LITELLM_SALT_KEY: ${LITELLM_SALT_KEY}
      DATABASE_URL: postgresql://litellm:litellm@db:5432/litellm
```

config.yaml with corrected DeepSeek pricing:
```yaml
model_list:
  - model_name: claude-sonnet-4-6
    litellm_params: {model: anthropic/claude-sonnet-4-6-20260315, api_key: os.environ/ANTHROPIC_API_KEY}
  - model_name: claude-haiku-4-5
    litellm_params: {model: anthropic/claude-haiku-4-5-20260101, api_key: os.environ/ANTHROPIC_API_KEY}
  - model_name: deepseek-v4-flash
    litellm_params:
      model: deepseek/deepseek-v4-flash
      api_key: os.environ/DEEPSEEK_API_KEY
      input_cost_per_token: 0.00000014      # $0.14 / 1M cache-miss
      output_cost_per_token: 0.00000028     # $0.28 / 1M
      # cache-hit ($0.0028 / 1M) tracked via prompt_cache_hit_tokens in response
general_settings:
  master_key: sk-1234
  database_url: postgresql://...
litellm_settings:
  max_budget: 100
  budget_duration: 30d
  default_fallbacks: ["claude-sonnet-4-6"]
```

Virtual key:
```bash
curl -X POST http://localhost:4000/key/generate \
  -H "Authorization: Bearer $LITELLM_MASTER_KEY" \
  -H "Content-Type: application/json" \
  -d '{"models":["claude-sonnet-4-6"],"max_budget":25,"duration":"30d","metadata":{"workstream":"verifier"}}'
```

### B.6 Cloudflare R2 + boto3 (evidence store)

**Free tier:** 10 GB Standard storage / 1M Class A ops / 10M Class B ops / month, zero egress.

Endpoint: `https://<ACCOUNT_ID>.r2.cloudflarestorage.com`. Region: `auto` (required by SDK, ignored by R2).

```python
import boto3, hashlib
s3 = boto3.client("s3",
    endpoint_url=f"https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com",
    aws_access_key_id=R2_ACCESS_KEY_ID,
    aws_secret_access_key=R2_SECRET_ACCESS_KEY,
    region_name="auto")

content = open("evidence.json","rb").read()
key = f"evidence/sha256/{hashlib.sha256(content).hexdigest()}"
s3.put_object(Bucket="bountystrike-evidence", Key=key, Body=content)

url = s3.generate_presigned_url("get_object",
    Params={"Bucket":"bountystrike-evidence","Key":key},
    ExpiresIn=3600)
```

**TRAP — boto3 1.36.0 R2 checksum break:** "Client version 1.36.0 introduced a modification to the default checksum behavior from the client that is currently incompatible with R2 APIs. To mitigate, users can use 1.35.99 or add the following to their s3 resource config" — pin `boto3<1.36` OR pass `request_checksum_calculation="when_required"` in config.

Class A (writes): PUT, COPY, ListObjects, multipart upload calls, lifecycle config. Class B (reads): HEAD, GET, UsageSummary, GetBucket*.

### B.7 SOPS + age

**Versions:** sops v3.9.0 (CNCF Sandbox under getsops/sops; donated from Mozilla in 2023), age current.

```bash
brew install sops age   # or curl release binaries
age-keygen -o ~/.config/sops/age/keys.txt && chmod 600 ~/.config/sops/age/keys.txt

cat > .sops.yaml <<EOF
creation_rules:
  - path_regex: 'secrets/.*\.ya?ml$'
    encrypted_regex: '^(data|stringData|password|api_key|token|secret)$'
    age: age1ql3z7hjy54pw3hyww5ayyfg7zqgvc7w3j2elw...
EOF

sops -e -i secrets/litellm.yaml
sops -d secrets/litellm.yaml    # CI: SOPS_AGE_KEY env var read automatically
```

CI pattern: store age private key as `SOPS_AGE_KEY` secret; `sops -d` reads from env. The `encrypted_regex` ensures only values are encrypted while keys/structure stay diff-friendly.

---

## TRACK C — Scope Ingestion (Phase 1.2)

### C.1 arkadiyt/bounty-targets-data

**Cadence:** README header says "hourly" but actual cron is **every 30 minutes** ("New changes (if any) are picked up every 30 minutes"). Phase 1.2's hourly polling is fine — just acknowledge 30-min freshness floor.

**Exact filenames (verified):**
- `data/domains.txt` — flat list, non-wildcard
- `data/wildcards.txt` — flat list of wildcard scopes
- `data/hackerone_data.json`
- `data/bugcrowd_data.json`
- `data/intigriti_data.json`
- `data/yeswehack_data.json`
- `data/federacy_data.json`

No Immunefi in this repo (use bbscope or projectdiscovery list). Raw URL pattern: `https://raw.githubusercontent.com/arkadiyt/bounty-targets-data/main/data/<file>`.

### C.2 sw33tLie/bbscope v2 — MAJOR API BREAK

**TRAP:** bbscope v2 (currently on `main` branch) **broke v1 subcommands entirely.** v1 was `bbscope h1 -t TOKEN -u USER`. v2 uses `bbscope poll <platform>` and `bbscope db <action>`. The tool prints a yellow warning if run with v1 syntax.

Install: `go install github.com/sw33tLie/bbscope@latest` OR `docker pull ghcr.io/sw33tlie/bbscope:latest`.

Config: `~/.bbscope.yaml` (auto-created on first run). Contains H1 username+token, Bugcrowd session cookie (**`_bugcrowd_session`** — NOT `_crowdcontrol_session`), Intigriti bearer (`api.intigriti.com` Authentication header), YesWeHack bearer (`api.yeswehack.com` Authorization header), Immunefi creds, AI normalization config (OpenAI), `db_url` (PostgreSQL).

```bash
bbscope poll h1 --db
bbscope poll bc --db --token "$BC_SESSION"
bbscope poll --db   # all platforms

bbscope db get -c wildcards | subfinder -dL -
bbscope db get -c cidrs -p h1
bbscope db get -c all | httpx -json
```

PostgreSQL backend optional but recommended. AI normalization batches per program; tunable `max_batch` and `max_concurrency`.

### C.3 projectdiscovery/public-bugbounty-programs

**TRAP:** old `chaos-bugbounty-list.json` at the repo root **404s** in the current repo. Current layout:
- `src/data.yaml` — source of truth (human-edited)
- `dist/data.json` — CI-generated; programs are under the top-level `programs` key
- `src/data.schema.json` — JSON schema

Raw URL: `https://raw.githubusercontent.com/projectdiscovery/public-bugbounty-programs/main/dist/data.json`

Schema:
```json
{"name":"HackerOne","url":"https://hackerone.com/security","bounty":true,"swag":true,
 "domains":["hackerone.com","hackerone.net","hacker101.com","hackerone-ext-content.com"]}
```
Only root/apex domains accepted; no wildcards, no subdomains.

### C.4 HackerOne API — structured_scopes HARD GATE RESOLUTION

**Primary source:** api.hackerone.com/getting-started/ (changelog).

**Verbatim (April 7, 2026):** "Removed documentation of the obsolete endpoints to create, update and archive structured scopes on the program level. Assets are managed via the organization asset management endpoints."

| Endpoint | Status (May 2026) | Action |
|---|---|---|
| `GET /v1/hackers/programs/{handle}/structured_scopes` | **CURRENT** (last revised 2026-01-16) | Use as primary scope source. Paginated. |
| `GET /v1/hackers/programs/{handle}/scope_exclusions` | **NEW** (added April 11, 2026) | Merge with structured_scopes as out-of-scope filter |
| Program-level POST/PUT/DELETE structured_scopes | **REMOVED** April 7, 2026 | Skip in CE; use org-level asset endpoints (Enterprise) |
| `GET /v1/programs/{id}/structured_scopes` (customer API) | **CURRENT** | Used for credentials/asset linking |

Response shape (verbatim):
```json
{"data":[{"id":"57","type":"structured-scope","attributes":{
  "asset_type":"URL","asset_identifier":"api.hackerone.com",
  "eligible_for_bounty":true,"eligible_for_submission":true,
  "instruction":"...","max_severity":"critical",
  "confidentiality_requirement":"high","integrity_requirement":"high","availability_requirement":"high",
  "created_at":"...","updated_at":"..."}}],
 "links":{"self":"...","next":"...","last":"..."}}
```
Auth: Basic `<API_USERNAME>:<API_TOKEN>`.

**Other 2026 changes worth wiring:** 2026-01-15 filtering by ID/created/updated date; 2026-04-11 scope_exclusions endpoint added; 2026-04-13 `severity_calculation_methods` attribute (`cvss_4_0`, `manual`) on Get Program; 2026-04-15 rate limiting 10 req/min on billing transactions endpoint; 2026-04-16 scope-exclusions CRUD endpoints; 2026-05-11 `hai_priority_score` (0-100) + `hai_prioritization_tier` (Critical/High/Medium/Low) on report objects (from Priority Escalation Agent).

**Implementation guidance:** Do NOT remove structured_scopes ingestion — still the primary asset list. ADD a second fetch for `/scope_exclusions` and merge as "out-of-scope categories" filter in the scope JWT claims.

### C.5 Platform schema notes

- **Bugcrowd** (`bugcrowd_data.json`): `code`, `name`, `tags`, `min_rewards`, `max_rewards`, `targets.in_scope[]` and `targets.out_of_scope[]` (each with `name`, `category`, `description`).
- **Intigriti** (`intigriti_data.json`): `companyHandle`, `handle`, `confidentialityLevel`, **`tier`** field (1-4, lower = higher payout), `domains[]`.
- **YesWeHack** (`yeswehack_data.json`): `slug`, `title`, `scopes[]` each with `scope`, `scope_type`, `description`, **`asset_value`** (low/medium/high/critical).
- **Immunefi** (NOT in arkadiyt — fetch from immunefi.com/explore or bbscope `poll immunefi`): **`impacts[]`** array with `category` (Critical/High/Medium/Low) + `description`, `assets[]` with `type` (Smart Contract / Websites and Applications / Blockchain/DLT).

### C.6 RS256 JWT — PyJWT 2.13.0

Install: `pip install pyjwt[crypto]` (RSA requires `cryptography`).

```python
import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
private_pem = key.private_bytes(
    serialization.Encoding.PEM,
    serialization.PrivateFormat.PKCS8,
    serialization.NoEncryption())
public_pem = key.public_key().public_bytes(
    serialization.Encoding.PEM,
    serialization.PublicFormat.SubjectPublicKeyInfo)

scope_token = jwt.encode({
    "iss":"bountystrike-scope","sub":"program:acme-h1",
    "iat":now,"exp":now+3600,
    "in_scope_domains":["*.acme.com"],
    "out_of_scope_domains":["dev.acme.com"],
    "platform":"hackerone","verified_at":"..."
}, private_pem, algorithm="RS256")

claims = jwt.decode(scope_token, public_pem, algorithms=["RS256"])
```

**SECURITY (verbatim from PyJWT docs):** "Do not compute the algorithms parameter based on the alg from the token itself, or on any other data that an attacker may be able to influence, as that might expose you to various vulnerabilities (see RFC 8725 §2.1)." — always hardcode `["RS256"]` to prevent `none`-algorithm attack.

---

## TRACK D — Deterministic Verifier Moat (Phase 1.3)

### D.1 Playwright Python XSS oracle

**Current:** `playwright>=1.50` (Python). Install: `pip install playwright && playwright install chromium`.

```python
import asyncio, secrets
from playwright.async_api import async_playwright

async def confirm_xss(url_with_payload: str) -> dict:
    fired = {"alert":False,"message":None,"type":None,"title_marker":False}
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(java_script_enabled=True)
        page = await ctx.new_page()

        async def on_dialog(d):
            fired["alert"] = True
            fired["type"] = d.type
            fired["message"] = d.message
            await d.dismiss()

        page.on("dialog", on_dialog)
        marker = "BSXSS-MARKER-" + secrets.token_hex(8)
        try:
            await page.goto(url_with_payload, wait_until="networkidle", timeout=15_000)
        except Exception:
            pass
        fired["title_marker"] = marker in (await page.title())
        await browser.close()
    return fired
```

**API facts (verified):**
- Handler must be registered BEFORE the action that triggers it.
- Default: dialogs are auto-dismissed if no listener. Once a listener is registered, it MUST call `dialog.accept()` or `dialog.dismiss()` or the page freezes.
- `dialog.type` returns `"alert"|"beforeunload"|"confirm"|"prompt"`.
- Python async API: handler can be `async def` with `await dialog.dismiss()`.

**Sandbox:** Docker container `--cap-drop=ALL --read-only --memory=512m --pids-limit=100`; network bound to a scope-JWT-enforcing egress proxy; image `mcr.microsoft.com/playwright/python:v1.50.0-jammy` (official, pinned); UID 1000; `seccomp=default`; `--security-opt=no-new-privileges`.

### D.2 interactsh SSRF oracle

Self-host: `go install github.com/projectdiscovery/interactsh/cmd/interactsh-server@latest`. Requires a domain with custom nameservers pointing at the host. `interactsh-srv --domain oast.bountystrike.io --auth --metrics --config-update`.

Go client (`github.com/projectdiscovery/interactsh/pkg/client`):
```go
client, _ := client.New(&client.Options{
    ServerURL: "https://oast.bountystrike.io",
    Token: "...",
    CorrelationIdLength: 20,
    CorrelationIdNonceLength: 13,
})
client.StartPolling(5*time.Second, func(interaction *server.Interaction) {
    // interaction.FullId, .Protocol ("dns"|"http"|"smtp"), .RawRequest
})
payloadURL := client.URL()  // e.g., c59e3crp82ke7bcnedq0cfjqdpeyyyyyn.oast.bountystrike.io
```

**Lightweight Python alternative:** `go-appsec/interactsh-lite` — drop-in protocol-compatible client+server with shorter LLM-friendly domains.

**Detection pattern:** per SSRF candidate param, generate unique correlation domain via `client.Domain()` → inject `http://<domain>/` (and DNS-only + cloud-metadata variants) → wait ≥5s → poll → confirmed iff DNS or HTTP callback to unique domain within the test window. Interactsh server has DNS records for cloud metadata services (e.g., 169.254.169.254-style) built in.

### D.3 Welch's t-test blind SQLi oracle

**Current:** `scipy==1.17.0`. Verified signature from docs.scipy.org/doc/scipy/reference/generated/scipy.stats.ttest_ind.html:
```
scipy.stats.ttest_ind(a, b, *, axis=0, equal_var=True, nan_policy='propagate',
                      alternative='two-sided', trim=0, method=None, keepdims=False)
```
Per docs: "equal_var bool, optional — If True (default), perform a standard independent 2 sample test that assumes equal population variances. If False, perform Welch's t-test, which does not assume equal population variance."

```python
from scipy import stats
import time, statistics, requests

N_SAMPLES = 8
SLEEP_SECONDS = 5
P_VALUE_THRESHOLD = 0.01
MIN_DELTA = SLEEP_SECONDS * 0.7

def t(url, params):
    s = time.perf_counter()
    requests.get(url, params=params, timeout=30)
    return time.perf_counter() - s

baseline = [t(target, {"id":"1"}) for _ in range(N_SAMPLES)]
sleep    = [t(target, {"id":f"1 AND SLEEP({SLEEP_SECONDS})"}) for _ in range(N_SAMPLES)]

r = stats.ttest_ind(sleep, baseline, equal_var=False)
is_vuln = (r.pvalue < P_VALUE_THRESHOLD and
           (statistics.mean(sleep) - statistics.mean(baseline)) >= MIN_DELTA)
```

**TRAP (SciPy 1.17.0):** all kwargs after `a, b` are keyword-only (`equal_var` etc.); `permutations` and `random_state` arguments were REMOVED in 1.17.0.

**DB-specific time-based payloads:**
| DB | Payload |
|---|---|
| MySQL | `1 AND SLEEP(5)` |
| Postgres | `1; SELECT pg_sleep(5)--` |
| MSSQL | `1; WAITFOR DELAY '0:0:5'--` |
| Oracle | `1 AND DBMS_PIPE.RECEIVE_MESSAGE('a',5)=1` |
| SQLite | recursive CTE generating ~1M rows |

**Calibration doctrine (Correction #5):** Document in CLAUDE.md: "Welch's t-test is a calibrated engineering heuristic, not academically derived. P-value threshold 0.01, mean-delta ≥ 70% of sleep duration, N=8 samples. At session start, run calibration on a known-clean endpoint to estimate baseline jitter; if jitter > 1.5s, double N_SAMPLES."

### D.4 Open-redirect oracle
Build `https://oast.bountystrike.io/oredirect/<nonce>`. Inject as redirect target. Confirmed iff (a) 3xx with `Location` matching exact nonce URL, OR (b) Playwright `page.on("framenavigated")` fires to that URL.

### D.5 SSTI oracle
Engine-specific marker expressions (verify computed result appears AND raw syntax does not): Jinja/Twig `{{7*7}}` → 49; FreeMarker `${7*7}`; Ruby/ERB `#{7*7}` or `<%= 7*7 %>`; Thymeleaf `*{7*7}`. Use unique non-trivial expressions (random prime products) to avoid collisions with legitimate content.

### D.6 "No verification, no submission" data model
```sql
CREATE TABLE findings (
  id UUID PRIMARY KEY,
  vuln_class TEXT NOT NULL,
  scope_jwt TEXT NOT NULL,
  verification_oracle TEXT NOT NULL CHECK (verification_oracle IN
    ('xss_playwright','ssrf_interactsh','sqli_welch','open_redirect','ssti')),
  verification_evidence_sha256 TEXT NOT NULL,
  verification_passed BOOLEAN NOT NULL,
  CONSTRAINT must_verify CHECK (verification_passed = TRUE)
);
```
Add an INSERT trigger that RS256-verifies the scope_jwt and aborts otherwise; row-level security: INSERT-only.

---

## TRACK E — Recon MCP + Pipeline (Phase 1.4)

### E.1 ProjectDiscovery tools — JSON output flags

Install (Go 1.21+):
```bash
go install -v github.com/projectdiscovery/subfinder/v2/cmd/subfinder@latest
go install -v github.com/projectdiscovery/dnsx/cmd/dnsx@latest
go install -v github.com/projectdiscovery/httpx/cmd/httpx@latest
go install -v github.com/projectdiscovery/naabu/v2/cmd/naabu@latest
go install -v github.com/projectdiscovery/katana/cmd/katana@latest
```

| Tool | JSON flag | Example |
|---|---|---|
| subfinder | `-oJ` (JSONL) or `-json` | `subfinder -d acme.com -all -silent -oJ -o subs.jsonl` |
| dnsx | `-json` | `cat subs.txt \| dnsx -a -aaaa -cname -json -o resolved.jsonl` |
| httpx | `-json` | `httpx -json -tech-detect -status-code -title -o live.jsonl` |
| naabu | `-json` | `naabu -p - -json -top-ports 100 -o ports.jsonl` |
| katana | `-j` or `-json` (with new `-eof`/`-lof` field filters) | `katana -u https://acme.com -d 3 -jc -kf -j -o crawl.jsonl` |

**Politeness flags:** subfinder `-rl <int>` + `-rls "shodan=15/s,..."`; httpx `-rl <int>` / `-c <int>`; naabu `-rate <int>`; katana `-rl <int>` / `-d` / `-jc` / `-kf`.

### E.2 Custom recon-MCP server (Python)

Use the official `mcp` Python SDK (FastMCP). Community `pd-tools-mcp` (TypeScript) exists but doesn't enforce scope/politeness — write your own.

```python
# bountystrike/mcp/recon.py
import asyncio, subprocess, json
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("bountystrike-recon")
_bucket = TokenBucket(rate=2.0, capacity=10)

@mcp.tool(name="subfinder",
  description="Passive subdomain enumeration for a SINGLE in-scope domain. Returns list of subdomains.")
async def subfinder(domain: str, scope_jwt: str) -> dict:
    # 1) RS256-verify scope_jwt, 2) check domain ∈ scope, 3) acquire token-bucket slot
    await _bucket.acquire()
    proc = await asyncio.create_subprocess_exec(
        "subfinder","-d",domain,"-silent","-oJ","-all","-timeout","30",
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    out,_ = await proc.communicate()
    return {"subdomains":[json.loads(l) for l in out.decode().splitlines() if l.strip()]}

if __name__ == "__main__":
    mcp.run(transport="stdio")
```

**TRAP (MCP stdio):** NEVER write to stdout from a stdio MCP server — corrupts JSON-RPC. Use stderr or file logging (per official MCP docs).

Token bucket pattern: async lock + tokens replenished by `elapsed × rate`; if < 1, `await asyncio.sleep((1 - tokens) / rate)`.

Register in `.claude/settings.json`:
```json
{"mcpServers": {"recon": {"command": "python", "args": ["-m", "bountystrike.mcp.recon"]}}}
```

### E.3 Asset provenance schema
```sql
CREATE TABLE assets (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  asset_type TEXT NOT NULL,           -- domain|subdomain|ip|url|port
  value TEXT NOT NULL,
  parent_id UUID REFERENCES assets(id),
  discovered_by TEXT NOT NULL,        -- subfinder|dnsx|httpx|...
  discovered_at TIMESTAMPTZ DEFAULT now(),
  scope_program TEXT NOT NULL,
  scope_jwt_jti TEXT NOT NULL,        -- ID of the JWT under which discovered
  raw_evidence_sha256 TEXT NOT NULL,  -- pointer into R2 evidence store
  UNIQUE (value, scope_program)
);
CREATE INDEX idx_assets_scope ON assets(scope_program);
```

---

## TRACK F — One-Shot Packaging

### F.1 Master task graph
```
tasks/
├── manifest.yaml              # ordered task list, dependency DAG
├── 000-bootstrap/             # node, pnpm, python, docker preflight
├── 001-monorepo/              # pnpm-workspace.yaml + turbo.json
├── 002-licenses/              # per-package LICENSE + headers
├── 003-feature-flags/         # OpenFeature SDK + Unleash compose
├── 010-postgres-stack/        # custom image: pg17 + vector + vectorscale + pg_search
├── 011-hatchet-lite/
├── 012-litellm-proxy/
├── 013-r2-evidence/           # bucket + boto3 client + content-addressable PUT
├── 014-audit-log/             # hash-chained PostgreSQL log
├── 015-cost-meter/            # LiteLLM hook + per-task budget tracking
├── 020-scope-arkadiyt-ingest/
├── 021-scope-bbscope/         # v2 subcommand wrapper
├── 022-scope-projectdiscovery/
├── 023-scope-normalizer/      # canonical schema across H1/BC/IT/YWH/Imm
├── 024-scope-jwt-issuer/      # RS256
├── 025-egress-enforcer/       # iptables + JWT-aware proxy
├── 026-scope-diff-notifier/   # Slack/Discord/Telegram/webhook fan-out
├── 030-verifier-xss/          # Playwright + sandbox container
├── 031-verifier-ssrf-interactsh/
├── 032-verifier-sqli-welch/   # SciPy + Hypothesis tests
├── 033-verifier-open-redirect/
├── 034-verifier-ssti/
├── 035-no-verify-no-submit-trigger/
├── 040-recon-mcp/             # FastMCP + token bucket + scope JWT verify
├── 041-recon-subagent/        # .claude/agents/recon-agent.md
├── 042-recon-pipeline/        # subfinder→dnsx→httpx→naabu→katana orchestration
└── 999-acceptance-suite/      # full E2E pytest
```

**task.yaml schema:**
```yaml
id: 010-postgres-stack
title: "Postgres 17 + pgvector + pgvectorscale + pg_search"
depends_on: [000-bootstrap]
files_created:
  - infra/postgres/Dockerfile
  - infra/postgres/init.sql
  - infra/docker-compose.postgres.yaml
acceptance:
  - "docker compose -f infra/docker-compose.postgres.yaml up -d"
  - "sleep 10 && docker compose exec -T pg psql -U bs -d bs -c \"SELECT extname FROM pg_extension WHERE extname IN ('vector','vectorscale','pg_search');\" | grep -c 'vector\\|vectorscale\\|pg_search' | grep -q '3'"
  - "pytest tests/infra/test_postgres_stack.py"
idempotent: true
estimated_minutes: 8
```

### F.2 Idempotency pattern
Every task script begins with the acceptance check; if it passes, exit 0 immediately. Re-running the whole graph is a no-op once green.

### F.3 `curl | bash` installer
```bash
#!/usr/bin/env bash
# https://install.bountystrike.io/community.sh
set -euo pipefail
command -v docker >/dev/null || { echo "Install Docker first"; exit 1; }
docker compose version >/dev/null 2>&1 || { echo "Need docker compose v2"; exit 1; }
DEST="${BS_HOME:-$HOME/.bountystrike}"
git clone --depth 1 https://github.com/bountystrike/community.git "$DEST"
cd "$DEST"
mkdir -p secrets
[ -f secrets/postgres.password ] || openssl rand -hex 32 > secrets/postgres.password
[ -f secrets/litellm.master_key ] || echo "sk-$(openssl rand -hex 24)" > secrets/litellm.master_key
[ -f secrets/scope_jwt.key ] || ssh-keygen -t rsa -b 2048 -m PKCS8 -f secrets/scope_jwt.key -N ""
docker compose -f infra/docker-compose.yaml up -d
./scripts/wait-for-health.sh
echo "✓ BountyStrike Community up at http://localhost:3000"
```

### F.4 Coolify deployment

**Current version:** Coolify v4.1.0, Apache-2.0 — per github.com/coollabsio/coolify/releases, v4.1.0 was released May 18, 2026 as the first stable (non-beta) release in the v4 line, superseding the beta series entirely.

Two Docker Compose modes:
1. **Compose-from-Git** (preferred): Build Pack: `Docker Compose`, repo with `docker-compose.yaml` at root, base directory `/`.
2. **Service Stack**: paste compose YAML directly.

Coolify "magic env vars" (`SERVICE_FQDN_*`, `SERVICE_URL_*`, `SERVICE_PASSWORD_*`) auto-generate domains and passwords on first deploy and persist across redeploys:
```yaml
services:
  postgres:
    environment:
      POSTGRES_PASSWORD: ${SERVICE_PASSWORD_POSTGRES}
  app:
    environment:
      DATABASE_URL: postgresql://bs:${SERVICE_PASSWORD_POSTGRES}@postgres:5432/bs
      APP_FQDN: ${SERVICE_FQDN_APP}
```
Traefik (built-in) handles SSL via Let's Encrypt automatically when a domain is mapped.

**Hetzner sizing:** AX52 (8c/16t/64 GB RAM/2×1 TB NVMe, ~€100/mo) for full BountyStrike stack; CPX41 (4 vCPU/8 GB/240 GB, ~$30/mo) sufficient for CE alone.

### F.5 Testing
```python
# tests/conftest.py
import pytest
from testcontainers.postgres import PostgresContainer

@pytest.fixture(scope="session")
def pg():
    with PostgresContainer("bountystrike/postgres:17-vectorscale-bm25").with_env(
        "POSTGRES_USER", "bs"
    ) as p:
        yield p

# tests/unit/test_welch_oracle.py — property-based
from hypothesis import given, strategies as st, settings

@given(
    baseline_mean=st.floats(0.05, 0.5),
    jitter=st.floats(0.01, 0.2),
    sleep_seconds=st.integers(3, 10),
)
@settings(max_examples=200)
def test_welch_detects_real_sleep(baseline_mean, jitter, sleep_seconds):
    # Synthesize samples; oracle must return vulnerable=True
    ...
```
Deps: `pytest-asyncio`, `pytest-mock`, `pytest-cov`, `hypothesis>=6.100`, `testcontainers[postgres]>=4.7`.

---

## SIX CORRECTIONS — RE-AUDITED

| # | Original Correction (from your task) | Audit Result | Action |
|---|---|---|---|
| 1 | DeepSeek $0.28 in / $0.42 out cache-miss, $0.028 cache-hit | **WRONG AGAIN.** Per api-docs.deepseek.com/quick_start/pricing (May 21, 2026): deepseek-chat/-reasoner are aliases for **deepseek-v4-flash**. Pricing: **$0.14 cache-miss input / $0.0028 cache-hit input / $0.28 output per 1M tokens.** Cache-hit reduced to 1/10 of launch price on 2026-04-26. V4 Pro promo at 75% off until 2026-05-31 15:59 UTC. | **REPLACE numbers in plan.** Wire LiteLLM to detect model rename. Cron-refresh pricing daily. |
| 2 | No hard Anthropic refusal-rate; runtime classifier | Still valid (no vendor publishes refusal-rate metrics) | Implement classifier + fallback chain claude-sonnet-4-6 → deepseek-v4-flash via LiteLLM `default_fallbacks` |
| 3 | XBOW Informative/N-A rate is industry estimate | Still valid | Document in `docs/methodology/disclosed-calibration.md` |
| 4 | HackerOne structured_scopes must be verified | **CONFIRMED VIA PRIMARY SOURCE.** Only program-level WRITE removed April 7, 2026. READ endpoint still current. NEW scope_exclusions endpoint April 11, 2026. | Implement structured_scopes read + scope_exclusions read + merge. Skip program-level WRITE; route asset management to org endpoints (Enterprise roadmap). |
| 5 | Welch's t-test is calibrated heuristic | Still valid. SciPy 1.17.0 keyword-only signature change noted; `permutations`/`random_state` REMOVED. | Document calibration in CLAUDE.md; ship defaults; calibrate on clean endpoint at session start |
| 6 | EV decay constants proprietary | Still valid | `docs/methodology/ev-decay.md` + ship defaults |

---

## CRITICAL TRAINING-DATA TRAPS (consolidated)

1. **claude-code-sdk → claude-agent-sdk** (Python + TS); class rename `ClaudeCodeOptions → ClaudeAgentOptions`.
2. **Hatchet v1 SDK** (1.33.5+): `@hatchet.task()` (function-based) not `@hatchet.workflow` (class-based); Pydantic inputs; `aio_` prefix for async.
3. **bbscope v1 → v2**: subcommand restructure to `poll`/`db`. v1 syntax only works on master branch (legacy).
4. **DeepSeek model rename**: `deepseek-chat`/`deepseek-reasoner` are aliases for canonical `deepseek-v4-flash`. Pricing structure changed (cache-hit at 1/10 launch price from 2026-04-26).
5. **boto3 1.36.0 R2 checksum break**: pin `boto3<1.36` or set `request_checksum_calculation="when_required"`.
6. **LiteLLM supply-chain 1.82.7/1.82.8** (March 24, 2026 at 10:39 UTC): must pin to 1.86.1 stable (or 1.87.0-rc.1 if testing).
7. **Turborepo 2.x `pipeline:` → `tasks:`** in turbo.json.
8. **`chaos-bugbounty-list.json` moved**: now at `dist/data.json` under `programs` key in projectdiscovery/public-bugbounty-programs.
9. **HackerOne structured_scopes**: NOT fully deprecated — only program-level WRITE removed.
10. **Bugcrowd cookie**: `_bugcrowd_session` NOT `_crowdcontrol_session`.
11. **SciPy 1.17.0 ttest_ind**: keyword-only args; `permutations` & `random_state` removed.
12. **Claude Code subagent frontmatter**: markdown uses `tools:` (not `allowed-tools:`); SDK uses `allowedTools`/`allowed_tools`.
13. **MCP stdio logging**: NEVER write to stdout (corrupts JSON-RPC) — use stderr or file logging.
14. **Playwright dialog handler**: register BEFORE the triggering action; once registered, MUST accept/dismiss or page freezes.
15. **PyJWT algorithms list**: always hardcoded; never derive from token (RFC 8725 §2.1 / `none`-algorithm attack).
16. **OpenFeature Python → Unleash**: no official provider as of May 2026 — write custom or use flagd intermediary.
17. **pgvectorscale registered name**: `vectorscale` not `pgvectorscale` in CREATE EXTENSION.
18. **ParadeDB removed pgvectorscale from its bundle**: need a custom Docker image to combine all three.
19. **1M context beta retired April 30, 2026**: use Sonnet 4.6 / Opus 4.6 native 1M instead; no beta header.
20. **Claude Agent SDK uses anyio.run, not asyncio.run**.

---

## RECOMMENDATIONS

**Stage 1 (Days 1-3, Phase 0):**
1. Build the custom `bountystrike/postgres:17-vectorscale-bm25` image first — every other component depends on it. Validate three CREATE EXTENSIONs in one DB.
2. Wire LiteLLM v1.86.1 with the corrected DeepSeek pricing from Track B.
3. Generate the RS256 keypair, commit pubkey, SOPS-encrypt privkey with age — this is the linchpin of scope enforcement.
4. Defer OpenFeature → Unleash provider decision; ship Phase 1 with a stub provider, revisit in Phase 2.

**Stage 2 (Days 4-10, Phase 1.1 + 1.2):**
5. Hatchet Lite up via docker-compose; smoke-test the `@hatchet.task()` example.
6. R2 bucket via Cloudflare dashboard; boto3 pinned `<1.36`.
7. Scope ingestion: arkadiyt first (zero auth, immediate value), then projectdiscovery, then bbscope v2.
8. HackerOne `structured_scopes` + `scope_exclusions` merge. Test against a public program (e.g., HackerOne's own `security`).

**Stage 3 (Days 11-21, Phase 1.3 — the moat):**
9. XSS oracle FIRST (least sandbox complexity).
10. SSRF oracle with self-hosted `interactsh-srv` on a controlled subdomain.
11. Welch's SQLi oracle with Hypothesis property tests (synthesize timing distributions; verify FP rate < 1%).
12. Open-redirect + SSTI (~1 day each).
13. The "no verification, no submission" CHECK constraint + INSERT trigger.

**Stage 4 (Days 22-28, Phase 1.4):**
14. Custom recon-MCP with token-bucket + scope-JWT verification.
15. Recon subagent (`.claude/agents/recon-agent.md`, model `claude-haiku-4-5`).
16. E2E smoke test: scope ingestion → recon → verifier → evidence store.

**Benchmarks that would change the plan:**
- Hatchet Lite p50 latency > 200ms under 100 RPS load → swap to full Hatchet (RabbitMQ) docker-compose.
- R2 free-tier Class A ops exceeded in dev → R2 paid tier ($0.015/GB/mo) before evaluating S3/B2 alternatives.
- pgvectorscale + pg_search co-residency causes > 10% query latency regression vs vector-only → split into two Postgres instances.
- HackerOne adds a mandatory CVSS-4.0 severity flag (already an accepted method per 2026-04-13 changelog) → update finding submission schema before launch.

---

## CAVEATS

1. **DeepSeek pricing volatility:** the V4 Pro 75%-off promo expires **2026-05-31 15:59 UTC.** Hardcoded LiteLLM pricing will silently overcharge tracking the day after. Mitigation: daily cron that re-fetches `api-docs.deepseek.com/quick_start/pricing` and updates config.yaml.
2. **Claude Code velocity:** v2.1.89 is current as of cutoff but v2.2 may ship mid-Phase-1. Pin via `claude --version` in CI; hook fails build if `< 2.1.89`.
3. **Hatchet Python v1 SDK is still marked "alpha"** on PyPI (`hatchet_sdk-1.33.5`). Production-ready for our usage pattern but be aware of churn risk. Fallback: legacy `hatchet-v1` repo (separate from `hatchet-dev/hatchet`), MIT.
4. **OpenFeature → Unleash gap in Python is real.** Plan an internal provider as a deliverable, not a dependency.
5. **The "one-shot" framing is optimistic.** Realistically the agent will need 2-4 `--resume` checkpoints across the 28-day phase to handle: (a) external secret material (API keys, interactsh server domain ownership), (b) human review at the structured_scopes + scope_exclusions merge task (program-policy-dependent semantics), (c) calibration of Welch's t-test against a real testbed. Design the task graph so each checkpoint boundary is a natural human gate ("all secrets gathered", "all scope ingestion green", "all verifiers passing self-test").
6. **The pgvectorscale benchmark (28×/16×/75%) is vendor-produced** by TigerData/Timescale on 50M Cohere 768-dim vectors at 99% recall on AWS EC2. Do not cite as independent third-party validation; treat as directional only.
7. **AGPLv3 compliance:** every file in `packages/community/**` must carry the AGPL-3.0 header; root NOTICE lists third-party dependencies and their licenses. Apache-2.0 ↔ AGPL-3.0 boundary at `core/` ↔ `community/` must be enforced by an ESLint rule + a pre-commit hook that rejects imports from `community` into `core`.