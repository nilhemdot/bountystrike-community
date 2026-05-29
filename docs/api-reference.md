# API Reference — BountyStrike v5

Programmatic interfaces in this repo. There is **no public REST API in v5** — `control-plane/api/` is intentionally empty per the design pillar "Single Postgres, no premature scale-out" ([`code-standards.md`](code-standards.md) §DDD Layout). Instead, the system exposes:

1. **MCP tools** (FastMCP stdio) — the agent-facing interface
2. **CLI scripts** under `scripts/`
3. **Subprocess agent contracts** (env-driven invocations of `validator-agent`, `exploit-agent`, `recon-agent`, `reporter-agent`)
4. **SQL surface** (read-side queries; the schema itself is in [`infra/sql/`](../infra/sql/))

This file catalogs each surface with input/output shape.

## 1. MCP Tools

15 servers (14 Python FastMCP stdio + 1 TypeScript). Inventory in [`codebase-summary.md`](codebase-summary.md) §MCP Inventory.

### 1.1 oracle-mcp

8 verifiers. Field-validated TPR=1.0/FPR=0.0 on 7 of 8 (SQLi suite landed `3fbe009`).

| Tool | Input fields | Output fields | Verifier |
|---|---|---|---|
| `verify_xss` | `url`, `parameter`, `payload`, `scope_jwt` | `status` (validated/unreproducible/flaky/inconclusive/error), `oracle_data`, `evidence_hash` | Playwright DOM mutation observer |
| `verify_ssrf` | `url`, `parameter`, `oast_token` | same | Interactsh callback match |
| `verify_ssrf_imds` | `url`, `parameter`, `oast_token` | same | 169.254.169.254 IMDS callback |
| `verify_sqli` | `url`, `parameter` | same + `t_statistic`, `p_value` | Welch's t-test on response timing |
| `verify_ssti` | `url`, `parameter`, `payload` | same + `engine_fingerprint` | Template-engine probe + execution proof |
| `verify_idor` | `url`, `object_id_a`, `object_id_b`, `auth_a`, `auth_b` | same + `cross_tenant_match` | Cross-tenant object-ID probe |
| `verify_rce` | `url`, `parameter`, `payload`, `sandbox_id` | same + `exec_artifacts` | Sandboxed payload execution |
| `verify_open_redirect` | `url`, `parameter`, `payload` | same + `final_location` | Location-header redirect chain |

Status enum: `validated`, `unreproducible`, `flaky`, `inconclusive`, `error`. Conservatism rule: any non-`validated` outcome on a known-vulnerable target is a TPR miss but never an FPR.

### 1.2 evidence-mcp

Hash-chained, content-addressable evidence store. Backend: aiosqlite + R2/local blob.

| Tool | Input | Output | Notes |
|---|---|---|---|
| `put_artifact` | `finding_id`, `request_transcript`, `response_transcript`, `oracle_data`, `reproduction_command`, `scope_token_jti`, `sandbox_vm_id`, optional `r2_key` | `content_hash` (sha256), `prev_audit_hash` | Computes `content_hash`, links into hash chain |
| `get_artifact` | `content_hash` | full artifact tuple | content-addressable |
| `append_audit_entry` | `actor`, `action`, `resource`, `payload` | `row_hash`, `prev_hash` | hash-chained `audit_log` write |
| `get_audit_chain` | optional `since` cursor | list of entries | chain replay / Rekor anchoring |

### 1.3 dedup-mcp

asyncpg + pgvector + OpenAI embeddings. Cross-session recall=1.0 since Phase 2 §10.4 (`3d9e915`).

| Tool | Input | Output |
|---|---|---|
| `check_duplicate` | `platform`, `program_handle`, `vuln_type`, `host`, `path` | `is_duplicate`, `existing_finding_id`, `tier` |
| `register_finding` | `finding_id`, `platform`, `program_handle`, `vuln_type`, `host`, `path` | `fingerprint_hex` |
| `check_semantic_duplicate` | `finding_id`, `embedding_text` (or `embedding_vector`) | `is_duplicate`, `nearest_neighbors[]` |
| `register_embedding` | `finding_id`, `text` | `embedding[]` (1536 dim), persisted |

Fingerprint: `sha256(platform || \x00 || program || \x00 || vuln_type || \x00 || host || \x00 || path)`. Semantic dedup uses HNSW (`vector_cosine_ops`, `m=16`, `ef_construction=64`).

### 1.4 state-mcp

Finding lifecycle + experience KB. asyncpg.

| Tool | Input | Output |
|---|---|---|
| `get_finding` | `finding_id` | full row + status + dedup info |
| `query_artifacts` | `finding_id` | list of evidence-artifact metadata |
| `query_experience_kb` | `vuln_type`, optional filters | curated past findings |
| `update_finding_status` | `finding_id`, `from`, `to`, `actor` | `success`, optimistic-lock metadata |

DSN parse + lock distinction fixed in `38dc943`. Status transitions enforce the 16-state ENUM machine (see [`system-architecture.md`](system-architecture.md) §Finding Status State Machine).

### 1.5 ev-mcp

Per-program EV ranking. asyncpg + workspace dep on control-plane.

| Tool | Input | Output |
|---|---|---|
| `rank_programs` | `operator_id`, optional `min_ev`, `limit` | sorted list `[{handle, platform, ev_score, factors{f_payout, f_saturation, f_ops, f_fit, f_cve}}]` |
| `get_program_details` | `handle` | program record + recent EV history + KEV matches |

EV formula: `EV = w_payout·f_payout + w_saturation·f_saturation + w_ops·f_ops + w_fit·f_fit + w_cve·f_cve`. Weights in `control-plane/src/control_plane/domains/program_ranking/services/scoring_service.py`. Freshness decay applied to EV history (`test_ev_freshness.py` validates).

### 1.6 kev-mcp

CISA KEV cross-reference. httpx + file cache.

| Tool | Input | Output |
|---|---|---|
| `kev_get_recent` | optional `since` | KEV entries newer than `since` |
| `kev_match_program` | `program_handle` (lookups tech stack) | matching KEV entries (`b7ec4e3`) |
| `kev_lookup` | `cve_id` | KEV entry or null |
| `kev_status` | — | last refresh timestamp + entry count |

### 1.7 scope-mcp (TypeScript)

JWT validation only.

| Tool | Input | Output |
|---|---|---|
| `validate_scope_jwt` | `jwt`, `target_host`, `target_path` | `in_scope`, `claim_match`, `decoded_claims` |
| `extract_claims` | `jwt` | `wildcards`, `exact_hosts`, `ips`, `exclusions.*`, `rate_limits.*`, `jti` |

Verifies RS256 signature against `keys/scope_jwt_public.pem`. Phase 2+ derives iptables egress allowlist from these claims.

### 1.8 Platform Submitters (5)

Each exposes `submit_report` with platform-specific request shape. Common error semantics: 429 honored via `Retry-After`, no retry on other 4xx (`fd55aff`, `0077e90`).

| MCP | Tool input (selected) | Output |
|---|---|---|
| `h1-mcp` | `program_handle`, `title`, `severity`, `vuln_info`, `structured_scope_id` | `submission_id`, `status` |
| `bugcrowd-mcp` | `program_handle`, `title`, `severity`, `vrt_id`, `description`, `bug_url` | same |
| `intigriti-mcp` | (placeholder — researcher API is read-only) | error or stub |
| `yeswehack-mcp` | `program_id`, `title`, `severity`, `description` | same |
| `immunefi-mcp` | `program_handle`, payload | same |

All gated by the `pretool_approval_gate.py` PreToolUse hook — `submit_report` cannot fire without an approved `approval_queue` row.

### 1.9 Utility MCPs

| MCP | Tools | Notes |
|---|---|---|
| `politeness-mcp` | `check_rate_limit` (per-host token bucket + adaptive backoff) | TOCTOU fix in `c38ff2e` |
| `sandbox-mcp` | `exec_safe` (LocalSubprocessDriver + DockerDriver scaffold) | Firecracker driver deferred (`b61546d`) |
| `normalize-mcp` | CVSS v3.1 + v4 normalization, CWE alignment | `cvss>=3.0`, accuracy fix in `34bb03c` |

## 2. CLI Scripts (`scripts/`)

| Script | Purpose | Required env |
|---|---|---|
| `orchestrator.py` | Full scan pipeline | `PROGRAM_HANDLE`, `PLATFORM`, `SCOPE_JWT`, `DATABASE_URL` |
| `gen_scope_jwt.py keygen --out keys/` | RS256 keypair generation | — |
| `gen_scope_jwt.py issue ...` | Issue a scope JWT | private key, claims |
| `approve.py list` | List pending approval queue | `DATABASE_URL` |
| `approve.py show <id>` | Show one request | `DATABASE_URL` |
| `approve.py approve <id> --reason "..."` | Approve. T3 returns None on first call. | `DATABASE_URL`, operator id implied |
| `approve.py reject  <id> --reason "..."` | Reject | same |
| `run_<vuln>_field_validation.py` | Oracle TPR/FPR harness (8 oracles) | (per-script lab containers) |
| `cost_audit.py` (Phase 3) | Cost reconciliation | `DATABASE_URL` |
| `metrics.py` (Phase 3) | Metric emission | `DATABASE_URL` |
| `onboard_hunter.py` (Phase 3) | Hunter onboarding | `DATABASE_URL` |
| `reconcile_hunt_outcomes.py` (Phase 3) | Hunt-outcome reconciliation | `DATABASE_URL`, platform creds |

## 3. Sub-Agent Contracts

The orchestrator launches sub-agents as subprocesses. Each sub-agent's spec lives at [`.claude/agents/<name>.md`](../.claude/agents/). Inputs are **environment variables**; outputs are stdout JSON lines + DB writes. One invocation = one finding (or one program for recon).

| Agent | Required env | Stdout contract |
|---|---|---|
| `recon-agent` | `SCOPE_JWT`, `PROGRAM_HANDLE`, `PLATFORM`, `DATABASE_URL` | `{"event": "recon_complete", "hosts": N, "endpoints": M}` |
| `cloud-recon-agent` | + cloud creds in scope JWT | `{"event": "cloud_recon_complete", ...}` |
| `scanner-agent` | `SCOPE_JWT`, recon artifacts ID | `{"event": "scan_complete", "candidates": N}` |
| `ai-vuln-hunter` | `SCOPE_JWT`, `FINDING_ID` (mode-dependent) | `{"event": "exploit_proposed" / "exploit_validated" / ...}` |
| `exploit-agent` | `SCOPE_JWT`, `FINDING_ID` | `{"event": "exploit_candidate", ...}` |
| `validator-agent` | `SCOPE_JWT`, `FINDING_ID` | `{"event": "validated" / "rejected", "oracle_data": {...}}` |
| `reporter-agent` | `SCOPE_JWT`, `FINDING_ID`, `APPROVAL_TOKEN` | `{"event": "submitted", "submission_id": "..."}` |
| `scope-guard` | (synchronous, called by hooks) | binding allow/deny verdict + reasoning trace |
| `program-selector` | operator profile + time budget | ranked program list |

The orchestrator parses stdout JSON lines for progress events; the canonical state lives in Postgres.

## 4. SQL Surface

Schema in [`infra/sql/01_schema.sql`](../infra/sql/01_schema.sql). 13 tables. Common read-side queries:

```sql
-- Pending approvals for an operator
SELECT id, finding_id, tier, requested_at, approver_id
FROM approval_queue
WHERE status = 'pending'
ORDER BY tier DESC, requested_at ASC;

-- Top-EV programs
SELECT p.handle, p.platform, e.ev_score
FROM programs p
JOIN LATERAL (
  SELECT ev_score FROM ev_score_history
  WHERE program_handle = p.handle
  ORDER BY computed_at DESC LIMIT 1
) e ON TRUE
ORDER BY e.ev_score DESC LIMIT 20;

-- Semantic dedup neighbors
SELECT id, 1 - (embedding <=> $1) AS cosine_sim
FROM findings
WHERE embedding IS NOT NULL
ORDER BY embedding <=> $1
LIMIT 10;

-- Hash-chain tail
SELECT id, ts, actor, action, encode(row_hash, 'hex') AS row_hash
FROM audit_log
ORDER BY id DESC LIMIT 1;

-- Submission funnel
SELECT status, COUNT(*) FROM findings GROUP BY status;
```

Don't write directly to `audit_log`, `evidence_artifacts`, or `findings` outside the application code — the hash-chain invariants and status-transition rules are enforced there.

## 5. Hook Wire Schemas

`.claude/hooks/*.py` are stdio scripts. Stdin is JSON; stdout is JSON. Examples in [`code-standards.md`](code-standards.md) §Hook Authoring. Wire schema corrected in `c75c3a9`.

```python
# Stdin
{"tool_name": "...", "tool_input": {...}, "session_id": "..."}

# Stdout — pass-through
{"continue": true}

# Stdout — deny
{"continue": false, "stopReason": "scope-violation: ..."}
```

Currently wired (3): `pretool_killswitch.py`, `pretool_antislop.py`, `pretool_approval_gate.py`. Settings: [`.claude/settings.json`](../.claude/settings.json). The pre-2026-05-18 `pretool_venice_route.py` hook was archived per the A4 verdict in [`audits/ollama-route-rewire.md`](audits/ollama-route-rewire.md).

## See Also

- [`codebase-summary.md`](codebase-summary.md) §MCP Inventory — full server table with backend/deps
- [`system-architecture.md`](system-architecture.md) §Component Graph — visual MCP topology
- [`code-standards.md`](code-standards.md) §MCP Server Template — how to add a new MCP tool
- [`testing-guide.md`](runbooks/testing-guide.md) — how to test MCP tools (respx, fixture patterns)
- [`research/04-skills-mcps.md`](research/04-skills-mcps.md) — full hook lifecycle (26 events) + MCP catalogue rationale
