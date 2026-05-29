# Testing Guide — BountyStrike v5

How to run, write, and validate tests in this repo. Pair with [`code-standards.md`](../code-standards.md) §Test Conventions for the style rules and [`phase1_signoff.md`](../signoffs/phase1_signoff.md) for the Phase 1 fixture pattern that the Phase 2 W7-8 field-validation suites generalised from.

## Test Surface

| Layer | Location | Count | Runner |
|---|---|---|---|
| control-plane unit + integration | `control-plane/tests/` | 21+ files | `pytest` |
| Per-MCP tests | `mcp/<name>-mcp/tests/` | 1-N per server | `pytest` |
| Repo-level integration (Postgres) | `tests/integration/test_*_postgres.py` | growing (Phase 2 §10.4 dedup, schema-vs-spec, approval-queue, validator-compliance, recon-assets, Phase 3 calibration & migration 07) | `pytest` against live Postgres |
| Field-validation harnesses (oracle TPR/FPR) | `scripts/run_*_field_validation.py` | 8 (one per oracle) | direct `python` invocation |
| OOS safety audits | `tests/safety/` (e.g. 100-scan OOS audit, commit `f5a50c1`) | small | direct invocation |

Total post-Phase-1: 216 tests; Round 5 added 39 (24 queue unit + 8 orchestration smoke + 7 Postgres integration); Round 6 field-validation suites added per-oracle integration tests on top. Phase 2 §10.4 and Phase 3 calibration further extended the integration surface.

## Pytest Configuration

Single config across packages (each package's `pyproject.toml` includes):

```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
```

`asyncio_mode = "auto"` means **every** `async def test_*` is collected automatically — no `@pytest.mark.asyncio` boilerplate.

## Running Tests

### Control-plane

```bash
# All control-plane tests
uv run --package control-plane pytest control-plane/tests/

# With coverage (PEP-style)
uv run --package control-plane pytest --cov=control_plane --cov-report=term-missing control-plane/tests/

# Single file / single test
uv run --package control-plane pytest control-plane/tests/test_approval_gate.py
uv run --package control-plane pytest control-plane/tests/test_approval_gate.py::test_t3_two_distinct_actors
```

### Per-MCP

```bash
uv run --package oracle-mcp pytest mcp/oracle-mcp/tests/
uv run --package dedup-mcp  pytest mcp/dedup-mcp/tests/
uv run --package ev-mcp     pytest mcp/ev-mcp/tests/
uv run --package kev-mcp    pytest mcp/kev-mcp/tests/
uv run --package evidence-mcp pytest mcp/evidence-mcp/tests/
```

The 9 unregistered MCPs (h1, bugcrowd, intigriti, yeswehack, immunefi, state, sandbox, normalize, politeness) need direct invocation:

```bash
cd mcp/state-mcp && uv run pytest tests/
```

### Postgres-integration suite

These talk to a live Postgres (the docker-compose one or any `DATABASE_URL`). Bring the stack up first.

```bash
docker compose -f infra/docker/docker-compose.yml --env-file .env up -d postgres
DATABASE_URL=postgresql://bs:$POSTGRES_PASSWORD@localhost:5432/bountystrike \
  uv run pytest tests/integration/

# Examples
uv run pytest tests/integration/test_recon_assets_postgres.py
uv run pytest tests/integration/test_dedup_postgres.py
uv run pytest tests/integration/test_dedup_recall_phase3.py
uv run pytest tests/integration/test_approval_queue_postgres.py
uv run pytest tests/integration/test_validator_compliance_postgres.py
uv run pytest tests/integration/test_schema_vs_spec_contract.py
uv run pytest tests/integration/test_migration_07_phase3.py
```

These tests **rebuild fixture state inside their own transactions** — they don't expect a clean DB but they don't leak rows either. Don't run them against prod data.

### Field-Validation Harnesses (Oracle TPR/FPR)

One harness per oracle. All currently shipping at **TPR=1.0 / FPR=0.0** on their published fixtures except SQLi (suite landed in `3fbe009`, ratify on next CI).

```bash
uv run python scripts/run_xss_field_validation.py            # Phase 1.1c
uv run python scripts/run_ssrf_field_validation.py           # Phase 1.1d
uv run python scripts/run_ssrf_imds_field_validation.py      # Phase 2 W7-8 (e9b4b77)
uv run python scripts/run_idor_field_validation.py           # Phase 2 W7-8 (65fe921)
uv run python scripts/run_rce_field_validation.py            # Phase 2 W7-8 (5493eea)
uv run python scripts/run_ssti_field_validation.py           # Phase 2 W7-8 (6ef4858)
uv run python scripts/run_open_redirect_field_validation.py  # Phase 2 W7-8 (1b6eb64)
uv run python scripts/run_sqli_field_validation.py           # Phase 2 W7-8 (3fbe009)
```

Each harness:

1. Loads JSON fixture (vulnerable + clean URLs) from `mcp/oracle-mcp/tests/fixtures/<vuln>_targets.json`
2. Brings up the lab Docker container under `mcp/oracle-mcp/tests/fixtures/<vuln>_lab/` (if applicable)
3. Dispatches each case through `FieldValidationRunner` → real oracle code path
4. Computes TPR + FPR
5. Writes a JSON report to `mcp/oracle-mcp/tests/reports/<vuln>_tpr_fpr.json`
6. Asserts `report.passes_exit_criterion(min_tpr=0.90, max_fpr=0.0)`

Conservatism rule: any non-`validated` outcome on a known-vulnerable target is a TPR miss but **never** an FPR.

## Lint / Type-check

```bash
# Lint (root)
uv run ruff check .
uv run ruff format --check .

# Type-check (control-plane)
uv run --package control-plane mypy control-plane/src/

# Pyright (root, configured in pyrightconfig.json — commit b00ce35)
pyright
```

Ruff config: `line-length = 100`, `target-version = "py312"`, rules `E F W I N UP B SIM ASYNC`. ASYNC is non-negotiable.

## Test Style — AAA

Use Arrange-Act-Assert. From [`code-standards.md`](../code-standards.md):

```python
async def test_t3_first_approver_returns_none(approval_queue):
    # Arrange
    request_id = await approval_queue.enqueue(finding_id="F-1", tier="T3")
    # Act
    token = await approval_queue.approve(request_id, actor="op-A", reason="r")
    # Assert
    assert token is None     # first approver still leaves request pending
```

Names should describe behaviour: `test_returns_empty_array_when_no_match`, `test_falls_back_when_redis_unreachable`. Avoid `test_works`, `test_method_one`.

## Mocking Policy

| What | Tool | Notes |
|---|---|---|
| `httpx.AsyncClient` | `respx>=0.21` | every external HTTP call MUST be mocked in CI |
| Postgres | **don't mock** | use a real Postgres via `tests/integration/`. Mocking the DB has bitten the project before. |
| Redis (kill switch) | in-memory backend (`KILL_SWITCH_BACKEND=memory`) | exercises L1 logic without a Redis instance |
| Crypto / RS256 | ephemeral keypair fixtures | never commit test keys |
| Anthropic / OpenRouter | `respx` or recorded fixtures under `tests/fixtures/` | LLM determinism is per-test |
| Time | real `now()` by default; `freezegun` only when timing matters | freshness decay tests use real time + small windows |

The "don't mock the DB" rule is project preference (validated by past incident — see code-standards `test_t3_first_approver_commits_before_returning` regression). Use the real Postgres via the docker-compose stack for any test that touches schema or constraints.

## Fixtures

### DB fixtures

Common pattern:

```python
import pytest_asyncio
import asyncpg

@pytest_asyncio.fixture
async def db_pool():
    pool = await asyncpg.create_pool(os.environ["DATABASE_URL"], min_size=1, max_size=4)
    try:
        yield pool
    finally:
        await pool.close()

@pytest_asyncio.fixture
async def db_clean(db_pool):
    """Truncate the tables this test owns. Call from the test."""
    async with db_pool.acquire() as conn:
        await conn.execute("TRUNCATE findings, evidence_artifacts, approval_queue CASCADE")
    yield
```

### Oracle fixtures

JSON files under `mcp/oracle-mcp/tests/fixtures/<vuln>_targets.json` follow the shape:

```json
{
  "vulnerable": [
    {"url": "http://lab.local/xss?q=<script>", "expected": "validated", "notes": "..."}
  ],
  "clean": [
    {"url": "http://lab.local/safe?q=hello", "expected": "unreproducible", "notes": "..."}
  ]
}
```

Each oracle's lab container is under `mcp/oracle-mcp/tests/fixtures/<vuln>_lab/Dockerfile` plus a `docker-compose.yml`.

## Per-Phase Coverage

| Phase | Coverage gate | Where |
|---|---|---|
| 1 | Oracle TPR/FPR fixtures (XSS, SSRF), JWT signing, scope ingest, kill switch L1+L2, evidence chain | `mcp/oracle-mcp/tests/`, `control-plane/tests/test_*` |
| 2 W7-8 | 5 new oracle field-validation suites, T3 approval lifecycle, exploit→T2/T3 wiring, schema-vs-spec contract, validator-compliance audit | `scripts/run_*_field_validation.py`, `tests/integration/test_approval_queue_postgres.py`, `tests/integration/test_validator_compliance_postgres.py` |
| 2 W9-10 | dedup-prod live-Postgres, kill-switch <5s SLA, SQLi field-validation, recon-assets emit | `tests/integration/test_dedup_postgres.py`, `tests/integration/test_dedup_recall_phase3.py`, kill-switch SLA test, SQLi harness |
| 3 (in-flight) | EV calibration via `hunt_outcome` reconcile + `calibration_service` | `control-plane/tests/test_calibration_service.py`, `tests/integration/test_migration_07_phase3.py` |

## CI

GitHub Actions workflows live under `.github/workflows/`. The `r2-smoke` workflow (commit `b8c9e1e` pinning `setup-uv@v8.1.0`) exercises the live R2 round-trip for evidence storage.

CI matrix expectations:

- `ruff check .`
- `pyright` (per `pyrightconfig.json`)
- `pytest` per workspace package
- selected `tests/integration/` against an ephemeral Postgres service container
- field-validation harnesses for the oracles whose labs are CI-runnable

## Coverage Targets

Project-wide preference (from `~/.claude/rules/ecc/python/testing.md`): **80% minimum**. Use:

```bash
uv run --package control-plane pytest --cov=control_plane --cov-report=term-missing control-plane/tests/
```

For oracles, the gate is TPR/FPR on the field-validation fixture, not line coverage — the JSON report under `mcp/oracle-mcp/tests/reports/` is the source of truth.

## Anti-Patterns

| Anti-pattern | Why wrong | Do instead |
|---|---|---|
| Mock the DB to "speed up tests" | Past regression (T3 distinct-actor) was hidden by mocked DB | Use real Postgres via integration suite |
| Add an oracle without a TPR/FPR fixture | No verifiable accuracy claim | Follow Phase 1.1c/1.1d / W7-8 pattern (4-piece scaffold in code-standards) |
| Hit a real platform API in CI | Rate limits + flakes | `respx` mocks + recorded fixtures |
| Commit a test RSA key | Exposed secret | Generate ephemeral in fixtures |
| `print()` from a test | Pollutes pytest output | Assert structured behaviour; use `caplog` for logger inspection |
| Skip a flaky test | Flakes hide real bugs | Quarantine + repro fixture, then fix |
| `--no-verify` to commit failing tests | Bypasses hooks/CI | Fix the failure |

## See Also

- [`code-standards.md`](../code-standards.md) §Test Conventions — full style rules
- [`code-standards.md`](../code-standards.md) §Field-Validation Suite Pattern — 4-piece scaffold for new oracles
- [`phase1_signoff.md`](../signoffs/phase1_signoff.md) — fixture pattern origin
- [`research/03-verifier-antislop.md`](../research/03-verifier-antislop.md) §SLOs — accuracy targets
