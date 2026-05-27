# mcp-patterns.md — MCP Server Patterns

## FastMCP Server Template (Python)

```python
from fastmcp import FastMCP
from pydantic import BaseModel

mcp = FastMCP("server-name")

class ToolInput(BaseModel):
    param: str

class ToolOutput(BaseModel):
    result: str
    success: bool

@mcp.tool()
async def tool_name(args: ToolInput) -> ToolOutput:
    # async only — no blocking calls
    ...

if __name__ == "__main__":
    mcp.run()
```

## Workspace Registration

Every new Python MCP must be added to root `pyproject.toml`:
```toml
[tool.uv.workspace]
members = [
    ...
    "mcp/new-mcp",
]
```

Then `uv sync` from root.

## Platform MCP Pattern (h1, bugcrowd, etc.)

- Tool: `submit_report(finding: FindingInput) -> SubmissionResult`
- Tool: `get_program_scope(program_slug: str) -> ScopeConfig`
- Auth via env vars, validated at startup with `pydantic-settings`
- Rate limiting: call politeness-mcp token bucket before every API call

## Politeness Pattern

```python
# Before any outbound HTTP call in an agent context:
await mcp_call("politeness-mcp", "check_token", {"domain": target_domain})
```

## Error Propagation

Return structured errors in `ToolOutput`, never raise unhandled exceptions:
```python
class ToolOutput(BaseModel):
    result: str | None
    success: bool
    error: str | None = None
```

## scope-mcp (TypeScript)

Located at `mcp/scope-mcp/`. Validates RS256 scope JWTs. Do not modify unless changing JWT claims schema — coordinate with `control-plane/core/security/`.
