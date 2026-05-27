# BountyStrike v6 — Phase 0 & Phase 1 Implementation-Ready Technical Brief

**Prepared for:** Evan Nil, DEVOPSEC lead, BountyStrike v6 (HexStrike-AI integrated)
**Date:** May 21, 2026
**Purpose:** Atomized, dependency-ordered, machine-executable task graph for one-shot Claude Code autonomous execution from empty repo → AGPLv3 Community Edition release.

> **Provenance note (added 2026-05-27):** This brief is the PRIMARY-SOURCE authority for Phase 0/1 facts. It supersedes the v6 plan's "Correction #1" on DeepSeek pricing (which was itself wrong) and resolves the HackerOne structured_scopes gate. See the SIX CORRECTIONS table at the bottom.

---

## TL;DR
- **HackerOne `structured_scopes` is NOT fully deprecated.** Per api.hackerone.com changelog (April 7, 2026): only **program-level WRITE** is removed. READ endpoint `GET /v1/hackers/programs/{handle}/structured_scopes` still current (last revised 2026-01-16); NEW `GET /v1/hackers/programs/{handle}/scope_exclusions` added April 11, 2026.
- **DeepSeek pricing in the v6 plan's "Correction #1" is itself wrong.** Per api-docs.deepseek.com/quick_start/pricing (May 21, 2026): `deepseek-chat`/`deepseek-reasoner` are aliases for `deepseek-v4-flash`, priced **$0.14 cache-miss input / $0.0028 cache-hit input / $0.28 output per 1M tokens** (cache-hit reduced to 1/10 of launch price on 2026-04-26).
- **Full toolchain verified.** Critical TRAINING-DATA TRAPS: `claude-code-sdk → claude-agent-sdk` rename; Hatchet v1 SDK breaking API; bbscope v1→v2 subcommand restructure; boto3 1.36.0 R2 checksum incompatibility; LiteLLM 1.82.7/1.82.8 supply-chain incident (use v1.86.1 stable).

---

## SIX CORRECTIONS — RE-AUDITED

| # | Original Correction (from v6 plan) | Audit Result | Action |
|---|---|---|---|
| 1 | DeepSeek $0.28 in / $0.42 out cache-miss, $0.028 cache-hit | **WRONG.** Primary source (api-docs.deepseek.com/quick_start/pricing, May 21 2026): deepseek-chat/-reasoner alias deepseek-v4-flash. **$0.14 cache-miss input / $0.0028 cache-hit input / $0.28 output per 1M.** Cache-hit cut to 1/10 launch price 2026-04-26. V4 Pro promo 75% off until 2026-05-31 15:59 UTC. | REPLACE numbers. LiteLLM model-rename detect. Cron-refresh pricing daily. |
| 2 | No hard Anthropic refusal-rate; runtime classifier | Valid (no vendor publishes refusal metrics) | Classifier + fallback claude-sonnet-4-6 → deepseek-v4-flash via LiteLLM `default_fallbacks` |
| 3 | XBOW Informative/N-A rate is industry estimate | Valid | Document in docs/methodology/disclosed-calibration.md |
| 4 | HackerOne structured_scopes must be verified | **CONFIRMED VIA PRIMARY SOURCE.** Only program-level WRITE removed Apr 7 2026. READ still current. NEW scope_exclusions Apr 11 2026. | Implement structured_scopes read + scope_exclusions read + merge. Skip program-level WRITE. |
| 5 | Welch's t-test is calibrated heuristic | Valid. SciPy 1.17.0 keyword-only sig; `permutations`/`random_state` REMOVED. | Document calibration in CLAUDE.md; calibrate on clean endpoint at session start |
| 6 | EV decay constants proprietary | Valid | docs/methodology/ev-decay.md + ship defaults |

---

## CRITICAL TRAINING-DATA TRAPS (consolidated)

1. **claude-code-sdk → claude-agent-sdk** (Python + TS); `ClaudeCodeOptions → ClaudeAgentOptions`.
2. **Hatchet v1 SDK** (1.33.5+): `@hatchet.task()` (function-based) not `@hatchet.workflow`; Pydantic inputs; `aio_` prefix for async.
3. **bbscope v1 → v2**: subcommand restructure to `poll`/`db`.
4. **DeepSeek model rename**: `deepseek-chat`/`deepseek-reasoner` alias `deepseek-v4-flash`. Cache-hit at 1/10 launch price from 2026-04-26.
5. **boto3 1.36.0 R2 checksum break**: pin `boto3<1.36` or set `request_checksum_calculation="when_required"`.
6. **LiteLLM supply-chain 1.82.7/1.82.8** (Mar 24 2026 10:39 UTC): pin to 1.86.1 stable.
7. **Turborepo 2.x `pipeline:` → `tasks:`** in turbo.json.
8. **`chaos-bugbounty-list.json` moved**: now `dist/data.json` under `programs` key.
9. **HackerOne structured_scopes**: NOT fully deprecated — only program-level WRITE removed.
10. **Bugcrowd cookie**: `_bugcrowd_session` NOT `_crowdcontrol_session`.
11. **SciPy 1.17.0 ttest_ind**: keyword-only args; `permutations` & `random_state` removed.
12. **Claude Code subagent frontmatter**: markdown uses `tools:` (not `allowed-tools:`); SDK uses `allowedTools`.
13. **MCP stdio logging**: NEVER write to stdout (corrupts JSON-RPC) — use stderr/file.
14. **Playwright dialog handler**: register BEFORE triggering action; once registered MUST accept/dismiss.
15. **PyJWT algorithms list**: always hardcoded `["RS256"]`; never derive from token (RFC 8725 §2.1).
16. **OpenFeature Python → Unleash**: no official provider as of May 2026 — write custom or use flagd.
17. **pgvectorscale registered name**: `vectorscale` not `pgvectorscale` in CREATE EXTENSION.
18. **ParadeDB removed pgvectorscale from its bundle**: need custom Docker image for all three.
19. **1M context beta retired April 30, 2026**: use Sonnet 4.6 / Opus 4.6 native 1M; no beta header.
20. **Claude Agent SDK uses anyio.run, not asyncio.run**.

---

## VERIFIED TOOLCHAIN VERSIONS

| Component | Pin | Note |
|---|---|---|
| turbo | ^2.9.0 (latest 2.9.12) | 2.x uses `tasks:` not `pipeline:` |
| pnpm | 9.x | Node 18+ |
| pgvector | 0.8.1+ | |
| pgvectorscale | 0.9.0 | `CREATE EXTENSION vectorscale CASCADE` |
| pg_search (ParadeDB) | current | BM25 |
| hatchet-sdk | 1.33.5+ | alpha; function-based `@hatchet.task()` |
| litellm | v1.86.1 | NEVER 1.82.7/1.82.8 |
| boto3 | <1.36 | or `request_checksum_calculation="when_required"` |
| sops | v3.9.0 | CNCF Sandbox (getsops/sops) |
| playwright | >=1.50 | `mcr.microsoft.com/playwright/python:v1.50.0-jammy` |
| scipy | 1.17.0 | keyword-only ttest_ind args |
| PyJWT | 2.13.0 | `pyjwt[crypto]` |
| Coolify | v4.1.0 | first stable v4 (May 18 2026) |
| Claude Code | v2.1.89+ | `defer` decision |

---

## DEEPSEEK PRICING — CANONICAL (for LiteLLM config.yaml)

```yaml
  - model_name: deepseek-v4-flash
    litellm_params:
      model: deepseek/deepseek-v4-flash
      api_key: os.environ/DEEPSEEK_API_KEY
      input_cost_per_token: 0.00000014      # $0.14 / 1M cache-miss
      output_cost_per_token: 0.00000028     # $0.28 / 1M
      # cache-hit ($0.0028 / 1M) tracked via prompt_cache_hit_tokens in response
```

---

## HACKERONE structured_scopes — GATE RESOLUTION

**Primary source:** api.hackerone.com/getting-started/ (changelog).

| Endpoint | Status (May 2026) | Action |
|---|---|---|
| `GET /v1/hackers/programs/{handle}/structured_scopes` | **CURRENT** (rev 2026-01-16) | Primary scope source. Paginated. |
| `GET /v1/hackers/programs/{handle}/scope_exclusions` | **NEW** (Apr 11 2026) | Merge as out-of-scope filter |
| Program-level POST/PUT/DELETE structured_scopes | **REMOVED** Apr 7 2026 | Skip in CE; org-level asset endpoints (Enterprise) |
| `GET /v1/programs/{id}/structured_scopes` (customer API) | **CURRENT** | Credentials/asset linking |

Auth: Basic `<API_USERNAME>:<API_TOKEN>`.

**Implementation:** Do NOT remove structured_scopes ingestion — still primary asset list. ADD `/scope_exclusions` fetch, merge as "out-of-scope categories" in scope JWT claims.

---

> **NOTE:** This file is the condensed authoritative record. The full brief (Tracks A–F: Claude Code conventions, foundation toolchain, scope ingestion, verifier moat, recon pipeline, one-shot packaging, with code samples) was delivered 2026-05-21 and is the source for Phase 1 build plans. Key code patterns and the `tasks/` master graph live in that delivery; reproduce on demand.

---
*Saved to docs 2026-05-27 during PAUL plan 00-01-FIX intake.*
