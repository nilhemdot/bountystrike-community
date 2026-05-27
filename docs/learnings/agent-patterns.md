# agent-patterns.md — Agent Authoring Patterns

## Agent Spec Format (.claude/agents/<name>.md)

```markdown
---
name: agent-name
description: When to activate this agent. Used by orchestrator for routing.
---

(Description of agent purpose, capabilities, and MCP dependencies)

Tools available: list of mcp__<server>__<tool> calls the agent uses.
```

## The 9 Agents

| Agent | Trigger | Key MCPs |
|-------|---------|---------|
| program-selector | EV ranking request | ev-mcp, kev-mcp |
| recon-agent | New program scope | scope-mcp, state-mcp, politeness-mcp |
| cloud-recon-agent | Cloud flags in recon | (AWS/GCP/Azure CLIs) |
| scanner-agent | Recon complete | oracle-mcp, sandbox-mcp, state-mcp |
| ai-vuln-hunter | AI endpoint detected | oracle-mcp (Garak probes) |
| exploit-agent | Scanner hypothesis | sandbox-mcp, oracle-mcp, evidence-mcp |
| validator-agent | Exploit evidence | oracle-mcp, dedup-mcp, evidence-mcp, normalize-mcp |
| reporter-agent | Validated finding | platform-mcp, evidence-mcp |
| scope-guard | Scope decision needed | scope-mcp |

## Hook Integration

All agents go through PreToolUse hooks automatically:
- `pretool_killswitch.py` — checks Redis kill-switch before every tool
- `pretool_antislop.py` — filters low-quality / hallucinated tool calls
- `pretool_approval_gate.py` — routes T2/T3 findings to approval queue

## Adding a New Agent

1. Create `.claude/agents/<name>.md`
2. Document: trigger conditions, available MCP tools, output format
3. Hooks apply automatically — no changes needed
4. If new scope required: coordinate with scope-guard spec

## Firecracker Isolation (exploit-agent)

exploit-agent runs PoC development inside Firecracker microVMs via sandbox-mcp. Never run untrusted payloads outside the sandbox.
