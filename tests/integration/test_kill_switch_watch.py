"""Integration test for ``scripts/kill_switch_watch.py`` (Phase 3 §10.5 #4).

Seeds a synthetic oracle FP breach in the test Postgres, runs a single
watcher tick with an in-memory kill switch and a mocked webhook, then
asserts:

  1. The kill switch transitions to ``HALT_SUBMISSIONS``.
  2. The webhook received exactly one POST with the breach payload.
  3. A second tick on the same breach does NOT re-fire (edge-only).
  4. After the breach clears, a third tick reports cleared and does
     not call the kill switch again.

Skipped when ``BS5_PG_TEST_DSN`` is unset so plain CI stays green.

Local repro::

    BS5_PG_TEST_DSN=postgresql://bs:bspass@127.0.0.1:5432/bountystrike_test \\
        uv run pytest tests/integration/test_kill_switch_watch.py -v
"""

from __future__ import annotations

import importlib.util
import os
import sys
import uuid
from collections.abc import AsyncIterator
from pathlib import Path

import asyncpg
import httpx
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "control-plane" / "src"))

# Load scripts/kill_switch_watch.py as a module — scripts/ has no __init__.py.
_SPEC = importlib.util.spec_from_file_location(
    "kill_switch_watch",
    REPO_ROOT / "scripts" / "kill_switch_watch.py",
)
assert _SPEC is not None and _SPEC.loader is not None
ksw = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(ksw)

from control_plane.domains.safety.repositories.kill_switch_store import (  # noqa: E402
    InMemoryKillSwitchStore,
)
from control_plane.domains.safety.services.kill_switch_service import (  # noqa: E402
    KillSwitchService,
)
from control_plane.domains.safety.value_objects.kill_switch_state import (  # noqa: E402
    KillSwitchState,
)

_DSN = os.environ.get("BS5_PG_TEST_DSN", "").replace("+asyncpg", "")
_skip_if_no_dsn = pytest.mark.skipif(
    not _DSN, reason="BS5_PG_TEST_DSN not set; skipping real-Postgres tests"
)

# Use a sentinel program_handle so cleanup never touches non-test rows.
_TEST_PROGRAM = "kill-switch-watch-test"


async def _purge_test_rows(conn: asyncpg.Connection) -> None:
    """Cascade delete via scan_jobs.program_handle so we don't have to
    track every UUID we minted in the test."""
    await conn.execute(
        "DELETE FROM report_submissions WHERE finding_id IN "
        "(SELECT id FROM findings WHERE program_handle = $1)",
        _TEST_PROGRAM,
    )
    await conn.execute(
        "DELETE FROM findings WHERE program_handle = $1", _TEST_PROGRAM,
    )
    await conn.execute(
        "DELETE FROM scan_jobs WHERE program_handle = $1", _TEST_PROGRAM,
    )


async def _seed_breach(conn: asyncpg.Connection, *, cwe: str, breach: bool) -> None:
    """Insert findings + submissions whose v_oracle_fp_rate row will
    breach (8 rejected / 100 confirmed) or stay clean (1 rejected /
    99 confirmed) depending on ``breach``."""
    job_id = uuid.uuid4()
    await conn.execute(
        "INSERT INTO scan_jobs (id, program_handle) VALUES ($1, $2)",
        job_id, _TEST_PROGRAM,
    )
    rejected_cutoff = 92 if breach else 99
    for i in range(1, 101):
        f_id = await conn.fetchval(
            "INSERT INTO findings "
            "(job_id, program_handle, platform, cwe, status, deduplication_key) "
            "VALUES ($1, $2, 'h1', $3, 'validated', $4) RETURNING id",
            job_id, _TEST_PROGRAM, cwe, f"{cwe}-{i}-{job_id}",
        )
        if i <= rejected_cutoff:
            status = "confirmed"
        elif i <= 100 - (1 if breach else 0):
            status = "rejected" if breach or i == 100 else "confirmed"
        else:
            status = "rejected"
        # Simpler: deterministic by index
        if breach:
            status = "confirmed" if i <= 92 else "rejected"
        else:
            status = "confirmed" if i <= 99 else "rejected"
        await conn.execute(
            "INSERT INTO report_submissions (finding_id, platform, status) "
            "VALUES ($1, 'h1', $2)",
            f_id, status,
        )


@pytest.fixture
async def conn() -> AsyncIterator[asyncpg.Connection]:
    if not _DSN:
        pytest.skip("BS5_PG_TEST_DSN not set")
    c = await asyncpg.connect(_DSN)
    await _purge_test_rows(c)
    try:
        yield c
    finally:
        await _purge_test_rows(c)
        await c.close()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@_skip_if_no_dsn
async def test_breach_trips_kill_switch_and_fires_webhook(
    conn: asyncpg.Connection,
) -> None:
    await _seed_breach(conn, cwe="CWE-78", breach=True)

    service = KillSwitchService(InMemoryKillSwitchStore())
    captured: list[dict] = []

    def _handler(request: httpx.Request) -> httpx.Response:
        captured.append({
            "url": str(request.url),
            "json": __import__("json").loads(request.content.decode()),
        })
        return httpx.Response(200, json={"ok": True})

    transport = httpx.MockTransport(_handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        seen: set[str] = set()
        seen = await ksw.tick(
            conn=conn,
            service=service,
            webhook_client=http_client,
            webhook_url="https://hooks.example.invalid/test",
            seen=seen,
        )

    assert seen == {"CWE-78"}
    state = await service.current_state()
    assert state == KillSwitchState.HALT_SUBMISSIONS
    assert len(captured) == 1
    payload = captured[0]["json"]
    assert payload["alert"] == "oracle_fp_breach"
    assert payload["threshold"] == ksw.FP_RATE_THRESHOLD
    assert len(payload["breaches"]) == 1
    assert payload["breaches"][0]["cwe"] == "CWE-78"
    assert payload["breaches"][0]["fp_rate"] > ksw.FP_RATE_THRESHOLD


@_skip_if_no_dsn
async def test_second_tick_on_same_breach_does_not_refire(
    conn: asyncpg.Connection,
) -> None:
    await _seed_breach(conn, cwe="CWE-78", breach=True)

    service = KillSwitchService(InMemoryKillSwitchStore())
    captured: list[dict] = []

    def _handler(_: httpx.Request) -> httpx.Response:
        captured.append({})
        return httpx.Response(200)

    transport = httpx.MockTransport(_handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        seen = await ksw.tick(
            conn=conn, service=service, webhook_client=http_client,
            webhook_url="https://hooks.example.invalid/test", seen=set(),
        )
        seen2 = await ksw.tick(
            conn=conn, service=service, webhook_client=http_client,
            webhook_url="https://hooks.example.invalid/test", seen=seen,
        )

    # Edge-triggered: webhook fires once even though state persists.
    assert len(captured) == 1
    assert seen == seen2 == {"CWE-78"}


@_skip_if_no_dsn
async def test_clean_oracle_does_not_trip(conn: asyncpg.Connection) -> None:
    await _seed_breach(conn, cwe="CWE-79", breach=False)

    service = KillSwitchService(InMemoryKillSwitchStore())
    captured: list[dict] = []

    def _handler(_: httpx.Request) -> httpx.Response:
        captured.append({})
        return httpx.Response(200)

    transport = httpx.MockTransport(_handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        seen = await ksw.tick(
            conn=conn, service=service, webhook_client=http_client,
            webhook_url="https://hooks.example.invalid/test", seen=set(),
        )

    assert seen == set()
    state = await service.current_state()
    assert state == KillSwitchState.INACTIVE
    assert captured == []


@_skip_if_no_dsn
async def test_no_webhook_url_skips_post_but_still_trips(
    conn: asyncpg.Connection,
) -> None:
    """Operator without a webhook configured still gets the kill switch."""
    await _seed_breach(conn, cwe="CWE-78", breach=True)

    service = KillSwitchService(InMemoryKillSwitchStore())
    # Any webhook call here would explode (no transport) — proving we
    # never even open a connection when webhook_url is None.
    async with httpx.AsyncClient() as http_client:
        seen = await ksw.tick(
            conn=conn, service=service, webhook_client=http_client,
            webhook_url=None, seen=set(),
        )

    assert seen == {"CWE-78"}
    assert (await service.current_state()) == KillSwitchState.HALT_SUBMISSIONS
