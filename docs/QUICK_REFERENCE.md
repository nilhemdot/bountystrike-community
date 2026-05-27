# QUICK_REFERENCE.md — BountyStrike v5

## Session Start Checklist

- [ ] Load CLAUDE.md
- [ ] Load .claude/COMMON_MISTAKES.md
- [ ] Load .claude/QUICK_START.md
- [ ] Load .claude/ARCHITECTURE_MAP.md
- [ ] Load task-specific doc from docs/INDEX.md

## Common Commands (copy-paste)

```bash
uv run ruff check . && uv run ruff format .
uv run pytest tests/
uv run pytest tests/integration/ -m integration
docker compose -f infra/docker-compose.yml up -d
python scripts/orchestrator.py
python scripts/health_check.sh
```

## Key Code Patterns

**FastMCP tool (Python):**
```python
from fastmcp import FastMCP
from pydantic import BaseModel

mcp = FastMCP("my-server")

class MyInput(BaseModel):
    target: str

class MyOutput(BaseModel):
    result: str

@mcp.tool()
async def my_tool(args: MyInput) -> MyOutput:
    ...
```

**Async DB query (control-plane):**
```python
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

async def get_finding(session: AsyncSession, finding_id: UUID) -> Finding | None:
    result = await session.execute(select(Finding).where(Finding.id == finding_id))
    return result.scalar_one_or_none()
```

**Integration test skeleton:**
```python
import pytest

@pytest.mark.integration
async def test_something_live():
    # arrange — real Postgres/Redis
    # act
    # assert
```

## Debugging Quick Tips

| Symptom | Check |
|---------|-------|
| Hunt hangs | Redis kill-switch flag (`KILL_SWITCH` key) |
| Oracle false positives | Run field-validation suite |
| Dedup collisions | `tests/integration/test_dedup_postgres.py` |
| MCP not found | Check workspace registration in pyproject.toml |
| JWT rejected | `keys/` dir exists, RS256 keypair present |
| Async error | Look for blocking calls (requests, open, time.sleep) |

## File Locations Quick Reference

| What | Where |
|------|-------|
| Finding state machine | `mcp/state-mcp/` |
| Oracle verifiers | `mcp/oracle-mcp/src/oracle_mcp/verifiers/` |
| Agent specs | `.claude/agents/` |
| PreToolUse hooks | `.claude/hooks/` |
| SQL migrations | `infra/migrations/` |
| Scope JWT logic | `mcp/scope-mcp/` (TypeScript) |
| Hunt driver | `scripts/orchestrator.py` |
| Approval flow | `scripts/approve.py` + `control-plane/domains/approval_gate/` |
