# Project Overview — BountyStrike v5

**Summary:** Autonomous, Claude Code-native bug bounty platform. A FastAPI control-plane orchestrates Claude sub-agents that recon targets, build exploit PoCs, validate them with deterministic oracles, deduplicate, route through a tiered human-approval gate, and submit reports to bounty platforms.

**Stack:** Python 3.12 (FastAPI + DDD, `uv` workspace) · 14 Python FastMCP servers + 1 TypeScript scope-mcp · Postgres 17 (pgvector + pg_trgm) · Redis 7 · Hatchet · Langfuse · Cloudflare R2 / local FS. Lint `ruff`, types `mypy`, tests `pytest` + `pytest-asyncio`.

**Team:** solo

## Architecture

One scan of one bounty program runs through `scripts/orchestrator.py`:

```
recon → scanner (skippable) → exploit → [T2 gate] → validator → [T3 gate] → reporter
```

Postgres is the single authoritative store; Redis is a kill-switch flag + approval cache; R2 holds blob evidence; Interactsh receives OAST callbacks for blind-vuln verification.

## Key Components
- [[ControlPlane]] — FastAPI orchestrator + DDD domains
- [[McpServers]] — the 15-server MCP inventory
- [[OracleMcp]] — deterministic vulnerability verifiers (TPR=1.0 / FPR=0.0)
- [[SubAgents]] — the 9 Claude sub-agent specs
- [[Orchestrator]] — the scan-pipeline entry point

## Key Concepts
- [[finding-lifecycle]] — the 16-state finding-status machine
- [[scope-jwt-trust-boundary]] — scope enforced at the network layer, not the prompt
- [[approval-tiers]] — T0/T1/T2/T3 human-in-the-loop gate
- [[ev-scoring]] — expected-value program ranking
- [[kill-switch]] — 3-layer emergency stop

## Design Decisions
- [[scope-enforced-at-network-not-prompt]]
- [[deterministic-oracles]]

## Authoritative source docs
The repo carries detailed engineering docs; the wiki summarizes and links them.
- `docs/codebase-summary.md` — file inventory, deps, Postgres schema, MCP catalogue
- `docs/system-architecture.md` — six Mermaid wiring diagrams
- `docs/code-standards.md` — DDD layout, how to add an MCP/hook/agent
- `CLAUDE.md` — Phase-1 build traps (stale-training-data corrections)

> **Freshness caveat:** the two docs above were generated 2026-05-01 at HEAD `e9b4b77`. Since then a Phase 0 "truth-in-claims" correction landed and a model-routing matrix was re-added (`core/routing`). Verify specific claims against current code.
