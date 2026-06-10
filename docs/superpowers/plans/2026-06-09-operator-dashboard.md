# Operator Dashboard v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Multi-user web operator console: hunt monitoring, T2/T3 approval action center, kill-switch — BFF inside control-plane + React SPA served by Caddy.

**Architecture:** New `dashboard` domain in control-plane wraps existing `approval_gate.queue` functions and `safety.KillSwitchStore`; a NEW FastAPI app entry (`control_plane.main:app`, none exists today) exposes `/api/dashboard/*`; React SPA (`dashboard/`, new top-level dir) polls REST + one SSE stream. Spec: `docs/superpowers/specs/2026-06-09-dashboard-design.md`.

**Tech Stack:** FastAPI ≥0.115 + uvicorn (already in `control-plane/pyproject.toml`), asyncpg, argon2-cffi (NEW), sse-starlette (NEW), Vite + React 18 + TS + Tailwind + shadcn/ui + TanStack Query/Router.

**Verified ground truth (2026-06-09 — do NOT rediscover):**
- No FastAPI app exists anywhere in control-plane. Caddy already proxies `/api/*` → `host.docker.internal:8000`.
- `queue_approve(conn, finding_id: uuid.UUID, approver_id: str, reason: str = "") -> uuid.UUID | None` — returns `None` when T3 awaits a second distinct approver; raises `ApprovalQueueError` (missing/terminal/expired/same-actor-T3) and `ValueError` (empty approver). `queue_reject(conn, finding_id, approver_id, reason)` — reason must be non-empty, raises `ApprovalQueueError` if no pending row. `queue_list_pending(conn, tier=None) -> list[QueueEntry]`. All importable from `control_plane.domains.approval_gate`.
- `QueueEntry` fields: `finding_id, tier (ApprovalTier), poc_text, status, token, requested_at, approved_at, approver_id, approver_id_2, reason, expires_at`.
- `KillSwitchState` (StrEnum, `control_plane.domains.safety`): `inactive | halt_submissions | halt_scans | halt_all`. Store protocol: `get_state() / set_state(state, ttl_seconds) / clear()`. Composition root: `make_kill_switch_store(env)` in `control_plane.domains.safety.repositories.factory` (env: `KILL_SWITCH_BACKEND=redis|memory`, `REDIS_HOST/PORT/PASSWORD/DB`, `KILL_SWITCH_KEY`).
- `audit_log` (migration 03) is per-finding hash-chained: `(id UUID, finding_id UUID NOT NULL FK, entry_type, payload, prev_hash, chain_hash, created_at)`. It CANNOT take kill-switch rows (no finding) — that's why migration 14 adds `dashboard_audit_log`.
- `finding_status` enum values: hypothesis, exploit_attempt, exploit_candidate, exploit_pending_validation (06), validation_pending, validated, dedup_check, approval_pending_t1/t2/t3, approved, submitted, confirmed, rejected, duplicate, wont_fix, archived, exploit_failed_oos/timeout/crash (13).
- DSN: `control_plane.infrastructure.database.get_database_url()` returns SQLAlchemy-style URL; asyncpg needs `.replace("+asyncpg", "")` (pattern used by `scripts/approve.py`).
- Existing SQL migrations 00–13; idempotent style with `IF NOT EXISTS` / `DO $$ ... EXCEPTION WHEN duplicate_object` blocks. SPDX header `-- SPDX-License-Identifier: AGPL-3.0-or-later` not used in .sql files; Python files start with `# SPDX-License-Identifier: AGPL-3.0-or-later`.
- Tests: backend unit in `control-plane/tests/` (pytest-asyncio, `asyncio_mode = "auto"` — NO `@pytest.mark.asyncio` decorators needed), integration in `tests/integration/` marked `@pytest.mark.integration`.
- Lint: `uv run ruff check .` — line-length 100, py312, rules E F W I N UP B SIM ASYNC.
- Cookie deviation from spec: spec said `__Host-` prefix; that requires Secure which breaks plain-HTTP Caddy local deploys. Implemented as cookie name `bs_session`, HttpOnly + SameSite=Lax always, Secure when `DASHBOARD_COOKIE_SECURE=1` (default off for local). Documented here intentionally.

**File structure (locked):**

```
infra/sql/14_dashboard_auth.sql                                    users, sessions, dashboard_audit_log
control-plane/src/control_plane/main.py                            uvicorn entry: app = create_app()
control-plane/src/control_plane/core/http/__init__.py
control-plane/src/control_plane/core/http/app.py                   create_app(), lifespan (asyncpg pool, kill-switch store, event bus)
control-plane/src/control_plane/domains/dashboard/__init__.py
control-plane/src/control_plane/domains/dashboard/auth/__init__.py
control-plane/src/control_plane/domains/dashboard/auth/passwords.py argon2 hash/verify
control-plane/src/control_plane/domains/dashboard/auth/sessions.py  token gen + sha256, dataclasses
control-plane/src/control_plane/domains/dashboard/auth/store.py     AuthStore Protocol + Asyncpg + InMemory impls
control-plane/src/control_plane/domains/dashboard/auth/rate_limit.py LoginRateLimiter Protocol + memory + redis
control-plane/src/control_plane/domains/dashboard/audit.py          write_dashboard_audit(conn, actor, action, resource, payload)
control-plane/src/control_plane/domains/dashboard/events/__init__.py
control-plane/src/control_plane/domains/dashboard/events/bus.py     EventBus (per-client asyncio queues)
control-plane/src/control_plane/domains/dashboard/events/bridge.py  PollBridge (DB diff → bus) + pg LISTEN
control-plane/src/control_plane/domains/dashboard/http/__init__.py
control-plane/src/control_plane/domains/dashboard/http/schemas.py   ALL Pydantic response/request models
control-plane/src/control_plane/domains/dashboard/http/deps.py      get_conn, current_session, require_operator, CSRF
control-plane/src/control_plane/domains/dashboard/http/router_auth.py
control-plane/src/control_plane/domains/dashboard/http/router_read.py
control-plane/src/control_plane/domains/dashboard/http/router_actions.py
control-plane/src/control_plane/domains/dashboard/http/router_events.py
scripts/dashboard_user.py                                           user CRUD CLI
control-plane/tests/test_dashboard_passwords.py
control-plane/tests/test_dashboard_sessions.py
control-plane/tests/test_dashboard_auth_http.py
control-plane/tests/test_dashboard_read.py
control-plane/tests/test_dashboard_actions.py
control-plane/tests/test_dashboard_events.py
tests/integration/test_dashboard_e2e.py
dashboard/                                                          Vite React SPA (see Task 10)
infra/docker/Caddyfile                                              + static SPA route
infra/docker/docker-compose.yml                                     + control-plane command/ports, caddy volume
```

Dependency order: Tasks 1→8 backend (each commits independently), 9→13 frontend, 14 deployment. Task N+1 may assume Task N's code exists.

---

### Task 1: Migration 14 — dashboard auth tables

**Files:**
- Create: `infra/sql/14_dashboard_auth.sql`
- Test: `tests/integration/test_dashboard_schema.py`

- [ ] **Step 1: Write the migration**

```sql
-- Migration 14: dashboard auth — users, sessions, dashboard action audit.
--
-- Backs the operator dashboard (docs/superpowers/specs/2026-06-09-dashboard-design.md).
-- dashboard_audit_log is a SEPARATE simple audit table because audit_log
-- (migration 03) is per-finding hash-chained (finding_id NOT NULL) and
-- kill-switch mutations have no finding.
--
-- Idempotent: re-running is a no-op when the tables already exist.

CREATE TABLE IF NOT EXISTS dashboard_users (
    id            UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    username      TEXT         NOT NULL UNIQUE,
    password_hash TEXT         NOT NULL,                 -- argon2id PHC string
    role          TEXT         NOT NULL CHECK (role IN ('viewer', 'operator')),
    disabled      BOOLEAN      NOT NULL DEFAULT false,
    created_at    TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS dashboard_sessions (
    token_hash  TEXT         PRIMARY KEY,                -- sha256 hex of the bearer token
    user_id     UUID         NOT NULL REFERENCES dashboard_users(id) ON DELETE CASCADE,
    csrf_token  TEXT         NOT NULL,
    ip          TEXT,
    created_at  TIMESTAMPTZ  NOT NULL DEFAULT now(),
    expires_at  TIMESTAMPTZ  NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_dashboard_sessions_user
    ON dashboard_sessions (user_id);
CREATE INDEX IF NOT EXISTS idx_dashboard_sessions_expires
    ON dashboard_sessions (expires_at);

CREATE TABLE IF NOT EXISTS dashboard_audit_log (
    id        BIGSERIAL    PRIMARY KEY,
    ts        TIMESTAMPTZ  NOT NULL DEFAULT now(),
    actor     TEXT         NOT NULL,                     -- dashboard username
    action    TEXT         NOT NULL,                     -- e.g. approval.approve, killswitch.set
    resource  TEXT,                                      -- e.g. finding:<uuid>, killswitch
    payload   JSONB
);

CREATE INDEX IF NOT EXISTS idx_dashboard_audit_ts ON dashboard_audit_log (ts DESC);
CREATE INDEX IF NOT EXISTS idx_dashboard_audit_actor ON dashboard_audit_log (actor);
```

- [ ] **Step 2: Write the integration test**

`tests/integration/test_dashboard_schema.py`:

```python
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Migration 14 contract: dashboard auth tables exist with expected columns."""

import os

import asyncpg
import pytest

pytestmark = pytest.mark.integration


async def _columns(conn: asyncpg.Connection, table: str) -> set[str]:
    rows = await conn.fetch(
        "SELECT column_name FROM information_schema.columns WHERE table_name = $1",
        table,
    )
    return {r["column_name"] for r in rows}


async def test_migration_14_tables_exist():
    dsn = os.environ["DATABASE_URL"].replace("+asyncpg", "")
    conn = await asyncpg.connect(dsn)
    try:
        assert {"id", "username", "password_hash", "role", "disabled", "created_at"} <= (
            await _columns(conn, "dashboard_users")
        )
        assert {"token_hash", "user_id", "csrf_token", "ip", "expires_at"} <= (
            await _columns(conn, "dashboard_sessions")
        )
        assert {"id", "ts", "actor", "action", "resource", "payload"} <= (
            await _columns(conn, "dashboard_audit_log")
        )
    finally:
        await conn.close()


async def test_role_check_constraint_rejects_unknown_role():
    dsn = os.environ["DATABASE_URL"].replace("+asyncpg", "")
    conn = await asyncpg.connect(dsn)
    try:
        with pytest.raises(asyncpg.CheckViolationError):
            await conn.execute(
                "INSERT INTO dashboard_users (username, password_hash, role) "
                "VALUES ('x-bad-role', 'h', 'superadmin')"
            )
    finally:
        await conn.close()
```

- [ ] **Step 3: Apply migration to local stack and run the test**

Run (stack must be up: `docker compose -f infra/docker/docker-compose.yml up -d postgres`):

```bash
docker compose -f infra/docker/docker-compose.yml exec -T postgres \
  psql -U bountystrike -d bountystrike < infra/sql/14_dashboard_auth.sql
uv run pytest tests/integration/test_dashboard_schema.py -m integration -v
```

Expected: 2 passed. (If no live Postgres available in this session: run `uv run pytest tests/integration/test_dashboard_schema.py --collect-only` to prove collection, note the skip in the commit message, and let Task 14's live pass cover it.)

- [ ] **Step 4: Commit**

```bash
git add infra/sql/14_dashboard_auth.sql tests/integration/test_dashboard_schema.py
git commit -m "feat(dashboard): migration 14 — users, sessions, dashboard audit tables"
```

---

### Task 2: FastAPI app bootstrap (`create_app` + `main.py`)

**Files:**
- Create: `control-plane/src/control_plane/core/http/__init__.py`, `control-plane/src/control_plane/core/http/app.py`, `control-plane/src/control_plane/main.py`
- Test: `control-plane/tests/test_dashboard_app.py`

- [ ] **Step 1: Add new backend deps**

```bash
cd control-plane && uv add argon2-cffi sse-starlette && cd ..
uv sync --all-packages
```

- [ ] **Step 2: Write the failing test**

`control-plane/tests/test_dashboard_app.py`:

```python
# SPDX-License-Identifier: AGPL-3.0-or-later
"""App factory smoke: health route, no DB needed in test mode."""

import httpx

from control_plane.core.http.app import create_app


async def test_health_route_no_db():
    app = create_app(testing=True)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as client:
        resp = await client.get("/api/dashboard/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest control-plane/tests/test_dashboard_app.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'control_plane.core.http'`

- [ ] **Step 4: Implement app factory**

`control-plane/src/control_plane/core/http/__init__.py`:

```python
# SPDX-License-Identifier: AGPL-3.0-or-later
from .app import create_app

__all__ = ["create_app"]
```

`control-plane/src/control_plane/core/http/app.py`:

```python
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Control-plane HTTP application factory.

First HTTP surface for control-plane (Caddy already proxies /api/* here).
``testing=True`` skips the asyncpg pool / kill-switch store / event-bridge
startup so unit tests can run with dependency overrides and no live infra.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

import asyncpg
from fastapi import FastAPI

from control_plane.infrastructure.database import get_database_url


def _asyncpg_dsn() -> str:
    return get_database_url().replace("+asyncpg", "")


@asynccontextmanager
async def _lifespan(app: FastAPI):
    from control_plane.domains.dashboard.events.bridge import PollBridge
    from control_plane.domains.dashboard.events.bus import EventBus
    from control_plane.domains.safety.repositories.factory import make_kill_switch_store

    app.state.pool = await asyncpg.create_pool(_asyncpg_dsn(), min_size=1, max_size=5)
    app.state.kill_switch = make_kill_switch_store()
    app.state.event_bus = EventBus()
    app.state.bridge = PollBridge(pool=app.state.pool, bus=app.state.event_bus)
    await app.state.bridge.start()
    try:
        yield
    finally:
        await app.state.bridge.stop()
        await app.state.pool.close()


def create_app(*, testing: bool = False) -> FastAPI:
    app = FastAPI(
        title="BountyStrike control-plane",
        lifespan=None if testing else _lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )

    @app.get("/api/dashboard/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    # Routers registered here as later tasks land them. Each import is
    # inside create_app so the module stays importable before all tasks exist.
    try:
        from control_plane.domains.dashboard.http import (
            router_actions,
            router_auth,
            router_events,
            router_read,
        )

        app.include_router(router_auth.router)
        app.include_router(router_read.router)
        app.include_router(router_actions.router)
        app.include_router(router_events.router)
    except ImportError:
        pass  # earlier tasks: routers not built yet

    return app
```

NOTE: the `try/except ImportError` is temporary scaffolding so Tasks 2–4 commit green independently. Task 8 (last router) REMOVES the try/except and makes the imports unconditional — see Task 8 Step 5.

`control-plane/src/control_plane/main.py`:

```python
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Uvicorn entrypoint: ``uvicorn control_plane.main:app --host 0.0.0.0 --port 8000``."""

from control_plane.core.http.app import create_app

app = create_app()
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest control-plane/tests/test_dashboard_app.py -v`
Expected: PASS (lifespan skipped in testing mode; bridge/bus modules don't exist yet but are only imported inside `_lifespan`).

- [ ] **Step 6: Lint and commit**

```bash
uv run ruff check control-plane/src/control_plane/core/http control-plane/src/control_plane/main.py
git add control-plane/src/control_plane/core/http control-plane/src/control_plane/main.py \
        control-plane/tests/test_dashboard_app.py control-plane/pyproject.toml uv.lock
git commit -m "feat(dashboard): FastAPI app factory + uvicorn entrypoint"
```

---

### Task 3: Auth core — passwords, session tokens, stores

**Files:**
- Create: `control-plane/src/control_plane/domains/dashboard/__init__.py` (empty + SPDX), `.../dashboard/auth/__init__.py`, `.../dashboard/auth/passwords.py`, `.../dashboard/auth/sessions.py`, `.../dashboard/auth/store.py`
- Test: `control-plane/tests/test_dashboard_passwords.py`, `control-plane/tests/test_dashboard_sessions.py`

- [ ] **Step 1: Write failing password tests**

`control-plane/tests/test_dashboard_passwords.py`:

```python
# SPDX-License-Identifier: AGPL-3.0-or-later
from control_plane.domains.dashboard.auth.passwords import hash_password, verify_password


def test_hash_and_verify_roundtrip():
    h = hash_password("correct horse battery staple")
    assert h.startswith("$argon2id$")
    assert verify_password(h, "correct horse battery staple") is True


def test_verify_rejects_wrong_password():
    h = hash_password("right")
    assert verify_password(h, "wrong") is False


def test_verify_rejects_garbage_hash():
    assert verify_password("not-a-phc-string", "anything") is False
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest control-plane/tests/test_dashboard_passwords.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement passwords.py**

`passwords.py`:

```python
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Argon2id password hashing for dashboard users."""

from __future__ import annotations

from argon2 import PasswordHasher
from argon2.exceptions import Argon2Error, InvalidHashError

_hasher = PasswordHasher()  # argon2id, library defaults (time_cost=3, 64 MiB)


def hash_password(plain: str) -> str:
    return _hasher.hash(plain)


def verify_password(stored_hash: str, plain: str) -> bool:
    try:
        return _hasher.verify(stored_hash, plain)
    except (Argon2Error, InvalidHashError):
        return False
```

- [ ] **Step 4: Run password tests — PASS, then write failing session tests**

`control-plane/tests/test_dashboard_sessions.py`:

```python
# SPDX-License-Identifier: AGPL-3.0-or-later
import datetime as dt

from control_plane.domains.dashboard.auth.sessions import hash_token, new_session
from control_plane.domains.dashboard.auth.store import InMemoryAuthStore


def test_new_session_token_is_long_and_hash_differs():
    s = new_session(user_id="u1", ip="1.2.3.4", ttl_seconds=60)
    assert len(s.token) >= 43          # 256-bit urlsafe
    assert s.token_hash == hash_token(s.token)
    assert s.token_hash != s.token
    assert len(s.csrf_token) >= 43


async def test_inmemory_store_user_and_session_roundtrip():
    store = InMemoryAuthStore()
    uid = await store.create_user("alice", "phc-hash", "operator")
    user = await store.get_user_by_username("alice")
    assert user is not None and user.id == uid and user.role == "operator"

    s = new_session(user_id=str(uid), ip=None, ttl_seconds=3600)
    await store.save_session(s)
    found = await store.get_session(s.token_hash)
    assert found is not None and found.user_id == s.user_id

    await store.delete_session(s.token_hash)
    assert await store.get_session(s.token_hash) is None


async def test_expired_session_not_returned():
    store = InMemoryAuthStore()
    uid = await store.create_user("bob", "h", "viewer")
    s = new_session(user_id=str(uid), ip=None, ttl_seconds=-1)  # already expired
    await store.save_session(s)
    assert await store.get_session(s.token_hash) is None
    assert s.expires_at < dt.datetime.now(dt.UTC) + dt.timedelta(seconds=1)
```

- [ ] **Step 5: Run to verify failure, then implement sessions.py + store.py**

`sessions.py`:

```python
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Session token generation. Tokens are stored only as sha256 hex."""

from __future__ import annotations

import datetime as dt
import hashlib
import secrets
from dataclasses import dataclass, field


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


@dataclass(frozen=True)
class Session:
    token: str          # returned to client once; NEVER persisted
    token_hash: str
    csrf_token: str
    user_id: str
    ip: str | None
    created_at: dt.datetime
    expires_at: dt.datetime


def new_session(*, user_id: str, ip: str | None, ttl_seconds: int) -> Session:
    token = secrets.token_urlsafe(32)
    now = dt.datetime.now(dt.UTC)
    return Session(
        token=token,
        token_hash=hash_token(token),
        csrf_token=secrets.token_urlsafe(32),
        user_id=user_id,
        ip=ip,
        created_at=now,
        expires_at=now + dt.timedelta(seconds=ttl_seconds),
    )
```

`store.py`:

```python
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Auth persistence: Protocol + asyncpg + in-memory implementations."""

from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

import asyncpg

from .sessions import Session


@dataclass(frozen=True)
class User:
    id: uuid.UUID
    username: str
    password_hash: str
    role: str            # 'viewer' | 'operator'
    disabled: bool


@runtime_checkable
class AuthStore(Protocol):
    async def create_user(self, username: str, password_hash: str, role: str) -> uuid.UUID: ...
    async def get_user_by_username(self, username: str) -> User | None: ...
    async def get_user_by_id(self, user_id: uuid.UUID) -> User | None: ...
    async def save_session(self, session: Session) -> None: ...
    async def get_session(self, token_hash: str) -> Session | None: ...
    async def delete_session(self, token_hash: str) -> None: ...


class InMemoryAuthStore:
    def __init__(self) -> None:
        self._users: dict[uuid.UUID, User] = {}
        self._sessions: dict[str, Session] = {}

    async def create_user(self, username: str, password_hash: str, role: str) -> uuid.UUID:
        uid = uuid.uuid4()
        self._users[uid] = User(uid, username, password_hash, role, disabled=False)
        return uid

    async def get_user_by_username(self, username: str) -> User | None:
        return next((u for u in self._users.values() if u.username == username), None)

    async def get_user_by_id(self, user_id: uuid.UUID) -> User | None:
        return self._users.get(user_id)

    async def save_session(self, session: Session) -> None:
        self._sessions[session.token_hash] = session

    async def get_session(self, token_hash: str) -> Session | None:
        s = self._sessions.get(token_hash)
        if s is None or s.expires_at <= dt.datetime.now(dt.UTC):
            return None
        return s

    async def delete_session(self, token_hash: str) -> None:
        self._sessions.pop(token_hash, None)


class AsyncpgAuthStore:
    """Same contract over dashboard_users / dashboard_sessions (migration 14)."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def create_user(self, username: str, password_hash: str, role: str) -> uuid.UUID:
        row = await self._pool.fetchrow(
            "INSERT INTO dashboard_users (username, password_hash, role) "
            "VALUES ($1, $2, $3) RETURNING id",
            username, password_hash, role,
        )
        return row["id"]

    async def get_user_by_username(self, username: str) -> User | None:
        row = await self._pool.fetchrow(
            "SELECT id, username, password_hash, role, disabled "
            "FROM dashboard_users WHERE username = $1",
            username,
        )
        return None if row is None else User(**dict(row))

    async def get_user_by_id(self, user_id: uuid.UUID) -> User | None:
        row = await self._pool.fetchrow(
            "SELECT id, username, password_hash, role, disabled "
            "FROM dashboard_users WHERE id = $1",
            user_id,
        )
        return None if row is None else User(**dict(row))

    async def save_session(self, session: Session) -> None:
        await self._pool.execute(
            "INSERT INTO dashboard_sessions "
            "(token_hash, user_id, csrf_token, ip, created_at, expires_at) "
            "VALUES ($1, $2, $3, $4, $5, $6)",
            session.token_hash, uuid.UUID(session.user_id), session.csrf_token,
            session.ip, session.created_at, session.expires_at,
        )

    async def get_session(self, token_hash: str) -> Session | None:
        row = await self._pool.fetchrow(
            "SELECT token_hash, user_id, csrf_token, ip, created_at, expires_at "
            "FROM dashboard_sessions WHERE token_hash = $1 AND expires_at > now()",
            token_hash,
        )
        if row is None:
            return None
        return Session(
            token="",  # original token is never recoverable
            token_hash=row["token_hash"],
            csrf_token=row["csrf_token"],
            user_id=str(row["user_id"]),
            ip=row["ip"],
            created_at=row["created_at"],
            expires_at=row["expires_at"],
        )

    async def delete_session(self, token_hash: str) -> None:
        await self._pool.execute(
            "DELETE FROM dashboard_sessions WHERE token_hash = $1", token_hash
        )
```

`auth/__init__.py`:

```python
# SPDX-License-Identifier: AGPL-3.0-or-later
from .passwords import hash_password, verify_password
from .sessions import Session, hash_token, new_session
from .store import AsyncpgAuthStore, AuthStore, InMemoryAuthStore, User

__all__ = [
    "AsyncpgAuthStore", "AuthStore", "InMemoryAuthStore", "Session", "User",
    "hash_password", "hash_token", "new_session", "verify_password",
]
```

`dashboard/__init__.py`: just the SPDX line and a module docstring `"""Dashboard bounded context — operator web console BFF."""`.

- [ ] **Step 6: Run both test files — PASS; lint; commit**

```bash
uv run pytest control-plane/tests/test_dashboard_passwords.py control-plane/tests/test_dashboard_sessions.py -v
uv run ruff check control-plane/src/control_plane/domains/dashboard
git add control-plane/src/control_plane/domains/dashboard control-plane/tests/test_dashboard_passwords.py control-plane/tests/test_dashboard_sessions.py
git commit -m "feat(dashboard): auth core — argon2 passwords, hashed session tokens, stores"
```

---

### Task 4: Auth HTTP — login/logout/me, session + CSRF deps, rate limit

**Files:**
- Create: `.../dashboard/auth/rate_limit.py`, `.../dashboard/http/__init__.py`, `.../dashboard/http/schemas.py` (auth models only; later tasks append), `.../dashboard/http/deps.py`, `.../dashboard/http/router_auth.py`
- Test: `control-plane/tests/test_dashboard_auth_http.py`

- [ ] **Step 1: Write failing HTTP auth tests**

`control-plane/tests/test_dashboard_auth_http.py`:

```python
# SPDX-License-Identifier: AGPL-3.0-or-later
import httpx
import pytest

from control_plane.core.http.app import create_app
from control_plane.domains.dashboard.auth import InMemoryAuthStore, hash_password
from control_plane.domains.dashboard.auth.rate_limit import InMemoryLoginRateLimiter
from control_plane.domains.dashboard.http.deps import get_auth_store, get_rate_limiter


@pytest.fixture
async def client():
    app = create_app(testing=True)
    store = InMemoryAuthStore()
    await store.create_user("op", hash_password("hunter2hunter2"), "operator")
    await store.create_user("ro", hash_password("readonlyreadonly"), "viewer")
    app.dependency_overrides[get_auth_store] = lambda: store
    app.dependency_overrides[get_rate_limiter] = lambda: InMemoryLoginRateLimiter(limit=5)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
        yield c


async def _login(client, username="op", password="hunter2hunter2"):
    return await client.post(
        "/api/dashboard/auth/login", json={"username": username, "password": password}
    )


async def test_login_sets_cookie_and_returns_csrf(client):
    resp = await _login(client)
    assert resp.status_code == 200
    body = resp.json()
    assert body["username"] == "op" and body["role"] == "operator"
    assert len(body["csrf_token"]) >= 43
    assert "bs_session" in resp.cookies


async def test_login_wrong_password_401_uniform_error(client):
    resp = await _login(client, password="nope-nope-nope")
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "invalid_credentials"


async def test_login_unknown_user_same_401(client):
    resp = await _login(client, username="ghost")
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "invalid_credentials"


async def test_me_requires_session(client):
    resp = await client.get("/api/dashboard/auth/me")
    assert resp.status_code == 401


async def test_me_returns_user_after_login(client):
    await _login(client)  # cookie persists on the client
    resp = await client.get("/api/dashboard/auth/me")
    assert resp.status_code == 200
    assert resp.json()["username"] == "op"


async def test_logout_invalidates_session(client):
    login = await _login(client)
    csrf = login.json()["csrf_token"]
    out = await client.post("/api/dashboard/auth/logout", headers={"X-CSRF-Token": csrf})
    assert out.status_code == 204
    assert (await client.get("/api/dashboard/auth/me")).status_code == 401


async def test_logout_without_csrf_403(client):
    await _login(client)
    assert (await client.post("/api/dashboard/auth/logout")).status_code == 403


async def test_login_rate_limited_after_5(client):
    for _ in range(5):
        await _login(client, password="wrong-wrong-wrong")
    resp = await _login(client, password="wrong-wrong-wrong")
    assert resp.status_code == 429
```

- [ ] **Step 2: Run to verify failure** (`ModuleNotFoundError` on deps import)

- [ ] **Step 3: Implement rate_limit.py**

```python
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Login rate limiting — Protocol + in-memory + Redis (fixed 60 s window)."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from redis.asyncio import Redis as AsyncRedis

_WINDOW_SECONDS = 60


@runtime_checkable
class LoginRateLimiter(Protocol):
    async def allow(self, key: str) -> bool: ...


class InMemoryLoginRateLimiter:
    def __init__(self, limit: int = 5) -> None:
        self._limit = limit
        self._hits: dict[str, list[float]] = {}

    async def allow(self, key: str) -> bool:
        now = time.monotonic()
        hits = [t for t in self._hits.get(key, []) if now - t < _WINDOW_SECONDS]
        if len(hits) >= self._limit:
            self._hits[key] = hits
            return False
        hits.append(now)
        self._hits[key] = hits
        return True


class RedisLoginRateLimiter:
    def __init__(self, client: AsyncRedis, limit: int = 5) -> None:
        self._client = client
        self._limit = limit

    async def allow(self, key: str) -> bool:
        rkey = f"bountystrike:dash:login:{key}"
        count = await self._client.incr(rkey)
        if count == 1:
            await self._client.expire(rkey, _WINDOW_SECONDS)
        return count <= self._limit
```

- [ ] **Step 4: Implement schemas.py (auth section), deps.py, router_auth.py**

`schemas.py` (this file accumulates ALL dashboard Pydantic models; auth ones now):

```python
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Pydantic models for every /api/dashboard boundary (project rule)."""

from __future__ import annotations

import datetime as dt
import uuid

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=1024)


class MeResponse(BaseModel):
    username: str
    role: str
    csrf_token: str


class ErrorBody(BaseModel):
    code: str
    message: str


class ErrorEnvelope(BaseModel):
    error: ErrorBody
```

`deps.py`:

```python
# SPDX-License-Identifier: AGPL-3.0-or-later
"""FastAPI dependencies: stores, session auth, role + CSRF guards.

Provider functions (get_auth_store / get_rate_limiter / get_pool /
get_kill_switch / get_event_bus) read app.state set by the lifespan;
tests replace them via dependency_overrides.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request

from control_plane.domains.dashboard.auth import AuthStore, hash_token
from control_plane.domains.dashboard.auth.rate_limit import LoginRateLimiter

SESSION_COOKIE = "bs_session"
SESSION_TTL_SECONDS = 7 * 24 * 3600


def cookie_secure() -> bool:
    return os.environ.get("DASHBOARD_COOKIE_SECURE", "0") == "1"


def get_auth_store(request: Request) -> AuthStore:
    store = getattr(request.app.state, "auth_store", None)
    if store is None:
        from control_plane.domains.dashboard.auth import AsyncpgAuthStore

        store = AsyncpgAuthStore(request.app.state.pool)
        request.app.state.auth_store = store
    return store


def get_rate_limiter(request: Request) -> LoginRateLimiter:
    limiter = getattr(request.app.state, "login_limiter", None)
    if limiter is None:
        from control_plane.domains.dashboard.auth.rate_limit import InMemoryLoginRateLimiter

        limiter = InMemoryLoginRateLimiter()
        request.app.state.login_limiter = limiter
    return limiter


def get_pool(request: Request):
    return request.app.state.pool


def get_kill_switch(request: Request):
    return request.app.state.kill_switch


def get_event_bus(request: Request):
    return request.app.state.event_bus


def _err(status: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status, detail={"code": code, "message": message})


@dataclass(frozen=True)
class AuthedUser:
    username: str
    role: str
    csrf_token: str
    token_hash: str


async def current_user(
    request: Request, store: AuthStore = Depends(get_auth_store)
) -> AuthedUser:
    raw = request.cookies.get(SESSION_COOKIE)
    if not raw:
        raise _err(401, "unauthenticated", "login required")
    session = await store.get_session(hash_token(raw))
    if session is None:
        raise _err(401, "unauthenticated", "session expired or invalid")
    import uuid as _uuid

    user = await store.get_user_by_id(_uuid.UUID(session.user_id))
    if user is None or user.disabled:
        raise _err(401, "unauthenticated", "account unavailable")
    return AuthedUser(
        username=user.username,
        role=user.role,
        csrf_token=session.csrf_token,
        token_hash=session.token_hash,
    )


async def csrf_checked(request: Request, user: AuthedUser = Depends(current_user)) -> AuthedUser:
    header = request.headers.get("X-CSRF-Token", "")
    import secrets

    if not header or not secrets.compare_digest(header, user.csrf_token):
        raise _err(403, "csrf", "missing or invalid CSRF token")
    return user


async def require_operator(user: AuthedUser = Depends(csrf_checked)) -> AuthedUser:
    if user.role != "operator":
        raise _err(403, "forbidden", "operator role required")
    return user
```

`router_auth.py`:

```python
# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response

from control_plane.domains.dashboard.auth import (
    AuthStore,
    hash_token,
    new_session,
    verify_password,
)
from control_plane.domains.dashboard.auth.rate_limit import LoginRateLimiter

from .deps import (
    SESSION_COOKIE,
    SESSION_TTL_SECONDS,
    AuthedUser,
    _err,
    cookie_secure,
    csrf_checked,
    current_user,
    get_auth_store,
    get_rate_limiter,
)
from .schemas import LoginRequest, MeResponse

router = APIRouter(prefix="/api/dashboard/auth", tags=["dashboard-auth"])


@router.post("/login", response_model=MeResponse)
async def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    store: AuthStore = Depends(get_auth_store),
    limiter: LoginRateLimiter = Depends(get_rate_limiter),
) -> MeResponse:
    ip = request.client.host if request.client else "unknown"
    if not await limiter.allow(ip):
        raise _err(429, "rate_limited", "too many login attempts; wait a minute")
    user = await store.get_user_by_username(body.username)
    # Uniform failure: same code/message for unknown user and bad password.
    if user is None or user.disabled or not verify_password(user.password_hash, body.password):
        raise _err(401, "invalid_credentials", "invalid username or password")
    session = new_session(user_id=str(user.id), ip=ip, ttl_seconds=SESSION_TTL_SECONDS)
    await store.save_session(session)
    response.set_cookie(
        SESSION_COOKIE,
        session.token,
        max_age=SESSION_TTL_SECONDS,
        httponly=True,
        samesite="lax",
        secure=cookie_secure(),
        path="/",
    )
    return MeResponse(username=user.username, role=user.role, csrf_token=session.csrf_token)


@router.get("/me", response_model=MeResponse)
async def me(user: AuthedUser = Depends(current_user)) -> MeResponse:
    return MeResponse(username=user.username, role=user.role, csrf_token=user.csrf_token)


@router.post("/logout", status_code=204)
async def logout(
    response: Response,
    user: AuthedUser = Depends(csrf_checked),
    store: AuthStore = Depends(get_auth_store),
) -> None:
    await store.delete_session(user.token_hash)
    response.delete_cookie(SESSION_COOKIE, path="/")
```

`http/__init__.py`: SPDX line only (routers imported by app factory directly).

Also add the error-envelope handler in `core/http/app.py` `create_app` (before the router block):

```python
    from fastapi import HTTPException
    from fastapi.responses import JSONResponse

    @app.exception_handler(HTTPException)
    async def _envelope(request, exc: HTTPException):
        detail = exc.detail if isinstance(exc.detail, dict) else {
            "code": "error", "message": str(exc.detail)
        }
        return JSONResponse(status_code=exc.status_code, content={"error": detail})
```

- [ ] **Step 5: Run tests — all 9 PASS; lint; commit**

```bash
uv run pytest control-plane/tests/test_dashboard_auth_http.py -v
uv run ruff check control-plane/src/control_plane/domains/dashboard
git add -A control-plane/src/control_plane/domains/dashboard control-plane/src/control_plane/core/http control-plane/tests/test_dashboard_auth_http.py
git commit -m "feat(dashboard): auth HTTP — login/logout/me, CSRF, role deps, rate limit"
```

---

### Task 5: `scripts/dashboard_user.py` CLI

**Files:**
- Create: `scripts/dashboard_user.py`
- Test: `control-plane/tests/test_dashboard_user_cli.py`

- [ ] **Step 1: Write failing test (parser + hashing logic, no DB)**

```python
# SPDX-License-Identifier: AGPL-3.0-or-later
import pytest

from scripts.dashboard_user import build_parser  # noqa: F401  (path via root pyproject)


def test_create_requires_role():
    p = build_parser()
    with pytest.raises(SystemExit):
        p.parse_args(["create", "alice", "--role", "superadmin"])


def test_create_parses_valid():
    args = build_parser().parse_args(["create", "alice", "--role", "operator"])
    assert args.cmd == "create" and args.username == "alice" and args.role == "operator"


def test_disable_parses():
    args = build_parser().parse_args(["disable", "alice"])
    assert args.cmd == "disable"
```

If `scripts/` is not importable as a package in the test env, add `sys.path.insert(0, str(Path(__file__).parents[2] / "scripts"))` at the top of the test and `import dashboard_user` instead — match whatever `scripts/test_init_wizard_e2e.py` already does (check that file first; copy its import pattern).

- [ ] **Step 2: Run to verify failure, then implement CLI**

`scripts/dashboard_user.py`:

```python
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Dashboard user management CLI.

    python scripts/dashboard_user.py create <username> --role viewer|operator
    python scripts/dashboard_user.py passwd <username>
    python scripts/dashboard_user.py disable <username>
    python scripts/dashboard_user.py list

Password is prompted (getpass), never argv. DATABASE_URL required.
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import os
import sys

import asyncpg

from control_plane.domains.dashboard.auth import hash_password


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="dashboard_user")
    sub = p.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("create")
    c.add_argument("username")
    c.add_argument("--role", choices=["viewer", "operator"], required=True)
    pw = sub.add_parser("passwd")
    pw.add_argument("username")
    d = sub.add_parser("disable")
    d.add_argument("username")
    sub.add_parser("list")
    return p


def _dsn() -> str:
    raw = os.environ.get("DATABASE_URL")
    if not raw:
        print("ERROR: DATABASE_URL is not set", file=sys.stderr)
        sys.exit(2)
    return raw.replace("+asyncpg", "")


def _prompt_password() -> str:
    pw = getpass.getpass("Password: ")
    if len(pw) < 12:
        print("ERROR: password must be at least 12 characters", file=sys.stderr)
        sys.exit(2)
    if pw != getpass.getpass("Repeat: "):
        print("ERROR: passwords do not match", file=sys.stderr)
        sys.exit(2)
    return pw


async def _run(args: argparse.Namespace) -> None:
    conn = await asyncpg.connect(_dsn())
    try:
        if args.cmd == "create":
            h = hash_password(_prompt_password())
            await conn.execute(
                "INSERT INTO dashboard_users (username, password_hash, role) "
                "VALUES ($1, $2, $3)",
                args.username, h, args.role,
            )
            print(f"created {args.username} ({args.role})")
        elif args.cmd == "passwd":
            h = hash_password(_prompt_password())
            r = await conn.execute(
                "UPDATE dashboard_users SET password_hash=$2 WHERE username=$1",
                args.username, h,
            )
            print("updated" if not r.endswith("0") else "no such user")
        elif args.cmd == "disable":
            await conn.execute(
                "UPDATE dashboard_users SET disabled=true WHERE username=$1", args.username
            )
            await conn.execute(
                "DELETE FROM dashboard_sessions WHERE user_id = "
                "(SELECT id FROM dashboard_users WHERE username=$1)",
                args.username,
            )
            print(f"disabled {args.username} and revoked sessions")
        elif args.cmd == "list":
            for row in await conn.fetch(
                "SELECT username, role, disabled, created_at FROM dashboard_users "
                "ORDER BY username"
            ):
                flag = " (disabled)" if row["disabled"] else ""
                print(f"{row['username']:24} {row['role']:8}{flag}")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(_run(build_parser().parse_args()))
```

- [ ] **Step 3: Run tests — PASS; lint; commit**

```bash
uv run pytest control-plane/tests/test_dashboard_user_cli.py -v && uv run ruff check scripts/dashboard_user.py
git add scripts/dashboard_user.py control-plane/tests/test_dashboard_user_cli.py
git commit -m "feat(dashboard): user management CLI (create/passwd/disable/list)"
```

---

### Task 6: Read endpoints — overview, hunts, findings, approvals

**Files:**
- Modify: `.../dashboard/http/schemas.py` (append read models)
- Create: `.../dashboard/http/router_read.py`
- Test: `control-plane/tests/test_dashboard_read.py`

Pipeline-stage bucketing (the ONE place this mapping lives — frontend receives stage names, never raw statuses, except findings table rows which carry both):

```python
STAGE_BY_STATUS = {
    "hypothesis": "scan",
    "exploit_attempt": "exploit", "exploit_candidate": "exploit",
    "approval_pending_t2": "exploit",
    "exploit_pending_validation": "validate", "validation_pending": "validate",
    "dedup_check": "validate", "validated": "validate",
    "approval_pending_t1": "report", "approval_pending_t3": "report",
    "approved": "report", "submitted": "report", "confirmed": "report",
    "rejected": "terminal", "duplicate": "terminal", "wont_fix": "terminal",
    "archived": "terminal", "exploit_failed_oos": "terminal",
    "exploit_failed_timeout": "terminal", "exploit_failed_crash": "terminal",
}
```

- [ ] **Step 1: Append read models to schemas.py**

```python
class OverviewResponse(BaseModel):
    findings_by_status: dict[str, int]
    pending_approvals: int
    worst_sla_seconds: int | None      # seconds until the earliest expires_at; negative = overdue
    kill_switch: str                   # KillSwitchState value
    active_programs: list[str]         # distinct program_handle with non-terminal findings


class ProgramPipeline(BaseModel):
    program_handle: str
    stages: dict[str, int]             # scan/exploit/validate/report/terminal -> count
    recon_assets: int


class HuntsResponse(BaseModel):
    programs: list[ProgramPipeline]
    recent_activity: list[ActivityItem]


class ActivityItem(BaseModel):
    ts: dt.datetime
    actor: str
    action: str
    resource: str | None
    payload: dict | None = None


class FindingRow(BaseModel):
    id: uuid.UUID
    program_handle: str | None
    platform: str | None
    cwe: str | None
    url: str | None
    status: str
    stage: str
    created_at: dt.datetime


class FindingsPage(BaseModel):
    items: list[FindingRow]
    total: int
    limit: int
    offset: int


class FindingDetail(FindingRow):
    parameter: str | None
    oracle_method: str | None
    evidence_hash: str | None
    audit_entries: list[AuditEntry]


class AuditEntry(BaseModel):
    entry_type: str
    payload: dict
    created_at: dt.datetime


class ApprovalItem(BaseModel):
    finding_id: uuid.UUID
    tier: str
    poc_text: str | None
    requested_at: dt.datetime
    expires_at: dt.datetime
    sla_seconds: int                   # seconds remaining; negative = overdue
    program_handle: str | None
    cwe: str | None
    url: str | None
    needs_second_approver: bool        # T3 with approver_id set, approver_id_2 null


class ApprovalsResponse(BaseModel):
    items: list[ApprovalItem]
```

(Declare `ActivityItem` and `AuditEntry` ABOVE the models that reference them.)

- [ ] **Step 2: Write failing tests**

`control-plane/tests/test_dashboard_read.py` — pattern: `create_app(testing=True)`, override `get_pool` with a `FakePool` whose `fetch/fetchrow/fetchval` return canned rows, override `get_kill_switch` with `InMemoryKillSwitchStore`, override `current_user` to return a viewer `AuthedUser("ro","viewer","x","h")`. Canned-row helper:

```python
class FakePool:
    """Returns canned rows keyed by a substring of the SQL text."""

    def __init__(self, responses: dict[str, list[dict]]):
        self._responses = responses

    def _match(self, sql: str) -> list[dict]:
        for key, rows in self._responses.items():
            if key in sql:
                return rows
        raise AssertionError(f"unexpected SQL: {sql[:120]}")

    async def fetch(self, sql, *args):
        return self._match(sql)

    async def fetchrow(self, sql, *args):
        rows = self._match(sql)
        return rows[0] if rows else None

    async def fetchval(self, sql, *args):
        rows = self._match(sql)
        return next(iter(rows[0].values())) if rows else 0
```

Tests to write (assert shapes, not SQL):
1. `test_overview_aggregates` — FakePool maps `"GROUP BY status"` → `[{"status": "hypothesis", "n": 3}, {"status": "validated", "n": 1}]`, `"FROM approval_queue"` → `[{"n": 2, "worst": <aware datetime now+3600>}]`, `"DISTINCT program_handle"` → `[{"program_handle": "pd-spotify"}]`. Assert `findings_by_status == {"hypothesis": 3, "validated": 1}`, `pending_approvals == 2`, `0 < worst_sla_seconds <= 3600`, `kill_switch == "inactive"`.
2. `test_hunts_buckets_statuses_into_stages` — rows `[{"program_handle": "p", "status": "hypothesis", "n": 2}, {"program_handle": "p", "status": "validated", "n": 1}]` → one ProgramPipeline with `stages["scan"] == 2`, `stages["validate"] == 1`, all five stage keys present.
3. `test_findings_pagination_clamps_limit` — request `?limit=5000` → response `limit == 200` (max).
4. `test_finding_detail_includes_audit_entries`.
5. `test_approvals_marks_t3_needing_second` — QueueEntry-shaped row with tier `T3`, `approver_id` set, `approver_id_2` None → `needs_second_approver is True`.
6. `test_read_requires_auth` — build app WITHOUT the `current_user` override; GET `/api/dashboard/overview` → 401.

- [ ] **Step 3: Run to verify failure, then implement router_read.py**

```python
# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import datetime as dt
import uuid

from fastapi import APIRouter, Depends, Query

from control_plane.domains.approval_gate import ApprovalTier, queue_list_pending

from .deps import AuthedUser, _err, current_user, get_kill_switch, get_pool
from .schemas import (
    ActivityItem, ApprovalItem, ApprovalsResponse, AuditEntry, FindingDetail,
    FindingRow, FindingsPage, HuntsResponse, OverviewResponse, ProgramPipeline,
)

router = APIRouter(
    prefix="/api/dashboard", tags=["dashboard-read"],
    dependencies=[Depends(current_user)],
)

STAGE_BY_STATUS = { ... }  # exact dict from the task header
STAGES = ["scan", "exploit", "validate", "report", "terminal"]
_TERMINAL = [s for s, stage in STAGE_BY_STATUS.items() if stage == "terminal"]


def _stage(status: str) -> str:
    return STAGE_BY_STATUS.get(status, "terminal")


@router.get("/overview", response_model=OverviewResponse)
async def overview(pool=Depends(get_pool), ks=Depends(get_kill_switch)) -> OverviewResponse:
    status_rows = await pool.fetch(
        "SELECT status::text AS status, count(*) AS n FROM findings GROUP BY status"
    )
    appr = await pool.fetchrow(
        "SELECT count(*) AS n, min(expires_at) AS worst "
        "FROM approval_queue WHERE status = 'pending'"
    )
    prog_rows = await pool.fetch(
        "SELECT DISTINCT program_handle FROM findings "
        "WHERE program_handle IS NOT NULL AND status::text != ALL($1::text[])",
        _TERMINAL,
    )
    worst = appr["worst"] if appr else None
    return OverviewResponse(
        findings_by_status={r["status"]: r["n"] for r in status_rows},
        pending_approvals=appr["n"] if appr else 0,
        worst_sla_seconds=(
            int((worst - dt.datetime.now(dt.UTC)).total_seconds()) if worst else None
        ),
        kill_switch=(await ks.get_state()).value,
        active_programs=sorted(r["program_handle"] for r in prog_rows),
    )


@router.get("/hunts/active", response_model=HuntsResponse)
async def hunts(pool=Depends(get_pool)) -> HuntsResponse:
    rows = await pool.fetch(
        "SELECT program_handle, status::text AS status, count(*) AS n FROM findings "
        "WHERE program_handle IS NOT NULL GROUP BY program_handle, status"
    )
    recon = await pool.fetch(
        "SELECT program_handle, count(*) AS n FROM recon_assets GROUP BY program_handle"
    )
    recon_by_prog = {r["program_handle"]: r["n"] for r in recon}
    programs: dict[str, dict[str, int]] = {}
    for r in rows:
        stages = programs.setdefault(r["program_handle"], dict.fromkeys(STAGES, 0))
        stages[_stage(r["status"])] += r["n"]
    activity = await pool.fetch(
        "SELECT ts, actor, action, resource, payload FROM dashboard_audit_log "
        "ORDER BY ts DESC LIMIT 50"
    )
    return HuntsResponse(
        programs=[
            ProgramPipeline(program_handle=p, stages=s, recon_assets=recon_by_prog.get(p, 0))
            for p, s in sorted(programs.items())
        ],
        recent_activity=[ActivityItem(**dict(a)) for a in activity],
    )


@router.get("/findings", response_model=FindingsPage)
async def findings(
    pool=Depends(get_pool),
    status: str | None = Query(default=None),
    program: str | None = Query(default=None),
    cwe: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1),
    offset: int = Query(default=0, ge=0),
) -> FindingsPage:
    limit = min(limit, 200)
    where, args = ["TRUE"], []
    if status:
        args.append(status); where.append(f"status::text = ${len(args)}")
    if program:
        args.append(program); where.append(f"program_handle = ${len(args)}")
    if cwe:
        args.append(cwe); where.append(f"cwe = ${len(args)}")
    w = " AND ".join(where)
    total = await pool.fetchval(f"SELECT count(*) FROM findings WHERE {w}", *args)
    rows = await pool.fetch(
        f"SELECT id, program_handle, platform, cwe, url, status::text AS status, created_at "
        f"FROM findings WHERE {w} ORDER BY created_at DESC "
        f"LIMIT {limit} OFFSET {offset}",
        *args,
    )
    return FindingsPage(
        items=[FindingRow(**dict(r), stage=_stage(r["status"])) for r in rows],
        total=total or 0, limit=limit, offset=offset,
    )


@router.get("/findings/{finding_id}", response_model=FindingDetail)
async def finding_detail(finding_id: uuid.UUID, pool=Depends(get_pool)) -> FindingDetail:
    row = await pool.fetchrow(
        "SELECT id, program_handle, platform, cwe, url, parameter, status::text AS status, "
        "oracle_method, evidence_hash, created_at FROM findings WHERE id = $1",
        finding_id,
    )
    if row is None:
        raise _err(404, "not_found", "no such finding")
    audit = await pool.fetch(
        "SELECT entry_type, payload, created_at FROM audit_log "
        "WHERE finding_id = $1 ORDER BY created_at ASC",
        finding_id,
    )
    return FindingDetail(
        **dict(row), stage=_stage(row["status"]),
        audit_entries=[AuditEntry(**dict(a)) for a in audit],
    )


@router.get("/approvals", response_model=ApprovalsResponse)
async def approvals(pool=Depends(get_pool)) -> ApprovalsResponse:
    now = dt.datetime.now(dt.UTC)
    rows = await pool.fetch(
        "SELECT q.finding_id, q.tier, q.poc_text, q.requested_at, q.expires_at, "
        "q.approver_id, q.approver_id_2, f.program_handle, f.cwe, f.url "
        "FROM approval_queue q JOIN findings f ON f.id = q.finding_id "
        "WHERE q.status = 'pending' ORDER BY q.expires_at ASC"
    )
    return ApprovalsResponse(items=[
        ApprovalItem(
            finding_id=r["finding_id"], tier=r["tier"], poc_text=r["poc_text"],
            requested_at=r["requested_at"], expires_at=r["expires_at"],
            sla_seconds=int((r["expires_at"] - now).total_seconds()),
            program_handle=r["program_handle"], cwe=r["cwe"], url=r["url"],
            needs_second_approver=(
                r["tier"] == "T3" and r["approver_id"] is not None
                and r["approver_id_2"] is None
            ),
        )
        for r in rows
    ])
```

(Write out STAGE_BY_STATUS literally in the file — the `{ ... }` above is plan shorthand for the exact dict from this task's header, nothing else.)

NOTE: `queue_list_pending` is imported but the approvals query is custom (needs the findings JOIN + the not-yet-decided T3 rows that `list_pending` also returns; custom SQL keeps one round trip). If ruff flags the unused import, remove it.

- [ ] **Step 4: Run tests — PASS; lint; commit**

```bash
uv run pytest control-plane/tests/test_dashboard_read.py -v && uv run ruff check control-plane/src
git add control-plane/src/control_plane/domains/dashboard/http control-plane/tests/test_dashboard_read.py
git commit -m "feat(dashboard): read endpoints — overview, hunts, findings, approvals"
```

---

### Task 7: Action endpoints — approve/reject + kill-switch + audit

**Files:**
- Create: `.../dashboard/audit.py`, `.../dashboard/http/router_actions.py`
- Modify: `.../dashboard/http/schemas.py` (append action models)
- Test: `control-plane/tests/test_dashboard_actions.py`

- [ ] **Step 1: Append action models to schemas.py**

```python
class DecisionRequest(BaseModel):
    reason: str = Field(default="", max_length=4000)


class RejectRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=4000)


class DecisionResponse(BaseModel):
    finding_id: uuid.UUID
    status: str                        # 'approved' | 'rejected' | 'pending_second_approval'


class KillSwitchResponse(BaseModel):
    state: str


class KillSwitchRequest(BaseModel):
    state: str = Field(pattern="^(inactive|halt_submissions|halt_scans|halt_all)$")
    reason: str = Field(min_length=1, max_length=4000)
```

- [ ] **Step 2: Write failing tests**

`control-plane/tests/test_dashboard_actions.py`. Setup: `create_app(testing=True)`; override `current_user`/`csrf_checked`/`require_operator` chain by overriding `get_auth_store` + real login? NO — simpler and consistent with Task 6: override `require_operator` to return an operator `AuthedUser`, override `current_user` for viewer-tests. Override `get_pool` with a `FakeAcquirePool` (adds `acquire()` context manager returning a FakeConn that records `execute` calls), `get_kill_switch` → `InMemoryKillSwitchStore`, `get_event_bus` → real `EventBus` (Task 8 module — for THIS task create a 10-line stub `events/bus.py` with `publish()` appending to a list; Task 8 replaces internals, keeps the API). Monkeypatch `router_actions.queue_approve` / `router_actions.queue_reject`.

Tests:
1. `test_approve_returns_approved_on_token` — monkeypatched `queue_approve` returns a uuid → 200, `status == "approved"`, audit insert recorded (FakeConn captured an `INSERT INTO dashboard_audit_log` with action `approval.approve`).
2. `test_approve_t3_first_returns_pending_second` — `queue_approve` returns `None` → `status == "pending_second_approval"`.
3. `test_approve_conflict_maps_409` — `queue_approve` raises `ApprovalQueueError("already terminal")` → 409, error code `approval_conflict`.
4. `test_reject_requires_reason` — body `{"reason": ""}` → 422.
5. `test_killswitch_set_and_get` — POST `{"state": "halt_all", "reason": "incident"}` → 200; GET returns `halt_all`; audit row recorded with action `killswitch.set`.
6. `test_killswitch_inactive_clears` — POST `{"state": "inactive", ...}` then store `get_state()` returns `INACTIVE`.
7. `test_viewer_blocked_from_all_mutations` — with viewer user (no operator override): approve, reject, killswitch POST each → 403.

- [ ] **Step 3: Run to verify failure, then implement audit.py + router_actions.py**

`audit.py`:

```python
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Dashboard action audit — simple actor/action rows (dashboard_audit_log)."""

from __future__ import annotations

import json


async def write_dashboard_audit(
    conn, *, actor: str, action: str, resource: str | None, payload: dict | None = None
) -> None:
    await conn.execute(
        "INSERT INTO dashboard_audit_log (actor, action, resource, payload) "
        "VALUES ($1, $2, $3, $4)",
        actor, action, resource, json.dumps(payload) if payload is not None else None,
    )
```

`router_actions.py`:

```python
# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends

from control_plane.domains.approval_gate import ApprovalQueueError, queue_approve, queue_reject
from control_plane.domains.dashboard.audit import write_dashboard_audit
from control_plane.domains.safety import KillSwitchState

from .deps import AuthedUser, _err, current_user, get_event_bus, get_kill_switch, get_pool, require_operator
from .schemas import (
    DecisionRequest, DecisionResponse, KillSwitchRequest, KillSwitchResponse, RejectRequest,
)

router = APIRouter(prefix="/api/dashboard", tags=["dashboard-actions"])

KILL_SWITCH_TTL_SECONDS = 24 * 3600  # matches RedisKillSwitchStore human-renewal design


@router.post("/approvals/{finding_id}/approve", response_model=DecisionResponse)
async def approve(
    finding_id: uuid.UUID,
    body: DecisionRequest,
    user: AuthedUser = Depends(require_operator),
    pool=Depends(get_pool),
    bus=Depends(get_event_bus),
) -> DecisionResponse:
    async with pool.acquire() as conn:
        try:
            token = await queue_approve(conn, finding_id, user.username, body.reason)
        except ApprovalQueueError as exc:
            raise _err(409, "approval_conflict", str(exc)) from exc
        except ValueError as exc:
            raise _err(422, "invalid", str(exc)) from exc
        status = "approved" if token is not None else "pending_second_approval"
        await write_dashboard_audit(
            conn, actor=user.username, action="approval.approve",
            resource=f"finding:{finding_id}", payload={"status": status, "reason": body.reason},
        )
    bus.publish({"type": "approval_decided", "finding_id": str(finding_id), "status": status})
    return DecisionResponse(finding_id=finding_id, status=status)


@router.post("/approvals/{finding_id}/reject", response_model=DecisionResponse)
async def reject(
    finding_id: uuid.UUID,
    body: RejectRequest,
    user: AuthedUser = Depends(require_operator),
    pool=Depends(get_pool),
    bus=Depends(get_event_bus),
) -> DecisionResponse:
    async with pool.acquire() as conn:
        try:
            await queue_reject(conn, finding_id, user.username, body.reason)
        except ApprovalQueueError as exc:
            raise _err(409, "approval_conflict", str(exc)) from exc
        await write_dashboard_audit(
            conn, actor=user.username, action="approval.reject",
            resource=f"finding:{finding_id}", payload={"reason": body.reason},
        )
    bus.publish({"type": "approval_decided", "finding_id": str(finding_id), "status": "rejected"})
    return DecisionResponse(finding_id=finding_id, status="rejected")


@router.get("/killswitch", response_model=KillSwitchResponse)
async def killswitch_get(
    user: AuthedUser = Depends(current_user), ks=Depends(get_kill_switch)
) -> KillSwitchResponse:
    return KillSwitchResponse(state=(await ks.get_state()).value)


@router.post("/killswitch", response_model=KillSwitchResponse)
async def killswitch_set(
    body: KillSwitchRequest,
    user: AuthedUser = Depends(require_operator),
    ks=Depends(get_kill_switch),
    pool=Depends(get_pool),
    bus=Depends(get_event_bus),
) -> KillSwitchResponse:
    target = KillSwitchState(body.state)
    if target is KillSwitchState.INACTIVE:
        await ks.clear()
    else:
        await ks.set_state(target, ttl_seconds=KILL_SWITCH_TTL_SECONDS)
    async with pool.acquire() as conn:
        await write_dashboard_audit(
            conn, actor=user.username, action="killswitch.set",
            resource="killswitch", payload={"state": target.value, "reason": body.reason},
        )
    bus.publish({"type": "killswitch_changed", "state": target.value})
    return KillSwitchResponse(state=(await ks.get_state()).value)
```

Stub `events/bus.py` (Task 8 replaces internals, keeps `publish` signature):

```python
# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations


class EventBus:
    def __init__(self) -> None:
        self.published: list[dict] = []

    def publish(self, event: dict) -> None:
        self.published.append(event)
```

`events/__init__.py`: SPDX line.

- [ ] **Step 4: Run tests — PASS; lint; commit**

```bash
uv run pytest control-plane/tests/test_dashboard_actions.py -v && uv run ruff check control-plane/src
git add control-plane/src/control_plane/domains/dashboard control-plane/tests/test_dashboard_actions.py
git commit -m "feat(dashboard): action endpoints — approve/reject, kill-switch, audit rows"
```

---

### Task 8: SSE — EventBus, PollBridge, events endpoint

**Files:**
- Modify: `.../dashboard/events/bus.py` (real implementation), `core/http/app.py` (unconditional router imports)
- Create: `.../dashboard/events/bridge.py`, `.../dashboard/http/router_events.py`
- Test: `control-plane/tests/test_dashboard_events.py`

- [ ] **Step 1: Write failing tests**

```python
# SPDX-License-Identifier: AGPL-3.0-or-later
import asyncio
import datetime as dt

from control_plane.domains.dashboard.events.bridge import PollBridge
from control_plane.domains.dashboard.events.bus import EventBus


async def test_bus_fanout_to_two_subscribers():
    bus = EventBus()
    async with bus.subscribe() as q1, bus.subscribe() as q2:
        bus.publish({"type": "x"})
        assert (await asyncio.wait_for(q1.get(), 1))["type"] == "x"
        assert (await asyncio.wait_for(q2.get(), 1))["type"] == "x"


async def test_bus_slow_subscriber_dropped_not_blocking():
    bus = EventBus(max_queue=2)
    async with bus.subscribe():
        for i in range(10):           # overflow queue; publish must never block
            bus.publish({"type": "x", "i": i})


async def test_bridge_emits_finding_status_changed_on_diff():
    bus = EventBus()
    rows = [
        [{"id": "f1", "status": "hypothesis", "updated_at": dt.datetime.now(dt.UTC)}],
        [{"id": "f1", "status": "validated", "updated_at": dt.datetime.now(dt.UTC)}],
    ]
    calls = {"n": 0}

    async def fake_fetch():
        out = rows[min(calls["n"], 1)]
        calls["n"] += 1
        return out

    bridge = PollBridge(pool=None, bus=bus, interval_seconds=0.01, fetch_findings=fake_fetch)
    async with bus.subscribe() as q:
        await bridge.start()
        evt = await asyncio.wait_for(q.get(), 2)
        await bridge.stop()
    assert evt["type"] == "finding_status_changed"
    assert evt["finding_id"] == "f1" and evt["status"] == "validated"
```

- [ ] **Step 2: Run to verify failure, then implement bus.py (replace stub) + bridge.py**

`bus.py`:

```python
# SPDX-License-Identifier: AGPL-3.0-or-later
"""In-process fan-out bus for dashboard SSE clients.

publish() never blocks: a full subscriber queue drops the event for that
subscriber (clients self-heal via REST polling — design §data-flow).
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator


class EventBus:
    def __init__(self, max_queue: int = 256) -> None:
        self._max_queue = max_queue
        self._subscribers: set[asyncio.Queue[dict]] = set()

    @contextlib.asynccontextmanager
    async def subscribe(self) -> AsyncIterator[asyncio.Queue[dict]]:
        q: asyncio.Queue[dict] = asyncio.Queue(maxsize=self._max_queue)
        self._subscribers.add(q)
        try:
            yield q
        finally:
            self._subscribers.discard(q)

    def publish(self, event: dict) -> None:
        for q in self._subscribers:
            with contextlib.suppress(asyncio.QueueFull):
                q.put_nowait(event)
```

(Task 7's test asserted `bus.published` on the stub — update that test in THIS task to subscribe instead, or have it assert via a subscriber queue. Do whichever keeps Task 7 tests green; the stub's `published` list is gone.)

`bridge.py`:

```python
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Poll bridge: diffs hot tables → synthesizes SSE events.

v1 has no NOTIFY emitters in agents; this bridge is the event source.
Tracks findings (id → status) and pending approval_queue keys between
ticks and publishes diffs. Cheap: two indexed queries per tick.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Awaitable, Callable

from .bus import EventBus

FetchFn = Callable[[], Awaitable[list]]


class PollBridge:
    def __init__(
        self,
        pool,
        bus: EventBus,
        interval_seconds: float = 3.0,
        fetch_findings: FetchFn | None = None,
        fetch_approvals: FetchFn | None = None,
    ) -> None:
        self._bus = bus
        self._interval = interval_seconds
        self._task: asyncio.Task | None = None
        self._known_findings: dict[str, str] = {}
        self._known_pending: set[str] = set()
        self._primed = False
        self._fetch_findings = fetch_findings or self._default_fetch_findings(pool)
        self._fetch_approvals = fetch_approvals or self._default_fetch_approvals(pool)

    @staticmethod
    def _default_fetch_findings(pool) -> FetchFn:
        async def fetch():
            return await pool.fetch(
                "SELECT id::text AS id, status::text AS status, updated_at "
                "FROM findings WHERE updated_at > now() - interval '1 hour'"
            )
        return fetch

    @staticmethod
    def _default_fetch_approvals(pool) -> FetchFn:
        async def fetch():
            return await pool.fetch(
                "SELECT finding_id::text AS finding_id, tier "
                "FROM approval_queue WHERE status = 'pending'"
            )
        return fetch

    async def start(self) -> None:
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task

    async def _loop(self) -> None:
        while True:
            with contextlib.suppress(Exception):  # one bad tick never kills the bridge
                await self._tick()
            await asyncio.sleep(self._interval)

    async def _tick(self) -> None:
        findings = {r["id"]: r["status"] for r in await self._fetch_findings()}
        pending = {r["finding_id"] for r in await self._fetch_approvals()}
        if self._primed:
            for fid, status in findings.items():
                if self._known_findings.get(fid) != status:
                    self._bus.publish(
                        {"type": "finding_status_changed", "finding_id": fid, "status": status}
                    )
            for fid in pending - self._known_pending:
                self._bus.publish({"type": "approval_requested", "finding_id": fid})
        self._known_findings.update(findings)
        self._known_pending = pending
        self._primed = True
```

`router_events.py`:

```python
# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Request
from sse_starlette.sse import EventSourceResponse

from .deps import current_user, get_event_bus

router = APIRouter(prefix="/api/dashboard", tags=["dashboard-events"])


@router.get("/events", dependencies=[Depends(current_user)])
async def events(request: Request, bus=Depends(get_event_bus)):
    async def stream():
        async with bus.subscribe() as q:
            while True:
                if await request.is_disconnected():
                    return
                event = await q.get()
                yield {"event": event["type"], "data": json.dumps(event)}

    return EventSourceResponse(stream(), ping=15)
```

- [ ] **Step 3: Remove the `try/except ImportError` scaffolding in `core/http/app.py`** — all four routers now exist; imports become unconditional (delete the `try:` / `except ImportError: pass`).

- [ ] **Step 4: Run FULL backend suite — everything green; lint; commit**

```bash
uv run pytest control-plane/tests/ -v
uv run ruff check control-plane/src
git add -A control-plane/src/control_plane control-plane/tests/test_dashboard_events.py control-plane/tests/test_dashboard_actions.py
git commit -m "feat(dashboard): SSE — event bus, poll bridge, events endpoint"
```

---

### Task 9: SPA scaffold + auth + API client

**Files:**
- Create: `dashboard/` (Vite scaffold), `dashboard/src/api/client.ts`, `dashboard/src/api/types.ts`, `dashboard/src/auth.tsx`, `dashboard/src/pages/Login.tsx`, `dashboard/src/main.tsx`, `dashboard/src/router.tsx`
- Test: `dashboard/src/api/client.test.ts`

- [ ] **Step 1: Scaffold**

```bash
npm create vite@latest dashboard -- --template react-ts
cd dashboard
npm install
npm install @tanstack/react-query @tanstack/react-router
npm install -D tailwindcss @tailwindcss/vite vitest @testing-library/react @testing-library/user-event jsdom @vitest/coverage-v8
npx shadcn@latest init -d
npx shadcn@latest add button card table badge sheet input sonner
```

Add to `vite.config.ts`: Tailwind plugin + dev proxy + vitest config:

```ts
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: { proxy: { "/api": "http://localhost:8000" } },
  test: { environment: "jsdom", globals: true },
});
```

Add ESLint guard (spec security invariant) to `eslint.config.js` rules:

```js
"react/no-danger": "error",
"no-restricted-properties": ["error", {
  object: "React", property: "dangerouslySetInnerHTML",
  message: "poc_text and all API strings must render as text (XSS bait)",
}],
```

(`react/no-danger` needs `eslint-plugin-react`: `npm install -D eslint-plugin-react`.)

- [ ] **Step 2: Write failing client test**

`dashboard/src/api/client.test.ts`:

```ts
import { describe, expect, it, vi, beforeEach } from "vitest";
import { api, setCsrfToken } from "./client";

describe("api client", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ ok: 1 }), { status: 200 })));
  });

  it("sends X-CSRF-Token on POST after setCsrfToken", async () => {
    setCsrfToken("tok123");
    await api.post("/api/dashboard/auth/logout", {});
    const [, init] = (fetch as ReturnType<typeof vi.fn>).mock.calls[0];
    expect((init.headers as Record<string, string>)["X-CSRF-Token"]).toBe("tok123");
    expect(init.credentials).toBe("include");
  });

  it("throws ApiError with envelope code on non-2xx", async () => {
    vi.stubGlobal("fetch", vi.fn(async () =>
      new Response(JSON.stringify({ error: { code: "csrf", message: "bad" } }), { status: 403 })));
    await expect(api.post("/x", {})).rejects.toMatchObject({ code: "csrf", status: 403 });
  });
});
```

- [ ] **Step 3: Run `npx vitest run` — FAIL; implement client.ts + types.ts**

`client.ts`:

```ts
let csrfToken: string | null = null;
export function setCsrfToken(t: string | null) { csrfToken = t; }

export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string) {
    super(message);
  }
}

async function request<T>(method: string, url: string, body?: unknown): Promise<T> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (method !== "GET" && csrfToken) headers["X-CSRF-Token"] = csrfToken;
  const resp = await fetch(url, {
    method, headers, credentials: "include",
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (resp.status === 204) return undefined as T;
  const data = await resp.json().catch(() => ({}));
  if (!resp.ok) {
    const err = data?.error ?? { code: "error", message: `HTTP ${resp.status}` };
    if (resp.status === 401 && !url.endsWith("/auth/me")) window.location.assign("/login");
    throw new ApiError(resp.status, err.code, err.message);
  }
  return data as T;
}

export const api = {
  get: <T>(url: string) => request<T>("GET", url),
  post: <T>(url: string, body: unknown) => request<T>("POST", url, body),
};
```

`types.ts` — mirror schemas.py exactly (write all of them):

```ts
export interface Me { username: string; role: "viewer" | "operator"; csrf_token: string }
export interface Overview {
  findings_by_status: Record<string, number>;
  pending_approvals: number;
  worst_sla_seconds: number | null;
  kill_switch: string;
  active_programs: string[];
}
export interface ProgramPipeline {
  program_handle: string;
  stages: Record<"scan" | "exploit" | "validate" | "report" | "terminal", number>;
  recon_assets: number;
}
export interface ActivityItem {
  ts: string; actor: string; action: string; resource: string | null;
  payload: Record<string, unknown> | null;
}
export interface Hunts { programs: ProgramPipeline[]; recent_activity: ActivityItem[] }
export interface FindingRow {
  id: string; program_handle: string | null; platform: string | null; cwe: string | null;
  url: string | null; status: string; stage: string; created_at: string;
}
export interface FindingsPage { items: FindingRow[]; total: number; limit: number; offset: number }
export interface AuditEntry { entry_type: string; payload: Record<string, unknown>; created_at: string }
export interface FindingDetail extends FindingRow {
  parameter: string | null; oracle_method: string | null; evidence_hash: string | null;
  audit_entries: AuditEntry[];
}
export interface ApprovalItem {
  finding_id: string; tier: "T0" | "T1" | "T2" | "T3"; poc_text: string | null;
  requested_at: string; expires_at: string; sla_seconds: number;
  program_handle: string | null; cwe: string | null; url: string | null;
  needs_second_approver: boolean;
}
export interface Approvals { items: ApprovalItem[] }
export interface DecisionResponse {
  finding_id: string; status: "approved" | "rejected" | "pending_second_approval";
}
export interface KillSwitch { state: "inactive" | "halt_submissions" | "halt_scans" | "halt_all" }
```

- [ ] **Step 4: Implement auth.tsx + Login.tsx + router.tsx + main.tsx**

`auth.tsx` — context with `me`, `login(u,p)`, `logout()`; `login` POSTs, calls `setCsrfToken(me.csrf_token)`, stores `me` in state; on app mount GET `/auth/me` to restore session (and re-set CSRF token). `RequireAuth` wrapper redirects to `/login` when `me === null` after load. `RequireOperator` renders children only when `me.role === "operator"` (else nothing — viewers see read-only UI).

```tsx
import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { api, setCsrfToken } from "./api/client";
import type { Me } from "./api/types";

interface AuthCtx {
  me: Me | null; loading: boolean;
  login: (u: string, p: string) => Promise<void>;
  logout: () => Promise<void>;
}
const Ctx = createContext<AuthCtx>(null!);
export const useAuth = () => useContext(Ctx);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [me, setMe] = useState<Me | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.get<Me>("/api/dashboard/auth/me")
      .then((m) => { setCsrfToken(m.csrf_token); setMe(m); })
      .catch(() => setMe(null))
      .finally(() => setLoading(false));
  }, []);

  const login = async (username: string, password: string) => {
    const m = await api.post<Me>("/api/dashboard/auth/login", { username, password });
    setCsrfToken(m.csrf_token); setMe(m);
  };
  const logout = async () => {
    await api.post("/api/dashboard/auth/logout", {});
    setCsrfToken(null); setMe(null);
  };
  return <Ctx.Provider value={{ me, loading, login, logout }}>{children}</Ctx.Provider>;
}

export function RequireOperator({ children }: { children: ReactNode }) {
  const { me } = useAuth();
  return me?.role === "operator" ? <>{children}</> : null;
}
```

`Login.tsx` — shadcn Card + Input + Button form; on submit call `login`; on `ApiError` show the message under the form; navigate to `/` on success.

`router.tsx` — TanStack Router code-based routes: `/login` → Login; layout route (sidebar nav: Overview, Approvals, Hunts, Findings + username + logout) guarding auth → children `/`, `/approvals`, `/hunts`, `/findings`. Page components are placeholder `<div>` stubs in THIS task; Tasks 11–13 fill them. `main.tsx` wires `QueryClientProvider` (defaults: `refetchInterval` set per-query later, `retry: 1`) + `AuthProvider` + `RouterProvider` + sonner `<Toaster/>`.

- [ ] **Step 5: Verify and commit**

```bash
cd dashboard && npx vitest run && npm run build && npx eslint src && cd ..
git add dashboard
git commit -m "feat(dashboard): SPA scaffold — Vite/React/Tailwind/shadcn, auth, typed API client"
```

Expected: vitest 2 passed, `vite build` completes, eslint clean.

---

### Task 10: Overview page + SSE hook + activity feed

**Files:**
- Create: `dashboard/src/sse.ts`, `dashboard/src/pages/Overview.tsx`, `dashboard/src/components/ActivityFeed.tsx`, `dashboard/src/components/KillSwitchBanner.tsx`
- Modify: `dashboard/src/router.tsx` (mount real Overview)
- Test: `dashboard/src/sse.test.ts`

- [ ] **Step 1: Write failing SSE hook test** — mock `EventSource` global; assert events dispatch to handler and that close+reopen happens after `onerror` (backoff scheduled via `setTimeout`; use `vi.useFakeTimers()`).

- [ ] **Step 2: Implement sse.ts**

```ts
import { useEffect, useRef, useState } from "react";

export type DashboardEvent = { type: string; [k: string]: unknown };

export function useEventStream(onEvent: (e: DashboardEvent) => void) {
  const [connected, setConnected] = useState(false);
  const handler = useRef(onEvent);
  handler.current = onEvent;

  useEffect(() => {
    let es: EventSource | null = null;
    let retry = 1000;
    let timer: ReturnType<typeof setTimeout>;
    let closed = false;

    const open = () => {
      es = new EventSource("/api/dashboard/events");
      es.onopen = () => { setConnected(true); retry = 1000; };
      es.onmessage = (m) => handler.current(JSON.parse(m.data));
      // sse-starlette sends named events; listen for each type we emit
      for (const t of ["finding_status_changed", "approval_requested",
                       "approval_decided", "killswitch_changed", "agent_activity"]) {
        es.addEventListener(t, (m) => handler.current(JSON.parse((m as MessageEvent).data)));
      }
      es.onerror = () => {
        setConnected(false);
        es?.close();
        if (!closed) { timer = setTimeout(open, retry); retry = Math.min(retry * 2, 30000); }
      };
    };
    open();
    return () => { closed = true; clearTimeout(timer); es?.close(); };
  }, []);

  return { connected };
}
```

- [ ] **Step 3: Implement Overview page**

`Overview.tsx`: three queries — `overview` (`refetchInterval: 10_000`), killswitch (`refetchInterval: 5_000`), and a local `events: DashboardEvent[]` state fed by `useEventStream` (cap 100 entries, newest first; on `approval_*` / `finding_*` events call `queryClient.invalidateQueries({queryKey:["overview"]})` and `["approvals"]`). Layout: `KillSwitchBanner` (red full-width banner when state ≠ inactive, shows state name), 4 stat cards (active programs count, total non-terminal findings, pending approvals + worst SLA countdown, kill-switch state), stage funnel (5 labeled count bars computed from `findings_by_status` via a `stageOf()` map duplicated in `types.ts` — copy STAGE_BY_STATUS values from Task 6 exactly), `ActivityFeed` right rail listing events + "feed disconnected — polling continues" amber banner when `!connected`.

`ActivityFeed.tsx` renders event rows as `<span className="font-mono text-xs">{JSON.stringify(...)}</span>`-free human lines: map event type → text (`finding_status_changed` → `Finding ${id8} → ${status}`). ALL strings rendered as React text nodes (auto-escaped) — never `dangerouslySetInnerHTML` (lint enforces).

- [ ] **Step 4: Verify and commit**

```bash
cd dashboard && npx vitest run && npm run build && npx eslint src && cd ..
git add dashboard && git commit -m "feat(dashboard): overview page, SSE hook with backoff, activity feed"
```

---

### Task 11: Approvals page — table, drawer, approve/reject

**Files:**
- Create: `dashboard/src/pages/Approvals.tsx`, `dashboard/src/components/ApprovalDrawer.tsx`
- Test: `dashboard/src/components/ApprovalDrawer.test.tsx`

- [ ] **Step 1: Write failing drawer tests** (Testing Library; mock `api`):
1. renders `poc_text` inside a `<pre>` — assert `screen.getByText(/<script>alert/)` appears as TEXT (pass a poc containing `<script>alert(1)</script>` and assert `document.querySelector("script")` is null).
2. Approve button disabled until confirm step: first click shows "Confirm approve" + reason input; second click calls `api.post` with `/approve` and reason.
3. Reject requires non-empty reason (button disabled when reason empty).
4. When `api.post` rejects with `ApiError(409, "approval_conflict", ...)` → drawer shows the conflict message and calls `onDecided` (parent refetch).
5. `needs_second_approver` renders the "awaiting second approver" badge.
6. Viewer role (mock `useAuth` returning viewer): no Approve/Reject buttons rendered.

- [ ] **Step 2: Run `npx vitest run` — FAIL; implement**

`Approvals.tsx`: `useQuery({queryKey: ["approvals"], queryFn, refetchInterval: 10_000})`; shadcn Table: tier Badge (T3 red, T2 amber, T1/T0 gray), finding id (8 chars), program, cwe, SLA countdown (`sla_seconds` rendered live with a 1 s ticker, red when negative), age. Row click opens `ApprovalDrawer` (shadcn Sheet).

`ApprovalDrawer.tsx`: props `{item: ApprovalItem, onClose(), onDecided()}`. Shows program/cwe/url/tier/SLA + `poc_text` in `<pre className="whitespace-pre-wrap font-mono text-xs ...">{item.poc_text}</pre>`. Two-step confirm: local state `mode: null | "approve" | "reject"`; reason `<Input>`; submit calls `useMutation` → `api.post(.../approve|reject, {reason})`; on success toast (`approved` / `pending_second_approval` → "recorded — awaiting second approver" / `rejected`), `onDecided()` invalidates `["approvals"]` + `["overview"]`. On `ApiError` 409: toast error message + `onDecided()` (refetch shows decided state). Buttons wrapped in `<RequireOperator>`.

- [ ] **Step 3: Verify and commit**

```bash
cd dashboard && npx vitest run && npm run build && npx eslint src && cd ..
git add dashboard && git commit -m "feat(dashboard): approvals action center — table, drawer, two-step decide"
```

---

### Task 12: Hunt monitor + kill-switch control + findings pages

**Files:**
- Create: `dashboard/src/pages/Hunts.tsx`, `dashboard/src/components/KillSwitchControl.tsx`, `dashboard/src/pages/Findings.tsx`, `dashboard/src/components/FindingDrawer.tsx`
- Test: `dashboard/src/components/KillSwitchControl.test.tsx`

- [ ] **Step 1: Write failing kill-switch tests**:
1. Engaging requires picking a tier + non-empty reason + typed confirmation: button disabled until reason filled AND a text input matches the literal target state string (e.g. user must type `halt_all`).
2. Success path calls `api.post("/api/dashboard/killswitch", {state, reason})` and shows the server-confirmed state from the response (NOT the optimistic one).
3. On `ApiError` → persistent red error box rendered (role="alert"), not a toast.
4. Viewer role → control not rendered.

- [ ] **Step 2: Implement**

`KillSwitchControl.tsx`: shows current state (query `["killswitch"]`, `refetchInterval: 5_000`); tier select (4 states with the §6.6 descriptions: T1 halt_submissions / T2 halt_scans / T3 halt_all / inactive=clear); reason input; type-to-confirm input; red Button. Mutation success → invalidate `["killswitch"]` + `["overview"]`; render state ONLY from query data. Error → `<div role="alert">` persistent until next successful state fetch.

`Hunts.tsx`: query `["hunts"]` `refetchInterval: 15_000`. Per program: card with 6 columns (recon `recon_assets` + the 5 stages) as count chips; recent_activity list below grouped by `actor`; `KillSwitchControl` in a top-right card wrapped in `<RequireOperator>` (viewers still see state via banner/overview).

`Findings.tsx`: filter selects (status — the 20 enum values, program — from overview `active_programs`, cwe — free text input), table (id8, program, cwe, stage Badge, status, created), pagination Prev/Next via offset. Row click → `FindingDrawer`: detail fields + audit chain entries listed as `entry_type @ created_at` with `payload` pretty-printed inside `<pre>` (text only).

- [ ] **Step 3: Verify and commit**

```bash
cd dashboard && npx vitest run && npm run build && npx eslint src && cd ..
git add dashboard && git commit -m "feat(dashboard): hunt monitor, kill-switch control, findings browser"
```

---

### Task 13: Backend integration tests (live DB flow)

**Files:**
- Create: `tests/integration/test_dashboard_e2e.py`

- [ ] **Step 1: Write the integration flow test**

Marked `@pytest.mark.integration`; needs live Postgres with migrations 00–14 applied. Uses `httpx.ASGITransport` against `create_app()` (REAL lifespan: set `KILL_SWITCH_BACKEND=memory` env for the test). Flow:

```python
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Live-DB dashboard flow: create user -> login -> see approval -> approve -> audit row."""

import os
import uuid

import asyncpg
import httpx
import pytest

from control_plane.domains.approval_gate import ApprovalTier, queue_enqueue
from control_plane.domains.dashboard.auth import hash_password

pytestmark = pytest.mark.integration


@pytest.fixture
async def db():
    conn = await asyncpg.connect(os.environ["DATABASE_URL"].replace("+asyncpg", ""))
    yield conn
    await conn.close()


@pytest.fixture
async def app_client(db, monkeypatch):
    monkeypatch.setenv("KILL_SWITCH_BACKEND", "memory")
    from control_plane.core.http.app import create_app

    app = create_app()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://t"
    ) as client, app.router.lifespan_context(app):
        yield client


async def test_login_approve_audit_flow(db, app_client):
    suffix = uuid.uuid4().hex[:8]
    username = f"it-op-{suffix}"
    await db.execute(
        "INSERT INTO dashboard_users (username, password_hash, role) VALUES ($1, $2, 'operator')",
        username, hash_password("integration-pass-123"),
    )
    fid = await db.fetchval(
        "INSERT INTO findings (program_handle, platform, cwe, url, status) "
        "VALUES ($1, 'h1', 'CWE-79', 'https://x.test/p', 'validated') RETURNING id",
        f"it-prog-{suffix}",
    )
    await queue_enqueue(db, fid, ApprovalTier.T2, poc_text="poc body")
    try:
        login = await app_client.post(
            "/api/dashboard/auth/login",
            json={"username": username, "password": "integration-pass-123"},
        )
        assert login.status_code == 200
        csrf = login.json()["csrf_token"]

        approvals = await app_client.get("/api/dashboard/approvals")
        assert any(i["finding_id"] == str(fid) for i in approvals.json()["items"])

        decided = await app_client.post(
            f"/api/dashboard/approvals/{fid}/approve",
            json={"reason": "integration test"},
            headers={"X-CSRF-Token": csrf},
        )
        assert decided.status_code == 200 and decided.json()["status"] == "approved"

        audit = await db.fetchrow(
            "SELECT actor, action FROM dashboard_audit_log "
            "WHERE resource = $1 ORDER BY ts DESC LIMIT 1",
            f"finding:{fid}",
        )
        assert audit["actor"] == username and audit["action"] == "approval.approve"

        viewer_block = await app_client.post(
            f"/api/dashboard/approvals/{fid}/reject",
            json={"reason": "x"}, headers={"X-CSRF-Token": csrf},
        )
        assert viewer_block.status_code == 409  # already decided -> conflict (operator)
    finally:
        await db.execute("DELETE FROM findings WHERE id = $1", fid)        # cascades queue
        await db.execute("DELETE FROM dashboard_users WHERE username = $1", username)
```

- [ ] **Step 2: Run against local stack**

```bash
docker compose -f infra/docker/docker-compose.yml up -d postgres redis
uv run pytest tests/integration/test_dashboard_e2e.py -m integration -v
```

Expected: PASS. (Same fallback rule as Task 1 if no live stack this session.)

- [ ] **Step 3: Commit**

```bash
git add tests/integration/test_dashboard_e2e.py
git commit -m "test(dashboard): live-DB integration flow — login, approve, audit"
```

---

### Task 14: Deployment — Caddy static route, compose wiring, smoke

**Files:**
- Modify: `infra/docker/Caddyfile`, `infra/docker/docker-compose.yml`
- Create: `dashboard/e2e/smoke.spec.ts`, `dashboard/playwright.config.ts`

- [ ] **Step 1: Caddyfile — add SPA route (keep existing /api, /langfuse, /hatchet blocks UNCHANGED; replace only the root `handle` block)**

```caddyfile
    # Operator dashboard SPA (built bundle volume-mounted at /srv/dashboard)
    handle {
        root * /srv/dashboard
        try_files {path} /index.html
        file_server
    }
```

(Caddy `handle` without path matcher is the fallback — declared LAST so /api//langfuse//hatchet keep winning. Delete the old `respond "BountyStrike v5 — solo stack up" 200` root block.)

- [ ] **Step 2: docker-compose — wire control-plane + caddy**

In `infra/docker/docker-compose.yml`:
- `control-plane` service: add/confirm `command: uvicorn control_plane.main:app --host 0.0.0.0 --port 8000` and `ports: ["8000:8000"]` (Caddy proxies to `host.docker.internal:8000` per existing Caddyfile — keep that contract; alternatively switch the Caddyfile to `reverse_proxy control-plane:8000` if the service is on the same compose network — pick whichever matches how control-plane currently runs, verify with `docker compose config`).
- `caddy` service: add volume `../../dashboard/dist:/srv/dashboard:ro`.
- Document in compose comments: `dashboard/dist` must exist (`cd dashboard && npm run build`).

- [ ] **Step 3: Playwright smoke**

```bash
cd dashboard && npm install -D @playwright/test && npx playwright install chromium
```

`dashboard/playwright.config.ts`:

```ts
import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir: "./e2e",
  use: { baseURL: process.env.DASH_URL ?? "http://localhost" },
});
```

`dashboard/e2e/smoke.spec.ts`:

```ts
import { expect, test } from "@playwright/test";

// Requires: stack up, migrations applied, user created:
//   DATABASE_URL=... python scripts/dashboard_user.py create smoke-op --role operator
//   (password via SMOKE_PASSWORD env)
test("login -> overview renders -> approvals page reachable", async ({ page }) => {
  await page.goto("/login");
  await page.fill('input[name="username"]', "smoke-op");
  await page.fill('input[name="password"]', process.env.SMOKE_PASSWORD ?? "");
  await page.click('button[type="submit"]');
  await expect(page.getByText(/pending approvals/i)).toBeVisible({ timeout: 10_000 });
  await page.goto("/approvals");
  await expect(page.getByRole("table")).toBeVisible();
});
```

- [ ] **Step 4: Live verification**

```bash
cd dashboard && npm run build && cd ..
docker compose -f infra/docker/docker-compose.yml up -d
docker compose -f infra/docker/docker-compose.yml exec -T postgres \
  psql -U bountystrike -d bountystrike < infra/sql/14_dashboard_auth.sql
DATABASE_URL=postgresql://... python scripts/dashboard_user.py create smoke-op --role operator
cd dashboard && SMOKE_PASSWORD=... npx playwright test && cd ..
uv run pytest tests/integration/ -m integration -v
```

Expected: smoke green, integration suite green. This is the live gate for Tasks 1 and 13 if they were collection-only earlier.

- [ ] **Step 5: Commit**

```bash
git add infra/docker/Caddyfile infra/docker/docker-compose.yml dashboard/e2e dashboard/playwright.config.ts dashboard/package.json dashboard/package-lock.json
git commit -m "feat(dashboard): deploy — Caddy SPA route, compose wiring, Playwright smoke"
```

---

## Post-plan notes for the executor

- **OpenWolf bookkeeping** (project rule): after each task, append one line to `.wolf/memory.md`; after creating files, add entries to `.wolf/anatomy.md`. Log any failed test/build to `.wolf/buglog.json`.
- **Ruff** runs over the whole repo in CI: `uv run ruff check .` before every commit.
- Deferred (NOT in this plan, by spec): hunt-launch UI, cost/EV analytics, full findings browser features, OIDC, NOTIFY emitters inside agents, hash-chain audit append for dashboard decisions.
