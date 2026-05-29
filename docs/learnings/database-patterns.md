# database-patterns.md — Database Patterns

## Phase 1 — Extension Traps

Hard-won, verified 2026-05-29 (plan 01-01). Read before touching Postgres
extensions, the custom image, or vector/BM25 indexes.

1. **`CREATE EXTENSION vectorscale` — NOT `pgvectorscale`.** The pgvectorscale
   package registers its extension under the name `vectorscale`; using
   `pgvectorscale` in a `CREATE EXTENSION` statement raises "extension not
   found". Source: CLAUDE.md trap #17, timescale/pgvectorscale README. Use
   `CREATE EXTENSION IF NOT EXISTS vectorscale CASCADE;` (CASCADE pulls in vector).

2. **ParadeDB dropped pgvectorscale from its bundle.** `paradedb/paradedb:pg17`
   no longer ships vectorscale, and `pgvector/pgvector:pg17` ships neither
   vectorscale nor pg_search. A custom image (`infra/docker/Dockerfile.postgres-bs`)
   is required to get all three (vector + vectorscale + pg_search) in one PG17
   server. Do NOT use the ParadeDB published image as the postgres base.

3. **Image build order.** `docker compose build postgres` (or a direct
   `docker build -f Dockerfile.postgres-bs`) must run before `docker compose up`.
   Any CI/CD pipeline must build + push `bs-postgres:pg17` to a registry before
   deploy — the image is not on Docker Hub.

4. **boto3 / R2 (for 01-02 evidence store).** When wiring evidence artifacts to
   Cloudflare R2, use `aioboto3` (async) and pin `boto3 < 1.36` OR set
   `request_checksum_calculation="when_required"` on the session config. boto3
   1.36.0 introduced a checksum change R2 does not support. Handled in 01-02;
   documented here for cross-reference.

5. **DiskANN index — plain `CREATE INDEX IF NOT EXISTS`, never `CONCURRENTLY`
   in init scripts.** vectorscale's DiskANN is the upgrade path from pgvector
   HNSW at >500K vectors; the HNSW index on `findings.embedding` stays primary
   until then and the DiskANN index coexists. First-boot init scripts
   (`/docker-entrypoint-initdb.d`) run in a single-tx path where CONCURRENTLY
   errors; worse, an interrupted CONCURRENTLY build leaves an INVALID index that
   a later `IF NOT EXISTS` silently skips, masking the failure permanently.
   (audit G6)

6. **ParadeDB pg_search BM25 — `CREATE INDEX ... USING bm25`, NOT the deprecated
   `paradedb.create_bm25()` function API.** ParadeDB maintainers: "Avoid using
   legacy docs as syntax has changed dramatically." Current form:
   `CREATE INDEX <name> ON <tbl> USING bm25 (<cols>) WITH (key_field='id')`.
   `key_field` MUST be the table's primary key. Latest release v0.23.5. (audit G2)

7. **`pg_search` REQUIRES `shared_preload_libraries = 'pg_search'`.** The BM25
   index access method and background worker need the shared library loaded at
   server start. Set via the postgres `command:` flags in docker-compose
   (`-c shared_preload_libraries=pg_search`). Without it, `CREATE EXTENSION
   pg_search` / BM25 index creation fail. Source: Context7 /paradedb/paradedb
   §self-hosted/extension.

8. **`findings` has NO `title`/`description` columns** (schema frozen). The BM25
   index must index existing text columns: `id, url, parameter, cwe,
   oracle_method`. Verify against `01_schema.sql` before assuming rich-text
   columns exist. (audit G1)

9. **Pin every extension + base image.** pgvector v0.8.0, pgvectorscale 0.9.0,
   pg_search v0.23.5, base to a fixed major+distro tag (never `:latest` / moving
   major). Building pgvectorscale needs the `cargo-pgrx` version that MATCHES the
   crate's pinned `pgrx` (`cargo install --locked cargo-pgrx --version <match>`,
   resolved via `cargo metadata`) plus `cargo pgrx init --pg17` before `cargo
   pgrx install`. Alpine/musl is NOT a documented upstream build target — the
   custom image uses the glibc `postgres:17-bookworm` base. (audit G3/G5)

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
