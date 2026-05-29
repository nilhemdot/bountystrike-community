# COMMON_MISTAKES.md — BountyStrike v5

## 1. Blocking calls inside async functions (ASYNC rule — ruff will catch)

```python
# WRONG
async def fetch(url: str) -> bytes:
    return requests.get(url).content  # blocks event loop

# CORRECT
async def fetch(url: str) -> bytes:
    async with httpx.AsyncClient() as client:
        r = await client.get(url)
        return r.content
```

## 2. Missing workspace registration for new MCP servers

New Python MCP packages must be added to `pyproject.toml` `[tool.uv.workspace] members`. If omitted, `uv sync` from root won't install them. 9 existing MCPs currently not registered (h1-mcp, bugcrowd-mcp, intigriti-mcp, yeswehack-mcp, immunefi-mcp, state-mcp, sandbox-mcp, normalize-mcp, politeness-mcp).

## 3. Raw dicts at input boundaries instead of Pydantic models

```python
# WRONG
async def handle_tool(args: dict) -> dict: ...

# CORRECT
class FindingInput(BaseModel):
    target: str
    severity: Literal["critical", "high", "medium", "low"]

async def handle_tool(args: FindingInput) -> FindingOutput: ...
```

## 4. Editing files blind (without reading first)

Never modify a file without reading it first. The codebase has subtle DDD layering — editing infrastructure code from memory will break domain boundaries.

## 5. Wiring oracles to agents before field-validation passes

Oracles must hit TPR=1.0 / FPR=0.0 on the field-validation suite before being enabled in agent specs. Run: `uv run pytest scripts/run_<oracle>_field_validation.py`

## 6. Committing .env or keys/

`.gitignore` excludes `.env` and `keys/` — never force-add them. Rotate any exposed keys immediately.

## 7. Using synchronous SQLAlchemy instead of async

Use SQLAlchemy 2.0 async sessions (`AsyncSession`) everywhere in control-plane. The infrastructure layer (`control-plane/src/control_plane/infrastructure/database.py`) wires this up.

## 8. Skipping `@pytest.mark.integration` on tests that need live services

Tests in `tests/integration/` that hit Postgres/Redis/R2 must be marked. Unmarked integration tests break CI when services are absent.
