# CLAUDE.md — BountyStrike v5

Autonomous Claude Code-native bug bounty platform. 15 MCP servers, 9 sub-agents, FastAPI control-plane, Postgres 17 + pgvector.

## Session Start Protocol

**MANDATORY** — load these 4 files at the start of every session (~800 tokens):
1. `CLAUDE.md` (this file)
2. `.claude/COMMON_MISTAKES.md` — critical errors to avoid
3. `.claude/QUICK_START.md` — essential commands
4. `.claude/ARCHITECTURE_MAP.md` — file locations

Then load task-specific docs from `docs/INDEX.md`.

**NEVER auto-load:** `.claude/completions/`, `.claude/sessions/`, `docs/archive/`

## Architecture Quick Reference

- **control-plane/** — FastAPI + DDD orchestrator (domains: recon, approval_gate, evidence_management, program_ranking, safety, scope_management)
- **mcp/** — 15 MCP servers (14 Python FastMCP + 1 TypeScript scope-mcp)
- **infra/** — Docker Compose: Postgres 17, Redis 7, Hatchet, Langfuse
- **scripts/** — CLI entry points (orchestrator.py, approve.py, gen_scope_jwt.py, etc.)
- **.claude/agents/** — 9 sub-agent specs (recon, cloud-recon, scanner, ai-vuln-hunter, exploit, validator, reporter, scope-guard, program-selector)
- # ... 1 more

## Quick Start Commands

```bash
uv run ruff check .                                    # lint
uv run ruff format .                                   # format
uv run pytest tests/                                   # unit tests
uv run pytest tests/integration/ -m integration        # integration (needs live services)
docker compose -f infra/docker-compose.yml up -d       # start infra
python scripts/gen_scope_jwt.py                        # issue scope JWT
python scripts/orchestrator.py                         # run hunt
```

## Code Style Rules

- Return code first, explanation after only if non-obvious
- No abstractions for single-use operations; three similar lines > premature abstraction
- All async: use `httpx.AsyncClient`, `asyncpg`, `aioboto3`; never blocking calls in async context
- Pydantic models at every input boundary (HTTP, MCP tool, file parser)
- ruff line-length 100, target py312, rules: E F W I N UP B SIM ASYNC
- # ... 1 more

## Testing Methodology

- `pytest-asyncio` with `asyncio_mode = "auto"`
- Unit tests: `tests/` — no live services needed
- Integration tests: `tests/integration/` — require Postgres, Redis, R2; mark with `@pytest.mark.integration`
- Oracle field-validation suites: TPR=1.0 / FPR=0.0 required before wiring to agents

## Documentation Navigation

| Task | Load |
|------|------|
| Add/modify MCP server | `docs/learnings/mcp-patterns.md` |
| Add/modify oracle | `docs/learnings/oracle-patterns.md` |
| Database work | `docs/learnings/database-patterns.md` |
| Agent work | `docs/learnings/agent-patterns.md` |
| Deployment / infra | `docs/learnings/deployment.md` |
| Full architecture | `docs/system-architecture.md` |
| File map | `docs/codebase-summary.md` |
| Code standards | `docs/code-standards.md` |
| Phase 0/1 build | `docs/bountystrike_v6_phase0-1_technical_brief.md` |

## Constraints — Phase 1 Build Traps (training-data is stale)

Verified May 21 2026. Source: `docs/bountystrike_v6_phase0-1_technical_brief.md`.

1. **claude-code-sdk → claude-agent-sdk** — `ClaudeCodeOptions` is now `ClaudeAgentOptions`. Agent SDK uses `anyio.run`, NOT `asyncio.run`. `setting_sources` defaults to `None` — must opt in to load `.claude/`.
2. **Hatchet v1** (sdk 1.33.5+): `@hatchet.task()` function-based, NOT `@hatchet.workflow`. Pydantic inputs; `aio_` async prefix.
3. **bbscope v2**: subcommands are `poll`/`db`, not v1 `bbscope h1 -t`.
4. **DeepSeek pricing**: `$0.14` cache-miss in / `$0.0028` cache-hit in / `$0.28` out per 1M. `deepseek-chat`/`-reasoner` alias `deepseek-v4-flash`. (v6 plan's $0.28/$0.42 was WRONG.)
5. **boto3 < 1.36** for R2 (1.36.0 checksum break) — or `request_checksum_calculation="when_required"`.
6. **LiteLLM pin v1.86.1** — NEVER 1.82.7/1.82.8 (supply-chain incident Mar 24 2026).
7. **Turborepo 2.x**: `tasks:` not `pipeline:` in turbo.json.
8. **projectdiscovery list**: `dist/data.json` under `programs` key (not `chaos-bugbounty-list.json`).
9. **HackerOne structured_scopes**: READ is CURRENT; only program-level WRITE removed. Merge `scope_exclusions`.
10. **Bugcrowd cookie**: `_bugcrowd_session` (not `_crowdcontrol_session`).
11. **SciPy 1.17.0 `ttest_ind`**: keyword-only args; `permutations`/`random_state` removed. Welch = `equal_var=False`.
12. **Subagent frontmatter**: markdown uses `tools:`; SDK uses `allowedTools`.
13. **MCP stdio**: never write stdout (corrupts JSON-RPC) — stderr/file only.
14. **Playwright dialog**: register handler BEFORE trigger; MUST accept/dismiss or page freezes.
15. **PyJWT**: hardcode `algorithms=["RS256"]` (RFC 8725 §2.1 none-alg attack).
16. **OpenFeature→Unleash Python**: no official provider (May 2026) — custom or flagd.
17. **CREATE EXTENSION `vectorscale`** (not `pgvectorscale`).
18. **ParadeDB dropped pgvectorscale from bundle** — custom image needed for vector+vectorscale+pg_search.
19. **1M context beta retired Apr 30 2026** — use Sonnet 4.6 / Opus 4.6 native 1M, no beta header.
20. **Coolify v4.1.0** first stable v4 (May 18 2026).


## Doc Exploration Policy

Always use jDocMunch-MCP tools for documentation navigation. Never fall back to Read for doc exploration.
**Exception:** Use `Read` when you need exact line numbers for `Edit`.

**Start any session:**
1. `doc_list_repos` — check what's indexed. If your docs aren't there: `index_local { "path": "." }`

**Finding content:**
- keyword/topic search -> `search_sections` (returns summaries only)
- browse structure -> `get_toc` (flat) or `get_toc_tree` (nested)
- single document -> `get_document_outline`

**Reading content:**
- one section -> `get_section` (full content via byte-range)
- multiple sections -> `get_sections` (batch)
- section + context -> `get_section_context` (ancestors + children)

**Maintenance:**
- broken internal links -> `get_broken_links`
- code/doc coverage gap -> `get_doc_coverage`


## Code Exploration Policy

Always use jCodemunch-MCP tools for code navigation. Never fall back to Read, Grep, Glob, or Bash for code exploration.
**Exception:** Use `Read` when you need to edit a file — the agent harness requires a `Read` before `Edit`/`Write` will succeed. Use jCodemunch tools to *find and understand* code, then `Read` only the specific file you're about to modify.

**Start any session:**
1. `resolve_repo { "path": "." }` — confirm the project is indexed. If not: `index_folder { "path": "." }`
2. `suggest_queries` — when the repo is unfamiliar

**Finding code:**
- symbol by name → `search_symbols` (add `kind=`, `language=`, `file_pattern=`, `decorator=` to narrow)
- decorator-aware queries → `search_symbols(decorator="X")` to find symbols with a specific decorator (e.g. `@property`, `@route`); combine with set-difference to find symbols *lacking* a decorator (e.g. "which endpoints lack CSRF protection?")
- string, comment, config value → `search_text` (supports regex, `context_lines`)
- database columns (dbt/SQLMesh) → `search_columns`

**Reading code:**
- before opening any file → `get_file_outline` first
- one or more symbols → `get_symbol_source` (single ID → flat object; array → batch)
- symbol + its imports → `get_context_bundle`
- specific line range only → `get_file_content` (last resort)

**Repo structure:**
- `get_repo_outline` → dirs, languages, symbol counts
- `get_file_tree` → file layout, filter with `path_prefix`

**Relationships & impact:**
- what imports this file → `find_importers`
- where is this name used → `find_references`
- is this identifier used anywhere → `check_references`
- file dependency graph → `get_dependency_graph`
- what breaks if I change X → `get_blast_radius`
- what symbols actually changed since last commit → `get_changed_symbols`
- find unreachable/dead code → `find_dead_code`
- class hierarchy → `get_class_hierarchy`

## Session-Aware Routing

**Opening move for any task:**
1. `plan_turn { "repo": "...", "query": "your task description", "model": "<your-model-id>" }` — get confidence + recommended files; the `model` parameter narrows the exposed tool list to match your capabilities at zero extra requests.
2. Obey the confidence level:
   - `high` → go directly to recommended symbols, max 2 supplementary reads
   - `medium` → explore recommended files, max 5 supplementary reads
   - `low` → the feature likely doesn't exist. Report the gap to the user. Do NOT search further hoping to find it.

**Interpreting search results:**
- If `search_symbols` returns `negative_evidence` with `verdict: "no_implementation_found"`:
  - Do NOT re-search with different terms hoping to find it
  - Do NOT assume a related file (e.g. auth middleware) implements the missing feature (e.g. CSRF)
  - DO report: "No existing implementation found for X. This would need to be created."
  - DO check `related_existing` files — they show what's nearby, not what exists
- If `verdict: "low_confidence_matches"`: examine the matches critically before assuming they implement the feature

**After editing files:**
- If PostToolUse hooks are installed (Claude Code only), edited files are auto-reindexed
- Otherwise, call `register_edit` with edited file paths to invalidate caches and keep the index fresh
- For bulk edits (5+ files), always use `register_edit` with all paths to batch-invalidate

**Token efficiency:**
- If `_meta` contains `budget_warning`: stop exploring and work with what you have
- If `auto_compacted: true` appears: results were automatically compressed due to turn budget
- Use `get_session_context` to check what you've already read — avoid re-reading the same files

## Model-Driven Tool Tiering

Your jcodemunch-mcp server narrows the exposed tool list based on the model you are running as. To avoid wasting requests on primitives when a composite would do, always include `model="<your-model-id>"` in your opening `plan_turn` call.

Replace `<your-model-id>` with your active model:
- Claude Opus variants → `claude-opus-4-7` (or any `claude-opus-*`)
- Claude Sonnet variants → `claude-sonnet-4-6`
- Claude Haiku variants → `claude-haiku-4-5`
- GPT-4o / GPT-5 / o1 / Llama → use the model id as printed by your runner

The `model=` parameter rides on the existing `plan_turn` call — it does **not** add a separate tool invocation. If `plan_turn` is not appropriate for a non-code task, call `announce_model(model="...")` once instead.

<!-- code-review-graph MCP tools -->
## MCP Tools: code-review-graph

**IMPORTANT: This project has a knowledge graph. ALWAYS use the
code-review-graph MCP tools BEFORE using Grep/Glob/Read to explore
the codebase.** The graph is faster, cheaper (fewer tokens), and gives
you structural context (callers, dependents, test coverage) that file
scanning cannot.

### When to use graph tools FIRST

- **Exploring code**: `semantic_search_nodes` or `query_graph` instead of Grep
- **Understanding impact**: `get_impact_radius` instead of manually tracing imports
- **Code review**: `detect_changes` + `get_review_context` instead of reading entire files
- **Finding relationships**: `query_graph` with callers_of/callees_of/imports_of/tests_for
- **Architecture questions**: `get_architecture_overview` + `list_communities`

Fall back to Grep/Glob/Read **only** when the graph doesn't cover what you need.

### Key Tools

| Tool | Use when |
| ------ | ---------- |
| `detect_changes` | Reviewing code changes — gives risk-scored analysis |
| `get_review_context` | Need source snippets for review — token-efficient |
| `get_impact_radius` | Understanding blast radius of a change |
| `get_affected_flows` | Finding which execution paths are impacted |
| `query_graph` | Tracing callers, callees, imports, tests, dependencies |
| `semantic_search_nodes` | Finding functions/classes by name or keyword |
| `get_architecture_overview` | Understanding high-level codebase structure |
| `refactor_tool` | Planning renames, finding dead code |

### Workflow

1. The graph auto-updates on file changes (via hooks).
2. Use `detect_changes` for code review.
3. Use `get_affected_flows` to understand impact.
4. Use `query_graph` pattern="tests_for" to check coverage.
