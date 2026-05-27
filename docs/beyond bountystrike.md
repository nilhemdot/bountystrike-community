# Beyond BountyStrike: A Clean‑Slate 2026 Build Plan for an Autonomous Bug Bounty Platform

## Executive summary

The bug bounty automation landscape changed more between October 2025 and April 2026 than in the prior five years combined. **XBOW closed a $120M Series C at unicorn valuation in March 2026** after topping the HackerOne US leaderboard; **Tenzai exited stealth in November 2025 with a $75M seed**; **RunSybil added $40M in March 2026**; **Hadrian, Terra, Novee, and Surf AI** all launched agentic offerings; **Bugcrowd acquired Mayhem (formerly ForAllSecure)**; **Anthropic's Project Glasswing / Mythos Preview** demonstrated a model that found a 27‑year‑old OpenBSD bug and a 16‑year‑old FFmpeg bug missed by 5M fuzzer runs. In parallel, **39+ open‑source agentic pentest projects** now exist (Strix, Shannon, Deadend CLI, NeuroSploit, AutoPentest‑AI, Pentest‑Swarm‑AI, Raptor, Transilience, Cyber‑AutoAgent), and a Chinese open offensive AI tool (CyberStrikeAI) is **already operational in the wild**, used by a Russian‑speaking actor to compromise 600+ FortiGate devices in early 2026.

Against this backdrop, a clean‑slate platform should not try to out‑XBOW XBOW. The opportunity is in three gaps: **(1)** a transparent, validation‑first, MCP‑native operator workbench that gives bug bounty hunters a single rail across HackerOne, Bugcrowd, Intigriti, YesWeHack, Immunefi, huntr, MSRC, Google VRP, Apple, Code4rena, and HackenProof; **(2)** a serious anti‑slop discipline (deterministic exploit verification, evidence‑gated triage, signed scope JWTs, sandboxed tool execution); **(3)** a price/perf curve nobody else hits — sub‑$0.20 full triage in solo mode using DeepSeek V4‑Flash + Grok 4.1 Fast + Devstral Small 2, scaling to $5–$50 SaaS scans with Sonnet 4.6 / GPT‑5.4 / Mythos for premium tiers.

The headline architectural calls in this report: **Hatchet (Postgres‑only, single binary)** for solo workflow orchestration and **Temporal Cloud** for SaaS; **Postgres 17 + pgvector + pgvectorscale + ParadeDB** as the unified relational/vector/FTS store, with Turbopuffer for per‑tenant finding namespaces at scale; **LangGraph 1.x + Claude Agent SDK + PydanticAI** for the agent runtime; **E2B or Firecracker microVMs** for any user‑defined offensive tool execution; **`arkadiyt/bounty-targets-data` (hourly) + `sw33tLie/bbscope` v2 with Postgres backend (6–12h, authenticated) + `projectdiscovery/public-bugbounty-programs` (daily)** as the federated scope‑retrieval layer; **Hetzner + Cloudflare R2** as the cost foundation. The MVP is shippable in four weeks; V1 in three months; V2 (multi‑tenant SaaS with SOC 2 path, MCP marketplace, exploit‑validation oracle) in six months.

The single most important strategic constraint is that **AI slop is now an existential threat to bug bounty itself** — curl shut down its HackerOne program in January 2026 because of LLM hallucinations. Any new platform must treat false‑positive elimination as a P0 product feature, not an afterthought.

---

## 1. New competitor matrix (NOT in BountyStrike v3 analysis)

The table below covers **only** competitors and tools that emerged or pivoted in late 2025 / 2026. PentAGI, CAI, ARTEMIS, AWE, xOffense, NodeZero, Mindgard, Sn1per, HexStrike, Caido, PDCP, Burp, Promptfoo, Garak, PyRIT are intentionally excluded.

### Tier 1 — well‑funded autonomous pentesting startups

| Company | Funding (latest) | Architecture signature | Why it matters | Weakness |
|---|---|---|---|---|
| **XBOW** | $237M total; $120M Series C, Mar 2026 ($1B+) | Thousands of short‑lived parallel agents; deterministic exploit verification (e.g., headless browser to confirm XSS payload executed) separated from AI exploration | Topped HackerOne US leaderboard June 2025; **Pentest On‑Demand GA Nov 2025** compresses 35–100‑day pentests into hours | ~25% Informative/N/A on H1 submissions; once removed from a program for being an automated scanner |
| **Tenzai** | $75M seed, Nov 2025 (Greylock + Battery + Lux) | "Always‑on offensive" multi‑agent platform; ex‑Guardicore + ex‑Snyk founders | Largest cybersec seed ever; Fortune 100 pilots in finance/health/tech | Pre‑GA; product not yet selling |
| **RunSybil** | $40M, Mar 2026 (Khosla, Anthology, Conviction, Elad Gil) | "Sybil" agent reasons like attacker, chains vulns across stacks; pre‑validated findings (zero triage burden) | Customers: Cursor, Notion, Turbopuffer, Baseten, Thinking Machines, multiple Fortune 500 banks | Small team (~13); narrow ICP (AI‑native cos) |
| **Terra Security** | $38M total ($30M Series A Sep 2025) | Agentic + human‑in‑the‑loop; per‑customer trained agents; **Terra Portal** collaboration UI; new ATLAS product | Won 2025 CrowdStrike + AWS Cybersecurity Accelerator | Slower than fully‑autonomous peers |
| **Hadrian "Nova"** | (Hadrian existing EASM player) | "Predictive discovery agent™" + modular hacker agents; on‑demand pentest with HITL verification; per‑test pricing | Launched Mar 24 2026 at RSAC; SOC 2 + ISO 27001; claims 99.5% FP elimination | Validation method less transparent than XBOW |
| **Novee** | $51.5M Series A, Jan 2026 | Custom agents trained "the way pentesters are trained"; consolidates DAST + EASM + manual pentest | Founder ex‑Orca VP Product | Still building customer base |
| **Surf AI** | $57M, Mar 2026 RSAC launch (Accel) | Agentic security operations | Brand‑new; details light | Pre‑production for most |
| **MindFort** (YC) | YC backing | In‑house models; multi‑agent web vuln discovery | Comprehensive 2026 buyer's guide as competitive intel | Smaller than peers |
| **Cobalt** | $36.6M total | Explicitly **rejects** fully autonomous; human‑led + AI‑powered PTaaS (Recon, Discovery, Enrichment, Dedup, Triage AI features added Mar 2026) | Pragmatic positioning sells well to risk‑averse buyers | Slower than agentic competitors |

### Tier 2 — established players adding agentic capabilities

| Player | 2026 move | Implication |
|---|---|---|
| **Pentera** | First AEV vendor to $100M ARR; **Pentera 8** (Mar 2026 GA Q2 2026) introduces **Pentera Peer™** (NL AI interface) and **Pentera Attack‑testing API**. Acquired EVA Information Security + DevOcean | Sets the enterprise "agentic NL pentest" UX bar |
| **RidgeBot / Ridge Security** | **RidgeGen** (Oct 2025) multi‑agent + **RidgeBrain**; scored 88% at DEFCON 2025 Bakeoff with 0 FPs; **PurpleRidge 3.0** for SMB/MSSP on GCP+Gemini at RSAC 2026 | First credible SMB‑self‑service offering; 36k+ plugin library |
| **Picus / AttackIQ / SafeBreach / Cymulate** | All BAS vendors layering "Agentic Exposure Validation" — Picus's **APV (Attack Path Validation)** GA Jan 2025 | BAS converging into AEV; framing the validation oracle as the differentiator |
| **Bugcrowd** | **Acquired Mayhem Security (ForAllSecure)** Nov 4 2025; David Brumley becomes Chief AI/Science Officer | Bugcrowd now owns DARPA‑Cyber‑Grand‑Challenge‑era coverage‑guided fuzzing + symbolic execution tech (claims 2× more bugs than fuzzing alone, zero FPs via proof‑of‑vulnerability) |
| **Code Intelligence** | **CI Spark** GA Jan 2025: AI Test Agent generating fuzz harnesses for JS/TS/Java/C/C++; 79.51% coverage; saves up to 1,000 manual hours; found WolfSSL bug in beta | Best fuzzing‑as‑a‑service productivity story |
| **Bright Security** | **Bright STAR** (Apr 2025): DAST+IAST+API with AI fixes + remediation validation loop; <3% FP, OWASP LLM Top 10 coverage | Top developer‑first DAST contender |
| **PortSwigger Burp AI** | Burp Pro 2025.2 added Explore Issue, Explainer, BAC FP reduction, AI recorded login | Note credit‑expiry pricing antipattern (12mo, no pooling) |
| **Akto** | **Agentic Security Platform** Sep 2025; AGPL‑3.0 OSS core; **MCP Security** added Jun 2025 | Best OSS API security pivot to agentic |
| **Salt Security** | **Agentic Security Graph** (1H 2026 report); **Salt Code** for shadow API/MCP discovery | Positioning around agentic stack security (LLMs + MCP + APIs) |
| **DefectDojo "Sensei"** | OWASP Global AppSec 2025 launch; uses **self‑training evolution algorithms (not RL)**, runs entirely in‑house — **no third‑party LLM dependency**; MCP support added Jun 2025 | Only major OSS vuln‑mgmt tool with first‑party agent + data‑residency story |
| **Faraday** | Active OSS (6.2k stars, GPL‑3.0) + commercial Enrichment/CART/OPS tiers | "Use Faraday for offense, DefectDojo for defense" — quote from DefectDojo's own positioning |
| **Trickest** | 300+ tools, 90+ workflow templates, 20+ modules, 800+ public bounty programs catalog | Closest commercial analogue to a workflow product |
| **Cobalt** | Per above; ships AI features Q4 2025/Q1 2026 | Validates the "human‑led + AI augmented" middle path |

### Tier 3 — open‑source agentic pentest frameworks (39+ documented, top picks below)

| Project | Stars / activity | Architecture | Standout |
|---|---|---|---|
| **Strix** (usestrix) | ~24.5k stars, 2.7k forks, Apache‑2.0, very active | Multi‑agent graph; HTTP proxy + browser + terminal + Python; CI/CD‑native via GitHub Actions diff‑scope | Built on LiteLLM/Caido/Nuclei/Playwright/Textual; fastest‑growing OSS project in this space |
| **Shannon** (Keygraph) | Highest XBOW benchmark score (96.15%) | White‑box + black‑box; "no exploit, no report"; Claude Agent SDK + Temporal task queue | Open weights of XBOW‑class benchmark performance |
| **Deadend CLI** (xoxruns) | ~221 stars | Two‑phase + supervisor‑subagent; Python+Deno; LiteLLM/Ollama | **80% on full XBOW suite at $122 total cost** with Kimi K2.5 |
| **AutoPentest‑AI** (bhavsec) | Active | 4 Claude Code subagents; **68+ MCP tools, 27 security tools**; OWASP WSTG + 31 PortSwigger Web Academy techniques; 12 WAF evasions | Most thorough MCP‑native open agent |
| **Zen‑Ai‑Pentest** (SHAdd0WTAka) | ~279 stars, Feb 2026 | Recon + Vuln + Exploit + Report agents over FastAPI+WS | **72+ tools across 9 categories**; ships as GitHub Action |
| **NeuroSploit v3** (CyberSecurityUP) | Active Apr 2026 | Per‑scan Kali Docker; 3‑stream parallel; 100 vuln types; **anti‑hallucination pipeline** + 25+ proof‑of‑execution methods | Strongest published anti‑hallucination guardrail design |
| **Pentest‑Swarm‑AI** (Armur‑AI) | Go‑native | 5‑agent swarm; native Go security tool integrations | Demonstrates Go‑native agent path |
| **Raptor** (Gadi Evron et al.) | Apr 2026 | **Claude Code‑native** (no custom framework); CLAUDE.md + slash commands; AFL + CodeQL | Simplest "claude code is the agent runtime" pattern |
| **PentestGPT v2 / Excalibur** | New paper | Difficulty‑aware planning; **86.5% XBOW success at $1.11 avg, 6.1 min median** | Most cost‑efficient open agent on XBOW |
| **CHECKMATE** (arXiv 2512.11143) | Paper | LLM writes PDDL → classical planner → executor agents | **+20% over Claude Code, 50% faster** |
| **Transilience Community Tools** | Open | 23 skills, 8 agents, 2 tools | **100/104 (perfect) on XBOW** |

### Tier 4 — MCP‑native security orchestration

| Tool | Source | What it adds |
|---|---|---|
| **Tencent A.I.G (AI‑Infra‑Guard)** | github.com/Tencent/AI-Infra-Guard | Black Hat Europe 2025 Arsenal; full‑stack AI red‑teaming with **MCP Server scan, Agent‑Scan, AI‑infra vuln scan, jailbreak eval**; 14 MCP risk categories; 589+ CVEs covered |
| **mcp‑fortress / mcp‑scan / McpSafetyScanner** | Multiple | Static + dynamic MCP server vuln scanning; covered in arXiv 2510.23673 (MCPGuard) |
| **Astrix MCP Secret Wrapper** | astrix.security | Pulls secrets from AWS Secrets Manager into MCP server env at start |
| **Microsoft Agent Governance Toolkit** | github.com/microsoft/agent-governance-toolkit | 7‑package suite (Py/TS/Rust/Go/.NET): policy engine <0.1ms p99, agent mesh w/ DIDs+IATP, runtime kill switch, EU AI Act/HIPAA/SOC2 compliance, OWASP Agentic Top 10 mapping |
| **Ship Safe** | github.com/asamassekou10/ship-safe | 23 specialized agents covering MCP misuse, OWASP Agentic Top 10 (ASI‑01 to ASI‑10), Claude Code hooks (CVE‑2026), .cursorrules/CLAUDE.md/AGENTS.md prompt injection |
| **Bug Bounty MCP** | akinabudu/bug-bounty-mcp | H1/Bugcrowd integration with strict scope validation, audit logging, rate limiting |
| **PortSwigger Burp MCP** | Official BApp | AI agents driving Burp extensions |

### Tier 5 — fine‑tuned offensive LLMs (beyond xOffense/Qwen3‑32B)

| Model | Source | Significance |
|---|---|---|
| **DeepHat / Kindo "Deep Hat V2" (30B)** | deephat.ai | Reportedly outperforms gpt‑oss‑120B and Llama‑Scout on CTFs/threat intel/offensive scenarios; **WhiteRabbitNeo‑V3 8B** still on HF |
| **Pentest‑R1** (arXiv 2508.07382) | RL on 500+ HTB/VulnHub walkthroughs + GRPO online RL | Approaches Claude 3.7 Sonnet / Gemini 2.5 Flash level on Cybench at 31% fewer tokens than base |
| **Red‑MIRROR** (arXiv 2603.27127) | LoRA on Qwen2.5‑14B over 1,644 CVE/CAPEC/MITRE pairs | Demonstrates self‑hosted offensive LLM viability with system‑level reflection |
| **Foundation‑Sec‑8B** (Cisco) | huggingface.co/fdtn-ai/Foundation-Sec-8B | Continued pre‑training on cybersec corpus; locally deployable |
| **Lily‑Cybersecurity‑7B‑v0.2** | segolilylabs | 22k handcrafted cyber pairs on Mistral‑7B‑Instruct |
| **Other HF tunes** | Canstralian/pentest_ai (13B), CyberNative/CyberBase‑13b, ZySec‑AI/SecurityLLM | Active community baseline pool |

### Tier 6 — academic frontiers (Oct 2025 – Apr 2026)

The most actionable arXiv papers for build planning: **CHECKMATE** (planner+LLM hybrid), **AgentFlow** (typed graph DSL for synthesizing multi‑agent harnesses, arXiv 2604.20801), **Co‑RedTeam** (>60% exploitation on CyberGym), **VulnSage** (~$0.97/vuln Qwen pricing), **CVE‑Genie** (reproduces 51% of 428/841 2024–25 CVEs at $2.77/CVE), **CRAKEN** (RAG‑augmented CTF), **AnyPoC** (PoC generator that addresses reward‑hacking failure mode). **DARPA AIxCC finalists** all open‑sourced post‑Aug 2025: Atlantis (Team Atlanta, $4M, 1st), Buttercup (Trail of Bits, $3M, 2nd), Theori, ARTIPHISHELL, all_you_need_is_a_fuzzing_brain, 42‑b3yond‑6ug, Lacrosse — detection rates jumped 37%→86% YoY.

### Tier 7 — adjacent / situational awareness

**Anthropic Project Glasswing / Claude Mythos Preview** (Apr 7 2026) — frontier model autonomously found "thousands of zero‑days in every major OS and browser," including a **27‑year‑old OpenBSD flaw** and **16‑year‑old FFmpeg bug missed by 5M fuzz tests**. Limited release to 12 partners + 40 critical infra orgs. Pricing $25/$125 per M. **NOT publicly released due to dual‑use risk.** Scores **83.1% on CyberGym vuln benchmark**. **Trend Micro AESIR** found 21 critical CVEs since mid‑2025. **CyberStrikeAI** — open offensive AI tool from a China‑based developer; documented compromising 600+ FortiGate devices in early 2026.

---

## 2. Feature gap analysis for the new platform

Aggregating user pain points and competitive coverage, the underserved feature set looks like this. The bullet lists below are short on purpose — every other section uses narrative prose.

**Highest‑leverage gaps the new platform should own:**

- A **federated, signed, scope‑aware ingestion layer** that beats every competitor's narrow integration set: nobody combines arkadiyt + bbscope + PD list + huntr + Immunefi + MSRC/Google/Apple in one normalized schema with primacy‑of‑impact + out‑of‑scope as first‑class entities.
- **Deterministic exploit verification** as a separate subsystem from generation (XBOW's moat) — but exposed to the operator as a transparent oracle rather than a black box, addressing community criticism that XBOW's "fully autonomous" submissions get hand‑filtered.

**Common tool capability gaps everywhere:**

- **Continuous diffing of scope and assets** with rich change events and per‑program "what's new since last hour" notifications — a need explicitly called out in sw33tLie's bbscope v2 changelog (`db changes`) and in hakluke's Detectify retrospective.
- **Authenticated scanning that actually works** for SPA + STS + OAuth + JWT + session refresh — a known Burp pain (forum threads, OAuthScan FP issues).
- **Mobile and cloud surface** (iOS app + Android app + S3 + Azure Blob + GCP) treated as native asset types, not bolt‑ons — most hunters skip mobile because of setup friction.
- **Built‑in distributed execution** with a single pane (the "Axiom but not bash" problem; Axiom users still manually clean up VPS sprawl and risk getting their cloud account banned).
- **A reasonable cost model**: solo hunters won't pay $475–$499/yr for Burp Pro plus per‑seat Caido plus an LLM bill. Sub‑$0.20 full triage is now achievable with DeepSeek V4‑Flash, and the platform should pass that price to operators.
- **Native ChatOps** (Slack/Discord/Telegram) and CI/CD hooks rather than yet another `notify`/Discord‑Recon glue.
- **Findings dedup that survives across scans** with vector similarity + structured fingerprints — the dupe complaint is universally cited as "the worst feeling in bug bounty."

The most novel gap is **transparent agent observability**. XBOW, Pentera Peer, RidgeGen, Hadrian Nova, and most commercial competitors are black boxes; their reports look polished but operators have no insight into the agent's reasoning chain or evidence basis. Open‑source projects (Strix, Shannon, NeuroSploit) are more transparent but lack production polish. A clean‑slate platform that ships **Langfuse traces + reasoning replay + signed evidence chains** as a first‑class operator workbench captures both audiences.

---

## 3. Build vs buy vs OSS recommendation table per subsystem

Decision logic: in solo mode, optimize for ops simplicity and zero recurring cost; in SaaS mode, optimize for differentiation, defensibility, and SOC 2 readiness. "Buy" rarely wins because every commercial competitor wants $25k+ ACV.

| Subsystem | Solo recommendation | SaaS recommendation | Rationale |
|---|---|---|---|
| Scope retrieval | **OSS**: arkadiyt (L1) + bbscope v2 (L2) + projectdiscovery list (L3) | Same OSS layers + custom adapters for huntr, Immunefi, MSRC, Google VRP, Apple, Code4rena | Reimplementing platform scrapers is months of churn; standing on these tools is a free moat |
| Recon engine | **OSS**: subfinder, amass, dnsx, httpx, naabu, katana, nuclei, gowitness, JSluice, gau | Same OSS + custom orchestrator + per‑tenant template registry | Best‑in‑class OSS already exists; build the orchestration layer, not the scanners |
| Exploit verification oracle | **Build** (deterministic, headless‑browser + SQLi time validator + SSRF callback verifier) | **Build** as the SaaS moat | This is the XBOW moat; nobody ships a clean OSS validator |
| Triage / dedup | **OSS**: pgvector + custom embedder; rule‑based fingerprinting | **Build** an evidence‑gated triage engine (false‑positive killer) on top of pgvector + LLM critique | Dedup is a specialized RAG problem with cybersec‑specific embeddings |
| Agent runtime | **OSS**: Claude Agent SDK + PydanticAI | **OSS**: LangGraph 1.x + PydanticAI + Claude Agent SDK as a sandboxed sub‑agent | Avoid OpenAI Agents SDK lock‑in for a security product |
| Workflow orchestration | **OSS**: Hatchet (single Postgres + binary) | **Buy**: Temporal Cloud (or self‑host on K8s once volume justifies) | Hatchet's Postgres‑only ops story is unbeatable for solo; Temporal earns its keep at SaaS scale |
| Sandboxing | **OSS**: hardened Docker (read‑only, cap‑drop, net‑internal) | **Buy**: E2B (Firecracker) or **OSS**: self‑run Firecracker on Hetzner | Docker is acceptable solo, insufficient for multi‑tenant; E2B is fastest path to launch |
| LLM gateway | **OSS**: LiteLLM proxy | **OSS**: LiteLLM + provider BYOK + per‑tenant cost ceilings | OpenRouter is great but a single‑vendor dependency; LiteLLM normalizes 100+ providers self‑hosted |
| Vector + FTS | **OSS**: Postgres + pgvector + ParadeDB | Same → migrate to Turbopuffer per‑tenant when >1M findings/tenant | One DB beats three until scale forces split |
| Auth | **OSS**: better‑auth | **Buy**: WorkOS AuthKit (free up to 1M MAU) + add SSO/SCIM/Audit when first enterprise signs | better‑auth owns the data; WorkOS is the cheapest enterprise path |
| LLM observability | **OSS**: Langfuse self‑hosted + Sentry | **Buy/OSS**: Langfuse Cloud + Grafana Cloud LGTM (OTel) + Sentry | Langfuse is the default OSS choice; LangSmith is overpriced and US‑only |
| Secrets | **OSS**: SOPS + age | **OSS**: Infisical self‑hosted (or OpenBao for Vault parity) | Avoid Doppler if privacy‑sensitive |
| Blob storage | **Buy/OSS**: Cloudflare R2 (zero egress) | Same + SeaweedFS cold tier on Hetzner | R2's free egress is a structural cost advantage |
| Notifications | **Build** thin: Slack/Discord/Telegram/email/webhook | Same + per‑tenant routing + rate‑limited digests | Off‑the‑shelf adapters but the routing logic is bespoke |
| Compliance / audit logs | **OSS**: append‑only Postgres table + signed hashes | **Build** an audit subsystem (SOC 2, signed scope JWTs, request provenance) | This is table‑stakes for SaaS; no OSS package nails it |

---

## 4. System architecture proposals

### 4.1 Solo self‑hosted architecture (Docker Compose, $25–60/month total)

The solo design collapses everything onto one Hetzner CCX22 dedicated VM (8 vCPU, 32GB RAM, ~€16/month) running Coolify, with Cloudflare in front and R2 for blob.

```
┌──────────────────────────────────────────────────────────────────────┐
│                         Cloudflare (DNS, R2, WAF)                     │
└──────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌──────────────────────────────────────────────────────────────────────┐
│    Hetzner CCX22 (single VM, Coolify-managed Docker Compose)          │
│                                                                       │
│  ┌─────────────────┐   ┌──────────────────────────────────────┐      │
│  │  Next.js 16     │   │    FastAPI Control Plane              │      │
│  │  + shadcn/ui    │◄──│    + better-auth + RS256 JWT scope    │      │
│  │  SSE for logs   │   │    + Pydantic v2 schemas              │      │
│  └─────────────────┘   └──────────────────┬───────────────────┘      │
│                                            │                          │
│                                            ▼                          │
│  ┌──────────────────────────────────────────────────────────────┐    │
│  │  Hatchet (workflow + queue, Postgres-backed, 1 binary)        │    │
│  │  ├── ScopeIngest (cron 1h)   - arkadiyt                      │    │
│  │  ├── BBScopePoll (cron 12h)  - bbscope v2 with stored creds  │    │
│  │  ├── PDListSync (cron 24h)   - PD public-bugbounty-programs  │    │
│  │  ├── ScanWorkflow            - per target, fan-out           │    │
│  │  ├── TriageWorkflow          - findings → evidence-gated     │    │
│  │  └── ReportWorkflow          - draft → critique → submit     │    │
│  └──────────────────────────────────────────────────────────────┘    │
│         │                                                             │
│         ▼                                                             │
│  ┌──────────────────────────────────────────────────────────────┐    │
│  │  Agent runners (Claude Agent SDK in hardened Docker)          │    │
│  │  - read-only rootfs, --cap-drop=ALL, --network=internal       │    │
│  │  - bind-mount tools volume (subfinder, httpx, nuclei, ...)    │    │
│  │  - LiteLLM proxy → DeepSeek V4-Flash + Grok 4.1 Fast +        │    │
│  │    Claude Sonnet 4.6 (premium reports) + local Devstral 2     │    │
│  └──────────────────────────────────────────────────────────────┘    │
│         │                                                             │
│         ▼                                                             │
│  ┌──────────────────────────────────────────────────────────────┐    │
│  │  Postgres 17 (single instance)                                │    │
│  │  ├── relational (programs, scopes, scans, findings, runs)    │    │
│  │  ├── pgvector + pgvectorscale (finding embeddings, RAG)      │    │
│  │  └── ParadeDB (BM25 FTS over scope, findings, JS strings)    │    │
│  └──────────────────────────────────────────────────────────────┘    │
│                                                                       │
│  ┌─────────────────┐  ┌──────────────────┐  ┌──────────────────┐    │
│  │ Langfuse self-  │  │ Sentry self-     │  │ MinIO/local FS    │    │
│  │ hosted          │  │ hosted           │  │ (or R2 direct)    │    │
│  └─────────────────┘  └──────────────────┘  └──────────────────┘    │
└──────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌──────────────────────────────────────────────────────────────────────┐
│  Cloudflare R2 (blobs: screenshots, HTTP responses, scan artifacts)   │
└──────────────────────────────────────────────────────────────────────┘
```

Secrets via SOPS+age in the infra repo; Hetzner private network for inter‑service traffic; Cloudflare Tunnel for the dashboard so the VM never exposes a public port. Backups: nightly `pg_dump` to R2 and weekly Borg snapshot of the whole VM.

### 4.2 Multi‑tenant SaaS architecture

The SaaS topology promotes per‑tenant isolation, swaps Hatchet for Temporal Cloud, replaces Docker with E2B/Firecracker microVMs for tool execution, and adds a control‑plane / data‑plane split so blast radius from a compromised tenant scan is contained.

```
                                  ┌────────────────────────────────┐
                                  │   Cloudflare (DNS, WAF, R2,    │
                                  │   Workers edge, Pages)         │
                                  └─────────────┬──────────────────┘
                                                │
                ┌───────────────────────────────┼────────────────────────────┐
                ▼                               ▼                            ▼
   ┌──────────────────────┐      ┌─────────────────────────┐    ┌──────────────────────┐
   │ Next.js 16 frontend  │      │ Go + Chi/Huma control   │    │ MCP server gateway    │
   │ shadcn + Server Comp │◄────►│ plane API + WorkOS Auth │    │ (per-tenant tokens)   │
   │ SSE + Durable Object │      │ + RS256 scope JWTs       │    └──────────────────────┘
   │ WS triage rooms      │      └────────────┬─────────────┘
   └──────────────────────┘                   │
                                              ▼
                          ┌───────────────────────────────────────┐
                          │       Temporal Cloud (orchestration)   │
                          │  - ScanWorkflow, TriageWorkflow,       │
                          │    ScopeIngest, ReportWorkflow          │
                          │  - per-tenant task queues + concurrency │
                          └────────────┬───────────────────────────┘
                                       │
            ┌──────────────────────────┼──────────────────────────┐
            ▼                          ▼                          ▼
  ┌──────────────────┐    ┌──────────────────────┐   ┌────────────────────┐
  │ LangGraph agents │    │ E2B / Firecracker     │   │ NATS JetStream      │
  │ + Claude Agent   │───►│ microVM pool          │   │ event bus           │
  │ SDK sub-agents   │    │ - per-job VM           │   │ (recon→scan→triage  │
  │ + LiteLLM proxy  │    │ - egress allowlist:    │   │  →report events)    │
  │   (BYOK + budget │    │   target+DNS only      │   └─────────┬──────────┘
  │   ceiling)       │    │ - 1 vCPU / 1GB cap     │             │
  └─────────┬────────┘    └─────────┬─────────────┘             ▼
            │                       │                ┌─────────────────────┐
            ▼                       ▼                │ Triage/Validation   │
  ┌────────────────────────────────────────────────┐ │ oracle (deterministic│
  │ LLM providers (Anthropic, OpenAI, Google,      │ │ exploit verifier)    │
  │  xAI, DeepSeek, OpenRouter, Groq, DeepInfra,   │ └─────────────────────┘
  │  self-hosted Devstral/Qwen/Kimi via vLLM/SGLang)│
  └────────────────────────────────────────────────┘
            │
            ▼
  ┌────────────────────────────────────────────────────────────────────┐
  │                  Stateful tier (Hetzner dedicated AX-line)          │
  │                                                                      │
  │  Postgres 17 primary + 2 replicas       │ Turbopuffer (per-tenant   │
  │  - operational, audit, scope            │  vector namespaces, BM25  │
  │  pgvector + pgvectorscale + ParadeDB    │  hybrid) — engaged when   │
  │                                          │  tenant > 1M findings    │
  └────────────────────────────────────────────────────────────────────┘
            │
            ▼
  ┌────────────────────────────────────────────────────────────────────┐
  │ Cloudflare R2 (hot blobs)  +  SeaweedFS on Hetzner (cold archive)   │
  └────────────────────────────────────────────────────────────────────┘
            │
            ▼
  ┌────────────────────────────────────────────────────────────────────┐
  │ Observability:  Langfuse Cloud (LLM traces) + Grafana Cloud / LGTM  │
  │                 (OTel) + Sentry Business + Infisical secrets        │
  │                 Audit log: append-only Postgres + signed hashes     │
  └────────────────────────────────────────────────────────────────────┘
```

Auth uses **WorkOS AuthKit** for the user base (free <1M MAU) with SSO and SCIM connections added per enterprise tenant. Scope JWTs are RS256‑signed by the control plane and validated at every microVM boot — this is the hard line that prevents an LLM prompt injection from extending scope. Egress allowlists are enforced at the Firecracker `tap0` layer, not in agent prompts. Per‑tenant LLM cost ceilings live in the LiteLLM proxy with budget‑exceeded errors that surface to the UI as "scan paused, top up."

### 4.3 Key differences solo vs SaaS

The big delta is the **isolation perimeter** and the **orchestration durability promise**. Solo runs everything in Docker on one VM with Hatchet — fine because the operator owns the box and the threats are limited to the upstream OSS supply chain. SaaS replaces Docker with **per‑job Firecracker microVMs**, replaces Hatchet with **Temporal Cloud** (multi‑week scans, idempotent replay, per‑tenant rate limits), splits Postgres into **a writer + replicas with PgBouncer + per‑tenant schemas or row‑level security**, adds **Turbopuffer per‑tenant namespaces** when finding count exceeds about 1M, and inserts a **Go control plane** in front of the Python agent services so the public API has predictable latency and tiny binaries that fit K8s readiness probes.

Frontend is the same Next.js + shadcn stack but SaaS adds **Cloudflare Durable Objects with WS hibernation** for collaborative triage rooms — solo doesn't need real‑time multi‑user state. Auth differs: better‑auth (solo) → WorkOS AuthKit (SaaS, with progressive add‑ons). Secrets diverge similarly: SOPS+age (solo) → Infisical self‑hosted (SaaS). Observability collapses Langfuse + Sentry + nothing‑else (solo) into Langfuse Cloud + Grafana LGTM + Sentry Business + an append‑only audit log table (SaaS).

A subtle but critical SaaS‑only addition is the **scope JWT issuer** and **MCP server gateway**. Every customer's scope ingestion outputs a signed JWT containing the canonical asset list and out‑of‑scope set; every agent invocation, MCP tool call, and microVM boot validates that JWT. This pattern is borrowed from BountyStrike v3's RS256 JWT design and remains the right answer in a clean‑slate build because it survives prompt injection.

---

## 5. The bbscope vs alternatives recommendation

The federated subagent's deep evaluation produces an unambiguous answer: layer **arkadiyt/bounty-targets-data** (free, MIT, every‑30‑min refresh, 5 platforms) at the public baseline; supplement with **sw33tLie/bbscope v2** (Apache‑2.0, Postgres‑backed, change‑tracking, AI normalization, supports H1/Bugcrowd/Intigriti/YesWeHack/Immunefi with stored credentials) for authenticated depth and Immunefi; supplement again with **projectdiscovery/public-bugbounty-programs** (`dist/data.json`, MIT, weekly PR cadence) for VDPs, HackenProof, and custom programs that arkadiyt doesn't crawl.

**ScopeHunter is a thin Bash wrapper around arkadiyt** — adopting bounty‑targets‑data directly is strictly better. **hacker-scoper is a scope filter, not a retriever**, and its AGPL‑3.0 license is a poison pill for closed‑source SaaS embedding. **FireBounty's API is undocumented and unstable** — only ingest if you obtain a parseable dump and even then only as a tertiary VDP source. **bbscope.com itself is a UI on top of the bbscope CLI** with no documented public API; self‑host the website mode if you want a UI.

Concretely, the ingestion cron looks like this. At `:00` every hour, `git pull` arkadiyt and ingest five JSON files into the normalized `programs`/`scopes` tables. At `:15` every 6 hours, run `bbscope poll --db` with stored per‑user credentials (sessions/JWTs preferred over email+password+TOTP for Bugcrowd/YesWeHack) — this UPSERTs into the same Postgres and emits change events. At daily cadence, `git pull` projectdiscovery and merge the `data.json` into the long‑tail tables. Every change event fires a Hatchet/Temporal workflow that recomputes per‑program priority, regenerates the signed scope JWT, and notifies subscribed users.

Two operational caveats to bake into V1: **HackerOne deprecates `structured_scopes` April 2026** in favor of organization‑level asset management endpoints — migrate before relying on the old endpoints. **Bugcrowd auto‑login requires 2FA disabled** for bbscope, so production deployments must inject session cookies rather than credentials. Pin a specific bbscope version (v2 introduced the `bbscope h1` → `bbscope poll h1` breaking change) and test upgrades.

---

## 6. Open vs closed LLM comparison with concrete cost numbers

Pricing as of April 25, 2026 (verified per vendor pricing pages). Token assumptions: full triage scan ≈ 500K input + 80K output; recon analysis ≈ 200K input + 30K output; report drafting ≈ 30K input + 15K output. The "$/scan" column is full‑triage cost.

| Model | Input $/M | Output $/M | $/scan | Solo $5? | SaaS $50? | Best for |
|---|---|---|---|---|---|---|
| **DeepSeek V4‑Flash** | 0.14 (cache 0.028) | 0.28 | **$0.09** cached | ✅ | ✅ | Bulk triage |
| **DeepSeek V4‑Pro** | 1.74 (currently 75% off) | 3.48 | **$1.15** | ✅ | ✅ | Cheap reasoning |
| **DeepSeek V3.2** | 0.14 | 0.42 | $0.17 | ✅ | ✅ | Triage fallback |
| **Grok 4.1 Fast** | 0.20 | 0.50 | **$0.14** | ✅ | ✅ | Fast supervisor / 2M ctx |
| **Grok 4.20** | 2.00 | 6.00 | $1.48 | ✅ | ✅ | Multi‑agent (2M ctx) |
| **Gemini 3.1 Flash‑Lite** | 0.25 | 1.50 | $0.25 | ✅ | ✅ | Recon analysis |
| **Gemini 3 Flash** | 0.50 | 3.00 | $0.49 | ✅ | ✅ | Recon analysis |
| **Gemini 3.1 Pro** (≤200K) | 2.00 | 12.00 | $1.96 | ✅ | ✅ | Long‑ctx recon |
| **Gemini 3.1 Pro** (>200K) | 4.00 | 18.00 | $3.44 | ✅ | ✅ | Whole‑codebase recon |
| **GPT‑5.4 Mini** | 0.75 | 6.00 | $0.86 | ✅ | ✅ | Fast triage |
| **GPT‑5.4** | 2.50 | 15.00 | **$2.45** | ✅ | ✅ | General workhorse |
| **GPT‑5.5** | 5.00 | 30.00 | $4.90 | ⚠️ | ✅ | Best‑in‑class exploit reasoning (CyberGym 81.8%, "High" cyber tier) |
| **Claude Haiku 4.5** | 1.00 | 5.00 | $0.90 | ✅ | ✅ | Cheap triage |
| **Claude Sonnet 4.6** | 3.00 | 15.00 | **$2.70** | ✅ | ✅ | Triage + report (SWE‑bench 79.6%) |
| **Claude Opus 4.7** | 5.00 | 25.00 | $4.50 | tight | ✅ | Supervisor / report quality |
| **Claude Mythos Preview** | 25.00 | 125.00 | $22.50 | ❌ | ✅ if Glasswing partner | Best published cyber benchmark (CyberGym 83.1%) |
| **GPT‑5.5 Pro** | 30.00 | 180.00 | $29.40 | ❌ | ✅ | Reasoning splurge |
| **Llama 3.3 70B / Groq** | 0.59 | 0.79 | $0.36 | ✅ | ✅ | Self‑host alt |
| **Qwen3‑Coder Plus** | 0.135 | 0.33 | $0.17 | ✅ | ✅ | Code reasoning |
| **Cohere Command R7B** | 0.0375 | 0.15 | $0.03 | ✅ | ✅ | Cheapest production‑grade |

**Open‑weight self‑host picks** (Apache‑2.0 or MIT unless noted): **Devstral Small 2 (24B)** runs on a single 4090/Mac 32GB and beats Qwen3‑Coder Flash on coding; **Qwen3‑Coder Next 80B‑A3B** (3B active) fits on 1×H100 or 2×4090; **Kimi K2.6** (1T MoE, 32B active, Modified MIT) — 96% τ²‑Bench Telecom tool use, 80.2% SWE‑bench Verified; **Gemma 4 26B‑A4B** for 256K real long‑context; **Phi‑4 Reasoning Vision (15B, MIT)** for screenshot‑aware on‑laptop triage; **gpt‑oss‑20B** (Apache‑2.0) for budget reasoning. **DeepSeek‑R1‑Distill‑Llama‑70B** fits on 1×H100 INT4 and is the strongest distilled reasoner in that VRAM class.

**Self‑host cost benchmarks** (April 2026): H100 80GB at $1.49–$2.69/hr (Vast.ai / RunPod / Lambda), A100 80GB at $0.78–$1.49/hr (Thunder Compute cheapest), B200 spot $2.12/hr. Hetzner GEX44 dedicated GPU at €184/month for 24/7 13–24B model serving. **vLLM** is the broadest‑hardware default; **SGLang** is ~29% faster than vLLM on prefix‑heavy multi‑turn agent loops (RadixAttention, FP8); **LMDeploy** ties SGLang on H100 Llama 8B (~16k tok/s). For solo on a Mac, **Ollama** (Devstral Small 2, Phi‑4 Reasoning Vision) is the path of least resistance.

**Fine‑tuning vs RAG vs prompting tradeoffs.** A QLoRA on Qwen3‑Coder‑32B over offsec data costs **$3–$25 on RunPod/Lambda Labs** (1×H100 or A100, 6–12 GPU‑hours). Devstral Small 2 LoRA fits on a single 4090 for under $2/run. Full SFT on 32B is $150–$400; RLHF/DPO is 2–5× SFT and rarely justified. **RAG beats fine‑tuning** for volatile knowledge (fresh CVEs, internal pentest writeups, disclosure databases), citation‑traceability (mandatory in bounty reports), and per‑tenant compliance. **Fine‑tuning wins** for tool‑use output conformance (always emit Burp/sqlmap JSON), report style conformance, and latency/cost when a 7B fine‑tune can replace a frontier API for narrow classification. The 2026 academic consensus (CRAKEN, CTFusion, CAIBench arXiv 2510.24317) is that **scaffold‑model matching matters more than model choice** — up to 2.6× variance — and that web‑search tool integration nearly doubles solve rates on static benchmarks. The implication for build planning: invest in retrieval and tool plumbing, not in fine‑tuning a hero model.

**Concrete role assignments.**

For SaaS mode at a $50/scan budget: **Claude Opus 4.7 as supervisor** (best instruction‑following, predictable refusal patterns), **Claude Sonnet 4.6 for triage** (1M context for entire repo intake at $3/$15), **Claude Opus 4.7 or Sonnet 4.6 for report drafting**, **Gemini 3.1 Pro for recon analysis** (2M context), **GPT‑5.5 for exploit reasoning** (top published cyber benchmarks; request Trusted Access via chatgpt.com/cyber to reduce refusals), **Claude Opus 4.7 with extended thinking for self‑critique**.

For solo mode at a $5/scan budget: **Grok 4.1 Fast as supervisor** ($0.20/$0.50, 2M context), **DeepSeek V4‑Flash for triage** ($0.14/$0.28, 1M context, 90% cache hit pricing — pennies/scan effective), **Claude Sonnet 4.6 for the actual report** (splurge here, one good report beats ten so‑so ones), **Gemini 3.1 Flash‑Lite for recon analysis**, **DeepSeek V4‑Pro for exploit reasoning** (currently 75% off until 2026‑05‑05; gold‑medal IMO/IOI 2025), **Kimi K2.6 self‑hosted for self‑critique** (distinct training distribution avoids reasoning‑mode collusion).

**Watch‑outs.** Claude Opus 4.7's new tokenizer can use up to **35% more tokens** vs Opus 4.6 on identical text — measure before migrating. **GPT‑5.5 doubled GPT‑5.4 pricing** on April 23 2026 ($5/$30 vs $2.50/$15) — for most production use, stick with GPT‑5.4 until benchmarks justify the jump for your specific workload. **OpenRouter** claims pass‑through pricing but third‑party reports allege markups on specific Anthropic SKUs — verify per model. **Treat Cybench / NYU CTF Bench / CyberGym numbers as upper bounds**: CTFusion (2026) showed web‑search tool integration alone doubles CTF solve rates. Use rankings, not absolute scores.

---

## 7. Prioritized roadmap (MVP → V1 → V2)

### MVP — 4 weeks (solo first)

The MVP is shippable to a single operator (the user) on one Hetzner box. Week one stands up Postgres 17 with pgvector/pgvectorscale/ParadeDB, the Hatchet binary, FastAPI control plane, better‑auth, and a Next.js 16 dashboard skeleton with SSE log streaming. Week two delivers scope ingestion: arkadiyt cron pull, normalized programs/scopes tables, projectdiscovery weekly merge, signed RS256 scope JWT issuance, and a "show me all bounty‑paid programs with `*.example.com` in scope" query path. Week three integrates bbscope v2 with Postgres backend behind a credentials vault (SOPS+age), wires HackerOne/Bugcrowd/Intigriti/YesWeHack/Immunefi adapters, and emits change events. Week four delivers the agent runtime: LiteLLM proxy with DeepSeek V4‑Flash + Grok 4.1 Fast + Sonnet 4.6 as the multi‑model panel, Claude Agent SDK runner in hardened Docker, a single ScanWorkflow that fans out subfinder → httpx → tech‑fingerprint → nuclei (curated templates only, no aggressive payloads), and a basic findings table backed by pgvector dedup. Slack/Discord notifications and an audit log come for free.

The MVP intentionally omits: the deterministic exploit verifier, multi‑tenant isolation, payment/billing, mobile testing, smart‑contract scope, MCP marketplace, and any commercial polish. Acceptance criterion: the operator can register on a Saturday morning, point at a HackerOne handle, get fresh recon and a basic Nuclei pass with LLM triage, draft a HackerOne‑formatted report, and submit by Sunday evening — all for under $1 in LLM cost.

### V1 — 3 months

Weeks 5–8 build the **deterministic exploit verifier**: headless‑browser XSS confirmation (Playwright), SQLi time‑based statistical validator (multiple baseline samples + variance check, addressing nuclei issue #15953), SSRF callback verifier with an OAST collaborator (own subdomain + Burp Collaborator‑style HTTP+DNS exfil), open‑redirect URL parser, and SSTI sandbox. Findings without verification are tagged `unverified` and filtered out by default in the dashboard. Weeks 9–12 introduce **evidence‑gated triage**: every LLM finding must reference at least one verifiable artifact (HTTP transcript, DNS hit, DOM snapshot, screenshot) before it can transition to `submitted`. Weeks 13–16 add **mobile** (apk/ipa upload → Frida + objection in a microVM with SSL‑pinning bypass workflows), **cloud** (cloud_enum, S3Scanner, Prowler integration), and **API** (Schemathesis, Akto OSS, ffuf API mode, Postman/OpenAPI ingest). Weeks 17–20 add **smart contract scope** (Code4rena/Sherlock GitHub repo ingestion + Slither/Mythril/Medusa orchestration) and **huntr.com** integration. Weeks 21–24 polish: built‑in Langfuse dashboards, CI/CD GitHub Actions for diff‑scope quick scans (à la Strix), pause/resume/checkpoint scans (à la reconFTW), per‑target budget caps in the LiteLLM proxy.

### V2 — 6 months (SaaS readiness)

Months 4–6 add multi‑tenancy: **WorkOS AuthKit**, per‑tenant Postgres schemas (or row‑level security), per‑tenant Turbopuffer namespaces when finding count exceeds 1M, **Temporal Cloud** replacing Hatchet for SaaS, **E2B microVMs** replacing Docker for tool execution, per‑tenant LiteLLM budget ceilings, billing (Stripe + usage‑based), audit logs (append‑only Postgres + signed hashes), and the SOC 2 Type 1 readiness path (Vanta or Drata). Add an **MCP marketplace** so operators can install third‑party security MCP servers (subfinder MCP, nuclei MCP, custom recon MCP) per tenant, with the same scope JWT enforcement at boot. Add **Cloudflare Durable Objects** with WS hibernation for collaborative triage rooms. Productize a **public scope diff feed** (per‑program webhook firing when scope changes) as a free tier hook to drive funnel — this is the single most requested feature in the bbscope GitHub issues and reconFTW community.

### Risks / weaknesses / implementation challenges

The biggest implementation risk is **the deterministic exploit verifier itself** — it's the moat but also the hardest engineering problem. Off‑the‑shelf headless browsers are fragile; the SQLi time‑based detector requires statistical rigor (server latency variance under WAF/CDN can cause false positives, which is exactly why nuclei templates have known FP rates); the SSRF verifier needs a collaborator infrastructure that doesn't itself become a free OAST service for bad actors. Plan 4–6 weeks of focused engineering and budget for ongoing maintenance.

The second risk is **the AI slop trap**. Curl shut down its bounty in January 2026 because of LLM‑generated reports that "look correct on first glance." If your platform makes it easy for operators to submit unverified LLM output, you'll be banned from HackerOne and Bugcrowd within months — XBOW was once removed from a program for being "an automatic scanner." The evidence‑gated triage layer is the answer; do not ship V1 without it.

The third risk is **legal/ToS**: HackerOne, Bugcrowd, Intigriti, YesWeHack all forbid bulk redistribution of program briefs to non‑account holders. The credential‑broker pattern (each tenant supplies their own PAT) keeps you legally clean; aggregating arkadiyt's public dataset is fine but treat private‑program data as per‑user only. **Synack scope is not legitimately obtainable** — do not be tempted by community shares.

The fourth risk is **scope safety under prompt injection**. OWASP LLM01 prompt injection has roughly 84% bypass rate in industry tests, which means your scope guardrail must live at the network layer (Firecracker tap0 egress allowlist), not in agent prompts. Even Claude Opus 4.7 with extended thinking is bypassable if the scope check is "in the prompt." Make this a P0 architectural rule.

The fifth risk is **LLM cost runaway**. An agent in a recursive loop on a juicy target can burn $50 in 20 minutes — the AnyPoC paper documents reward‑hacking failure modes where agents fabricate "successful" exploits. Cap per‑scan token budget in the orchestrator and surface "scan paused, top up" UX.

The sixth risk is **vendor lock‑in**. Highest‑lock‑in‑first ranking: OpenAI Agents SDK > Cloudflare Workflows > Temporal Cloud > Clerk > LangGraph > Hatchet > Postgres‑everything. Plan exits accordingly; the Postgres‑everything baseline gives you maximal portability.

The seventh risk is **GPU supply and price volatility** for self‑hosted models. Hetzner GPU dedicated supply is intermittent; H100 spot pricing on Vast.ai swings 30–50% week to week. Build the platform to fail‑over from self‑host to API providers automatically (LiteLLM does this).

---

## 8. User pain points appendix (selected, with sources)

The full subagent appendix captured ~60 distinct pain points with direct quotes; the most actionable signals for the build plan are reproduced below.

**The "AI slop" extinction risk.** Daniel Stenberg, in late January 2026, ended curl's HackerOne bug bounty entirely after a flood of LLM‑generated false reports. Harry Sintonen warned that AI slop "could easily kill the whole concept of bug bounties" because genuine researchers quit and orgs abandon programs. Vlad Ionescu (RunSybil CTO, ex‑Meta red team) described the slop pattern: "people are receiving reports that sound reasonable, they look technically correct. And then you end up digging into them, trying to figure out, 'oh no, where is this vulnerability?'… It turns out it was just a hallucination all along." HackerOne co‑founder Michiel Prins admitted: "actual hallucination is getting less and less common. But what is getting more common is overstating things. Because these models tend to be very pleasing." Brendan Dolan‑Gavitt (XBOW) at Black Hat USA 2025: "Hopefully, I've given you lots of good reasons not to trust language models when they tell you there's a vulnerability. But there's still some hope because there's a lot of things you can deterministically verify." (Sources: bleepingcomputer.com curl ending bug bounty, socket.dev/blog/ai-slop-polluting-bug-bounty-platforms, techcrunch.com 2025-07-24, darkreading.com/vulnerabilities-threats/ai-based-pen-tester-top-bug-hunter-hackerone.)

**Nuclei false positive war.** GitHub issue projectdiscovery/nuclei-templates #15953 (April 2026) documents a CVE‑2023‑5652 SQLi time‑based template producing FPs on slow servers. Issue #13765 (October 2025) shows the external‑service‑interaction template self‑triggering via redirect chains. Issue #14950 (January 2026) reveals a flow‑logic bug that returns "matched" prematurely. Issue #15563 cites "extremely high false positives in credentials‑disclosure template" due to over‑permissive regex. ProjectDiscovery's own Ultimate Nuclei Guide warns: "Many people run Nuclei on its default settings, making it highly likely that you'll just get the same findings as everyone else."

**Burp Suite / proxy pain.** Burp Pro is now $499/year and seen as a barrier ("a lot of money for some people," thexssrat). Burp's authenticated scanner can't combine credentials and recorded login sequences, only one auth method per scan. The PortSwigger forum has unresolved threads on SPA + STS + OpenID Connect + OAuth2 authenticated scanning. Caido pricing ($200/yr individual, $30/seat/mo team) drove regional discounts in Brazil and India because base pricing was unaffordable in many markets.

**The "I built my own" pattern.** Hakluke's classic Detectify Labs retrospective: he reverted to manual httpx/nuclei tools after his automation bash script "errored out somewhere along the line and found zero bugs" overnight. He explicitly identified the missing piece: "I wanted to combine the power of the Unix philosophy with the power of horizontal scaling and relational databases" — that gap is still open. Muhammad Faizan Anwar's "RECON GHOST" Medium post: "You spend hours running a dozen different tools — Amass, Subfinder, Httpx, Nmap, FFUF, Aquatone… The recon process is fragmented, messy, and full of false positives." canuk40/xpfarm README explicitly motivates the project as: "Tools like Assetnote are great… But they're not open source." shuvonsec/claude-bug-bounty: "Instead of juggling 15 different tools and writing reports from scratch, you just type a command and the AI handles the rest." Penligent (2026) coined the right framing: "Many 2026 workflows are breaking under the cost of context switching."

**Setup pain.** RECON GHOST author: "from GitHub cloning nightmares to dependency hell." reconftw issue #1004 documents scans hanging on `sub_brute` for a full day. The reconftw FAQ openly states: "Red‑colored tools in the install.sh output indicate installation failures." HexStrike v6's marketing leans heavily on "one‑command setup" specifically because prior setup pain is universal. Setting up an Axiom hacking VPS used to be "an afternoon project, sometimes a whole day."

**Distributed compute pain.** DigitalOcean's 10‑droplet limit is the universally‑cited chokepoint. `axiom-rm "*"` deletes other VPSes ("trust me, I learned the hard way"). Cloud providers ban port‑scanning ("not only will you be banned, but also you could get in legal lawsuit"). $5–$20/month VPS forever isn't enticing for the "I just need a public IP to catch a shell now" use case.

**Mobile and API pain.** Frida crashes apps mid‑session, forcing re‑login (Optiv blog). UI animator‑thread bugs manifest as "Animators may only be run on Looper threads." BugHunter's Journal February 2026: "most hunters skip mobile testing entirely… because of myths: 'The setup is complicated.' 'I need expensive phones.'" Postman pulled offline‑first features, stranding pentesters who needed to import OpenAPI specs without a cloud account. APIsec: "API breaches happen because automated scanners can't detect business logic flaws. When T‑Mobile exposed 37 million records… both breaches stemmed from authorisation failures that no scanner flagged."

**Triage / dedup pain.** bl4de calls duplicates "the worst feeling bug bounty hunter can feel." Bugcrowd's own blog notes program owners often mishandle dupes: "It may be tempting to assert that they're all one‑in‑the‑same, but that is very rarely the case… each requires a unique fix." Nuclei v3.x added `-honeypot-detect`, `-honeypot-threshold`, `-suppress-honeypot` flags as implicit acknowledgment of honeypot‑induced FP storms.

**Scope management pain.** sw33tLie's bbscope README is itself a pain‑point declaration: "bbscope is a powerful scope aggregation tool… designed to fetch, store, and manage program scopes from HackerOne, Bugcrowd, Intigriti, YesWeHack, and Immunefi right from your command line." The v2 release added an opt‑in "LLM Cleanup" feature explicitly because scope strings are messy. sw33tLie's own Bugcrowd LevelUp post calls "recon over time" — differential scope tracking — "still elusive" in 2025.

**Notifications pain.** The existence of Notify, Discord‑Recon, Sambal0x's Recon‑tools (Slack webhook plumbing) all signal the same gap: no platform ships native ChatOps. Hunters end up gluing Discord webhooks manually because there's no remote control plane.

**Cost pain.** Pentera's 2025 State of Pentesting survey: "45% of enterprises expanded their security technology stacks, with organizations now managing an average of 75 different security solutions. Yet despite these layers of security tools, 67% of U.S. enterprises experienced a breach." Tool‑sprawl plus per‑seat pricing is a market failure.

The implication for the build plan is straightforward: **own these pain points as positioning**. The clean‑slate platform's marketing copy writes itself — "one rail across HackerOne/Bugcrowd/Intigriti/YesWeHack/Immunefi/huntr; deterministic verification before any LLM finding is shown; native Slack/Discord/Telegram; one‑command Hetzner deploy; sub‑$0.20 full‑triage scans." Every claim in that sentence maps to a documented user pain.

---

## 9. Closing argument and novel insights

The dominant narrative across both commercial and open‑source competition in April 2026 is **convergence on a multi‑agent + deterministic verification architecture**. XBOW, RidgeBot RidgeGen, Terra Security, Hadrian Nova, Strix, Shannon, NeuroSploit, AutoPentest‑AI, Pentest‑Swarm‑AI all independently arrived at the same shape: a supervisor orchestrating specialized recon, exploit, and validation sub‑agents, with the validation step deliberately separated from generation and grounded in deterministic execution. The novel insight is that **the agent runtime is no longer the moat**. Claude Agent SDK, LangGraph, Temporal, and the OpenAI Agents SDK are all good enough that what differentiates platforms is **the verification oracle, the scope ingestion breadth, and the operator workbench transparency**.

The second novel insight is that **the cost curve has collapsed**. A solo bug bounty hunter can run full‑triage scans at sub‑$0.20 with DeepSeek V4‑Flash today; this was not true twelve months ago. The economic implication is that the existing "per‑seat $475/yr Burp + $200/yr Caido + $20/mo VPS" baseline is no longer competitive — a clean‑slate platform can ship at a fraction of that cost and still land 80% of the capability. **The price floor for serious bug bounty automation in 2026 is the LLM API bill plus a Hetzner box, not a Burp license.**

The third novel insight is that **AI slop is the platform's greatest existential risk and greatest differentiation opportunity simultaneously**. Curl shutting down its program is the canary; HackerOne launching Hai Triage and Bugcrowd acquiring Mayhem are the establishment responses. A clean‑slate platform that bakes evidence‑gated triage and deterministic verification into the product as P0 features — not as an enterprise add‑on — earns trust with both operators and program owners faster than competitors who treat verification as an afterthought.

The fourth novel insight is that **MCP is becoming the ambient integration substrate for offensive security**. Tencent A.I.G, AutoPentest‑AI's 68 MCP tools, the Microsoft Agent Governance Toolkit, the Burp PortSwigger MCP server, the Bug Bounty MCP — all imply that within 12 months, "is this tool MCP‑compatible?" will be a default purchase question. Building MCP server gateway plus MCP marketplace into V2 is an obvious bet.

The fifth and most important insight is that **the platform must be designed under the assumption that frontier offensive AI is an active participant in the threat landscape**. Anthropic Mythos found a 27‑year‑old OpenBSD bug. CyberStrikeAI is in active threat actor hands compromising 600+ FortiGate devices. CrowdStrike's 2026 Global Threat Report documents APT28 (FANCY BEAR) deploying malware that queries an AI model in real time. Defensive bug bounty automation is no longer a "nice productivity tool"; it is an asymmetric counter to rapidly‑improving offensive AI. A clean‑slate platform built today with this assumption — sandboxed by default, evidence‑gated, scope‑signed, audit‑logged, MCP‑native, transparent — has a structural advantage over both legacy commercial vendors retrofitting agentic features and pure‑hype agentic startups skipping the safety rails.

Build the workbench, not the hero agent.