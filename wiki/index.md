# Wiki Index — BountyStrike v5

_Maintained by Pith. Updated on every ingest._

See [[overview]] for the project summary.

## Entities
- [[ControlPlane]] — FastAPI orchestrator + DDD domains
- [[McpServers]] — the 15-server MCP inventory
- [[OracleMcp]] — deterministic vulnerability verifiers
- [[SubAgents]] — the 9 Claude sub-agent specs
- [[Orchestrator]] — scan-pipeline entry point (`scripts/orchestrator.py`)

## Concepts
- [[finding-lifecycle]] — 16-state finding-status machine
- [[scope-jwt-trust-boundary]] — scope enforced at the network layer
- [[approval-tiers]] — T0/T1/T2/T3 human-in-the-loop gate
- [[ev-scoring]] — expected-value program ranking
- [[kill-switch]] — 3-layer emergency stop

## Decisions
- [[scope-enforced-at-network-not-prompt]] — 2026-05-01
- [[deterministic-oracles]] — 2026-05-01

## Sources Processed
- docs/codebase-summary.md (2026-05-01, HEAD e9b4b77) — bootstrap
- docs/system-architecture.md (2026-05-01, HEAD e9b4b77) — bootstrap
- repo structure scan (control-plane/, mcp/, scripts/, .claude/agents/) — 2026-05-28
