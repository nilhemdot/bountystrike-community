# Code Standards — BountyStrike v5

How to write code that fits the existing structure of this repo. Covers Python style (ruff/mypy), DDD layout under `control-plane/`, the FastMCP server template, hook authoring, test conventions, and SQL migrations.

Read [`codebase-summary.md`](codebase-summary.md) first for the file map and [`system-architecture.md`](system-architecture.md) for the visual context. This document is the "how to add new code" companion.

**Generated:** 2026-05-01 against git HEAD `e9b4b77`. Includes Phase 2 W7-8 additions: the field-validation suite pattern (now used by 7 of 8 oracles) and the T3 approval lifecycle.

## Python Style

### ruff — single source of truth

From root [`pyproject.toml`](../pyproject.toml):

```toml
[tool.ruff]
line-length = 100
target-version = "py312"

[tool.ruff.lint]
select = ["E", "F", "W", "I", "N", "UP", "B", "SIM", "ASYNC"]
```

Rule families enabled: pycodestyle (E/W), pyflakes (F), isort (I), pep8-naming (N), pyupgrade (UP), flake8-bugbear (B), flake8-simplify (SIM), flake8-async (ASYNC). Run before any commit:

```bash
uv run ruff check .
uv run ruff format .
```

`ASYNC` is non-negotiable — every blocking call inside an async function is a bug. Use `httpx.AsyncClient`, `asyncpg`, `aioboto3`, `aiofiles`. Use `asyncio.to_thread(...)` only as a last resort.

### Type hints + mypy

`mypy>=1.13` is a dev dep on `control-plane`. Public functions and dataclass-like objects are typed. Pydantic models replace raw dicts at any input boundary (HTTP, MCP tool, file parser).

```python
# Good
async def get_finding(finding_id: UUID) -> Finding | None:
    ...

# Bad — never return Any from a service layer
def parse(data):
    return data
```

### Imports

isort handles ordering (auto via `ruff format`). One import per line for stdlib + third-party + local. Local imports use absolute paths from the package root (`from control_plane.domains.recon.service import ReconService`), not relative (`from ..service import ReconService`).

### Logging

`structlog>=24` is the only logger. Initialize once per process; pass the bound logger through services. Never use `print()` or stdlib `logging.info()` directly in production code (orchestrator scripts are an exception — they print human-friendly status with timestamps).

```python
import structlog
log = structlog.get_logger(__name__)

log.info("recon_complete", program_handle=ph, hosts=n_hosts)
```

### Error handling

Fail loud at config boundaries — environment variables that aren't set are bugs, not warnings. The pattern in [`scripts/orchestrator.py`](../scripts/orchestrator.py):

```python
def _get_required(key: str) -> str:
    val = os.environ.get(key)
    if not val:
        print(f"[orchestrator] ERROR: {key} is not set", file=sys.stderr)
        sys.exit(1)
    return val
```

Catch only specific exceptions. Never `except Exception:` without re-raising or logging context.

## Domain-Driven Design Layout (`control-plane/`)

The control-plane uses bounded contexts. Each domain owns its aggregates, value objects, services, and repositories. Cross-domain coupling goes through events or the application service layer, never through direct imports of internal aggregates.

```
control-plane/src/control_plane/
├── core/                       # cross-cutting primitives
│   ├── security/               # validation patterns, path guards
│   └── shared/                 # AggregateRoot, DomainEvent, ValueObject
├── domains/                    # bounded contexts
│   └── <context>/
│       ├── aggregates.py       # AR + invariants
│       ├── value_objects/      # immutable types
│       ├── services/           # domain services (no I/O)
│       ├── repositories/       # interfaces + implementations
│       ├── integrations/       # external API clients
│       └── __main__.py         # optional container entrypoint
└── infrastructure/             # ORM, engine, pooling — composition root
```

### Where new code goes

| Adding... | Location |
|---|---|
| A new aggregate (e.g. `ScanReport`) | `control-plane/src/control_plane/domains/<context>/aggregates.py` |
| A pure-function calculation | `control-plane/src/control_plane/domains/<context>/services/` |
| External API client (e.g. new platform) | `control-plane/src/control_plane/domains/<context>/integrations/` |
| Cross-context utility (e.g. new validator) | `control-plane/src/control_plane/core/security/` or `core/shared/` |
| HTTP route (only if exposed externally) | `control-plane/api/` (currently empty — no REST API in v5) |

### Forbidden coupling

- A domain `services/` module imports from `infrastructure/` ✗
- A domain imports another domain's `aggregates.py` ✗ (use events)
- `core/shared/` imports from any `domains/*` ✗
- `infrastructure/database.py` imports any domain's value-objects ✓ (composition root)

## MCP Server Template

Every Python MCP follows the same skeleton. Use [`mcp/oracle-mcp/`](../mcp/oracle-mcp/) as the reference — it has the most surface area.

### Directory layout

```
mcp/<name>-mcp/
├── pyproject.toml
├── src/
│   └── <name>_mcp/
│       ├── __init__.py
│       └── server.py           # FastMCP entry — main()
├── tests/
│   ├── __init__.py
│   └── test_server.py
└── README.md (optional)
```

### `pyproject.toml` template

Copy from [`mcp/kev-mcp/pyproject.toml`](../mcp/kev-mcp/pyproject.toml):

```toml
[project]
name = "<name>-mcp"
version = "0.1.0"
description = "BountyStrike v5 — <one-line purpose>"
requires-python = ">=3.12"
dependencies = [
    "mcp>=1.0",
    "structlog>=24",
    # add only what this server needs
]

[project.optional-dependencies]
dev = [
    "pytest>=8",
    "pytest-asyncio>=0.24",
    "respx>=0.21",      # only if using httpx
    "ruff>=0.7",
]

[project.scripts]
<name>-mcp = "<name>_mcp.server:main"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/<name>_mcp"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

**Then register in workspace:** add `"mcp/<name>-mcp"` to `[tool.uv.workspace].members` in the root [`pyproject.toml`](../pyproject.toml). The 9 platform/utility MCPs that aren't yet registered (h1, bugcrowd, intigriti, yeswehack, immunefi, state, sandbox, normalize, politeness) need this fix as a Phase 2 cleanup task.

### `server.py` shape

Keep tools small and explicit. Pydantic models at every input/output boundary. Return JSON-serializable dicts.

```python
"""<name>-mcp — <one-line>"""
from __future__ import annotations

import asyncio
import structlog
from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, Field

log = structlog.get_logger(__name__)
mcp = FastMCP("<name>-mcp")


class FooInput(BaseModel):
    target: str = Field(..., description="...")


class FooResult(BaseModel):
    status: str
    detail: dict


@mcp.tool()
async def do_foo(input: FooInput) -> FooResult:
    """One-paragraph docstring describing what the tool does, for the agent."""
    log.info("do_foo_invoked", target=input.target)
    # ... actual work ...
    return FooResult(status="ok", detail={})


def main() -> None:
    asyncio.run(mcp.run_stdio_async())


if __name__ == "__main__":
    main()
```

### Backend choice

| Need | Library | Example |
|---|---|---|
| Postgres reads/writes | `asyncpg>=0.29` | `dedup-mcp`, `state-mcp`, `ev-mcp` |
| Local SQLite | `aiosqlite>=0.20` | `evidence-mcp` |
| HTTP to external API | `httpx>=0.27` (`AsyncClient`) | `kev-mcp`, all 5 platform submitters |
| Browser automation | `playwright>=1.48` | `oracle-mcp` (XSS DOM observer only) |
| Stats / numerics | `scipy>=1.13` | `oracle-mcp` (Welch t-test for SQLi) |
| CVSS / CWE | `cvss>=3.0` | `normalize-mcp` |
| Token bucket / rate limit | stdlib only (`asyncio` + `time.monotonic()`) | `politeness-mcp` |

Don't add a new dependency without a clear reason; baseline `mcp + structlog` is enough for many servers.

### Error semantics

- Return error info as a structured field in the result, not as an HTTP status or raised exception. Agents should be able to inspect failures programmatically.
- Use `respx>=0.21` to mock httpx in tests; never hit real platform APIs from CI.
- Honor `Retry-After` on 429s (see `0077e90` for the cross-platform pattern). Do NOT retry on 4xx other than 429 (`fd55aff`).

## Hook Authoring

Hooks live under [`.claude/hooks/`](../.claude/hooks/) and are wired in [`.claude/settings.json`](../.claude/settings.json). Schema must match the Claude Code wire format (see commit `c75c3a9` for the fix that landed correct schema across the four hooks).

### Wire schema (PreToolUse)

A hook is a stdin/stdout script. Stdin is JSON; stdout is JSON. The minimal pass-through:

```python
#!/usr/bin/env python3
import json, sys

payload = json.loads(sys.stdin.read())
# inspect payload["tool_name"], payload["tool_input"], payload["session_id"]
print(json.dumps({"continue": True}))
```

To deny a tool call:

```python
print(json.dumps({
    "continue": False,
    "stopReason": "scope-violation: target outside JWT claims",
}))
```

### settings.json registration

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "^(Write|Edit|MultiEdit)$",
        "hooks": [
          {
            "type": "command",
            "command": "$CLAUDE_PROJECT_DIR/.claude/hooks/pretool_<name>.py"
          }
        ]
      }
    ]
  }
}
```

Without a `matcher`, the hook applies to all tool calls (this is what `pretool_killswitch.py` uses). Match on tool-name regex when the hook is type-specific (write/edit, MCP submit, etc.).

### Fail-open vs fail-closed

| Hook | Default on hook-internal error |
|---|---|
| `pretool_killswitch.py` | **fail-open** if Redis unreachable (L3 supervisor is the backstop) |
| `pretool_antislop.py` | **fail-closed** — never let unverified report writes through |
| `pretool_approval_gate.py` | **fail-closed** — submission without approval is the worst case |

Document the fail mode in a docstring at the top of every hook.

### Permissions

Hooks must be `chmod +x`. Use `#!/usr/bin/env python3` shebang (never hardcode the venv interpreter). Test with:

```bash
echo '{"tool_name":"Write","tool_input":{"file_path":"/tmp/x"}}' | \
  .claude/hooks/pretool_antislop.py
```

## Test Conventions

### Layout

```
control-plane/tests/                 # 21 test files
mcp/<name>-mcp/tests/                # per-MCP tests
tests/fixtures/                      # shared fixtures (rare)
```

Test files mirror source files: `services.py` → `test_services.py`. One module per concept; one class per scenario when state is involved.

### Pytest config

`asyncio_mode = "auto"` is set in every package's `[tool.pytest.ini_options]`. All `async def test_*` are collected automatically.

### Fixtures

- **DB fixtures:** spin up a test Postgres via `pytest_asyncio` + `asyncpg`. Don't share state across tests.
- **HTTP mocks:** `respx>=0.21` for httpx-based code.
- **Time:** `freezegun` only when timing matters (rare); otherwise let real `now()` flow.
- **Crypto:** generate ephemeral RS256 keypairs in fixtures; never commit test keys.

### What to test

| Layer | Test what |
|---|---|
| Pure services (no I/O) | All branches; property-based when math involved (EV scoring uses `test_ev_fixture_50.py`) |
| Repositories | Round-trip writes; constraint violations; pagination |
| MCP tools | Tool registration, schema validation, error paths (use `respx` for external HTTP) |
| Oracles | TPR/FPR fixtures stored as JSON in `mcp/oracle-mcp/tests/reports/` (e.g. `phase1_xss_tpr_fpr.json`) |
| Hooks | Wire-schema in/out, fail-open/fail-closed branches, Redis-down case |

### Phase 1 fixture pattern

The Round 4 closeout used JSON fixture files (40-case for XSS, 5-endpoint for SSRF) checked into `mcp/oracle-mcp/tests/reports/`. Result: TPR=1.0, FPR=0.0. Reuse this pattern for new oracle additions: define cases as JSON, run them through the oracle, assert recall + precision targets.

### Field-Validation Suite Pattern (Phase 2 W7-8 onward)

Phase 2 generalised the Phase 1.1c/1.1d pattern into a 4-piece scaffold that every new oracle now follows. SSRF→IMDS (canonical example, commit `e9b4b77`) is the cleanest reference; IDOR (`65fe921`), RCE (`5493eea`), SSTI (`6ef4858`), and Open Redirect (`1b6eb64`) all match this shape exactly. All five reach **TPR=1.0, FPR=0.0** on the published fixtures; SQLi is the only oracle without a field-validation suite (pending Phase 2 W9-10).

| Piece | Path | Responsibility |
|---|---|---|
| 1. Test harness CLI | `scripts/run_<vuln>_field_validation.py` | Loads the JSON fixture, dispatches to the oracle through `FieldValidationRunner`, prints + writes a TPR/FPR report. Designed to be CI-runnable with no live external dependencies (lab containers + local OAST collector handle the rest). |
| 2. Oracle implementation | `mcp/oracle-mcp/src/oracle_mcp/oracles/<vuln>.py` | Pure async function. Returns one of `validated / unreproducible / flaky / inconclusive / error`. Emits oracle_data dict for evidence storage. No side effects beyond the HTTP probe / sandbox exec. |
| 3. Fixture pair + lab | `mcp/oracle-mcp/tests/fixtures/<vuln>_targets.json` (vulnerable + clean URLs) + a Docker container under `mcp/oracle-mcp/tests/fixtures/<vuln>_lab/` if the oracle needs a server-side surface. The clean control set must be at least as large as the vulnerable set. |
| 4. Integration test | `mcp/oracle-mcp/tests/test_oracles_phase2.py` (or a per-vuln `test_<vuln>_field_validation.py`) | Brings up the lab compose stack, runs the harness, asserts `report.passes_exit_criterion(min_tpr=0.90, max_fpr=0.0)`. The published JSON report under `mcp/oracle-mcp/tests/reports/` is the merge gate. |

The oracle dispatcher in `mcp/oracle-mcp/src/oracle_mcp/field_validation.py` is injectable, so unit tests can stub Playwright / httpx / Interactsh / sandbox-mcp. Production calls the real oracle. Conservatism rule from Phase 1 still applies: any non-`validated` outcome on a known-vulnerable target is a TPR miss but never an FPR.

The orchestrator's validator phase (`scripts/orchestrator.py`) is the production path — it picks a finding, hands it to a validator-agent subprocess, which calls the oracle MCP. The field-validation harness is the offline equivalent that runs the same oracle code against fixed inputs.

### T3 Approval Lifecycle

T0/T1/T2 are documented above (PreToolUse hook, single-human approval, etc.). T3 is the two-distinct-human gate added in Phase 2 W7-8 (commit `7001be1`). Triggers per `control-plane/src/control_plane/domains/approval_gate/services.py:classify_tier`: CVSS > 9.0, novel chain hop_count ≥ 3, PII exposure > 10 records, credential-theft class, smart-contract-critical, or any sandbox execution. SLA: 30 min.

The lifecycle is implemented across four files; do not bypass any of them.

```
classify_tier (services.py)
   └─ if T3 → status=approval_pending_t3
       └─ orchestrator._enqueue_pending_t3 → queue.enqueue(finding_id, tier=T3)
           └─ approval_queue row inserted (status=pending, approver_id=NULL, approver_id_2=NULL)
               └─ wait_for_approval (queue.py) — exp backoff 5s → 60s
                   ├─ operator runs scripts/approve.py approve <id>
                   │   ├─ first call → approver_id set, returns None (still pending)
                   │   └─ second call (DISTINCT actor) → approver_id_2 set, returns APPROVAL_TOKEN
                   └─ orchestrator relaunches reporter-agent with APPROVAL_TOKEN env
```

Important constraints (Round 5 Bug-1 surfaced these):

- `queue.approve()` returns `Optional[uuid.UUID]`. `None` means "first approver recorded, still need a second distinct actor". Do not interpret `None` as failure.
- The first-approver write must commit before the second call arrives — never wrap the distinct-actor check in an `async with conn.transaction()` that raises to "signal pending", because asyncpg interprets the raise as rollback and you lose the first approver.
- Distinct-actor enforcement is on `approver_id != approver_id_2`. The same operator approving twice is rejected at the queue layer, not at the CLI.

A regression test for Bug-1 lives at `tests/integration/test_approval_queue_postgres.py::test_t3_first_approver_commits_before_returning`. Don't touch the commit ordering without re-running it.

## SQL Migration Conventions

Migrations live in [`infra/sql/`](../infra/sql/) with numeric prefix + descriptive name. They auto-apply on first Postgres boot via the `docker-entrypoint-initdb.d` mount in [`docker-compose.yml`](../infra/docker/docker-compose.yml).

### File order

```
00_extensions.sql        # extensions (pgvector, pg_trgm, pgcrypto)
01_schema.sql            # core tables + ENUMs
02_<feature>.sql         # additive — new tables or columns
03_<feature>.sql         # additive
...
```

Migrations are append-only by convention. Never modify a previously-merged migration; add a new file.

### Idempotence

Every migration must be re-runnable without error. Patterns:

```sql
CREATE TABLE IF NOT EXISTS ...
CREATE INDEX IF NOT EXISTS ...

DO $$ BEGIN
  CREATE TYPE foo AS ENUM (...);
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
  ALTER TABLE bar ADD COLUMN IF NOT EXISTS baz INTEGER;
EXCEPTION WHEN undefined_table THEN NULL;
END $$;
```

### Applying outside Docker

For dev iteration on an already-running Postgres:

```bash
psql "$DATABASE_URL" -f infra/sql/02_dedup_fingerprints.sql
```

The `IF NOT EXISTS` patterns make this safe even if the migration has already been applied.

## Commit Conventions

Recent git history shows a clean Conventional Commits-ish pattern:

```
feat: kev-mcp kev_match_program — tech-stack ↔ KEV cross-reference
fix: PreToolUse hooks emit valid Claude Code wire schema
fix(security): platform-MCP SSRF + base_url + body-leak hardening
docs: phase1 signoff Round 4 — close 1.1c + 1.1d (TPR=1.0, FPR=0.0)
chore: add ruflo runtime/data files to .gitignore
```

Type prefixes: `feat`, `fix`, `fix(security)`, `docs`, `chore`. Subject is imperative, ≤72 chars. Body explains *why* if non-obvious. Reference commit hashes when phase-tracking (`Phase 1.1d` etc.).

Never use `--amend` after pushing. Never `--no-verify` to skip hooks.

## What NOT To Do

| Anti-pattern | Why wrong | Do instead |
|---|---|---|
| Add MCP without registering in workspace | `uv sync` won't install it; tests won't run in CI | Add to `[tool.uv.workspace].members` in root `pyproject.toml` |
| Log secrets via structlog | Logs may be persisted to Langfuse / files | Redact at the boundary; never pass raw JWT or API key to a logger |
| Bypass scope-mcp for "convenience" | Breaks non-negotiable #1 | Always validate JWT at the MCP boundary |
| Commit a `.env` or `keys/` file | Permanent leak | Check `.gitignore` covers it; pre-commit hook enforces |
| Use `print()` in service-layer code | Bypasses structured logging + Langfuse | Inject a `structlog.BoundLogger` |
| Add a new oracle without TPR/FPR fixture | No verifiable accuracy claim | Follow Phase 1.1c/1.1d pattern: JSON fixture in `tests/reports/` |
| Register a hook with broken wire schema | Claude Code rejects it silently | Test with `echo $JSON \| ./hook.py` before wiring |
| Catch `Exception:` and swallow | Hides real bugs | Catch specific types; re-raise with context |
| Run `git commit --no-verify` | Skips secret-scan + lint | Fix the underlying lint / hook failure |

## See Also

- [`codebase-summary.md`](codebase-summary.md) — file inventory + dependency table
- [`system-architecture.md`](system-architecture.md) — visual flows
- [`research/04-skills-mcps.md`](research/04-skills-mcps.md) — full hook lifecycle (26 events) + MCP catalogue rationale
- [`phase1_signoff.md`](signoffs/phase1_signoff.md) — example of a clean signoff doc
