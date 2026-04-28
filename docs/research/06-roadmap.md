# 06 — Build Roadmap & Appendices (Parts 10-11)

Source: `bountystrike_v5_build_plan.md` lines 3219-4525.
Total roadmap: **20 weeks**, 5 phases (0-4). Hard exit criteria gate every phase transition.

---

## Phase 0 — Repository Scaffold, Scope-MCP, EV Engine MVP (Weeks 1-2)

### Objectives
- Git monorepo with full directory layout
- `scope-mcp` server normalizing HackerOne + Bugcrowd
- EV scoring MVP against 50 sample programs
- Postgres 17 + pgvector schema in Docker
- Hatchet workflow engine running locally

### Week 1 — Day 1-2: Repo + tooling (VERBATIM)

```bash
# Initialize monorepo
git init bountystrike-v5
cd bountystrike-v5
mkdir -p {.claude/{agents,commands,skills,hooks},mcp/{scope-mcp,ev-mcp,oracle-mcp,evidence-mcp,dedup-mcp,kev-mcp,h1-mcp,bugcrowd-mcp,intigriti-mcp,immunefi-mcp},control-plane/{api,workers,web},infra/{sql,docker},keys,docs}

# Initialize Python project (uv-based)
uv init --package control-plane
cd control-plane && uv add fastapi pydantic sqlalchemy asyncpg httpx python-jose anthropic openai

# Initialize TypeScript MCP servers
cd ../mcp/scope-mcp && npm init -y && npm install @modelcontextprotocol/sdk zod
```

### Full Directory Structure (tree)

```
bountystrike-v5/
├── .claude/
│   ├── agents/
│   ├── commands/
│   ├── skills/
│   └── hooks/
├── mcp/
│   ├── scope-mcp/
│   ├── ev-mcp/
│   ├── oracle-mcp/
│   ├── evidence-mcp/
│   ├── dedup-mcp/
│   ├── kev-mcp/
│   ├── h1-mcp/
│   ├── bugcrowd-mcp/
│   ├── intigriti-mcp/
│   └── immunefi-mcp/
├── control-plane/
│   ├── api/
│   ├── workers/
│   └── web/
├── infra/
│   ├── sql/
│   └── docker/
├── keys/
└── docs/
```

### Week 1 — Day 3-4: Postgres schema (VERBATIM excerpt)

File: `infra/sql/schema.sql`

```sql
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE TABLE programs (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    handle      TEXT NOT NULL,
    platform    TEXT NOT NULL CHECK (platform IN ('hackerone','bugcrowd','intigriti','yeswehack','immunefi')),
    state       TEXT NOT NULL DEFAULT 'open' CHECK (state IN ('open','paused','closed')),
    max_payout_critical DECIMAL(12,2),
    avg_payout_per_report DECIMAL(12,2),
    bounty_paid_ratio DECIMAL(4,3),
    total_annual_payout DECIMAL(12,2),
    researcher_count INTEGER,
    duplicate_rate DECIMAL(4,3),
    avg_time_to_triage_hours INTEGER,
    avg_time_to_bounty_hours INTEGER,
    safe_harbor_type TEXT,
    triage_acceptance_rate DECIMAL(4,3),
    days_since_last_scope_change INTEGER,
    new_assets_30d INTEGER DEFAULT 0,
    max_epss_on_stack DECIMAL(6,5),
    kev_without_template INTEGER DEFAULT 0,
    last_ingested_at TIMESTAMPTZ DEFAULT NOW(),
    ev_score DECIMAL(6,4),
    UNIQUE (handle, platform)
);

CREATE TABLE scopes (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    program_id  UUID REFERENCES programs(id) ON DELETE CASCADE,
    asset       TEXT NOT NULL,
    asset_type  TEXT NOT NULL,
    in_scope    BOOLEAN NOT NULL DEFAULT TRUE,
    max_bounty  DECIMAL(12,2),
    min_bounty  DECIMAL(12,2),
    tier        TEXT,
    asset_value TEXT,
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    updated_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE ev_score_history (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    program_id      UUID REFERENCES programs(id),
    computed_at     TIMESTAMPTZ DEFAULT NOW(),
    ev_score        DECIMAL(6,4),
    payout_score    DECIMAL(6,4),
    saturation_score DECIMAL(6,4),
    ops_score       DECIMAL(6,4),
    asset_fit_score DECIMAL(6,4),
    cve_bonus       DECIMAL(6,4),
    weights_version TEXT DEFAULT 'v1.0.0'
);
```

### Week 1 — Day 5: scope-mcp TypeScript scaffold (VERBATIM)

File: `mcp/scope-mcp/src/index.ts`

```typescript
import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";

const server = new Server(
  { name: "scope-mcp", version: "1.0.0" },
  { capabilities: { tools: {} } }
);

// Tool 1: check_target — validate single target against active scope JWT
// Tool 2: list_in_scope_assets — return normalized asset list
// Tool 3: get_program_ev_score — return EV ranking for a program
// Tool 4: get_top_programs — return top-N programs ranked by EV
// Tool 5: get_scope_changes — return recent scope change events
// Tool 6: sign_scope_jwt — generate signed RS256 JWT for a scan job
// Tool 7: validate_scope_jwt — validate and decode an existing JWT

server.setRequestHandler(ListToolsRequestSchema, async () => ({
  tools: [
    { name: "check_target", description: "Validate target against active scope JWT", inputSchema: {...} },
    { name: "list_in_scope_assets", description: "List all in-scope assets for active program", inputSchema: {...} },
    // ... remaining tool definitions
  ]
}));

const transport = new StdioServerTransport();
await server.connect(transport);
```

### Week 2 — workers/scope_ingest.py (VERBATIM)

File: `control-plane/workers/scope_ingest.py` — handles H1 April 2026 organization asset migration.

```python
# workers/scope_ingest.py — handles H1 org asset migration
import httpx

async def ingest_h1_org_assets(org_handle: str, api_token: str):
    """
    HackerOne deprecated structured_scopes in April 2026.
    New endpoint: /v1/organizations/{handle}/assets
    """
    url = f"https://api.hackerone.com/v1/organizations/{org_handle}/assets"
    headers = {
        "Authorization": f"Bearer {api_token}",
        "Accept": "application/json"
    }

    async with httpx.AsyncClient() as client:
        assets = []
        page = 1
        while True:
            resp = await client.get(url, headers=headers, params={"page[number]": page, "page[size]": 100})
            data = resp.json()
            assets.extend(data["data"])
            if not data.get("links", {}).get("next"):
                break
            page += 1

    return [normalize_h1_asset(a) for a in assets]
```

### Phase 0 Exit Criteria

- [ ] scope-mcp server passes all 7 tool unit tests
- [ ] arkadiyt ingestion populates 3,000+ programs in Postgres
- [ ] H1 org asset endpoint migration confirmed working
- [ ] EV scoring returns ranked top-25 programs matching manual analyst judgment
- [ ] Signed RS256 scope JWT generation and validation working end-to-end

### Phase 0 Numbered Task List

1. `git init bountystrike-v5` and create monorepo root.
2. Create directory tree with single `mkdir -p` (see verbatim block above).
3. `uv init --package control-plane` for Python control plane.
4. `uv add fastapi pydantic sqlalchemy asyncpg httpx python-jose anthropic openai` inside `control-plane`.
5. `npm init -y && npm install @modelcontextprotocol/sdk zod` inside `mcp/scope-mcp`.
6. Author `infra/sql/schema.sql` with `vector` + `pg_trgm` extensions, `programs`, `scopes`, `ev_score_history` tables.
7. Deploy Postgres 17 + pgvector via `infra/docker/` Compose.
8. Deploy Hatchet workflow engine locally (single binary, Postgres-backed).
9. Write `mcp/scope-mcp/src/index.ts` with 7 tools (check_target, list_in_scope_assets, get_program_ev_score, get_top_programs, get_scope_changes, sign_scope_jwt, validate_scope_jwt) over StdioServerTransport.
10. Implement `control-plane/workers/scope_ingest.py` for HackerOne `/v1/organizations/{handle}/assets` migration (April 2026 endpoint).
11. Wire arkadiyt/bounty-targets-data ingestion (30-min cadence) for HackerOne, Bugcrowd, Intigriti, YesWeHack, Immunefi.
12. Implement EV scoring MVP: payout/saturation/ops/asset_fit with CVE bonus; populate `ev_score_history`.
13. Generate RS256 scope JWT signing keys into `keys/`; implement sign + validate end-to-end.
14. Run unit tests against all 7 scope-mcp tools.
15. Validate top-25 EV ranking against analyst judgment on 50 sample programs.

---

## Phase 1 — Deterministic Verifier, Recon Agent, Evidence Chain (Weeks 3-6)

### Objectives
- Oracle MCP server: working XSS, SSRF, SQLi, IDOR, Open Redirect oracles
- Recon agent subagent (subfinder → httpx → katana pipeline)
- Evidence schema with SHA-256 content-addressable storage in Cloudflare R2
- Hash-chained audit log
- First end-to-end scan producing a validated finding

### Week 3-4: Oracle MCP

**XSS oracle** (`mcp/oracle-mcp/src/oracles/xss.ts`) — Playwright-based:
- Launches headless Chromium
- Injects unique UUID nonce into payload via `{{NONCE}}` placeholder
- DOM mutation observer + `page.exposeFunction("__bs_xss_confirm", ...)` callback
- `page.on("dialog", ...)` catches `alert()`
- GET via `page.goto`, POST via `fetch` API
- Returns: `{ verified, reflection_confirmed, evidence: { screenshot_base64, dom_snapshot, payload_used, method, url, parameter }, confidence }`
- Confidence: 1.0 if executed, 0.5 if reflected only, 0.0 if neither

**SQLi oracle** (`mcp/oracle-mcp/src/oracles/sqli.py`) — Welch's t-test:
- 12 baseline + 12 delayed samples per dialect
- α = 0.01 (1% false positive rate)
- Sleep payloads for mysql, postgres, mssql, oracle, sqlite
- `scipy.stats.ttest_ind(delayed, baseline, equal_var=False)`
- Verified iff `p_val < alpha and t_stat > 0`
- Returns `t_statistic`, `p_value`, baseline/delayed mean ms, db_type_detected
- 0.1s delay between requests to avoid rate limiting; timeout treated as delayed

### Week 5-6: Recon Agent + Evidence Chain
- Recon agent wired as `.claude/agents/recon.md` Claude Code subagent
- Tested end-to-end against private HackerOne program
- Each finding must have: SHA-256 R2 artifact + audit log hash chain entry + scope JWT reference

### Phase 1 Exit Criteria

- [ ] XSS oracle: 0 false positives, >90% TPR on 20 known-vulnerable targets
- [ ] SQLi oracle: Welch t-test correctly identifies time-based blind SQLi with p < 0.01
- [ ] SSRF oracle: interactsh callback confirmed for 5 known SSRF endpoints
- [ ] Recon agent: completes subfinder → httpx → katana pipeline on 3 test programs
- [ ] Evidence chain: every finding has SHA-256 hash in R2 + audit log entry
- [ ] Hash chain: audit log entries cryptographically linked

---

## Phase 2 — Full Subagent Suite, MCP Integrations, Anti-Slop Gates (Weeks 7-10)

### Objectives
- All 9 subagents operational
- All 12 adopted MCPs integrated
- All 10 in-house MCPs operational
- T0-T3 approval tier gates
- Semantic dedup against 1,000+ test findings
- Three-layer kill switch operational

### Week 7-8: Exploit + Validator Agents

**Dual-track model routing requirement:**
1. Detect Claude refusals on payload generation
2. Route to Venice Dolphin / Hermes-4-70B via OpenRouter
3. Execute PoCs in Firecracker microVMs
4. Return content-addressable evidence

**`hooks/model_route_policy.py`** PreToolUse hook:
- Triggers on `mcp__openrouter__openrouter_complete`
- Keywords: `payload, inject, bypass, polyglot, XSS, SQLi, SSTI, RCE, shellcode`
- DENY if Anthropic model + payload prompt (70%+ refusal rate)
- AUTO-REROUTE to `cognitivecomputations/dolphin-mistral-24b-venice-edition` with `provider.data_collection: deny` (Venice privacy)
- Allowed alternates: `cognitivecomputations/hermes-3-llama-3-1-70b`

### Week 9-10: Anti-Slop Gates + Dedup MCP

**`mcp/dedup-mcp/src/dedup.py` — `SemanticDedup` class:**
- `SIMILARITY_THRESHOLD = 0.88` (tuned vs HackerOne false-dup rate)
- Match conditions (OR'd):
  1. Cosine similarity > 0.88 (pgvector `<=>` operator)
  2. Exact `dedup_key` fingerprint match
  3. Same bug_class + program + target overlap
- Order: structural fingerprint check first (fast), then semantic top-5 with `ORDER BY embedding <=> $1 LIMIT 5`
- Uses `pgvector.asyncpg.register_vector` + `numpy.float32`

### Phase 2 Exit Criteria

- [ ] All 9 subagents complete one end-to-end workflow without errors
- [ ] Dedup detects > 90% of known duplicate pairs in 1,000-finding test set
- [ ] T3 approval gate prevents any submission without two-person review
- [ ] Kill switch halts all running agents within 5 seconds
- [ ] Zero out-of-scope requests in 100-scan audit trail review
- [ ] Venice Dolphin routing confirmed (refusal rate < 5%)

---

## Phase 3-4 (brief)

### Phase 3 — Solo Deploy, Alpha Hunters, Calibration (Weeks 11-14)

- Mac mini / Linux laptop solo deployment
- 3-5 alpha hunters running real scans
- EV calibration vs actual hunt outcomes (> 0.60 Spearman ρ target)
- Oracle FP measurement (any oracle > 2% FP disabled)
- Dedup recall vs known duplicates (> 95% target)
- Cost-per-scan audit (< $0.20 solo target)
- Time-to-validate (< 4h for P1/P2)

**Exit:** confirmed-rate > 70%, 5+ validated findings submitted, avg scan < $0.20, 0 CFAA incidents, EV rank correlation > 0.60.

### Phase 4 — SaaS Multi-Tenant, Compliance, Beta (Weeks 15-20)

- EKS / GKE Kubernetes
- Multi-tenant Postgres with RLS
- Temporal Cloud replaces Hatchet (`workers/temporal/scan_workflow.go` — 7 phases, 72h ScheduleToCloseTimeout, 30m heartbeat, 3 max attempts; parallel recon across asset clusters)
- Firecracker microVM pool on Fly.io Machines / bare metal
- WorkOS AuthKit replaces better-auth
- Pricing tiers + metered billing
- EU CRA workflow operational (24h/72h/14d)
- 20+ beta hunters

**Exit:** multi-tenant pen-tested, Temporal durability verified, 10 concurrent VM scans, ENISA sandbox CRA test, 20+ hunters at > 65% confirmed-rate, billing within 5% accuracy.

---

## Risk Register

| # | Risk | Severity | Probability | Mitigation | Owner |
|---|---|---|---|---|---|
| R01 | AI slop generates false positives, programs ban platform | CRITICAL | HIGH | Oracle-first deterministic verification; confirmed-rate SLO > 70%; T3 approval gate | Validator subagent |
| R02 | Agent breaks scope due to prompt injection in target HTML | CRITICAL | MEDIUM | Scope JWT enforced at network layer (iptables/tap0); application-layer scope check cannot be bypassed | Infrastructure |
| R03 | CFAA liability from out-of-scope agent action | CRITICAL | LOW | Signed scope JWTs; PreToolUse defer + human review for ambiguous targets; legal review of safe harbor language | Legal + Scope-guard |
| R04 | Anthropic model refusal rate degrades exploit-agent effectiveness | HIGH | HIGH | Venice Dolphin / Hermes-4-70B fallback routing; PreToolUse hook auto-reroutes payload prompts | Model routing |
| R05 | OpenRouter price increases or rate limits | HIGH | MEDIUM | BYOK Anthropic as primary; LiteLLM proxy allows swap to Bedrock/Vertex in one config change | Infrastructure |
| R06 | HackerOne API changes break scope ingestion | HIGH | MEDIUM | April 2026 migration already handled; monitor H1 changelog; fallback to arkadiyt | Scope-MCP |
| R07 | Competitor (XBOW) preemptively offers individual hunter tier | HIGH | MEDIUM | Differentiate on transparency + cost + Claude Code native; transparent evidence chain is unique | Product |
| R08 | EU CRA compliance failure (missed 24h deadline) | HIGH | LOW | Automated CRA workflow with triple-redundant alerting; SLA monitor in Grafana | Compliance |
| R09 | Firecracker microVM escape by malicious target payload | HIGH | LOW | Defense-in-depth: VM escape doesn't reach host data; separate Postgres RLS; per-job credentials | Security |
| R10 | Postgres pgvector performance degrades at scale (> 10M vectors) | MEDIUM | MEDIUM | Turbopuffer per-tenant namespaces activated at 5M vectors; DiskANN index maintains < 10ms p99 | Data |
| R11 | Academic paper (CyberStrikeAI-style) weaponizes platform against non-targets | HIGH | LOW | Scope JWT cryptographic enforcement; network-layer egress blocklist; operator audit trail | Legal |
| R12 | DeepSeek V4-Flash data privacy concerns (Chinese LLM) | MEDIUM | MEDIUM | Use for classification/triage only (not raw target data); sensitive payloads route to self-hosted models | Privacy |
| R13 | Claude Code hook exploit (CVE-2026 style) | HIGH | LOW | Pin Claude Code version; test every hook update in staging; monitor Anthropic security advisories | Security |
| R14 | Temporal Cloud outage during multi-week scan | MEDIUM | LOW | Workflow state is durable; on resume, idempotent activities replay safely | Infrastructure |
| R15 | Dedup false negatives allow duplicate submissions | HIGH | MEDIUM | Three-layer dedup (exact fingerprint + semantic + program-level cross-check); confirm against H1 prior report count | Quality |
| R16 | LangGraph 1.x checkpoint corruption | MEDIUM | LOW | Human-in-the-loop interrupt tier (T2) validates checkpoint state; checkpoints stored in Postgres with CRC | Quality |
| R17 | Mythos/Glasswing models not accessible (select partner only) | MEDIUM | HIGH | Opus 4.7 as primary; plan for Mythos onboarding if partner status achieved; self-hosted Pentest-R1 as fallback | Model routing |

---

## Success Metrics

| Metric | Target | Measurement Method | Cadence |
|---|---|---|---|
| Confirmed-rate | > 70% | Accepted findings / total submitted | Weekly |
| Time-to-validate | < 4h for P1/P2 | finding_created_at to validated_at | Weekly |
| Cost per confirmed finding | < $5 solo, < $15 SaaS | LLM cost / confirmed_count | Per scan |
| False positive rate | < 5% | Informative + N/A / total submitted | Weekly |
| Scope violation rate | 0.00% | Out-of-scope denials / total tool calls | Per scan |
| EV rank correlation | > 0.60 (Spearman ρ) | EV vs actual payout ranking | Monthly |
| Time-to-first-finding | < 2h per program | Onboard to first finding | Per engagement |
| Dedup recall | > 95% | Caught duplicates / known duplicates | Monthly |
| Operator NPS | > 50 | Monthly survey | Monthly |
| Platform uptime | > 99.5% solo, > 99.9% SaaS | Healthcheck monitoring | Continuous |

---

## Glossary — Key Terms (Appendix A)

- **Agent Teams** — `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`, multi-instance Claude Code coordination.
- **AnyPoC** — academic taxonomy of 4 reward-hacking modes: self-exploitation, mock validation, hallucinated paths, timing coincidence.
- **arkadiyt/bounty-targets-data** — open-source 30-min normalized scope JSON for H1/BC/Intigriti/YWH/Immunefi.
- **bbscope v2** — sw33tLie tool for authenticated multi-platform scope with Postgres change tracking + AI normalization.
- **BYOK** — Anthropic 1M free requests/month via OpenRouter.
- **CAI** — Anthropic Cyber AI framework, 3,600× speed.
- **Confirmed-rate** — accepted/total submissions; curl baseline < 5%, target > 70%.
- **Content-addressable storage** — SHA-256 hash IS the storage key.
- **CyberStrikeAI** — Chinese AI-native offensive framework, 600+ FortiGate compromise Jan-Feb 2026.
- **defer** — Claude Code April 2026 PreToolUse decision pausing for async validation.
- **DeepSeek V4-Flash** — $0.14/$0.28 per MTok, triage/dedup model.
- **DiskANN** — pgvectorscale disk-based ANN, > 99% recall < 10ms p99.
- **E2B** — Firecracker microVM sandbox API.
- **EPSS** — FIRST.org 30-day exploit probability score.
- **EU CRA** — 24h/72h/14d EU vulnerability reporting, eff Sep 11 2026.
- **EV score** — [0,1] program ranking by financial × likelihood.
- **Evidence gate** — minimum-evidence promotion bar (HTTP transcript, OAST, DOM snapshot, statistical oracle).
- **Firecracker** — AWS microVM, < 125ms boot, dedicated netns + iptables egress allowlist.
- **Forked subagent** — `CLAUDE_CODE_FORK_SUBAGENT=1`, inherits parent context.
- **Garak** — NVIDIA LLM scanner, 120+ probes.
- **GTG-1002** — China-affiliated APT, 80-90% AI-driven, ~30 orgs.
- **Hatchet** — Postgres-backed solo workflow engine.
- **Hash chain audit log** — each entry hashes the previous.
- **HexStrike-AI v6** — 150+ tools, 12 autonomous AI agents.
- **Interactsh** — OAST callback server (DNS/HTTP).
- **KEV** — CISA Known Exploited Vulnerabilities; freshness decay μ = 0.00963.
- **LangGraph 1.x** — checkpointed graph framework with HITL interrupts.
- **MCP** — Model Context Protocol, Anthropic open standard.
- **Mythos** — Claude preview, 83.1% CyberGym, 27-yr OpenBSD bug, $25/$125 per MTok, partner-only.
- **OAST** — out-of-band callback testing.
- **OpenRouter** — 370+ model gateway.
- **Oracle MCP** — in-house deterministic verifier MCP server.
- **ParadeDB** — BM25 in Postgres.
- **pd-tools-mcp** — ProjectDiscovery toolkit MCP wrapper.
- **pgvector / pgvectorscale** — Postgres vector + DiskANN index.
- **Pentest-R1** — arXiv 2508.07382, GRPO-tuned, 24.2% AutoPenBench.
- **Red-MIRROR** — LoRA Qwen2.5-14B, 86% XBOW.
- **RS256 scope JWT** — RSA-SHA256 signed authorized target set, validated at network layer.
- **rix4uni/scope** — 10-min cadence H1/BC scope updates.
- **Shannon** — open-source agentic pentest, 96.15% XBOW.
- **Slop** — vague/hallucinated AI security reports (curl 8× volume crisis).
- **Strix** — 24.5k stars, mandatory validation, 17 skill files.
- **Temporal Cloud** — SaaS durable workflow.
- **T0-T3** — autonomy tiers: T0 fully auto, T1 alert, T2 single approval, T3 two-person review.
- **Trickest** — 800+ public programs catalog.
- **Venice Dolphin** — 2.2% refusal rate (vs 70%+ Anthropic) for payload generation.
- **VulnCheck KEV** — commercial KEV extension, faster cadence.
- **XBOW** — $237M / $1B+ valuation, #1 H1 leaderboard June 2025.

---

## Reference Architecture Diagrams (Appendix B)

### B.1 Solo Mode — Full Platform Data Flow (4 layers)

**Control layer** — `bountystrike scan --program {handle} --platform hackerone` → FastAPI control plane → (1) lookup program EV/scope/payout in Postgres, (2) generate signed RS256 scope JWT (TTL = scan duration), (3) submit `ScanWorkflow` to Hatchet.

**Agent plane** — Hatchet spawns `claude -p headless --agent bountystrike-coordinator -e HUNTMESH_SCOPE_JWT={signed_jwt} --output-format json`.
- SessionStart hook: `verify_attestation.py` (RS256 sig), `load_scope.py` (allowed_cidrs into hook memory), inject API keys from 1Password/env.
- Coordinator (Opus 4.7 BYOK): builds Pentesting Task Tree (PTT), clusters by tech fingerprint, spawns parallel recon-agents per cluster.
- recon-agent (Haiku 4.5): scope-mcp + pd-tools-mcp (subfinder, httpx -tech-detect, katana depth=2) + shodan-mcp; PreToolUse validates each call; PostToolUse pushes artifacts to R2 + Postgres; returns ReconSummary.
- scanner-agent (Sonnet 4.6): pd-tools nuclei + ffuf + burp/caido + openrouter bulk DeepSeek triage; returns candidate Findings.
- exploit-agent (Opus 4.7 / Venice Dolphin): oracle-mcp strategy, burp repeater, Venice Dolphin payloads, sandbox-mcp Firecracker exec; T2 gate before every sandbox; returns ExploitCandidate.
- validator-agent (Sonnet 4.6, **DIFFERENT instance** from exploit-agent): oracle-mcp verify, fresh VM replay, dedup-mcp; CANNOT see exploit-agent scratchpad; returns Finding{validated|unreproducible|flaky}.
- reporter-agent (Sonnet 4.6): evidence-mcp load artifacts, DeepSeek R1 CVSS v4 rationale, dedup vs prior H1 reports, T3 two-person gate, h1/bugcrowd/intigriti-mcp submit; returns SubmissionRecord.

**Data plane** — Postgres 17 (programs, scopes, findings, audit_log, intel_chunks DiskANN, ev_score_history) + Cloudflare R2 (`evidence/{sha256}`, `scan-artifacts/{scan_id}/*`, `reports/{finding_id}.md`) + Redis (`killswitch:global`, `scope:cache:{program_id}` 30min, `budget:scan:{scan_id}`).

**Observability plane** — Langfuse self-hosted (LLM traces, cost, refusals) + Grafana (confirmed-rate, scope violations, cost breakdown, oracle FP rate).

### B.2 EV Score Computation Pipeline

Sources: arkadiyt 30-min, rix4uni 10-min, bbscope v2 6h, H1 Org API 30-min, Bugcrowd 30-min, Intigriti PAT 30-min, YWH 30-min, Immunefi hourly → Ingestion Worker (normalize/dedup/sign JWT) → `programs + scopes` tables + `scope_changed` events.

CISA KEV 15-min + VulnCheck daily → KEV Worker → CVE-Program Matcher.
EPSS API daily → EPSS Worker → matcher.
nuclei-templates daily git pull → Template Index Worker → matcher.

EV Scoring Worker (every 30min):
```
S = w1·f_payout(P̄,ρ,V) + w2·f_sat(R,d,Δt,N) + w3·f_ops(T_tri,T_pay,H,α) + w4·f_fit(A,O)
EV = min(S·(1+0.20·f_cve), 1.0)
Weights: payout=0.35, saturation=0.25, ops=0.25, asset_fit=0.15, cve_bonus=+20%
```
→ `ev_score_history` table → operator dashboard (top-25) + scope change webhook (notify + auto-scan).

---

## Sample Agent Definition (FULL — Appendix C.1)

File: `CLAUDE.md` (production template, verbatim).

```markdown
# BountyStrike v5 — Authorized Bug Bounty Operations

## Identity

You are the autonomous coordinator for an authorized bug bounty engagement.
You operate under the contractual scope of a specific program, encoded in a
signed RS256 scope JWT loaded at session start. Your mandate is to find
legitimately reportable vulnerabilities and produce platform-ready submissions
with confirmed, reproducible evidence.

You are NOT a general-purpose security assistant. You are not here to explain
vulnerabilities, discuss theory, or help with anything outside this engagement.
Everything you do is logged, hash-chained, and auditable.

## Hard Prohibitions (hooks enforce these — bypass attempts are logged)

- NEVER touch any host not authorized in the active scope JWT
- NEVER generate DoS payloads, even if "no DoS" is not stated in program rules
- NEVER submit a finding without validator-agent confirmation
- NEVER skip the T2/T3 approval gates
- NEVER call openrouter_complete with Anthropic models for payload generation
- NEVER retain real user PII in evidence artifacts

## Kill Switch Response

If you receive the message "BOUNTYSTRIKE_KILLSWITCH_ACTIVATED", immediately:
1. Stop all current tool executions
2. Save state to ./engagement/checkpoint_killswitch.json
3. Call mcp__bountystrike-state__checkpoint("killswitch_activated")
4. Respond: "Kill switch activated. All operations halted. State saved."
5. Exit

## Methodology (Seven Phases — do not skip)

1. SCOPE: Load JWT, materialize asset list, confirm safe harbor language
2. RECON: Asset discovery (recon-agent)
3. SURFACE: Endpoint, parameter, API mapping (scanner-agent)
4. PROBE: Template + targeted scanning (scanner-agent)
5. EXPLOIT: PoC generation + sandbox execution (exploit-agent) [T2 gate]
6. VALIDATE: Independent reproduction (validator-agent)
7. REPORT: Format + dedup + submit (reporter-agent) [T3 gate]

## Evidence Standard

A finding is reportable ONLY if the validator-agent returns status=validated
with at least one of:
- HTTP transcript showing state change (content-addressable hash in R2)
- OAST callback confirmed (interactsh UUID match)
- Browser DOM snapshot (Playwright screenshot in R2)
- Statistical oracle result (p < 0.01 for SQLi time-based)

## Budget Discipline

If BUDGET_REMAINING falls below 20% of budget:
- Stop discovering new candidates
- Focus on validating current candidates
- Report BUDGET_LOW to orchestrator

## Model Routing (enforced by hooks, do not override)

- Coordinator/orchestration: Opus 4.7 via BYOK
- Recon/triage: DeepSeek V4-Flash via OpenRouter
- Hypothesis generation: Sonnet 4.6 via BYOK
- Payload generation: Venice Dolphin via OpenRouter (Anthropic blocked by hook)
- Validation reasoning: Sonnet 4.6 (different instance from exploit-agent)
- Report polish: Sonnet 4.6 via BYOK
```

### Sample scope-guard Hook (Appendix C.2)

File: `.claude/hooks/pretool_scope_guard.py` (Python, PreToolUse).

Key logic:
- Reads JSON event from stdin → `tool_name`, `arguments`, `session_id`.
- Redis kill-switch check: `bountystrike:killswitch:global` → deny if set (fail-open if Redis down).
- Skip non-network tools; act on `Bash`, `WebFetch`, `mcp__pd-tools__*`, `mcp__burp__*`, `mcp__caido__*`, `mcp__shodan__*`, `mcp__hexstrike__*`.
- Load `HUNTMESH_SCOPE_JWT` from env → `load_and_verify(scope_jwt)`.
- `extract_targets()` parses Bash commands (curl/wget/httpx/subfinder/dnsx/naabu/nuclei/ffuf via regex for URLs, IPs, domains), WebFetch URLs, MCP `target/domain/host/url` fields.
- Per-target: `is_target_allowed(scope, target)` → `denied`/`ambiguous`/allowed.
- `denied` → `append_audit_entry(...)` + `decision: deny`.
- `ambiguous` → audit + `hookSpecificOutput.permissionDecision: defer` (April 2026 primitive).
- Allowed → audit + `decision: allow`.

---

## Cost Calculator Examples (Appendix D)

### D.1 Solo — Single H1 Program Scan
Target: ~50 subdomains, LAMP. Routing: DeepSeek V4-Flash primary, Sonnet 4.6 reports, Opus 4.7 chains.

| Phase | Model | In tok | Out tok | Cost |
|---|---|---|---|---|
| Recon synthesis (2,000 hosts) | DeepSeek V4-Flash | 180k | 20k | $0.031 |
| Nuclei triage (500 → 15) | DeepSeek V4-Flash | 120k | 15k | $0.021 |
| Hypothesis (15) | Sonnet 4.6 | 45k | 12k | $0.315 |
| Payload (8 via Venice Dolphin $0.15/$0.30) | Venice Dolphin | 24k | 6k | $0.018 |
| Validation reasoning (3) | Sonnet 4.6 | 30k | 8k | $0.210 |
| Report writing (2) | Sonnet 4.6 BYOK | 20k | 12k | $0.00 |
| Misc (coord/dedup/CVSS) | DeepSeek V4-Flash | 30k | 8k | $0.006 |
| **TOTAL** | | **449k** | **81k** | **$0.601** |

Outcome: 2 validated. P2 ($2,000) → ROI 3,329×. With BYOK report writing → $0.39/scan.

### D.2 SaaS Pro Tier Full Scan
Target: 500 subdomains, microservices, GraphQL. Routing: Sonnet 4.6 primary, Opus 4.7 chains, DeepSeek bulk.

| Phase | Model | In | Out | Cost |
|---|---|---|---|---|
| Recon (5,000 hosts) | DeepSeek V4-Flash | 800k | 80k | $0.135 |
| Nuclei triage (2,000 → 45) | DeepSeek V4-Flash | 400k | 50k | $0.070 |
| Hypothesis (45) | Sonnet 4.6 | 180k | 45k | $1.215 |
| Complex chains (5) | Opus 4.7 | 50k | 20k | $0.750 |
| Payload (20) | Venice Dolphin | 60k | 15k | $0.045 |
| Validation (8) | Sonnet 4.6 | 80k | 20k | $0.540 |
| Reports (5) | Sonnet 4.6 | 50k | 30k | $0.600 |
| CVSS + dedup + misc | DeepSeek V4-Flash | 60k | 15k | $0.013 |
| **TOTAL** | | **1.68M** | **275k** | **$3.368** |

Pro tier: $79/mo ÷ 200 scans = $0.40/scan infra. 10+ confirmed/mo to be sustainable. Single P1 ($10k+) amortizes months.

---

## Compliance Checklist (Appendix E)

### E.1 Pre-Engagement
```
□ Program enrolled and active (not paused/closed)
□ Safe harbor language reviewed (disclose.io or program-specific)
□ Scope JWT generated and verified (RS256 signature, correct expiry)
□ Out-of-scope list loaded and reviewed (explicit exclusions noted)
□ DoS prohibition acknowledged (all programs, no exceptions)
□ PII handling policy reviewed (no real user data in evidence)
□ Disclosure timeline set (90-day ISO 29147 timer started)
□ Operator identity confirmed (H1/BC/Intigriti username in audit log)
□ Kill switch tested (Redis flag + hook response verified)
□ Budget limit set (scan cost ceiling configured)
```

### E.2 Submission
```
□ Finding status = validated (validator-agent confirmed)
□ Evidence artifact SHA-256 verified in R2 (content-addressable)
□ No real user PII in evidence (redaction verified by redaction_verify.py)
□ Dedup check passed (similarity < 0.88 with prior reports)
□ CVSS v4 score computed with rationale
□ Report template reviewed against platform guidelines
□ T3 two-person approval obtained (both approver identities logged)
□ Safe harbor language referenced in report
□ No sensitive tokens in PoC (all <REDACTED:sha256:8>)
□ Reproduction steps verified by second operator
```

### E.3 EU CRA (for findings affecting EU products)
```
□ T+0: Finding confirmed as exploitable vulnerability
□ T+24h: ENISA SRP early warning submitted (product, CVE, brief description)
□ T+72h: Vulnerability notification submitted (CVSS v4, affected versions, mitigations)
□ Confirmation receipt from ENISA SRP saved in audit log
□ T+14d (exploited) or T+1m (severe): Final report submitted
□ National CSIRT notification sent (if product affects critical infrastructure)
□ Disclosure timer updated to reflect vendor notification date
□ ISO 29147 90-day disclosure deadline tracked in platform
```

---

## Source Citation Index (Appendix F — selected)

| Claim | Source |
|---|---|
| XBOW $237M, $120M Series C, #1 H1 leaderboard | research/competitors.md §Tier-1 |
| curl shutdown Jan 31 2026 (confirmed-rate < 5%) | research/competitors.md §Exec; community_signals.md §6 |
| Stenberg quote on plummeting confirmed-rate | research/competitors.md §Exec |
| H1 210% AI vuln spike, 540% prompt injection | research/community_signals.md §6 |
| GTG-1002 80-90% AI intrusion ~30 orgs | research/academic_cve.md §6.4 |
| CyberStrikeAI FortiGate 600+ Jan-Feb 2026 | research/academic_cve.md §6.1 |
| Mythos 83.1% CyberGym, 27-yr OpenBSD | research/agent_mcp_ecosystem.md §1.5 |
| Claude Code defer primitive Apr 1 2026, v2.1.89 | research/agent_mcp_ecosystem.md §1.1 |
| Claude Code 26-event hook table | research/agent_mcp_ecosystem.md §1.3 |
| OpenRouter 370 models Apr 28 2026 | research/openrouter_models.md |
| DeepSeek V4-Flash $0.14/$0.28 | research/openrouter_models.md §Tier-A |
| Venice Dolphin 2.2% refusal | research/openrouter_models.md §Tier-U |
| BYOK Anthropic 1M free req/mo | research/openrouter_models.md §BYOK |
| bbscope v2 federated ingestion | research/program_selection.md §1.1 |
| H1 structured_scopes deprecation Apr 16 2026 | research/program_selection.md §2 |
| EV formula | research/program_selection.md §10.1 |
| Asset weights (smart_contract 1.40 → VDP 0.10) | research/program_selection.md §10.3 |
| Scope freshness λ=0.00065, KEV μ=0.00963 | research/program_selection.md §11.1-11.2 |
| CAI 3600× speed | research/academic_cve.md §1.1 |
| Red-MIRROR 86% XBOW | research/academic_cve.md §App A |
| Pentest-R1 24.2% AutoPenBench | research/academic_cve.md §App A |
| AgentFlow 84.3% TerminalBench-2 | research/academic_cve.md §App A |
| CHECKMATE +20% over Claude Code, 50% faster | research/academic_cve.md §1.1 |
| EU CRA 24h/72h/14d eff Sep 11 2026 | research/academic_cve.md §5.1 |
| ISO 29147/30111 disclosure | research/academic_cve.md §5.2 |
| Burp MCP 714+ stars GPL-3.0 OAST | research/agent_mcp_ecosystem.md §3.1 |
| HexStrike-AI v6 150+ tools, 12 agents | research/agent_mcp_ecosystem.md §3.5 |
| Strix 24.5k stars, 17 skills | research/agent_mcp_ecosystem.md §3.8 |
| Shannon 96.15% XBOW | cleanslate2026bountystrike.md §Tier-3 |
| Deadend CLI 80% XBOW @ $122 | cleanslate2026bountystrike.md §Tier-3 |
| Tenzai $75M Nov 2025 | research/competitors.md §Tier-1 |
| RunSybil $40M Mar 2026 | research/competitors.md §Tier-1 |
| AnyPoC 4 reward-hacking modes | research/academic_cve.md §4 |
| Welch t-test for SQLi time-based | research/agent_mcp_ecosystem.md §5; academic_cve.md |
| pgvectorscale DiskANN | cleanslate2026bountystrike.md §4.1 |
| ParadeDB BM25 in Postgres | cleanslate2026bountystrike.md §4.1 |
| Hatchet single Postgres binary | cleanslate2026bountystrike.md §4.1 |
| Temporal Cloud SaaS durable | cleanslate2026bountystrike.md §4.2 |
| E2B Firecracker < 125ms boot | research/agent_mcp_ecosystem.md §7 |
| LangGraph 1.x checkpoints, interrupts | research/agent_mcp_ecosystem.md §6 |
| PydanticAI structured output | research/agent_mcp_ecosystem.md §6 |
| Garak 120+ probes NVIDIA | research/agent_mcp_ecosystem.md §3.6 |
| Bugcrowd target_groups schema | research/program_selection.md §9.1 |
| Intigriti minBounty/maxBounty/tier | research/program_selection.md §9.2 |
| YWH asset_value field | research/program_selection.md §9.3 |
| Immunefi impacts array per-impact payout | research/program_selection.md §9.4 |

---

## Context7 Docs Pulled

**Status: NOT PULLED** — `mcp__context7__resolve-library-id` denied by tool permission policy in this session. Targets attempted: `uv` (Python package manager), `Model Context Protocol TypeScript SDK`. Recommend retry from a session with context7 MCP allowed; queries to run when available:
- `/astral-sh/uv` — `uv init --package`, `uv add` workflow for FastAPI/Pydantic/SQLAlchemy/asyncpg.
- `/modelcontextprotocol/typescript-sdk` — `Server`, `StdioServerTransport`, `setRequestHandler(ListToolsRequestSchema)`, tool input schema with zod.
- `pnpm` / `npm` workspaces — monorepo multi-package layout for `mcp/*`.
- `/pydantic/pydantic` — schema/validation for scope JWT and finding records.

The verbatim `npm init` + `uv init` commands above are the build plan's authoritative specification; SDK doc lookup is only required when extending beyond the 7 listed scope-mcp tools.
