# `bspass` Credential Audit

**Date:** 2026-05-18
**Branch:** `audit/bspass-credential`
**Trigger:** PR #11 review consumer-scan surfaced a hardcoded `DATABASE_URL` with plaintext password `bspass` in three `.mcp.json` env blocks (lines 15, 22, 49 — `dedup`, `state`, `ev`).

## Verdict — LOW

`bspass` is a stale placeholder, not a working credential.

Confirmed via `docs/phase3_lessons.md:184` (operator's own historical note):

> `.env` line 10: password `bspass → ${POSTGRES_PASSWORD}` (role password set on volume init to long value, hardcoded `bspass` never worked over TCP)

The real Postgres password is generated per-host via `openssl rand -hex 32` (see `docs/configuration-guide.md:23-26`) and stored in the gitignored `.env`. Postgres' `pg_hba.conf` enforces password auth on TCP, so any connection to `127.0.0.1:5432` using `bspass` would be rejected. The placeholder gives the appearance of a credential without actually being one.

## Containment check

| Concern | Verified | Note |
|---|---|---|
| Is `.env` tracked in git? | **No** | `git ls-files --error-unmatch .env` → exit 1, "did not match." `.gitignore:2` lists `.env`. |
| Is `.env.example` tracked with secrets? | **Safe** | `.env.example:5` has `POSTGRES_PASSWORD=` (empty), no real secret. |
| Does the real prod password appear anywhere in tracked files? | **No** (no obvious leak surfaced in audit) | `git log -p` history sweep not exhaustive — operator should run their own canary scan if rotating. |

## Inventory — every `bspass` reference (15 total)

| File | Line(s) | Context | Risk |
|---|---|---|---|
| `.mcp.json` | 15, 22, 49 | `DATABASE_URL` env in `dedup` / `state` / `ev` MCP entries | LOW — placeholder; TCP connections fail. Misleading to readers. |
| `.github/workflows/integration-pg.yml` | 84, 97, 98 | Postgres-service password for CI integration runs | NONE — ephemeral CI container; destroyed after job; never reachable externally. Standard CI pattern. |
| `scripts/seed_programs.py` | 14 | Docstring `DATABASE_URL=...` example | NONE — illustration only. |
| `tests/integration/test_approval_queue_postgres.py` | 13 | Skip-message docstring showing `BS5_PG_TEST_DSN` convention | NONE |
| `tests/integration/test_dedup_postgres.py` | 13 | same | NONE |
| `tests/integration/test_dedup_semantic_postgres.py` | 13 | same | NONE |
| `tests/integration/test_kill_switch_watch.py` | 17 | same | NONE |
| `tests/integration/test_migration_07_phase3.py` | 12 | same | NONE |
| `tests/integration/test_orchestrator_skip_idor.py` | 13 | same | NONE |
| `tests/integration/test_recon_assets_postgres.py` | 14 | same | NONE |
| `tests/integration/test_schema_vs_spec_contract.py` | 18 | same | NONE |
| `tests/integration/test_validator_compliance_postgres.py` | 17 | same | NONE |
| `docs/phase3_lessons.md` | 184 | Operator's note that `bspass` doesn't work | NONE — the disclosure itself |

## Recommended action

Two items, both LOW priority — neither blocks PR #11.

### 1. Stop printing `bspass` in `.mcp.json` (defer to the `.mcp.json` cleanup PR)

When the `.mcp.json` homedir-path PR opens (currently held — see PR #11 review section), replace the three hardcoded `DATABASE_URL` values with environment-variable references so the MCP servers read the real password from the operator's `.env`:

```jsonc
// Current (lines 14-16, 21-23, 48-50)
"env": {
  "DATABASE_URL": "postgresql://bs:bspass@127.0.0.1:5432/bountystrike_v5"
}

// Proposed
"env": {
  "DATABASE_URL": "${DATABASE_URL}"
}
```

Claude Code's `.mcp.json` supports `${VAR}` interpolation in `command`, `args`, `env`, and `url` fields (verified 2026-05-18 against `https://code.claude.com/docs/en/mcp` § "Environment variable expansion in `.mcp.json`"). The optional fallback form `${VAR:-default}` is also supported. **Note:** the syntax is `${VAR}`, not `${env:VAR}` — the latter was an earlier mis-spec in this document and was corrected after consulting the loader docs. This single change removes all three `bspass` placeholders, sources the real password from the operator-side `.env`, and stops misleading any future reader into thinking the password is `bspass`.

### 2. No action for the CI workflow + test docstrings

`bspass` in `.github/workflows/integration-pg.yml` is the standard pattern for an ephemeral CI Postgres service. The container is created with `POSTGRES_PASSWORD=bspass`, used only within the CI job, then destroyed. No real-world exposure.

`bspass` in test docstrings (8 files) is illustration of the `BS5_PG_TEST_DSN` env-var convention for local-host integration runs. Replacing those would clutter the docstrings without adding security value.

## Out-of-audit observation

The `.mcp.json` cleanup PR (held) needs:
1. Operator authorization to edit `.mcp.json` (auto-mode classifier flags it as agent-startup config).
2. Path-syntax decision for the 15 `/home/nilhem/bountystrike-ai5/...` paths (relative recommended).
3. **Plus this audit's recommendation** — flip `DATABASE_URL` to env-var interpolation.

Folding all three into one PR keeps the `.mcp.json` change to a single review pass.
