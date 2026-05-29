# 00 — Context7 Doc Snippets (Phase 0 Critical Libraries)

Pulled by parent agent. For Phase 0 use. Re-query for deeper API surface as needed.

## Library IDs Resolved

| Lib | Context7 ID | Snippets | Purpose |
|---|---|---|---|
| Hatchet | `/hatchet-dev/hatchet` | 1867 | Workflow orchestration |
| Claude Agent SDK (Python) | `/anthropics/claude-agent-sdk-python` | 94 | Agent runtime + hooks |
| MCP | `/modelcontextprotocol/modelcontextprotocol` | 1375 | Server scaffolding TS+Py |
| uv | `/astral-sh/uv` | 912 | Python pkg + workspace |
| Pydantic | `/pydantic/pydantic` | 755 | Typed message contracts |
| PyJWT | `/jpadilla/pyjwt` | 145 | RS256 sign/verify |
| pgvector | `/pgvector/pgvector` | 93 | Vector search Postgres |
| FastAPI | `/fastapi/fastapi` | 956 | Async REST + SSE |

## Hatchet — Python Workflow

```python
from hatchet_sdk import Hatchet, Context
from pydantic import BaseModel

hatchet = Hatchet()

class MyInput(BaseModel):
    name: str

workflow = hatchet.workflow("my-workflow", input_type=MyInput)

@workflow.task()
def greet(input, ctx):
    return f"Hello, {input.name}!"

# Sync run
result = workflow.run(MyInput(name="World"))

# Async run
result = await hatchet.workflows.get("my-workflow").aio_run(input=MyInput(name="World"))
```

**Multi-task with parents:**
```python
simple = hatchet.workflow(name="SimpleWorkflow")

@simple.task()
def task_1(input: EmptyModel, ctx: Context) -> dict[str, str]:
    return {"result": "task_1"}

@simple.task(parents=[task_1])
def task_2(input: EmptyModel, ctx: Context) -> None:
    first_result = ctx.task_output(task_1)
    print(first_result)
```

**Fanout (parent → child workflows):**
```python
@app.workflow()
def fanout_parent():
    child_wf = fanout_child()
    child_wf.create_workflow_run_config(input=ChildInput(value="hello"))

@app.workflow()
def fanout_child():
    pass
```

## Claude Agent SDK — Hooks Configuration

```python
import asyncio
from claude_agent_sdk import (
    ClaudeSDKClient, ClaudeAgentOptions,
    AssistantMessage, TextBlock,
)
from claude_agent_sdk.types import HookContext, HookInput, HookJSONOutput, HookMatcher

async def security_check_hook(input_data: HookInput, tool_use_id: str | None, context: HookContext) -> HookJSONOutput:
    tool_name = input_data["tool_name"]
    tool_input = input_data["tool_input"]
    if tool_name == "Bash":
        cmd = tool_input.get("command", "")
        for pattern in ["rm -rf", "sudo", "chmod 777"]:
            if pattern in cmd:
                return {
                    "hookSpecificOutput": {
                        "hookEventName": "PreToolUse",
                        "permissionDecision": "deny",
                        "permissionDecisionReason": f"Blocked: {pattern}",
                    }
                }
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "allow"}}

options = ClaudeAgentOptions(
    allowed_tools=["Bash", "Write", "Read"],
    hooks={
        "PreToolUse": [HookMatcher(matcher="Bash|Write", hooks=[security_check_hook])],
        "PostToolUse": [HookMatcher(matcher=None, hooks=[audit_tool_output])],
    }
)

async with ClaudeSDKClient(options=options) as client:
    await client.query("...")
    async for msg in client.receive_response():
        if isinstance(msg, AssistantMessage):
            for block in msg.content:
                if isinstance(block, TextBlock):
                    print(block.text)
```

**Full ClaudeAgentOptions surface:** `tools`, `allowed_tools`, `disallowed_tools`, `system_prompt`, `model`, `fallback_model`, `session_id`, `resume`, `fork_session`, `continue_conversation`, `max_turns`, `max_budget_usd`, `permission_mode` (`default|acceptEdits|plan|bypassPermissions|dontAsk|auto`), `can_use_tool` callback, `thinking`, `effort` (`low|medium|high|max`), `mcp_servers`, `hooks`, `agents` (subagents), `cwd`, `add_dirs`, `cli_path`, `settings`, `setting_sources` (`user|project|local`), `env`, `include_partial_messages`, `sandbox` (`SandboxSettings(enabled, autoAllowBashIfSandboxed, excludedCommands)`), `betas`, `enable_file_checkpointing`, `output_format`, `task_budget`, `extra_args`.

## MCP — TypeScript Server (stdio)

```typescript
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { z } from "zod";

const server = new McpServer({
  name: "scope-mcp",
  version: "1.0.0",
});

// Register tool example
server.tool(
  "check_target",
  "Check if target is in scope",
  { target: z.string() },
  async ({ target }) => {
    return { content: [{ type: "text", text: `Target ${target} status: ...` }] };
  }
);

async function main() {
  const transport = new StdioServerTransport();
  await server.connect(transport);
  console.error("scope-mcp running on stdio");
}

main().catch(console.error);
```

## MCP — Python FastMCP

```python
from typing import Any
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("oracle")

@mcp.tool()
async def oracle_xss(url: str, payload: str) -> str:
    """Verify XSS via Playwright DOM execution.

    Args:
        url: Target URL
        payload: XSS payload to test
    """
    # ...
    return result

def main():
    mcp.run(transport="stdio")

if __name__ == "__main__":
    main()
```

## uv — Monorepo Workspace

**Init project:**
```bash
uv init bountystrike-v5
cd bountystrike-v5
```

**Workspace pyproject.toml (root):**
```toml
[project]
name = "bountystrike-v5"
version = "0.1.0"
requires-python = ">=3.12"

[tool.uv.workspace]
members = ["packages/*", "control-plane", "mcp/oracle-mcp", "mcp/evidence-mcp", "mcp/dedup-mcp"]
```

**Workspace member with internal dep:**
```toml
[project]
name = "control-plane"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = ["evidence-mcp", "fastapi", "pydantic>=2", "asyncpg"]

[tool.uv.sources]
evidence-mcp = { workspace = true }

[build-system]
requires = ["uv_build>=0.11.8,<0.12"]
build-backend = "uv_build"
```

## Pydantic v2 — Discriminated Unions (for FindingCandidate variants)

```python
from typing import Literal
from pydantic import BaseModel, Field

class XssFinding(BaseModel):
    cwe: Literal['CWE-79'] = 'CWE-79'
    payload: str

class SqliFinding(BaseModel):
    cwe: Literal['CWE-89'] = 'CWE-89'
    parameter: str

class Finding(BaseModel):
    detail: XssFinding | SqliFinding = Field(discriminator='cwe')
```

**JSON schema generation:**
```python
schema = MyModel.model_json_schema()  # or mode='validation'/'serialization'
```

## PyJWT — RS256 Sign/Verify

```python
import jwt

# Encode
encoded = jwt.encode({"some": "payload"}, private_key, algorithm="RS256")

# Decode + validate
payload = jwt.decode(token, public_key, algorithms=["RS256"])

# With required claims + audience + issuer + leeway
payload = jwt.decode(
    token, public_key,
    algorithms=["RS256"],
    audience="bountystrike",
    issuer="bountystrike-control-plane",
    leeway=5,
    options={"require": ["exp", "iss", "sub", "jti"]}
)

# Errors
# jwt.ExpiredSignatureError, jwt.InvalidAudienceError, jwt.InvalidIssuerError,
# jwt.InvalidSignatureError, jwt.DecodeError
```

**Passphrase-protected key:**
```python
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.backends import default_backend

private_key = serialization.load_pem_private_key(
    pem_bytes, password=passphrase, backend=default_backend()
)
encoded = jwt.encode({"some": "payload"}, private_key, algorithm="RS256")
```

**Install:** `pip install pyjwt[crypto]`

## pgvector — Setup + HNSW

**Enable:**
```sql
CREATE EXTENSION vector;
```

**Schema (1536-dim for text-embedding-3-large):**
```sql
CREATE TABLE findings (
  id bigserial PRIMARY KEY,
  content text,
  embedding vector(1536)
);
```

**HNSW indexes:**
```sql
-- Cosine (used in plan: 1 - (a <=> b) > 0.85)
CREATE INDEX ON findings USING hnsw (embedding vector_cosine_ops);

-- L2
CREATE INDEX ON findings USING hnsw (embedding vector_l2_ops);

-- Custom params
CREATE INDEX ON findings USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64);

-- Concurrent (no write block)
CREATE INDEX CONCURRENTLY ON findings USING hnsw (embedding vector_cosine_ops);
```

**Query nearest neighbors:**
```sql
SELECT id, 1 - (embedding <=> '[0.1,0.2,...]'::vector) AS similarity
FROM findings
ORDER BY embedding <=> '[0.1,0.2,...]'::vector
LIMIT 10;
```

## FastAPI — Lifespan + SSE

**Lifespan:**
```python
from contextlib import asynccontextmanager
from fastapi import FastAPI

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: connect DB pool, load embeddings
    yield
    # Shutdown: close pools

app = FastAPI(lifespan=lifespan)
```

**SSE streaming:**
```python
from typing import AsyncIterable
from fastapi.sse import EventSourceResponse
from pydantic import BaseModel

class Update(BaseModel):
    finding_id: str
    status: str

@app.get("/stream", response_class=EventSourceResponse)
async def stream() -> AsyncIterable[Update]:
    async for evt in agent_stream():
        yield evt
```
