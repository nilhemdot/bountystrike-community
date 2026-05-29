# QUICK_START.md — BountyStrike v5

## Essential Commands

```bash
# Lint & format
uv run ruff check .
uv run ruff format .

# Type check (control-plane only)
cd control-plane && uv run mypy src/

# Unit tests
uv run pytest tests/

# Integration tests (requires: Postgres, Redis, R2)
uv run pytest tests/integration/ -m integration

# Oracle field-validation
uv run pytest scripts/run_xss_field_validation.py
uv run pytest scripts/run_sqli_field_validation.py
uv run pytest scripts/run_ssrf_field_validation.py
uv run pytest scripts/run_ssrf_imds_field_validation.py
uv run pytest scripts/run_idor_field_validation.py
uv run pytest scripts/run_rce_field_validation.py
uv run pytest scripts/run_ssti_field_validation.py
uv run pytest scripts/run_open_redirect_field_validation.py

# Infrastructure
docker compose -f infra/docker-compose.yml up -d      # start all services
docker compose -f infra/docker-compose.yml down        # stop
docker compose -f infra/docker-compose.yml logs -f     # tail logs

# Scope JWT
python scripts/gen_scope_jwt.py                        # issue JWT for a program

# Run a hunt
python scripts/orchestrator.py

# Approve a finding (T3 manual review)
python scripts/approve.py <finding_id>

# Health check
bash scripts/health_check.sh

# Cost report
python scripts/cost_audit.py
```

## Adding a New MCP Server (Python)

1. Create `mcp/<name>-mcp/` with `pyproject.toml` + `src/<name>_mcp/server.py`
2. Add to `pyproject.toml` workspace members
3. Register FastMCP tools with Pydantic input/output models
4. Write field-validation suite if it's an oracle
5. Run `uv sync` from root

## Adding a New Agent

1. Create `.claude/agents/<name>.md` following existing spec format
2. Declare MCP tool dependencies in the spec
3. Wire scope-guard and kill-switch hooks

## Common Workflows

**Debug a failing integration test:**
```bash
docker compose -f infra/docker-compose.yml up -d
uv run pytest tests/integration/test_<name>.py -v -s
```

**Check dedup fingerprint collisions:**
```bash
uv run pytest tests/integration/test_dedup_postgres.py -v
```

**Schema contract check:**
```bash
bash scripts/run-schema-contract-test.sh
```
