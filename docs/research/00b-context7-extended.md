# 00b — Context7 Extended Docs (Phase 1+ Libraries)

10 additional libraries pulled. For Phase 1+ build reference.

## Library IDs Resolved (extended)

| Lib | Context7 ID | Snippets | Usage |
|---|---|---|---|
| LangGraph | `/websites/langchain_oss_python_langgraph` | 733 | T2/T3 approval gates |
| Temporal Python | `/websites/python_temporal_io` | 7783 | SaaS migration |
| PydanticAI | `/pydantic/pydantic-stack-demo` | 80 | Multi-agent typed framework |
| Playwright Python | `/websites/playwright_dev_python` | 1991 | XSS DOM oracle |
| Anthropic SDK Python | `/anthropics/anthropic-sdk-python` | 186 | Direct Claude API |
| httpx | `/encode/httpx` | 208 | Async HTTP everywhere |
| SQLAlchemy 2.0 | `/websites/sqlalchemy_en_20` | 19338 | Postgres async ORM |
| OpenRouter | `/websites/openrouter_ai` | 3340 | Multi-model routing |
| pgvectorscale | `/timescale/pgvectorscale` | 36 | DiskANN at scale |
| Firecracker | `/firecracker-microvm/firecracker` | 1162 | SaaS sandbox plane |

## LangGraph — Interrupt for T2/T3 Approval Gates

```python
from langgraph.types import interrupt, Command
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import StateGraph, START, END

def approval_node(state: ApprovalState) -> Command[Literal["proceed", "cancel"]]:
    decision = interrupt({
        "question": "Approve T3 submission?",
        "details": state["finding_details"],
    })
    return Command(goto="proceed" if decision else "cancel")

builder = StateGraph(ApprovalState)
builder.add_node("approval", approval_node)
# ...

checkpointer = SqliteSaver(sqlite3.connect("approval.db"))  # or PostgresSaver in prod
graph = builder.compile(checkpointer=checkpointer)

config = {"configurable": {"thread_id": "finding-123"}}
initial = graph.invoke({"finding_details": "..."}, config=config)
print(initial["__interrupt__"])  # surface to dashboard

# Resume after approval
graph.invoke(Command(resume=True), config=config)
```

**Key:** `checkpointer` mandatory for `interrupt()`; `thread_id` per finding; resume with `Command(resume=value)`.

## Temporal — Python Workflow Client

```python
from temporalio.client import Client

# Connect
client = await Client.connect("localhost:7233", namespace="bountystrike")

# Start workflow
handle = await client.start_workflow(
    ScanJobWorkflow.run,
    args=[ScanJobInput(...)],
    id="scan-job-123",
    task_queue="bountystrike-tasks",
    execution_timeout=timedelta(hours=4),
    retry_policy=RetryPolicy(maximum_attempts=3),
)

result = await handle.result()
```

**Hatchet → Temporal migration:** workflow decorators differ (`@app.workflow()` vs `@workflow.defn`), but task queue + activity model maps 1:1. Plan migration as Phase 4.

## PydanticAI — Typed Multi-Agent

```python
from dataclasses import dataclass
from httpx import AsyncClient
from pydantic_ai import Agent, RunContext

@dataclass
class Deps:
    client: AsyncClient

scanner_agent = Agent(
    'anthropic:claude-sonnet-4-6',
    instructions='Scan target; return findings.',
    deps_type=Deps,
    retries=2,
)

@scanner_agent.tool
async def fetch_target(ctx: RunContext[Deps], url: str) -> dict:
    r = await ctx.deps.client.get(url)
    r.raise_for_status()
    return r.json()

# Parallel agents
async with asyncio.TaskGroup() as tg:
    tasks = [tg.create_task(scanner_agent.run(t)) for t in targets]
results = [t.result().output for t in tasks]
```

**Memory persistence (asyncpg):** `ModelMessagesTypeAdapter.validate_json` to load history; `result.new_messages_json()` to store.

## Playwright Python — XSS Oracle

```python
import asyncio
from playwright.async_api import async_playwright

async with async_playwright() as p:
    browser = await p.chromium.launch(args=['--no-sandbox', '--disable-dev-shm-usage'])
    context = await browser.new_context()
    page = await context.new_page()

    dialog_fired = asyncio.Event()
    
    async def handle_dialog(dialog):
        dialog_fired.set()
        await dialog.dismiss()
    
    page.on("dialog", handle_dialog)
    
    await page.expose_function("__bsmutationObserver", lambda data: print(data))
    await page.add_init_script("""
        new MutationObserver(muts => window.__bsmutationObserver(JSON.stringify(muts)))
            .observe(document.body, {childList: true, subtree: true, characterData: true});
    """)
    
    await page.goto(target_url, timeout=15000, wait_until='networkidle')
    
    try:
        await asyncio.wait_for(dialog_fired.wait(), timeout=5.0)
    except asyncio.TimeoutError:
        pass
    
    await browser.close()
```

## Anthropic SDK — Async + Streaming

```python
import asyncio
from anthropic import AsyncAnthropic

client = AsyncAnthropic()

async with client.messages.stream(
    max_tokens=1024,
    messages=[{"role": "user", "content": "..."}],
    model="claude-sonnet-4-6",
    extra_headers={"anthropic-beta": "prompt-caching-2024-07-31,output-300k-2026-03-24"},
) as stream:
    async for text in stream.text_stream:
        print(text, end="", flush=True)
    final = await stream.get_final_message()
    print(f"Tokens: in={final.usage.input_tokens} out={final.usage.output_tokens}")
```

**Batch API (cheaper, async):**
```python
batch = client.messages.batches.create(requests=[
    {"custom_id": "req-1", "params": {...}},
    {"custom_id": "req-2", "params": {...}},
])
# Poll batch.processing_status until "ended"
for result in client.messages.batches.results(batch.id):
    print(result.custom_id, result.result)
```

## httpx — Async Client + Timeouts + Retries

```python
import httpx

# Fine-grained timeouts (production)
timeout = httpx.Timeout(10.0, connect=30.0, read=60.0, write=60.0, pool=10.0)

# Connection retries (transport-level)
transport = httpx.AsyncHTTPTransport(retries=2)

async with httpx.AsyncClient(
    timeout=timeout,
    transport=transport,
    follow_redirects=False,  # for open-redirect oracle: no follow
    limits=httpx.Limits(max_connections=100, max_keepalive_connections=20),
) as client:
    try:
        r = await client.get(url, headers={"User-Agent": "BountyStrike/v5"})
    except httpx.TimeoutException:
        ...
    except httpx.ConnectError:
        ...
```

## SQLAlchemy 2.0 — Async ORM with asyncpg + pgvector

```python
from sqlalchemy.ext.asyncio import create_async_engine, AsyncAttrs, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import select
from pgvector.sqlalchemy import Vector

engine = create_async_engine("postgresql+asyncpg://user:pwd@host/db", echo=False)
async_session = async_sessionmaker(engine, expire_on_commit=False)

class Base(AsyncAttrs, DeclarativeBase):
    pass

class Finding(Base):
    __tablename__ = "findings"
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str]
    embedding: Mapped[list[float]] = mapped_column(Vector(1536))

async with async_session() as session:
    # Vector similarity search
    query_vec = [0.1, 0.2, ...]  # 1536-dim
    stmt = select(Finding).order_by(Finding.embedding.cosine_distance(query_vec)).limit(10)
    result = await session.scalars(stmt)
    for f in result:
        print(f.title)
```

## OpenRouter — Provider Routing + Fallback + JSON Schema

```python
import requests

response = requests.post(
    "https://openrouter.ai/api/v1/chat/completions",
    headers={
        "Authorization": f"Bearer {OPENROUTER_KEY}",
        "Content-Type": "application/json",
        "X-OpenRouter-Provider-Key": ANTHROPIC_KEY,  # BYOK
    },
    json={
        "model": "anthropic/claude-sonnet-4-6",
        "models": ["anthropic/claude-sonnet-4-6", "openai/gpt-5.4", "deepseek/deepseek-v4-flash"],
        "provider": {
            "order": ["Anthropic", "Amazon Bedrock"],
            "allow_fallbacks": True,
            "data_collection": "deny",
            "require_parameters": True,
        },
        "messages": [{"role": "user", "content": "..."}],
        "response_format": {
            "type": "json_schema",
            "json_schema": {"name": "Finding", "schema": {...}}
        },
        "plugins": [{"id": "response-healing"}],
    }
)
```

**:nitro suffix** — append `:nitro` to model id for throughput priority (validation oracle only). **partition: 'none'** in provider sort → maximize BYOK across fallback chain.

## pgvectorscale — DiskANN Index

```sql
CREATE EXTENSION IF NOT EXISTS vectorscale CASCADE;

CREATE TABLE documents (
    id SERIAL PRIMARY KEY,
    embedding VECTOR(1536),
    labels SMALLINT[],  -- for filtered search
    status TEXT,
    created_at TIMESTAMPTZ
);

-- Plain DiskANN
CREATE INDEX document_embedding_idx ON documents
USING diskann (embedding vector_cosine_ops);

-- Filtered DiskANN (label-aware)
CREATE INDEX ON documents USING diskann (embedding vector_cosine_ops, labels);

-- Filtered query
SELECT * FROM documents
WHERE labels && ARRAY[1, 3]  -- label 1 OR 3
ORDER BY embedding <=> '[...]'
LIMIT 10;
```

**Trade-off vs HNSW:** DiskANN higher build cost, lower memory, sub-10ms p99 at 10M+ vectors. Solo (<500K) → HNSW. SaaS → DiskANN.

## Firecracker — TAP + Network + Egress (host kernel)

```bash
# Setup TAP device (host-side; guest cannot modify)
sudo ip tuntap add dev tap0 mode tap
sudo ip addr add 172.16.0.1/30 dev tap0
sudo ip link set dev tap0 up

# Enable forwarding
sudo sh -c "echo 1 > /proc/sys/net/ipv4/ip_forward"

# Scope JWT egress filter — read JWT.targets.ips, materialize iptables
sudo iptables -P FORWARD DROP  # default deny
for ip in $(jq -r '.targets.ips[]' < scope.jwt.json); do
    sudo iptables -A FORWARD -i tap0 -d "$ip" -j ACCEPT
done
sudo iptables -A FORWARD -i tap0 -d "$INTERACTSH_IP" -j ACCEPT  # OAST allowed
sudo iptables -t nat -A POSTROUTING -o "$HOST_IFACE" -j MASQUERADE

# Configure VM via API socket
curl --unix-socket /tmp/firecracker.socket -X PUT \
    -H 'Content-Type: application/json' \
    -d '{
        "iface_id": "eth0",
        "guest_mac": "06:00:AC:10:00:02",
        "host_dev_name": "tap0"
    }' \
    http://localhost/network-interfaces/eth0

# Boot source + rootfs + start
curl --unix-socket /tmp/firecracker.socket -X PUT \
    -d '{"kernel_image_path": "./vmlinux", "boot_args": "console=ttyS0 reboot=k panic=1"}' \
    http://localhost/boot-source

curl --unix-socket /tmp/firecracker.socket -X PUT \
    -d '{"drive_id": "rootfs", "path_on_host": "./rootfs.ext4", "is_root_device": true, "is_read_only": true}' \
    http://localhost/drives/rootfs

curl --unix-socket /tmp/firecracker.socket -X PUT \
    -d '{"action_type": "InstanceStart"}' \
    http://localhost/actions
```

**Critical:** iptables rules live on **host kernel**, not guest. Guest has no path to modify them — prompt injection inside VM cannot bypass scope.

**Rate limiting via PATCH /network-interfaces/{iface_id}:**
```json
{
  "rx_rate_limiter": {"bandwidth": {"size": 10485760, "refill_time": 1000}},
  "tx_rate_limiter": {"bandwidth": {"size": 10485760, "refill_time": 1000}}
}
```
