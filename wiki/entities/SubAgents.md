# SubAgents
**Type:** component
**Summary:** 9 Claude sub-agent specs in `.claude/agents/*.md`. Each is a single-responsibility worker the orchestrator spawns; agents reach into [[McpServers]] for all side-effecting work and are gated by PreToolUse hooks.

## Key Facts
| Agent | Role |
|---|---|
| recon-agent | enumerate attack surface for one program → `findings` (status=hypothesis) |
| cloud-recon-agent | AWS/Azure/GCP/container/IAM/storage/k8s surface; runs when JWT carries cloud creds |
| scanner-agent | nuclei / ffuf / sqlmap / kiterunner / arjun against recon artifacts |
| ai-vuln-hunter | LLM attack surface — Garak probes + AI-Infra-Guard; OWASP LLM Top 10 |
| exploit-agent | build minimal reproducible PoC per finding_id (Firecracker microVM target) |
| validator-agent | run the matching oracle, store evidence, register dedup fingerprint, update status |
| reporter-agent | generate report, route through approval, submit to platform (one finding_id) |
| scope-guard | synchronous adjudicator for ambiguous scope decisions the regex hook can't resolve |
| program-selector | EV-ranked program recommendations (read-only) |

## Key Facts (conventions)
- Frontmatter: markdown specs use `tools:`; the Agent SDK uses `allowedTools`.
- claude-code-sdk is now **claude-agent-sdk** — `ClaudeAgentOptions`, `anyio.run` (not `asyncio.run`), `setting_sources` defaults to `None` (must opt in to load `.claude/`).
- One invocation = one unit of work (one program scan, or one finding_id).

## Connections
- [[Orchestrator]] — spawns and fans out the agents
- [[McpServers]] — agents' only side-effect channel
- [[approval-tiers]] — exploit/validator/reporter agents pause on the gate
- [[kill-switch]] — every agent tool call passes the killswitch hook

## Sources
- .claude/agents/*.md — current
- docs/system-architecture.md §1 — 2026-05-01
