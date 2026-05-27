# database-patterns.md — Database Patterns

## SQLAlchemy 2.0 Async (control-plane)

```python
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy import select, update

# Session factory (wired in infrastructure/database.py)
engine = create_async_engine(DATABASE_URL, echo=False)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)

# Usage
async def get_finding(session: AsyncSession, finding_id: UUID) -> Finding | None:
    result = await session.execute(
        select(Finding).where(Finding.id == finding_id)
    )
    return result.scalar_one_or_none()
```

## Direct asyncpg (MCP servers)

For MCP servers not in control-plane, use asyncpg directly:
```python
import asyncpg

async def get_conn() -> asyncpg.Connection:
    return await asyncpg.connect(dsn=DATABASE_URL)
```

## Migration Pattern

SQL migrations live in `infra/migrations/`. Naming: `NN_description.sql`.
Apply in order. Current migrations: 01-05. Next is 06.

## pgvector (dedup-mcp)

```python
# Similarity search
await conn.fetch(
    "SELECT id FROM dedup_fingerprints ORDER BY embedding <-> $1 LIMIT 5",
    embedding_vector
)
```

Requires `pgvector` extension. Already enabled in Postgres init.

## Key Tables

| Table | Owner | Notes |
|-------|-------|-------|
| findings | state-mcp | Status state machine |
| findings_raw_finding | state-mcp | JSONB raw scan output |
| dedup_fingerprints | dedup-mcp | pgvector embeddings |
| evidence | evidence-mcp | R2/local blob references |
| approval_queue | control-plane | T3 review workflow |
| ev_scores | ev-mcp | Expected value per program |

## Never

- Never use synchronous SQLAlchemy in async context
- Never raw string interpolation in SQL — always parameterized
- Never skip migrations — apply in sequence
