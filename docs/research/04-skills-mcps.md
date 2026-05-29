# 04 — Skills, MCPs, Subagents & Cross-Source Ingestion (Parts 7-8, lines 2047-2673)

Source: `bountystrike_v5_build_plan.md`

## Claude Code Features Used

1. **`defer` decision on PreToolUse (April 1, 2026)** — pauses headless session at dangerous tool calls, hands control to external system without aborting; session persists `cleanupPeriodDays` (default 30) and resumes via `claude -p --resume <session-id>`. Used for: scope ambiguity, T2 sandbox approval, T3 submission approval.
2. **`PermissionDenied` retry hook** — fires on auto-classifier denials (distinct from PreToolUse manual denials); receives `reason` field; can return `retry: true`. Used for legitimate security tools (`nuclei`, `ffuf`, `httpx`, `subfinder`, `sqlmap`).
3. **26-event hook lifecycle** — used: SessionStart, PreToolUse, PermissionDenied, PostToolUse, SubagentStart, SubagentStop, TaskCreated, TaskCompleted, Stop, PreCompact, ConfigChange, WorktreeCreate.
4. **Agent Teams** (`CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`) — SaaS spawns up to 8 recon-agents over subdomain clusters, communicate laterally via shared task list + shared state MCP.
5. **Forked Subagents** (`CLAUDE_CODE_FORK_SUBAGENT=1`) — scope-guard judgment forks inherit full conversation history without separate session.

## Skills List (12)

| Skill | Phase | File Path | Purpose |
|---|---|---|---|
| ssrf-callback | Exploit | `.claude/skills/ssrf-callback/SKILL.md` | SSRF payloads + Interactsh OAST callback tracking; AWS IMDS chain |
| graphql-introspection | Recon | `.claude/skills/graphql-introspection/SKILL.md` | Schema extraction, field enum, batching attacks, fragment injection |
| jwt-attacks | Exploit | `.claude/skills/jwt-attacks/SKILL.md` | alg:none, key confusion, weak-secret enum, kid injection, PKCE downgrade |
| ai-prompt-injection | AI-vuln | `.claude/skills/ai-prompt-injection/SKILL.md` | Direct + indirect injection, system-prompt extraction, context overflow |
| oauth-flows | Exploit | `.claude/skills/oauth-flows/SKILL.md` | redirect_uri manipulation, state prediction, PKCE bypass, token leakage |
| idor-patterns | Exploit | `.claude/skills/idor-patterns/SKILL.md` | Sequential ID enum, GUID prediction, mass assignment, indirect chains |
| report-formatting | Report | `.claude/skills/report-formatting/SKILL.md` | H1/Bugcrowd/Intigriti/YesWeHack/Immunefi report templates |
| api-recon | Recon | `.claude/skills/api-recon/SKILL.md` | GraphQL introspection, OpenAPI/Swagger discovery, kiterunner |
| cloud-attack-chains | Exploit | `.claude/skills/cloud-attack-chains/SKILL.md` | SSRF→IMDS, S3 exposure, Lambda injection, IAM privesc |
| smart-contract-audit | Exploit | `.claude/skills/smart-contract-audit/SKILL.md` | Reentrancy, overflow, access control, flash-loan (Solidity/Vyper) |
| rate-limit-bypass | Exploit | `.claude/skills/rate-limit-bypass/SKILL.md` | XFF rotation, UA cycling, endpoint variation, timing analysis |
| mfa-bypass | Exploit | `.claude/skills/mfa-bypass/SKILL.md` | Session fixation, backup-code enum, OTP race conditions |

Each skill may include hooks with `once: true` (fires once per session, then self-removes).

## MCP Servers (20 total)

### Adopted External (10)

| Name | Source | Lang/Transport | Tools Provided |
|---|---|---|---|
| PortSwigger Burp MCP | Official BApp | SSE + stdio JAR | Burp Collaborator OAST; proxy history; Repeater |
| Caido MCP v1.1.0 | c0tton-fluff / caido-community | Go binary, stdio | HTTP/2 traffic; HTTPQL filtering; replay |
| pd-tools-mcp | intelligent-ears | Node.js, stdio | subfinder + dnsx + naabu + httpx + katana + nuclei chain |
| Shodan MCP (ADEO) | ADEOSec | Node.js, stdio | Shodan + VirusTotal combined; 11 analysis prompts |
| HexStrike-AI v6.0 | 0x4m4 hardened fork | Python, stdio | 150+ tools; 12 autonomous agents; IntelligentDecisionEngine |
| Garak MCP | mcpmarket/NVIDIA | Python, stdio | 120+ LLM probes; `run_attack`, `list_probes` |
| AutoPentest-AI MCP | bhavsec | Python, stdio | 68 tools; OWASP WSTG coverage; 12 WAF evasions |
| Strix MCP | usestrix | Python, stdio | Deep mode 2000+ steps; 17 skill files; Caido + Playwright |
| Tencent AI-Infra-Guard | Tencent | Python, stdio | 14 MCP risk categories; 589+ CVEs; agent scan; jailbreak eval |
| MCP-Scan | multiple | Python, stdio | Static + dynamic MCP server vuln scanning (defensive) |

### Built In-House (10)

| Name | Lang | Key Tools | Purpose |
|---|---|---|---|
| scope-mcp | TS | check_target, list_in_scope_assets, issue_scope_jwt, revoke_scope_jwt, get_scope_changes, rank_programs | Scope enforcement, JWT issuance, EV ranking |
| ev-mcp | TS | rank_programs, score_program, get_program_details, compute_freshness | EV scoring engine |
| oracle-mcp | Py | oracle_xss, oracle_ssrf_oast, oracle_sqli_timing, oracle_ssti_sandbox, oracle_idor_matrix, oracle_open_redirect, oracle_rce_sandbox, oracle_ssrf_imds | Deterministic verification oracle |
| evidence-mcp | Py | put_artifact, get_artifact, checkpoint, list_artifacts | Content-addressable evidence store |
| dedup-mcp | Py | check_similarity, find_duplicates, embed_finding | pgvector semantic dedup |
| kev-mcp | TS | get_recent_kev, match_program, get_epss, alert_on_new_kev | CISA + VulnCheck KEV |
| h1-mcp | TS | list_programs, get_program, get_org_assets, submit_report, get_report_status | HackerOne API (post-Apr 2026 org assets) |
| bugcrowd-mcp | TS | list_programs, get_target_groups, submit_report, get_vrt | Bugcrowd API |
| intigriti-mcp | TS | list_programs, get_scopes, submit_report, get_tier_info | Intigriti API |
| immunefi-mcp | TS | list_programs, get_impacts, submit_report | Immunefi API (no auth required) |

## Subagent Template (`validator-agent`)

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

Protocol:
1. Identify CWE class, select appropriate oracle.
2. Call oracle with exact PoC (no modifications).
3. Interpret oracle result per verdict schema.
4. If verdict = "unreproducible", retry at most TWICE with variations.
5. If all attempts fail: verdict = "unreproducible".
6. If 1 of 3 attempts succeeds: verdict = "flaky" — T2 escalation.
7. Write ValidationResult to evidence store.
8. Update finding status via mcp__state__update_finding_status.
9. Cleanup: verify no test artifacts remain on target.

Default to rejection when uncertain.
```

Frontmatter conventions: `name`, `description`, `model`, `color`, `maxTurns`, `permissionMode`, explicit `tools` allowlist using `mcp__<server>__<tool>` namespacing, per-subagent `hooks` block with matcher regex.

## Hooks (8 events configured in production `.claude/settings.json`)

### SessionStart
```json
"SessionStart": [{"hooks": [
  {"type":"command","command":"$BS_HOME/hooks/verify_attestation.py"},
  {"type":"command","command":"$BS_HOME/hooks/load_scope.py"},
  {"type":"command","command":"$BS_HOME/hooks/inject_api_keys.py"}
]}]
```

### PreToolUse (3 matchers)
```json
"PreToolUse": [
  {"matcher":"mcp__*__*","hooks":[
    {"type":"command","command":"$BS_HOME/hooks/killswitch_check.py"},
    {"type":"command","command":"$BS_HOME/hooks/scope_enforce.py"},
    {"type":"command","command":"$BS_HOME/hooks/politeness_gate.py"},
    {"type":"command","command":"$BS_HOME/hooks/cost_ceiling_check.py"}
  ]},
  {"matcher":"mcp__*__submit_*","hooks":[
    {"type":"command","command":"$BS_HOME/hooks/approval_gate.py --tier T3"},
    {"type":"command","command":"$BS_HOME/hooks/evidence_required.py"},
    {"type":"command","command":"$BS_HOME/hooks/quality_gate.py"}
  ]},
  {"matcher":"mcp__sandbox__*","hooks":[
    {"type":"command","command":"$BS_HOME/hooks/approval_gate.py --tier T2"}
  ]}
]
```

### PermissionDenied
```json
"PermissionDenied": [{"hooks":[{"type":"command","command":"$BS_HOME/hooks/permdenied_retry.py"}]}]
```
`permdenied_retry.py` checks args for `LEGITIMATE_TOOLS = ["nuclei","ffuf","httpx","subfinder","sqlmap"]` and emits `{hookSpecificOutput:{hookEventName:"PermissionDenied", retry:true, context:"...scope JWT and program safe harbor."}}`.

### PostToolUse
```json
"PostToolUse": [{"hooks":[
  {"type":"command","command":"$BS_HOME/hooks/evidence_capture.py"},
  {"type":"command","command":"$BS_HOME/hooks/audit_log.py"},
  {"type":"command","command":"$BS_HOME/hooks/cost_track.py"}
]}]
```

### SubagentStart / SubagentStop / Stop / PreCompact
```json
"SubagentStart": [{"hooks":[{"type":"command","command":"$BS_HOME/hooks/inject_scope_to_subagent.py"}]}]
"SubagentStop": [{"hooks":[{"type":"command","command":"$BS_HOME/hooks/validate_subagent_output.py"}]}]
"Stop": [{"hooks":[
  {"type":"command","command":"$BS_HOME/hooks/finalize_audit.py"},
  {"type":"command","command":"$BS_HOME/hooks/flush_langfuse.py"}
]}]
"PreCompact": [{"hooks":[{"type":"command","command":"$BS_HOME/hooks/block_if_unsaved_evidence.py"}]}]
```

## CLAUDE.md Gate Template

Structure: Identity & Authorization → Hard Prohibitions → Kill-chain Phases → Budget Controls → Evidence Standard. Variables (`${OPERATOR_ID}`, `${PROGRAM_HANDLE}`, `${PLATFORM}`, `${SCOPE_JWT_JTI}`, `${ENGAGEMENT_ID}`, `${SESSION_START}`, `${COST_BUDGET_USD}`) injected by SessionStart hooks.

5 hard prohibitions (hook-enforced, prompt-injection-resistant): no out-of-scope action; no submission without `evidence_hash`; no submission without human approval; no destructive payloads (DROP/TRUNCATE/rm -rf/shutdown/reboot/format); no exfil beyond 1 record / 1 file PoC.

7 phases: SCOPE → RECON → SURFACE → PROBE → VERIFY → TRIAGE → REPORT.

Budget: pause at 80% with zero validated findings; halt at 100% awaiting extension.

5 evidence-standard predicates: OAST callback w/ matching source IP, Playwright DOM execution, Welch p<0.01 with delta≥4s timing, template-engine math expression evaluation, cross-account access matrix.

## Slash Commands (8)

| Command | File | Description |
|---|---|---|
| `/scope <program>` | `.claude/commands/scope.md` | Load program scope, display EV score + top candidates |
| `/recon <target>` | `.claude/commands/recon.md` | Run recon-agent on single target/program |
| `/scan <program>` | `.claude/commands/scan.md` | Full pipeline: recon → scanner → exploit → validate |
| `/triage <finding-id>` | `.claude/commands/triage.md` | Review finding, run dedup, set approval tier |
| `/submit <finding-id>` | `.claude/commands/submit.md` | Generate report and submission workflow |
| `/cost` | `.claude/commands/cost.md` | Show LLM cost breakdown |
| `/halt` | `.claude/commands/halt.md` | Activate kill switch (T1/T2/T3) |
| `/benchmark` | `.claude/commands/benchmark.md` | Run platform vs Cybench / XBOW-104 |

## Cross-Source Ingestion Sources (13)

| # | Source | Connector | Cadence | Primary Signal |
|---|---|---|---|---|
| 1 | Web (general) | WebFetch + rate-limited crawler | On-demand | Target recon, JS analysis |
| 2 | Apify/Pipedream | `apify__pipedream` | Hourly | Reddit, X/Twitter, YouTube, blogs |
| 3 | Google Drive | `google_drive` MCP | Daily | Private intel docs |
| 4 | Scholar (arXiv) | `scholar` MCP | Daily | Papers on CVEs, techniques |
| 5 | Google Calendar | `gcal` MCP | Real-time | Engagement scheduling, deadlines |
| 6 | YouTube Analytics | `youtube_analytics` | Weekly | Conf talks, PoC videos |
| 7 | Vercel | `vercel` MCP | On-deploy | Deploy status, edge-fn analysis |
| 8 | Supabase | `supabase` MCP | Real-time | Data plane (findings, evidence) |
| 9 | GitHub direct | `github_mcp_direct` | On-event | CVE PoCs, nuclei PRs, scope changes |
| 10 | CISA KEV | REST polling | Continuous | Known-exploited feed |
| 11 | EPSS (First.org) | REST polling | Daily | Exploitation probability |
| 12 | VulnCheck | REST polling | Continuous | Extended KEV + enriched CVE |
| 13 | GreyNoise | REST polling | Real-time | Internet noise, scanner detection |

### Embedding Pipeline (Section 8.3)

512-token chunks w/ 50-token overlap, sentence-aware. Embedders:
- Primary `text-embedding-3-large` (1536d, OpenAI)
- Fallback `Qwen3-Embedding-8B` (4096d, vLLM)
- Solo `nomic-embed-text` (768d, Ollama)

Indexed via pgvectorscale DiskANN (>99% recall @ 10ms p99). Solo (<500K chunks) HNSW. SaaS (>5M chunks/tenant) Turbopuffer. Schema: `chunk_id, content, embedding, source, item_id, created_at, ttl_days(default 90)`.

### Daily Brief (8.4)

06:00 UTC Hatchet/Temporal cron. Sonnet 4.6 synthesis. Top 20 by `operator_impact_score`. Sections: Critical Actions / New KEV / Scope Changes / Community / Academic. Slack/email/webhook delivery.

### New-CVE Alert (8.5)

Half-life ≈ 72h (λ=0.00963). KEV polled q15min → score `kev_freshness × P(program_uses_product)` → if >0.3 publish to NATS/Hatchet → parallel NOTIFY (Slack/Discord/ntfy.sh in <2min) + DRAFT_POC. Goal: 30-60min head start over manual monitoring.
