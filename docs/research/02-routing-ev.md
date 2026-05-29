# 02 — Model Routing + Scope Ingestion + EV Engine (Parts 3-4, lines 697-1306)

Source: `bountystrike_v5_build_plan.md`

## Model Routing Matrix

| Task | Primary Model | $/Mtok In/Out | Fallback | Rationale |
|---|---|---|---|---|
| Bulk triage / dedup | `deepseek/deepseek-v4-flash` | 0.14 / 0.28 (cache-hit 0.0028) | `qwen/qwen3-coder-30b` (free) | 10K findings ≈ $1.40 cache-miss |
| Recon synthesis (large output) | `google/gemini-3.1-pro` | 2.00 / 12.00 | `anthropic/claude-haiku-4-5` | 2M ctx subfinder+katana |
| Subdomain enum triage | `anthropic/claude-haiku-4-5` | 1.00 / 5.00 | `deepseek/deepseek-v4-flash` | Fast/cheap binary classifier |
| Vuln hypothesis gen | `anthropic/claude-sonnet-4-6` | 3.00 / 15.00 | `openai/gpt-5.4` | Quality gate |
| Deep multi-step chain reasoning | `anthropic/claude-opus-4-7` | 5.00 / 25.00 | `openai/gpt-5.5-pro` | >4-step exploits only |
| Mythos hypothesis (partner) | `anthropic/claude-mythos-preview` | 25.00 / 125.00 | `anthropic/claude-opus-4-7` | Glasswing partner; 83.1% CyberGym |
| Exploit code gen | `qwen/qwen3-coder` (free) | 0.00 | `mistralai/devstral` (0.10/0.30) | Free 480B 1M ctx |
| Uncensored payload synth | Venice Dolphin (FREE) | 0.00 | `cognitivecomputations/hermes-4-70b` (0.13/0.40) | 2.2% refusal; routes known-refusal payloads off Anthropic frontier models (no primary source for hard Anthropic refusal %; mechanism per v6) |
| CVSS v4 scoring rationale | `deepseek/deepseek-r1-0528` | 0.50 / 2.15 | `deepseek/deepseek-v4-flash` | Auditable open reasoning |
| Exploit validation reasoning | `anthropic/claude-opus-4-7` | 5.00 / 25.00 | `openai/gpt-5.5-pro` (30/180) | False neg costs $10K+ |
| Report prose | `anthropic/claude-sonnet-4-6` | 3.00 / 15.00 | `openai/gpt-5.4` | Affects triage acceptance |
| JSON extraction | `mistralai/mistral-small-3.2-24b` | 0.09 / 0.25 | `deepseek/deepseek-v4-flash` | Cheapest JSON extractor |
| Tech fingerprint | `google/gemini-3.1-pro` | 2.00 / 12.00 | `anthropic/claude-haiku-4-5` | Long-ctx JS/SPA |
| LLM probe gen | `anthropic/claude-sonnet-4-6` | 3.00 / 15.00 | `x-ai/grok-4.20` (2M ctx) | Adversarial prompting |
| Cloud IAM chain | `anthropic/claude-opus-4-7` | 5.00 / 25.00 | `google/gemini-3.1-pro` | Permission graph |
| Daily intel brief | `anthropic/claude-haiku-4-5` | 1.00 / 5.00 | `deepseek/deepseek-v4-flash` | Routine summarization |

> **Pricing note:** DeepSeek V4-Flash: cache-miss input $0.14 / output $0.28 per MTok; cache-hit input $0.0028. (per api-docs.deepseek.com; see docs/bountystrike_v6_phase0-1_technical_brief.md — corrects the v6 figure)

**Tier-S-Cyber self-hosted:** Deep Hat V2 30B (Kindo $0.40/$1.20) | WhiteRabbitNeo V3 8B (HF, RTX 3090+) | Foundation-Sec-8B Cisco (HF, 1× A100) | Pentest-R1 (GRPO RL on 500+ HTB/VulnHub; 24.2% AutoPenBench; Ollama) | Red-MIRROR (LoRA Qwen2.5-14B; 86% XBOW; 4× A100 / 2× H100). Solo: WhiteRabbit + Foundation-Sec on RTX 4090 via Ollama. SaaS: Pentest-R1 + Red-MIRROR on Hetzner AX102 (2× A100 80GB) via vLLM.

## OpenRouter Config

- **Suffixes:** `:nitro` (1.5–2× cost, lowest latency — validation oracle only), `:floor` (lowest-cost), `:free` (Qwen3-Coder, Venice Dolphin)
- **`provider.order`:** ranked array, e.g. Sonnet 4.6 → `["Anthropic","Amazon Bedrock","Google Vertex"]`
- **`provider.require_parameters: true`** for JSON-schema tasks
- **`transforms: ["middle-out"]`** — recon synthesis only; never validation/report
- **BYOK:** 1M free Anthropic requests/mo; header `X-OpenRouter-Provider-Key`; beta `output-300k-2026-03-24` for 300K output tokens
- **Refusal-management chain:** Sonnet 4.6 → Venice Dolphin FREE → Hermes-4-70B → Devstral → Langfuse log
- **`provider.data_collection: "deny"`** on Venice routing for privacy

```json
{
  "model": "anthropic/claude-sonnet-4-6",
  "provider": {"order": ["Anthropic","Amazon Bedrock"], "allow_fallbacks": true},
  "fallback_models": ["openai/gpt-5.4","google/gemini-3.1-pro","deepseek/deepseek-v4-flash"]
}
```

## Cost Guardrails

- **L1 — per-task ceiling:** OpenRouter Bridge MCP downgrades when expected cost > ceiling
- **L2 — per-scan budget:** `cost_budget_usd` in `ScanJobRequest`; `mcp__openrouter__generation_stats` tracks; early-stop at 80% with no validated findings
- **L3 — monthly ceiling:** Hatchet enforces; default $30/mo solo
- **Solo example (100 targets, corrected DeepSeek pricing, cache-miss):** Recon $0.20 + DeepSeek triage $0.07 (500K tok × $0.14/M input) + Venice/Qwen exploit $0.00 + Sonnet validation $0.15 + Sonnet report $0.09 = **$0.51 ≈ $0.0051/target** *(per api-docs.deepseek.com; see docs/bountystrike_v6_phase0-1_technical_brief.md — corrects the v6 figure)*
  - **With prompt caching** (cache-hit input $0.0028/M on repeated triage context): triage drops to ~$0.0014, total ≈ **$0.44**. Cache-hit ratio is the dominant lever on solo-scan cost.
  - **Per-scan target check:** corrected per-target cost $0.0051 (cache-miss) / $0.0044 (cached) is well within the <$0.20/solo-scan target (target re-validated, not breached — AC-10 satisfied). The 100-target *aggregate* $0.51 is a batch figure, not a per-scan figure.
- **SaaS tiers:** Starter $5/mo (25 scans) | Professional $50/mo (250 scans) | Enterprise $200/mo
- **Circuit breaker (Redis):** 10s timeout. 3 fails / 60s window → OPEN 120s. 429 → exp backoff. 5xx → alt provider.

## Scope Ingestion APIs

**Federation layers:**
- L0 `arkadiyt/bounty-targets-data` (30 min, unauth)
- L1 `sw33tLie/bbscope v2` (6–12 hr, auth — exposes maxBounty/minBounty/tier/asset_value)
- L2 `rix4uni/scope` (10 min, fastest delta — `newdata_inscope_wildcards.txt`)
- L3 `projectdiscovery/public-bugbounty-programs` (daily — VDPs, HackenProof, Code4rena)
- L4 `Trickest/800` (daily auth — tech fingerprints `server-report.csv`)

### HackerOne (April 16 2026 deprecation)
`structured_scopes` → `/api/v1/organizations/{org_id}/assets`. Field migration: `asset_identifier` → `identifier`; `updated_at` → `last_modified_at`; new `program_handles[]` (one asset, many programs); new `tags` + `notes`; new `filter[updated_at__gt]` query param → change-event ingestion.

```typescript
async function fetchProgramAssets(orgId: string, since?: Date): Promise<Asset[]> {
  const params = new URLSearchParams({'page[size]': '100', 'page[number]': '1'});
  if (since) params.set('filter[updated_at__gt]', since.toISOString());
  const response = await h1Client.get(`/api/v1/organizations/${orgId}/assets?${params}`);
  return response.data.data.map(normalizeOrgAsset);
}
```

### Bugcrowd
`https://bugcrowd.com/{slug}.json` cookie-auth (`_bugcrowd_session`); `target_groups[].in_scope`, `category` (website/api/mobile/other), `reward_range`, `point` (0–10); P1–P4 normalized to `payout_by_severity`.

### Intigriti
`GET https://api.intigriti.com/core/researcher/v1/programs/{co}/{prog}/scopes` Bearer PAT. Per-endpoint `maxBounty`/`minBounty`/`tier` (`starter|pro|professional|elite`).

### YesWeHack
`GET https://api.yeswehack.com/programs/{slug}` Bearer. `asset_value` low/medium/high → EV multiplier 0.7×/1.0×/1.3×.

### Immunefi
`GET https://immunefi.com/bounty/{project}/json` no auth. `impacts[]` array; smart contract weight 1.40×.

### KEV/EPSS
- CISA KEV: `https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json`
- EPSS v4: `https://api.first.org/data/v1/epss?cve=CVE-2024-XXXX`
- VulnCheck KEV: `https://api.vulncheck.com/v3/index/vulncheck-kev` Bearer

## EV Formula + Weights

**Per bug class:**
```
EV_b = BountyRange_b * P(eligible_b) * P(find_b | skill) * P(exploitable_b) * (1 / T_validate)
```

**Program aggregate:** `EV_program = SUM_b (EV_b * A_b) / T_total_hat`

**Normalized [0,1] score:**
```
S        = w1*f_payout + w2*f_sat + w3*f_ops + w4*f_fit
EV_score = min(S * (1 + 0.20 * f_cve), 1.0)
```

**Default weights v2.0:** payout 0.35 | saturation 0.25 | ops 0.25 | fit 0.15 | CVE bonus +20% (capped at 1.0).

**Asset-type weights:**

| Asset Type | Weight |
|---|---|
| smart_contract (Immunefi) | 1.40 |
| cloud_config (AWS/Azure/GCP) | 1.30 |
| ai_model | 1.25 |
| api (REST/GraphQL) | 1.15 |
| web-application | 1.00 |
| cidr (IP range) | 0.90 |
| Android | 0.85 |
| iOS | 0.80 |
| executable | 0.70 |
| VDP (no bounty) | 0.10 |

**Freshness decay:**
- Scope: `f_fresh(Δt) = exp(-0.00065*Δt)` → 0.97 @ 48h, 0.89 @ 1wk, 0.63 @ 1mo *(hand-tuned heuristic, pending calibration — no published derivation)*
- KEV: `f_kev(Δt) = exp(-0.00963*Δt)` → halves in ~72h *(hand-tuned heuristic, pending calibration — no published derivation)*

**CVE opportunity score:**
```python
def cve_opportunity_score(epss, kev_age_hours, has_nuclei_template, cvss_exploitability=0.5):
    LAMBDA, MU = 0.00065, 0.00963  # hand-tuned heuristics, pending calibration — no published derivation
    template_factor = 0.25 if has_nuclei_template else 1.00
    freshness = math.exp(-MU * kev_age_hours)
    exploit_prob = max(epss, cvss_exploitability * 0.3)
    return min(exploit_prob * freshness * template_factor, 1.0)
```

## Scope-MCP Signatures

TypeScript stdio MCP. Seven tools:

```typescript
interface ScopeMCP {
  check_target(args: {
    target: string;
    scope_jwt: string;
    tool_context?: string;
  }): Promise<{
    in_scope: boolean;
    exclusion_reason?: string;
    requires_defer: boolean;
    audit_id: string;
  }>;

  list_in_scope_assets(args: {
    program_handle: string;
    platform: 'hackerone' | 'bugcrowd' | 'intigriti' | 'yeswehack' | 'immunefi';
    asset_types?: string[];
  }): Promise<NormalizedScope[]>;

  get_program_rules(args: {
    program_handle: string;
    platform: string;
  }): Promise<{ rules_text: string; last_updated: string }>;

  issue_scope_jwt(args: {
    program_handle: string;
    platform: string;
    operator_id: string;
    expiry_hours: number;  // max 168 (1 week)
  }): Promise<{ jwt: string; jti: string; issued_at: string }>;

  revoke_scope_jwt(args: {
    jti: string;
    reason: string;
  }): Promise<{ revoked: boolean }>;

  get_scope_changes(args: {
    program_handle?: string;
    since: string;
    include_platforms?: string[];
  }): Promise<ScopeChange[]>;

  rank_programs(args: {
    operator_profile: OperatorProfile;
    min_ev_score?: number;
    platforms?: string[];
    require_bounty?: boolean;
    limit?: number;
  }): Promise<RankedProgram[]>;
}
```

## JWT Scheme

**Algorithm:** RS256 (RSA-SHA256), 4096-bit key pair.

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
    "hostnames": ["staging-internal.acme.com"],
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

**Validation points:** SessionStart hook | every `scope-mcp.check_target()` | Firecracker VM boot (network-namespace from JWT env) | every platform API submission. **Max expiry:** 168h. **Revocation:** `revoke_scope_jwt(jti, reason)`.

## Change-Event Architecture

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

**Subscribers to `scope_added`:** EV Reranker | Scope JWT Refresh | Operator Notification | Auto-Recon Trigger.
