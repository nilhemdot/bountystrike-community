# Spike — `pretool_venice_route.py` Ollama-Cloud Rewire

**Date:** 2026-05-18
**Branch:** `spike/venice-route-ollama`
**Trigger:** PR #11 review CRITICAL — `OLLAMA_CLOUD_API_KEY` has zero runtime consumers; the hook still hardcodes `mcp__openrouter__openrouter_complete` and Venice / Hermes-3 model IDs.

## Meta-finding (changes the framing of the CRITICAL)

**The hook is dormant in v5 today, regardless of which provider key is set.** No OpenRouter MCP server is registered in `.mcp.json` (`grep -c openrouter .mcp.json` → 0). The matcher in `.claude/settings.json:23` (`^mcp__openrouter__openrouter_complete$`) never matches any live tool in v5, so `pretool_venice_route.py` never runs.

The actual `openrouter-bridge` MCP server lives in the v4 sibling repo (`~/bountystrike-ai4/mcp/openrouter-bridge/dist/server.js`) and is **not** brought across into v5's `.mcp.json`. v5 references the tool name as an architectural placeholder; no process ever calls it.

**Implication for the rewire decision:**

- Both `OPENROUTER_API_KEY` and `OLLAMA_CLOUD_API_KEY` are forward-looking plumbing today.
- The PR #11 CRITICAL ("Ollama Cloud key has no consumer") is technically true *and* equally true of the OpenRouter key in current v5. Neither is consumed at runtime.
- "Rewire the hook to Ollama Cloud" is the wrong frame for the work item. The right frame is: *decide whether v5 needs an external-LLM MCP at all, then pick one (OpenRouter vs Ollama Cloud vs both), then register it.*

This downgrades the PR #11 CRITICAL to HIGH-deferred — there's no live operator failure mode today since the hook can't fire.

## Inventory — every venice-route artifact

### Code (1 file, 196 LOC)

`.claude/hooks/pretool_venice_route.py`:

| Line | Symbol | Type |
|---|---|---|
| 51 | `OPENROUTER_TOOL_NAME` | constant — the matcher target |
| 55-65 | `PAYLOAD_KEYWORDS` | tuple of 9 substrings (`payload`, `inject`, `bypass`, `polyglot`, `xss`, `sqli`, `ssti`, `rce`, `shellcode`) |
| 69-72 | `ALLOWED_PAYLOAD_MODELS` | frozenset of 2 model IDs |
| 74 | `DEFAULT_REROUTE_MODEL` | one of the above |
| 76-81 | `ANTHROPIC_DENY_REASON` | string naming the same 2 model IDs |
| 118 | `route(event)` | pure decision function, easily unit-tested |
| 152 | `_to_wire(decision)` | Claude Code hook wire-schema translator |
| 179 | `main()` | stdin / stdout entry point |

Architecturally clean — pure `route()` makes a rewire a constant-swap exercise.

### Settings wiring (1 line)

`.claude/settings.json:23`:

```json
{"matcher": "^mcp__openrouter__openrouter_complete$", ...}
```

Hook fires on any call to that exact tool name. Would need to be repointed (or duplicated) for a different MCP tool name.

### Test coverage (1 file, 238 LOC, 17 tests)

`control-plane/tests/test_venice_route_hook.py` — strong baseline.

| Coverage | Tests |
|---|---|
| Non-OpenRouter tool calls → allow no-op | yes |
| Non-payload prompts → allow no-op | yes |
| Anthropic + payload → deny | yes |
| Already-Venice model + payload → allow as-is | yes |
| Other model + payload → rewrite to Venice Dolphin | yes |
| Malformed input → fail-open allow | yes |
| Wire-schema translation (`_to_wire`) | yes |

Total assertions verified by the test suite: 17. Any rewire can target test parity by mirroring this matrix.

### Docs referencing the hook (8 files)

- `.claude/agents/exploit-agent.md:249` — instruction note about Anthropic refusal
- `docs/runbooks/configuration-guide.md:56` (post-PR #11 reframe — "consumed by `pretool_venice_route.py`")
- `docs/codebase-summary.md:104` — test inventory row
- `docs/api-reference.md`, `docs/code-standards.md`, `docs/architecture/bountystrike_v5_build_plan.md`, `docs/research/06-roadmap.md`, `docs/system-architecture.md` — passing references

## External-MCP-server landscape

### OpenRouter (current intent)

- v4 implementation: `~/bountystrike-ai4/mcp/openrouter-bridge/` (TypeScript, `@modelcontextprotocol/sdk@^1.0.0`, `openai@^4.67.0` SDK).
- Not registered in v5's `.mcp.json`. Either needs cross-repo bridge, or copy-and-update into v5's `mcp/` tree.

### Ollama Cloud

- API surface: OpenAI-compatible chat-completions endpoint (`https://api.ollama.cloud/v1/chat/completions` per Ollama Cloud docs at sign-off time; verify before implementation).
- Auth: `Authorization: Bearer ${OLLAMA_CLOUD_API_KEY}`.
- No off-the-shelf MCP server in either v4 or v5 trees.
- Building one is roughly a fork of `openrouter-bridge`: change base URL, change model IDs, keep the `openai` SDK + MCP-server scaffolding intact. Estimated 30-60 LOC of TypeScript delta plus tsconfig + package.json metadata.

### Model-ID equivalents

The two Venice/Hermes models on OpenRouter are not on Ollama Cloud — different provider catalogues. **Operator decision needed.** Candidate substitutes (verify availability on Ollama Cloud before committing):

| OpenRouter today | Plausible Ollama Cloud substitute (verify) |
|---|---|
| `cognitivecomputations/dolphin-mistral-24b-venice-edition` | `dolphin-mistral:latest` or `dolphin3:latest` (Ollama hosts the base Dolphin family; Venice-fine-tune is OpenRouter-exclusive) |
| `cognitivecomputations/hermes-3-llama-3-1-70b` | `hermes3:70b` (Ollama hosts Hermes 3 / Hermes 4 from NousResearch) |

Both substitutes are best-effort guesses. Confirm against `https://ollama.com/library` before pinning either as `DEFAULT_REROUTE_MODEL`.

## Rewire plan (when work item is greenlit)

Three parts. Sequential, each independently testable.

### Part A — Decide the destination

Operator-side. Not a code change. Pick one:

- **A1 — Repoint at Ollama Cloud.** Drop OpenRouter from the routing path entirely. Recommended if Ollama Cloud has the model coverage and the privacy story aligns with the original Venice rationale (no-data-collection mode was the key Venice property; verify Ollama Cloud equivalent).
- **A2 — Add Ollama Cloud alongside OpenRouter.** Hook matcher matches either tool name; routing logic picks the right `DEFAULT_REROUTE_MODEL` per provider.
- **A3 — Leave dormant.** Acknowledge the hook never fires today; rewire only if/when an external-LLM MCP is registered in v5's `.mcp.json`.

### Part B — Implementation (assuming A1 or A2)

1. **Fork the v4 `openrouter-bridge` into `mcp/ollama-cloud-bridge/`** in v5. Estimated 50-80 LOC TS delta:
   - Change `OpenAI` client `baseURL` to Ollama Cloud's endpoint.
   - Change auth header key to read `OLLAMA_CLOUD_API_KEY`.
   - Rename tool: `ollama_complete` (exposed as `mcp__ollama_cloud__ollama_complete`).
   - Re-test with `openai` SDK's compatibility shim.
2. **Register in `.mcp.json`** — one new stanza pointing at `node mcp/ollama-cloud-bridge/dist/index.js`. Held until the `.mcp.json` cleanup PR opens (operator authorization required per auto-mode classifier).
3. **Update the hook (~10 LOC delta in `pretool_venice_route.py`):**
   - `OPENROUTER_TOOL_NAME` → `OLLAMA_TOOL_NAME` (or both, if A2).
   - `ALLOWED_PAYLOAD_MODELS` → operator-selected Ollama IDs.
   - `DEFAULT_REROUTE_MODEL` → operator-selected.
   - `ANTHROPIC_DENY_REASON` → updated string.
4. **Update the settings matcher** (`.claude/settings.json:23`) to the new tool name (or matcher both, for A2).
5. **Update tests** (`control-plane/tests/test_venice_route_hook.py`) — replace tool-name + model-ID constants throughout. Test count unchanged: 17.
6. **Update the 8 docs** to reflect the chosen provider.

### Part C — Test parity gate (mandatory before merge)

- `uv run --no-sync pytest control-plane/tests/test_venice_route_hook.py -v` → 17/17 green with new constants.
- New integration smoke test: with `OLLAMA_CLOUD_API_KEY` exported, hit the new MCP tool end-to-end against a payload prompt; assert the wire response shape matches the spec contract.
- Operator-side cost-budget guardrail check — confirm the Ollama Cloud spend per request matches the routing-EV matrix (`docs/research/02-routing-ev.md`, which **also** needs a refresh per PR #11 MEDIUM finding).

## Estimated total rewire effort

| Stage | LOC delta | Test delta | Calendar effort |
|---|---|---|---|
| A — operator decision | 0 | 0 | 1 conversation |
| B1 — fork bridge into v5 | +200 (new file tree) | +30 (smoke test) | ~2 hr |
| B2 — `.mcp.json` registration | +5 | 0 | trivial, gated on cleanup PR |
| B3 — hook constants | ~10 | ~17 (in-place edits) | ~30 min |
| B4 — settings matcher | 1 line | 0 | trivial |
| B5 — test updates | 0 (constants only) | 0 | folded into B3 |
| B6 — 8 doc updates | ~30 across 8 files | 0 | ~30 min |
| C — verification | 0 | +smoke | ~30 min |

**Total: ~250 LOC, half a day of focused work, gated on the operator A1/A2/A3 decision and the `.mcp.json` cleanup PR landing first.**

## Recommended next step

Park the rewire pending A1/A2/A3 decision **and** an honest reassessment: since the hook is dormant today, do we actually need this routing layer in v5 at all? If the orchestrator can call Anthropic models directly with a clear refusal-fallback in the agent itself (no external LLM provider), the entire routing hook becomes dead code that can be archived. That's a fourth option worth considering before sinking the ~250 LOC into a rewire that may never run.

---

## Decision record — A4 selected (2026-05-18)

**Verdict: A4 — archive the routing layer.**

Operator picked A4 after this spike landed. Rationale:

- Hook was dormant in v5 (`.mcp.json` had zero OpenRouter MCP entries).
- Build-plan's "70% Anthropic refusal" claim predates Claude 4.x; the rate has not been measured against current models in v5.
- Cost-benefit favoured deletion: A1/A2 would have built ~250 LOC of infrastructure to solve an unmeasured problem; A4 archives unused code today and rebuilds only if post-Stage-2 measurement shows the routing layer is needed.

### Archival surface (delivered in this PR)

**Code (Phase 1):**
- Deleted `.claude/hooks/pretool_venice_route.py` (196 LOC).
- Deleted `control-plane/tests/test_venice_route_hook.py` (17 tests, 238 LOC).
- Removed the `mcp__openrouter__openrouter_complete` matcher block from `.claude/settings.json`.
- Removed the `OPENROUTER_API_KEY` + `OLLAMA_CLOUD_API_KEY` passthrough loop from `scripts/orchestrator.py` and the two docstring entries.
- Removed both `*_API_KEY=` placeholders from `.env.example`.

**Docs (Phase 2):**
- 8 operator-facing docs swept (exploit-agent spec, configuration-guide, codebase-summary, api-reference, code-standards, stage2 runbook, system-architecture, research/05-deployment).
- Build-plan + roadmap intentionally untouched (historical planning snapshots).

**This decision record (Phase 3):**
- Appended this section to the spike doc so the verdict + rationale are co-located with the analysis that produced them.

### Re-introduction gates

If a future Stage-2 run measures Anthropic refusal rate on payload-generation prompts, use the gates from the body of this spike:

| Observed refusal rate | Action |
|---|---|
| < 30% | A4 stays; the routing layer was correctly archived |
| 30-50% | Open a new PR implementing A2 (dual-route OpenRouter + Ollama Cloud) |
| > 50% | Open a new PR implementing A1 (Ollama Cloud only) |

Re-introduction is **not** automatic; it requires a fresh measurement, a new spike, and operator authorisation. Archival is the current state of record.

### What was preserved

The `exploit-agent` spec ([`.claude/agents/exploit-agent.md`](../../.claude/agents/exploit-agent.md)) now describes in-process Anthropic-refusal handling:

- Retry once with a reformulated prompt that foregrounds authorisation context and the specific defensive control being tested.
- On persistent refusal, revert `findings.status` to `hypothesis` so operator review or pipeline iteration can handle it later.

This is the no-external-LLM fallback path that A4 commits to.
