# 01 — Strategy & Architecture (Parts 1-2, lines 1-696)

Source: `bountystrike_v5_build_plan.md`

## Vision & Constraints

Claude Code-native autonomous bug bounty / red team platform. Solo: <$0.20/target, $30/mo infra. SaaS: linear scale. Universal-agent-compatible: Claude Code default, OpenAI Agent SDK first-class alt, LangGraph 1.x / PydanticAI / OpenCode fallbacks. All tools behind open MCP servers.

**Five Non-Negotiables (MUST):**
1. Deterministic verification before submission — hardware-isolated, SHA-256 evidence (XBOW moat; curl shutdown <5% confirmed-rate proves alternative is fatal).
2. Scope enforced at network layer (RS256 JWT at Firecracker tap0 egress) — NOT prompt layer.
3. Economic model works for individuals — DeepSeek V4-Flash for triage, BYOK Anthropic (1M free req/mo).
4. Transparent auditable evidence chain — content-addressable blobs, hash-chained audit log, optional Sigstore Rekor.
5. Federated multi-platform scope — H1 / Bugcrowd / Intigriti / YesWeHack / Immunefi normalized.

**WILL NOT:** black-box opaque model (XBOW); enterprise-only pricing; narrow ICP; prompt-layer scope; non-verified submissions; closed verifier methodology; recursive subagent spawning; LLM-creative validators (echo-chamber).

**Targets:** >70% confirmed-rate (vs XBOW ~25% N/A); beat Shannon's 96.15% XBOW; beat Deadend's $122 / 80%.

## Subagents (9, in `.claude/agents/` markdown + YAML frontmatter)

1. **recon-agent** (Haiku 4.5 / Sonnet 4.6) — Passive + light-active asset discovery. No Bash/Write/Agent.
2. **scope-guard** (Sonnet 4.6) — Resolves PreToolUse `defer`s. Read-only.
3. **program-selector** (Sonnet 4.6) — EV-ranked program recommendations. Read-only.
4. **scanner-agent** (Sonnet 4.6 + DeepSeek V4-Flash bulk triage + Qwen3-Coder templates) — Nuclei/ffuf/sqlmap.
5. **AI-vuln-hunter** (Sonnet 4.6, Opus 4.7 chains) — OWASP LLM Top 10; Garak 120+ probes.
6. **exploit-agent** (Opus 4.7; Mythos partners; OpenRouter Venice Dolphin / Hermes-4 / Qwen3-Coder for refusal-prone payloads) — PoC chain construction. T2 approval per sandbox call.
7. **validator-agent** (Sonnet 4.6 — *intentionally different model from exploit-agent*) — Re-runs PoCs in fresh Firecracker VM with deterministic per-class oracles. No OpenRouter, no creative reinterpretation.
8. **reporter-agent** (Sonnet 4.6 BYOK + prompt caching; Opus 4.7 premium) — CVSS v4, redaction, anti-slop filter, multi-platform submit. T3 two-person approval.
9. **cloud-recon-agent** (Haiku 4.5 → Sonnet 4.6) — AWS/Azure/GCP/K8s; runs parallel to recon when cloud assets in scope.

Rule: one subagent per phase or vuln class — never per tool.

## Message Contracts (Pydantic v2 typed; cross-plane msgs carry crypto identity)

- **ScanJobRequest** (Control → Coord): `job_id, scope_jwt(RS256), program_handle, platform, asset_cluster[], operator_profile{skill_vector, time_budget_hours, cost_budget_usd}, ev_score, priority_classes[]`.
- **ReconResult**: `checkpoint, job_id, hosts[{hostname,ip,tech[],ai_endpoint}], high_priority[], ai_endpoints[], evidence_refs[](sha256:), tokens_used, cost_usd`.
- **FindingCandidate**: `finding_id, job_id, deduplication_key, url, parameter, cwe, provisional_severity, evidence_ref, candidate_for_exploit, scanner_tool, template_id, scope_token`.
- **ValidationResult**: `finding_id, verdict∈{validated|unreproducible|flaky}, oracle_used, oast_callback{type,token,received_from_ip,received_timestamp}, evidence_hash, attempts, cleanup_confirmed, validator_model`.
- **scope-guard verdict**: `{decision, target, reasoning, confidence, audit_ref}`.

## Storage Architecture

**Postgres 17 single-DB-centric** with three extensions:
- **pgvector** — 1536-dim OpenAI `text-embedding-3-large`; semantic dedup `1 - (a <=> b) > 0.85`, experience KB, report similarity.
- **pgvectorscale (DiskANN)** — sub-10ms similarity at 10M+ vectors.
- **ParadeDB / pg_search** — BM25 hybrid; required for exact CVE/product/param lookups.

**Tables:** `programs, scopes, scope_changes, ev_score_history, scan_jobs, findings, evidence_artifacts, audit_log, agent_sessions, model_costs, report_submissions`.

**Evidence store:** Cloudflare R2 (hot) + SeaweedFS / Hetzner (cold). Key `r2://{bucket}/{platform}/{program}/{finding_id}/{sha256_hex}`. Auto-dedup, immutable.

**Hash-chained audit log:** every row has `prev_hash` (BYTEA SHA-256) + `row_hash`. Optional Sigstore Rekor daily root-hash anchoring.

## Sandbox Plane

Three-tier isolation:
- **microsandbox (solo):** gVisor + seccomp; ~50ms boot.
- **Firecracker microVM (SaaS):** KVM; ~125ms boot, ~5MB overhead. Per-job VM destroyed after. Egress controlled by **iptables on tap0 in host kernel** — guest cannot modify. Scope JWT materialized to iptables allow rules at VM boot (only `targets.ips` + Interactsh/Burp Collaborator IPs reachable).
- **E2B (managed):** Firecracker-as-service; bootstraps SaaS pre-bare-metal.

**VM specs:** 1 vCPU, 1GB RAM, 2GB ephemeral disk; read-only rootfs except /tmp.

**In-VM tools:** nuclei, ffuf, feroxbuster, sqlmap, httpx, subfinder, dnsx, naabu, katana, Playwright (headless Chromium), curl, Python 3.12, Node.js 22, jwt-tool, wafw00f, interactsh-client, dalfox, semgrep, trufflehog.

## Orchestration

- **Hatchet (solo):** Postgres-backed single binary, zero extra deps. Cron, fan-out/fan-in, durable state, typed step IO. Workflows: `ScopeIngest, EVRanker, ScanJob, TriageJob, ReportJob`.
- **Temporal Cloud (SaaS):** Drop-in upgrade — multi-tenant namespaces, geo continuations, workflow versioning, SLAs. SDK call-compatible.
- **LangGraph 1.x:** Checkpoints + interrupts at T2/T3 approval gates — saves to Postgres, suspends, resumes after operator approval.
- **26-event Claude Code hook stack** (v2.1.89+): `defer` PreToolUse decision, `PermissionDenied` retry, Agent Teams lateral comms, forked subagents w/ conversation inheritance. Exit-code-enforced policy, not prompt-level.

## Tech Stack

**Agent runtimes/SDKs:** Claude Code v2.1.89+; Claude Agent SDK; OpenAI Agents SDK; LangGraph 1.x; PydanticAI; OpenCode.

**Models:** Claude Opus 4.7 / Sonnet 4.6 / Haiku 4.5 / Mythos Preview ($25/$125 Mtok); DeepSeek V4-Flash ($0.14/$0.28, cache-hit $0.0028 input) (per api-docs.deepseek.com; see docs/bountystrike_v6_phase0-1_technical_brief.md — corrects the v6 figure); DeepSeek R1-0528; Qwen3-Coder (free + 480B 1M ctx); Qwen2.5-14B (Red-MIRROR LoRA); Pentest-R1 (Ollama); Venice Dolphin Mistral 24B (FREE, 2.2% refusal); Hermes-4-70B ($0.13/$0.40); OpenRouter (370 models); OpenAI text-embedding-3-large (1536-dim).

**Orchestration:** Hatchet; Temporal Cloud / Temporal self-hosted; Bifrost (MCP federation).

**Sandbox:** Firecracker; microsandbox (gVisor + seccomp); E2B.

**Data plane:** Postgres 17; pgvector; pgvectorscale (DiskANN); ParadeDB / pg_search; Cloudflare R2; SeaweedFS / Hetzner; Sigstore Rekor.

**Frontend/API:** Next.js 16 + shadcn/ui + SSE; FastAPI / Go control plane; WorkOS / better-auth.

**External MCPs:** PortSwigger Burp (official); Caido (c0tton); pd-tools (subfinder/dnsx/httpx/naabu/katana/nuclei/ffuf/feroxbuster); Shodan (ADEO+VT); HexStrike v6.0 fork (Prowler/ScoutSuite/Pacu/Trivy/kube-hunter/Checkov); Garak (NVIDIA 120 probes); AutoPentest-AI (68 tools); Strix (usestrix); Tencent AI-Infra-Guard.

**In-house MCPs:** scope-mcp (TS rewrite); ev-mcp (KEV decay); oracle-mcp (xss/ssrf_oast/sqli_timing/ssti_sandbox/idor_matrix/open_redirect/rce_sandbox/ssrf_imds); evidence-mcp; dedup-mcp; kev-mcp (CISA + VulnCheck); h1-mcp / bugcrowd-mcp / intigriti-mcp / yeswehack-mcp / immunefi-mcp; politeness-mcp; normalize-mcp (CVSS v4); state-mcp; sandbox-mcp.

**Observability:** OpenTelemetry; Grafana Cloud LGTM; Langfuse; Honeycomb; Sentry; custom Cybench / XBOW-104 / CVE-Bench harness.

## Context7 Docs (deferred)

Permission denied for subagent. Re-query in Phase 0 build:
1. **Hatchet** — workflow DSL, fan-out/fan-in
2. **Claude Agent SDK** — headless `claude -p`, Task subagent spawn, hook contract
3. **MCP** — server scaffolding Py + TS, stdio/SSE/HTTP
4. **LangGraph 1.x** — checkpoint/interrupt at T2/T3
5. **Temporal Cloud SDK** — Hatchet→Temporal migration
6. **pgvector / pgvectorscale / ParadeDB** — DiskANN DDL, BM25 hybrid
7. **Firecracker** — tap0 + iptables, JWT egress filter
8. **PydanticAI** — typed agent defs matching v2 contracts

## Top 3 Architectural Insights

1. **Verification independence = moat.** Validator uses *different model* (Sonnet 4.6) from generator (Opus 4.7), no access to generator transcript, deterministic oracles in fresh Firecracker VMs. Counters AnyPoC "mock validation" reward-hacking. XBOW keeps closed; BountyStrike open-sources methodology.
2. **Scope enforcement = infrastructure, not prompt.** RS256 scope JWTs materialized into iptables rules on host kernel tap0 at VM boot. Prompt injection cannot bypass — LLM has no path to modify host iptables.
3. **Single-Postgres data plane = operational simplicity bet.** pgvector + pgvectorscale (DiskANN) + ParadeDB (BM25) collapse Redis/Elasticsearch/Pinecone into one DB. Same binary solo Docker Compose → SaaS RDS.
