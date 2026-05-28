# McpServers
**Type:** component
**Summary:** 15 MCP servers under `mcp/` (14 Python FastMCP stdio + 1 TypeScript scope-mcp). All side-effecting agent work — verification, evidence, dedup, state, platform submission, rate limiting, sandbox exec — goes through these.

## Key Facts
| MCP | Type | Backend | Role |
|---|---|---|---|
| oracle-mcp | Py | Playwright + Interactsh | 8 deterministic verifiers — see [[OracleMcp]] |
| evidence-mcp | Py | aiosqlite + R2/local | `put_artifact`, `get_artifact`, hash-chained audit log |
| dedup-mcp | Py | asyncpg + pgvector + OpenAI | exact + semantic duplicate check |
| state-mcp | Py | asyncpg | finding read/update, artifact + experience-KB queries |
| ev-mcp | Py | asyncpg + control-plane dep | `rank_programs`, `get_program_details` |
| kev-mcp | Py | httpx + file cache | CISA KEV + EPSS, `kev_match_program` |
| scope-mcp | TS | JWT lib | RS256 verify + claims extraction |
| h1 / bugcrowd / intigriti / yeswehack / immunefi | Py | httpx | `submit_report` per platform (429 retry semantics) |
| politeness-mcp | Py | stdlib | per-host token-bucket rate limit + adaptive backoff |
| sandbox-mcp | Py | stdlib | `exec_safe` (local subprocess + Docker scaffold; Firecracker deferred) |
| normalize-mcp | Py | cvss | CVSS v3.1/v4 + CWE normalization |

## Key Facts (drift to watch)
- Only 5 Python MCPs (`oracle`, `evidence`, `dedup`, `kev`, `ev`) are registered as `uv` workspace members; the other 9 are standalone — `uv sync` from root won't install them.
- `intigriti-mcp.submit_report` is a **placeholder** — the researcher API is read-only.
- MCP stdio rule: never write to stdout (corrupts JSON-RPC); log to stderr/file only.

## Connections
- [[OracleMcp]] — the verification MCP, detailed separately
- [[SubAgents]] — agents call MCPs for all side effects
- [[finding-lifecycle]] — state-mcp + dedup-mcp drive status transitions
- [[scope-jwt-trust-boundary]] — scope-mcp validates the JWT

## Sources
- docs/codebase-summary.md §MCP Inventory — 2026-05-01
