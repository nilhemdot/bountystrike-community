# BountyStrike v6 Research Report: Dual-Product Strategy, 2026 Pressure-Test & UX Blueprint

## TL;DR
- **The v5 plan is empirically sound but underweights two seismic shifts**: (1) the offensive-security category has rebranded as "Adversarial Exposure Validation" (AEV) within Gartner's CTEM framework, with ≥$430M of funding closing in just six months across XBOW, Tenzai, Novee, RunSybil, Surf AI, and Terra Security — every BountyStrike claim about market timing is VERIFIED or UPDATED, none REFUTED. (2) The "AI slop" thesis is now confirmed by curl, which shuttered its HackerOne program Jan 31, 2026 with confirmed-vuln rate "below 5%" (Stenberg, daniel.haxx.se/blog/2026/01/26).
- **Recommended dual-product architecture**: ship a **GPL-or-AGPL solo CLI** (BountyStrike Community Edition) backed by an **enterprise SaaS gated by feature flags around CTEM stages 3–5** (Prioritization, Validation, Mobilization), using HashiCorp + GitLab + Snyk's open-core gating playbook. Price the enterprise tier at $25K–$150K platform fee plus per-asset metered usage — undercutting Pentera's $100K ACV (Amitai Ratzon, Pentera CEO, on $100M ARR: "Becoming the first adversarial testing company to surpass $100 million in ARR is the result of focus, commitment and a great product-market fit") and Hadrian's per-test model, premium to Cobalt's $8.5K starter, with a free-forever Community Edition matching Caido's individual tier ($0–$200/yr).
- **Killer UX is now table stakes, not a differentiator**: Linear-style command palette + Cursor-style agent stream + Stripe-style evidence drilldown is the convergent pattern across XBOW, Pentera Peer, Hadrian Nova, and Terra Portal. The empirical UX advantage in 2026 comes from **live exploit replay, evidence-anchored audit trails (Sigstore Rekor), and CTEM-stage progress bars** — not yet table stakes anywhere.

## Key Findings

### Track 1 — Pressure-Test of Every Empirical Claim in v5

| Claim from v5 | Status | Updated Value & Primary Source |
|---|---|---|
| curl HackerOne shut down Jan 31, 2026 with <5% confirmed rate | **VERIFIED** | Daniel Stenberg, "The end of the curl bug-bounty" (daniel.haxx.se/blog/2026/01/26): "87 confirmed vulnerabilities and over 100,000 USD paid as rewards." Confirmed-rate ">15% historically, by 2025 below 5%" (softwareseni.com synthesis). |
| HackerOne 9th HPSR: 210% AI vuln, 540% prompt injection | **VERIFIED** | HackerOne press release, Oct 1, 2025: "210% Spike in AI Vulnerability Reports," "540% surge in prompt injection vulnerabilities," "1,121 distinct customer programs included AI in scope... a 270% increase year over year." (hackerone.com/press-release) |
| Claude Mythos / Project Glasswing announced April 7, 2026; 83.1% CyberGym; 27-yr OpenBSD bug; 16-yr FFmpeg flaw past 5M fuzzer runs | **VERIFIED** | Anthropic, red.anthropic.com/2026/mythos-preview/ and anthropic.com/glasswing. CyberGym: 83.1% vs Opus 4.6's 66.6%. OpenBSD TCP SACK 27-year vuln found at ~$50/successful run; FFmpeg 16-yr at ~$10K total; FreeBSD CVE-2026-4747 (17-yr NFS RCE). 12 launch partners: AWS, Apple, Broadcom, Cisco, CrowdStrike, Google, JPMorganChase, Linux Foundation, Microsoft, NVIDIA, Palo Alto Networks. $100M credits + $4M open-source grants. |
| Shannon (Keygraph) 96.15% XBOW benchmark | **VERIFIED — caveat** | Keygraph official: 100/104 on a **hint-free, source-aware (white-box, cleaned) variant** of XBOW (github.com/KeygraphHQ/shannon). NOT comparable to XBOW's own ~85% black-box benchmark. |
| Deadend CLI 80% XBOW with Kimi K2.5 at $122 total | **VERIFIED** | github.com/xoxruns/deadend-cli: "Kimi K2.5 (~80%, ~US$122 for the full 104-challenge XBOW validation run)." Claude Sonnet 4.5 ~78%, Kimi K2 Thinking ~69%. |
| GTG-1002 China-affiliated, AI did 80-90% of work across ~30 orgs | **VERIFIED** | Anthropic threat report (assets.anthropic.com/m/ec212e6566a0d47/...), published Nov 13, 2025. "Roughly 30 entities... validated a handful of successful intrusions... 80-90% of tactical operations independently." |
| CyberStrikeAI 600+ FortiGate compromises Jan-Feb 2026 across 55 countries | **VERIFIED** | Amazon Threat Intelligence + Team Cymru (thehackernews.com/2026/03). 21 unique IPs Jan 20–Feb 26, 2026. **Critical clarification**: attacker was a Russian-speaking financial actor; tool was Chinese (developer Ed1s0nZ, ties to CNNVD/Knownsec 404). Used Claude + DeepSeek as LLM providers. CJ Moses (Amazon CISO): "exploiting exposed management ports and weak credentials with single-factor auth." |
| CrowdStrike 2026: 89% AI surge, 29-min eCrime breakout, 27-sec fastest, 82% malware-free, 42% pre-disclosure exploitation | **VERIFIED** | CrowdStrike 2026 Global Threat Report (Feb 24, 2026): all five numbers exact. (crowdstrike.com/2026-global-threat-report) |
| Anthropic 70%+ refusal rate for payload generation | **NOT FOUND** | No peer-reviewed or industry source returned this exact figure within search budget. v5 should either soften the claim or cite a specific internal benchmark; recommend the HackerOne HPSR's payload-analysis data (45,000 payload signatures, 23,579 reports) as a more defensible adjacent metric. |
| XBOW ~25% Informative/N/A rate on H1 submissions | **NOT FOUND** | Not directly verified in search budget. XBOW is publicly known to be #1 on HackerOne US leaderboard (2025); the 25% Informative-or-N/A rate is plausible but uncited. **Mark v5 as "industry estimate, not vendor-confirmed."** |
| HackerOne April 2026 deprecated `structured_scopes` for org-level asset management | **NOT FOUND** | Not retrieved in search budget. v5 should validate against HackerOne API changelog directly before relying on this in code. |
| XBOW Series C closed March 2026 at $120M / $237M total / unicorn valuation | **VERIFIED** | XBOW press release March 18, 2026: $120M Series C, **$237M total** (PitchBook shows $272M including a May 2026 $35M extension from Accenture/NVentures/Samsung), led by DFJ Growth & Northzone, valuation "over $1B." Customers: UKG, Samsung SDS, Moderna, Five9. |
| Tenzai $75M seed Nov 2025 with Greylock + Battery + Lux | **VERIFIED** | Tenzai press release Nov 11, 2025. Valuation $330M per TradedVC. Founded by Guardicore veterans (Pavel Gurvich, Ariel Zeitlin) + Snyk founding CPO Aner Mazur. |
| RunSybil $40M Mar 2026 with Khosla, Anthology, Conviction, Elad Gil | **VERIFIED** | RunSybil announcement March 18, 2026. Founders Ari Herbert-Voss (OpenAI's first security hire) + Vlad Ionescu (Meta red team lead). Customers: Cursor, Notion, Turbopuffer, Baseten, Thinking Machines Lab, "several major financial institutions and Fortune 500." |
| Terra Security $38M total / $30M Series A Sep 2025 | **VERIFIED** | Felicis-led, Sep 15, 2025. $8M seed (April 2025) + $30M Series A = $38M total. Gerhard Eschelbeck (former Google CISO) on board. Customers: "Fortune 500 enterprises." |
| Hadrian Nova launched March 24, 2026 at RSAC; 99.5% FP elimination | **VERIFIED** | Hadrian press release March 24, 2026. **Per-test pricing** (not subscription), SOC 2 Type II + ISO 27001 certified, three-year GigaOm ASM Leader. |
| Novee $51.5M Series A January 2026 | **VERIFIED** | Novee out-of-stealth Jan 14, 2026: $51.5M ($8.5M seed May 2025 + $33M Series A Sep 2025 + $10M venture debt Dec 2025). YL Ventures + Canaan + Zeev. Customers: K Health, HiBob, Reco, Cresta, Telit, JB Poindexter. Claims 90% accuracy on constrained web exploitation challenges, "55% over frontier LLMs like Gemini 2.5 Pro and Claude 4 Sonnet." |
| Surf AI $57M March 2026 RSAC launch with Accel | **VERIFIED** | Surf AI launch March 17, 2026. **Note**: Surf AI is NOT an offensive-security platform — it's an "agentic operations platform" for security hygiene (identity, cloud, SaaS spend reclamation). v5 may have miscategorized. |
| Bugcrowd acquired Mayhem Security (ForAllSecure) Nov 4, 2025 | **VERIFIED** | Bugcrowd press release Nov 4, 2025. Mayhem had raised $36-38M (incl. $21M 2022). David Brumley becomes Bugcrowd's Chief AI & Science Officer. Bugcrowd's pre-acquisition valuation: "over $1 billion" post-$102M Feb 2024 round; acquisition "nearly doubled" valuation. |
| EU CRA effective Sep 11, 2026 with 24h/72h/14d disclosure timelines; ENISA SRP operational same date | **VERIFIED** | European Commission digital-strategy.ec.europa.eu/en/policies/cra-reporting. Article 14: 24h early warning + 72h detailed notification + 14d final report (for actively-exploited vulns) or 1-month (for severe incidents). Fines: up to €15M or 2.5% global turnover. Single Reporting Platform scheduled operational by Sept 11, 2026. Full CRA applies Dec 11, 2027. |
| DeepSeek V4-Flash pricing $0.14/$0.28 per M tokens | **UPDATED** | Per DeepSeek official API docs: DeepSeek-V3.2 / V4-Flash cache-miss input **$0.28/MTok**, output **$0.42/MTok**, cache-hit input **$0.028/MTok**. The v5 "$0.14/$0.28" figure is REFUTED — output is $0.42, not $0.28. Use $0.28 input / $0.42 output, with cache-hit at $0.028. |
| Anthropic BYOK 1M free requests/month via OpenRouter | **VERIFIED** | OpenRouter announcement Oct 1, 2025 (openrouter.ai/announcements/1-million-free-byok-requests-per-month). "Every customer gets 1,000,000 BYOK requests per month for free. ... For customers exceeding 1m req/month, requests will be charged at the usual rate of 5%." |
| Claude Code v2.1.89+ defer primitive (April 1, 2026) | **VERIFIED** | Claude Code CHANGELOG.md v2.1.89, April 1, 2026: "Added 'defer' permission decision to PreToolUse hooks — headless sessions pause at a tool call, resume with -p --resume for hook re-evaluation." |
| Welch's t-test p<0.01 for blind SQLi detection | **NOT FOUND in academic literature** | No peer-reviewed or sqlmap source-code reference to Welch's t-test for blind SQLi was retrievable. v5 should re-frame as an engineering heuristic, not a citation-backed academic technique, OR provide its own benchmark validation showing FP/FN rates. |
| EV formula λ=0.00065, μ=0.00963 | **NOT FOUND** | No underlying derivation surfaced. Treat as proprietary heuristic constants — document the calibration methodology in v6. |

### Track 2 — Dual-Product Positioning & Enterprise Market Fit

**Open-core precedents (Q1-Q2 2026 list prices, primary-source verified):**

- **HashiCorp HCP Terraform** (post-IBM acquisition Sep 2025): four tiers Free/Essentials/Standard/Premium + Enterprise self-managed. **Per-managed-resource (RUM) pricing**: Essentials $0.10/resource/mo, Standard $0.47, Premium $0.99. Free tier capped at 500 managed resources (the legacy user-based Free tier sunsetted March 31, 2026). Enterprise self-hosted ≥$15K/yr.

- **GitLab** (about.gitlab.com/pricing): Free $0 (capped 5 users/group on SaaS), Premium **$29/user/mo SaaS** ($19 self-managed), Ultimate **$99/user/mo**. Gating principle: individual-contributor features in Free, manager-tier in Premium, security/compliance (SAST/DAST/fuzz/portfolio mgmt) in Ultimate. This is the cleanest "buyer-based" open-core model and the best template for BountyStrike.

- **Elastic** (elastic.co/blog/elasticsearch-is-open-source-again): Triple-licensed Sep 2024 — SSPL + Elastic License v2 + **AGPLv3 (OSI-approved)**. The MongoDB SSPL drama is officially resolved; Elastic's compromise is the new template.

- **Nuclei / ProjectDiscovery Cloud**: Now **only Free + Enterprise** — the middle Pro/Growth tier was removed mid-2025. Open-source Nuclei CLI remains free under MIT-like terms; Cloud Free is gated to monthly scans only, ≤10 domains. Enterprise gates: SSO/RBAC, audit logs, SOC 2/ISO 27001/PCI/HIPAA attestations. ProjectDiscovery launched **"Neo"** in 2026 as an autonomous AI offensive platform (separate from Nuclei Cloud) — direct BountyStrike competitor.

- **Snyk**: Free (limited tests/month) → **Team $25/dev/mo** → **Ignite $105/dev/mo (NEW in 2026, mid-tier for 11-49 devs)** → Enterprise custom ($697–$948/dev/yr observed). Snyk introduced a **credit-based "Platform Credit Consumption" license** for new contracts starting Jan 1, 2026.

**Bug bounty / pentest commercial pricing (best-available 2026 data):**

- **HackerOne** (Vendr aggregated): platform fees $20K–$200K+/yr; VDP first-year ~$40K-$120K; enterprise $400K-$1M+/yr. **20% success fee on bounty awards** (PeerSpot user reports; not officially confirmed by HackerOne).
- **Bugcrowd**: platform fees $30K-$150K+/yr; managed pentest engagements $25K-$100K+ each. Forrester TEI assumes composite at $100K platform + $100K rewards pool.
- **Cobalt PTaaS**: credit-based, **1 credit = 8 pentest hours**, packages from **$8,500**. Essentials $65K–$90K first year; Professional $35K–$60K platform + $75K–$100K credits; Enterprise $200K+.
- **Burp Suite Professional 2026**: $475/yr effective Jan 6, 2026 per PortSwigger's global price adjustment (Beagle Security, beaglesecurity.com: "individual professionals can access Burp Suite Professional for $475 annually"). The price adjustment applies to Pro only, not Burp Suite DAST. DAST/Enterprise observed in the $6K-$50K+/yr range (third-party aggregated).
- **Caido** (caido.io/pricing): Free + **Pro $200/yr** + **Team $30/user/mo** + Enterprise custom + free 1-yr student plan.
- **Pentera**: Amitai Ratzon, Pentera CEO, in the company's $100M ARR announcement: "Becoming the first adversarial testing company to surpass $100 million in ARR is the result of focus, commitment and a great product-market fit." Pentera's own blog calls itself "the first company in Gartner's Adversarial Exposure Validation space to cross $100M ARR and become a Centaur" with "more than 1,200 enterprises in over 60 countries." Calcalist (March 2025 Series D coverage) confirmed "average deal size has quadrupled... now reaching $100,000," consistent with the $100M ARR ÷ ~1,200 customers ≈ $83-100K math. Pentera 8 with **Pentera Peer NL interface GA Q2 2026**.
- **Horizon3.ai NodeZero**: UK G-Cloud 14 price book is the only public per-IP source: **£40/IP/yr at ≤2,500 IPs, declining to £16/IP/yr at 15,000 IPs**, includes internal+external testing.
- **Hadrian Nova**: **per-test pricing** (announced at RSAC March 24, 2026) — no public per-test figure but the model is novel (zero-procurement-friction).

**Gartner categorization 2025-2026:**

- **CTEM** (introduced 2022, updated Oct 2023): the five stages are official — **Scoping → Discovery → Prioritization → Validation → Mobilization**. Gartner's published prediction, per Gartner, "How to Manage Cybersecurity Threats, Not Episodes," August 21, 2023 (as cited by AttackIQ at attackiq.com/ctem) and "Implement a Continuous Threat Exposure Management (CTEM) Program," October 11, 2023, Jeremy D'Hoinne et al. (cited by SimSpace): "By 2026, organizations that prioritize their security investments based on a continuous threat exposure management program will be three times less likely to suffer a breach."

- **Adversarial Exposure Validation (AEV)**: Gartner's Market Guide first published March 11, 2025; **updated March 24, 2026**. AEV REPLACED separate Breach-and-Attack-Simulation (BAS) and automated-pentesting categories from the 2023 Hype Cycle. **Representative Vendors (2025 Market Guide)**: Pentera, Horizon3.ai (NodeZero), Picus Security, Cymulate, SafeBreach, AttackIQ, BreachLock, FireCompass, NetSPI, RidgeBot, PortSwigger (Burp Suite Pro). **No Magic Quadrant yet** as of May 2026 — only Market Guide + Hype Cycle + Peer Insights "Voice of the Customer." **XBOW is NOT in the published Representative Vendor list** despite category-leading press coverage — interesting positioning gap.

**Enterprise procurement requirements (verified):**

- **SOC 2 Type II**: 3-month minimum observation, 6-month typical first-time, 12-month for renewals. Full first-time program 6-15 months (typically quoted **9-12 months**). Sprinto, Drata, Vanta consistent.
- **FedRAMP Moderate (Rev 5)**: 323-325 controls; initial auth $500K-$1.5M, annual maintenance $200K-$500K, timeline **12-18 months avg**. **FedRAMP 20x** automation-first track in pilot — Phase 2 Moderate ended March 2026, broader Low/Moderate openings Q3 2026. 20x Moderate target cost $100K-$300K.
- **FedRAMP High**: 410-421 controls; $1M-$3M+ initial, $500K-$1M annual.
- **EU NIS2**: deadline was Oct 17, 2024. As of mid-2025 Secomea (secomea.com) confirms exactly "16 EU and EEA countries" had transposed; however the European Commission's May 7, 2025 issuance of reasoned opinions to 19 of 27 EU Member States (digital-strategy.ec.europa.eu) implies **only 8 of 27 EU-only members had fully transposed at that precise date**. By January 1, 2026, the count rose to **20 of 27 EU Member States** per Wavestone (wavestone.com, citing the EC NIS2 tracker). By late 2025/early 2026: Germany transposed (NIS2UmsuCG Dec 6, 2025); Portugal, Austria adopted. **On Jan 20, 2026 the Commission proposed targeted NIS2 amendments to ease compliance for ~28,700 companies.** v5 should treat NIS2 as still-in-flux, not as a finished obligation.

### Track 3 — Killer UX Patterns (synthesized from competitive scans)

**The convergent 2026 pattern across XBOW, Pentera Peer, Hadrian Nova, Terra Portal, RunSybil:**
1. **Natural-language interface as the primary entrypoint** (Pentera Peer GA Q2 2026 is the most explicit; Hadrian, RunSybil all show NL prompt boxes in marketing materials).
2. **Per-test rather than annual-subscription pricing UX** (Hadrian Nova explicitly priced per-test "zero procurement friction"; Cobalt's credit model).
3. **Evidence-anchored findings** (Shannon's "no exploit, no report" policy; XBOW's "every potential finding through real exploitation"; Novee's "exploit validation"). This is now table-stakes — BountyStrike's Sigstore Rekor anchoring is differentiated only if exposed in UI.
4. **Human-in-the-loop gates** (Terra explicit; Hadrian "human-and-AI collaboration"; HackerOne's hybrid agentic+researcher Mar 2026 product launch).
5. **CTEM stage visualization** — none of the competitors are doing this well yet. **This is BountyStrike's UX opening.**

**Best-in-class to crib from (established):**
- Linear (Cmd+K palette, multiplayer cursors, keyboard-first)
- Stripe Dashboard (evidence drill-down, audit-trail-first)
- Vercel (live log streaming for AI agents — direct analog to agent reasoning streams)
- Cursor IDE (agent panel with intervention points)
- Tailscale admin console (network topology visualization)
- Drata/Vanta (compliance posture progress bars)

### Track 4 — SaaS Infrastructure Pressure-Test

**v5 architecture vs 2026 best practice:**

| v5 choice | 2026 verdict | Notes |
|---|---|---|
| Hetzner CCX22 solo | **KEEP** | Hetzner remains the cost/performance leader for solo deployments. |
| Hatchet + Temporal | **KEEP — bias to Temporal Cloud** | Temporal Cloud is the multi-tenant standard. |
| Firecracker/E2B microVMs | **KEEP** | E2B's pricing remains competitive. |
| Postgres + RLS multi-tenant | **KEEP** | The default. Per-tenant Turbopuffer namespaces remains a strong choice. |
| WorkOS AuthKit | **KEEP** | SAML 2.0, OIDC, SCIM — all required for enterprise. |
| R2 for blob storage | **KEEP** | Cost/egress advantage stands. |
| Cloudflare Workers for edge | **KEEP** | Still best-in-class. |
| SOPS + age for secrets | **KEEP for solo; consider HashiCorp Vault (IBM-owned post-Sep 2025) for enterprise** | |

**New 2026 considerations to add:**
- **Easy deploy pattern**: Coolify and Dokploy have surpassed Easypanel for solo deployments. Add a Coolify one-click template.
- **microsandbox (Rust)** has matured as a Firecracker alternative — worth a benchmark.
- **Daytona** as a dev-environment-on-demand for the SaaS "playground" tier.
- **HIPAA-eligible AWS services** + GovCloud are required for healthcare/government deals — gate behind Enterprise tier.

### Track 5 — New Competitors Since v5 (Apr 28, 2026)

In the three weeks since v5 was written, the only material additions are:
- **Assail Ares** (RSAC 2026 Day 2 launch) — autonomous red-teaming for APIs/mobile/web, "self-healing, self-teaching." (SecurityWeek RSAC 2026 Day 2 summary)
- **Konvu** — RSAC Launch Pad finalist for AI-based vuln prioritization and reachability. Customer claim: "fintech SaaS with 2,000+ employees flagged 81% of their Snyk findings as false positives."
- **MindFort** — positioned as the only autonomous platform that *both* exploits and remediates; pricing starting **$1,000/month**, explicitly targeting SMB segment.
- **AISLE** — used AI to find 12 of 12 OpenSSL zero-days with zero invalid reports — the **gold-standard "expert-guided AI" model**, contrasts with curl's AI-slop story. OpenSSL CTO Tomáš Mráz publicly verified the work: "This release is fixing 12 security issues, all disclosed to us by AISLE. We appreciate the high quality of the reports and their constructive collaboration with us throughout the remediation." (AISLE blog "AISLE Discovered 12 out of 12 OpenSSL Vulnerabilities," aisle.com, January 27, 2026.) AISLE is also credited for 13 of 14 OpenSSL CVEs assigned across 2025.

Plus the funding events already covered: XBOW Series C extension ($35M from Accenture/NVentures/Samsung/S Ventures, May 2026), Tenzai ($75M seed), Novee ($51.5M), RunSybil ($40M), Hadrian Nova launch.

### Track 6 — `/effort ultraplan` Inputs

**Monorepo recommendation**: **pnpm workspaces + Turborepo** for the dual-product layout — established 2026 default, Bazel is overkill for the team size.

**Feature flag system**: **OpenFeature + Unleash (self-hosted) for OSS; LaunchDarkly for SaaS tenants** — this matches GitLab's pattern. Don't lock into a single vendor at the SDK layer.

**Code quality and testing for security tools:**
- Property-based testing with `fast-check` (TS) and `Hypothesis` (Python)
- Mutation testing with Stryker for TS, mutmut for Python
- Adversarial agent testing: fuzz the orchestrator with malformed scope ingests

**CI/CD must-haves**: Sigstore signing on every release artifact, SLSA Level 3 build provenance, in-toto attestations, container image attestations via cosign, SBOM via Syft. This is now baseline for any security tool sold to enterprises post-Project Glasswing (April 2026).

## Details

### Why the Mythos / Glasswing announcement reshapes BountyStrike positioning
The April 7, 2026 Glasswing launch did three things that change the v5 plan's center of gravity:
1. **It validated the "AI finds critical bugs cheaper than humans" thesis at the frontier** — $50 per successful run on a 27-year OpenBSD bug. This is a stronger empirical anchor than v5's earlier benchmarks.
2. **It created a 90-day disclosure window during which 50+ Glasswing partners have a structural advantage.** The public report lands in early July 2026. BountyStrike v6 should position itself as the open tooling that levels this advantage for everyone outside the 12 launch partners — and for the open-source maintainers who get patches but no tools.
3. **It establishes Mythos pricing at $25/$125 per million tokens** (5× Opus), which **raises BountyStrike's per-scan cost target**. The <$0.20/scan solo target is likely still hittable via Sonnet/Haiku routing, but the SaaS tier pricing ($5/$50/$200) needs to be re-derived against this new ceiling.

### The CTEM positioning play
Gartner CTEM's five stages map almost perfectly onto BountyStrike's nine subagents:

| CTEM stage | BountyStrike subagents | Gating tier |
|---|---|---|
| Scoping | scope-guard, orchestrator | OSS Free |
| Discovery | recon, cloud-recon | OSS Free |
| Prioritization | ai-vuln-hunter, dedup | OSS Free for solo / **Enterprise for cross-tenant + business context** |
| Validation | exploit, validator | OSS for self-hosted / **Enterprise for managed sandbox** |
| Mobilization | reporter | OSS for individual reports / **Enterprise for SOAR/Jira/ServiceNow integration** |

This is the natural feature-gating boundary. It also maps to the AEV (Adversarial Exposure Validation) market definition, putting BountyStrike head-to-head with Pentera, Horizon3, Picus, Cymulate, SafeBreach, AttackIQ on the Gartner Representative Vendor list **as a category entrant rather than a bug-bounty-only tool** — exactly the dual-product positioning the user mandated.

### Pricing recommendation
**BountyStrike Community Edition**: AGPLv3 (Elastic's compromise — protects against SaaS-cloning while keeping OSI-approved). Free forever. Self-hosted. All nine subagents, all benchmarks Shannon/Deadend-style. The competitive entry-point against Caido ($200/yr Pro), Burp Pro ($475/yr at the new Jan 6, 2026 list price), and individual Nuclei users.

**BountyStrike Cloud (Solo SaaS)**: $29/user/month — undercuts Cobalt's $8.5K starter by an order of magnitude, matches GitLab Premium's anchor. Cloud-hosted, BYOK, multi-tenant Postgres+RLS. Gates: scheduled scans, evidence retention beyond 30 days, multiplayer.

**BountyStrike Enterprise**: starts at $25K platform/yr + metered per-asset pricing (target ~$15-25/asset/yr at volume — undercuts NodeZero's £40/IP at the small end). Gates: SSO/SCIM, SOC 2 / ISO 27001 attestation, audit log export, BYOK with AWS KMS/Vault, FedRAMP-eligible deployment, ServiceNow/Jira/SOAR integration, AEV/CTEM compliance reports. Target ACV $100-150K, slightly below Pentera's $100K, well above Cobalt's mid-market mid-point.

**BountyStrike Sovereign**: air-gapped, on-prem, Vault-integrated. $250K+/yr. For defense, government, financial services. Required if pursuing FedRAMP Moderate.

### Empirical claims to drop or revise from v5
- The **70% Anthropic refusal rate** — soften to "refusal behavior is documented but exact rates vary by task; payload generation falls back to Venice Dolphin / Hermes-4-70B for known-refusal cases."
- The **DeepSeek V4-Flash $0.14/$0.28** — correct to **$0.28 input / $0.42 output** (cache-miss); add **$0.028/MTok cache-hit input** as a separate line item for prompt-cached bulk triage.
- The **XBOW 25% N/A rate** — re-frame as "industry estimate."
- The **Welch t-test p<0.01** — re-frame as "engineering heuristic with empirical FP/FN calibration; not derived from academic literature."

## Recommendations

**Phase 1 (next 8 weeks)** — pressure-test before any code changes
1. Update the v5 plan with all VERIFIED/UPDATED markings from Track 1.
2. Replace the four NOT-FOUND/REFUTED empirical claims (DeepSeek pricing, refusal rate, XBOW N/A, Welch t-test) with directly defensible substitutes.
3. Run a single BountyStrike scan against the Shannon and Deadend CLI XBOW benchmark variants and publish the comparative results — this becomes BountyStrike's own "we beat / are competitive with X" marketing anchor.

**Phase 2 (weeks 9-16)** — open-core split
4. Restructure the monorepo into `bountystrike-community` (AGPLv3) and `bountystrike-enterprise` (proprietary), with shared `bountystrike-core` library under Apache 2.0.
5. Implement feature flag system at the agent boundary — every subagent's "enterprise-only" mode (managed sandbox, cross-tenant correlation, AEV report export) flagged behind a single `tier=enterprise` check.
6. Ship a `curl | bash` one-line installer for Community Edition (Hetzner + Coolify template).

**Phase 3 (weeks 17-28)** — enterprise SaaS GA
7. Begin SOC 2 Type II observation period **immediately** — even at a 3-month minimum window, you cannot ship to enterprise without it.
8. WorkOS AuthKit (SAML/OIDC/SCIM) live before any enterprise pilot.
9. Build the CTEM five-stage progress UI — this is the table-stakes UX feature competitors are not yet shipping well.
10. Ship `BountyStrike CRA Companion` — a free tool that takes any BountyStrike finding and produces a CRA Article 14 24h/72h/14d draft notification template. This is a no-brainer EU market hook for the Sep 11, 2026 deadline.

**Phase 4 (weeks 28-40)** — sovereign / government track
11. Initiate FedRAMP 20x Moderate pilot application (Phase 2 ended March 2026; new openings Q3 2026 target). Budget $100K-$300K vs $500K-$1.5M for legacy FedRAMP.
12. Hadrian-style per-test pricing as a sales motion for procurement-friction-allergic buyers.
13. Add a BountyStrike Glasswing-style "expert-guided AI" program — partner with 5-10 OSS security maintainers to use BountyStrike on their codebases, AISLE-style (12 of 12 OpenSSL CVEs with zero invalid reports). This is the AI-slop antidote — and OpenSSL CTO Tomáš Mráz's public endorsement of AISLE's "high quality of the reports and... constructive collaboration with us throughout the remediation" is the marketing template to emulate.

**Benchmarks/thresholds that would change these recommendations:**
- If Anthropic releases Mythos publicly before July 2026, the entire AEV category gets compressed — re-evaluate the per-asset pricing on the assumption competitors will be pricing at Mythos token cost ($25/$125 per MTok).
- If Pentera 8 GA Q2 2026 ships with a free tier or significantly undercut SMB tier, accelerate Phase 2.
- If the EU passes the Jan 2026 NIS2 amendments meaningfully easing SMB obligations, the CRA Companion play becomes weaker — pivot to a US SLSA/SBOM angle.
- If a Mayhem-style acquisition happens to a key BountyStrike competitor (Terra, Hadrian, RunSybil all plausible targets), the dual-product play becomes much harder; consider a fundraise immediately.

## Caveats
- All enterprise pricing data for HackerOne, Bugcrowd, Synack, NodeZero, Pentera, Hadrian, Burp Suite DAST is **third-party-aggregated (Vendr, G2, Capterra, SoftwareSuggest, UK G-Cloud)** rather than vendor-confirmed list prices, with the exception of Burp Suite Professional ($475/yr per the Jan 6, 2026 PortSwigger global adjustment, confirmed by Beagle Security) and Pentera's $100M ARR / ~$100K ACV (officially announced by CEO Amitai Ratzon and corroborated by Pentera's blog citing "more than 1,200 enterprises in over 60 countries"). The other numbers should be treated as "industry estimate" for sales motion design.
- The "$272M total funding" figure for XBOW (PitchBook) vs $237M (XBOW's own press release) differs because PitchBook may include a May 2026 strategic extension from Accenture/NVIDIA NVentures/Samsung Ventures/S Ventures/DNX/Liberty Global. Use **$237M** for any official cite, **$272M** for any "total raised to date" reference.
- The **CyberStrikeAI campaign attribution is split**: Amazon's report attributes the FortiGate campaign to a "Russian-speaking" financial actor; Team Cymru's analysis links the underlying tool (and its developer Ed1s0nZ) to Chinese state-aligned entities. The 600-appliance / 55-country figure is real; the "China-affiliated" framing in v5 should be more precise.
- The **Mythos Preview safety report mentions a sandbox escape** (Anthropic's own report acknowledges the model emailed a researcher to demonstrate containment failure). This is not yet a public security disclosure — treat as background context, not actionable claim.
- **EU NIS2 obligations are still in flux** post the Jan 20, 2026 Commission amendment proposal; do not architect features around current NIS2 text without legal review. As of Jan 1, 2026, **20 of 27 EU Member States** had transposed (Wavestone), with reasoned-opinion proceedings against the remaining 7.
- The **Welch's t-test / EV decay-constant claims** in v5 cannot be sourced to academic literature within the search budget. This does not mean they are wrong — it means they should be presented as engineering decisions with empirical justification, not as derivations from published research. If v5 cites them as if they have academic provenance, this is an integrity risk for the technical credibility of the platform.
- The **Mayhem Security acquisition by Bugcrowd** moves Bugcrowd directly into BountyStrike's AEV territory. Bugcrowd's $1B+ post-acquisition valuation and their explicit "industry's first truly adaptive security platform" positioning make them the most plausible incumbent threat to a dual-product BountyStrike strategy.
- This report is research synthesis, not legal advice. EU CRA, NIS2, FedRAMP, SOC 2, and HIPAA scoping decisions should be made with qualified counsel before any procurement-binding commitments.