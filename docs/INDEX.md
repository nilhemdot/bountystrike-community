# docs/INDEX.md — Master Navigation

Token estimates are approximate (1 token ~= 4 chars).

## Always-loaded (~800 tokens)

| File | Tokens | Purpose |
|------|--------|---------|
| CLAUDE.md | ~300 | Project rules, session protocol |
| .claude/COMMON_MISTAKES.md | ~200 | Critical errors |
| .claude/QUICK_START.md | ~200 | Commands |
| .claude/ARCHITECTURE_MAP.md | ~300 | File locations |

## Load by Task (~500-1500 tokens each)

| Task | File | Tokens |
|------|------|--------|
| MCP server work | `docs/learnings/mcp-patterns.md` | ~600 |
| Oracle / vuln detection | `docs/learnings/oracle-patterns.md` | ~700 |
| Database / migrations | `docs/learnings/database-patterns.md` | ~500 |
| Agent authoring | `docs/learnings/agent-patterns.md` | ~600 |
| Deployment / infra | `docs/learnings/deployment.md` | ~500 |
| Full system overview | `docs/system-architecture.md` | ~2000 |
| File map + schema | `docs/codebase-summary.md` | ~1500 |
| Code conventions | `docs/code-standards.md` | ~1200 |

## Never Auto-load

- `docs/archive/**` — historical docs
- `.claude/completions/**` — task completion records
- `.claude/sessions/**` — session state files

## Decision Trees

**Adding a new vulnerability oracle:**
1. Load `docs/learnings/oracle-patterns.md`
2. Implement in `mcp/oracle-mcp/`
3. Write field-validation suite in `scripts/run_<name>_field_validation.py`
4. Must hit TPR=1.0 / FPR=0.0
5. Wire to agent spec

**Adding a new bug bounty platform:**
1. Load `docs/learnings/mcp-patterns.md`
2. Create `mcp/<platform>-mcp/`
3. Register in workspace
4. Wire to reporter-agent spec

**Debugging a hunt failure:**
1. Load `.claude/COMMON_MISTAKES.md`
2. Check `scripts/health_check.sh` output
3. Check Langfuse traces
4. Load `docs/learnings/agent-patterns.md` if agent-level issue
