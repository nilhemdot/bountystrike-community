"""Unit tests for scripts.filter_unreflected_findings.

Exercises the core ``filter_unreflected`` function against a mock asyncpg
connection and a scripted prober, mirroring the test patterns in
control-plane/tests/test_recon.py.
"""

from __future__ import annotations

import os
import sys
import uuid
from typing import Any

import pytest

# Make scripts/ + control-plane/src importable in this test process.
ROOT = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, os.path.join(ROOT, "control-plane", "src"))
sys.path.insert(0, ROOT)

from scripts.filter_unreflected_findings import (  # noqa: E402
    FP_CLASS_TAG,
    FilterResult,
    _inject_param,
    filter_unreflected,
)


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class _FakeConn:
    """asyncpg.Connection stand-in — records SQL + serves canned fetches."""

    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows
        self.executed: list[tuple[str, tuple]] = []

    async def fetch(self, sql: str, *args: Any) -> list[dict[str, Any]]:
        del sql, args
        return list(self._rows)

    async def execute(self, sql: str, *args: Any) -> None:
        self.executed.append((sql, args))


class _ScriptedProber:
    def __init__(self, reflects: dict[tuple[str, str], bool]) -> None:
        self.reflects = reflects
        self.calls: list[tuple[str, str]] = []

    async def probe(self, url: str, parameter: str, sentinel: str) -> bool:
        del sentinel
        self.calls.append((url, parameter))
        # Match by the URL path + param so callers can ignore the random sentinel.
        from urllib.parse import urlparse

        path = urlparse(url).path
        return self.reflects.get((path, parameter), False)


class _BoomProber:
    async def probe(self, url: str, parameter: str, sentinel: str) -> bool:
        del url, parameter, sentinel
        raise RuntimeError("network exploded")


# ---------------------------------------------------------------------------
# _inject_param helper
# ---------------------------------------------------------------------------


def test_inject_param_replaces_existing_value():
    out = _inject_param("https://x/a?tab=foo", "tab", "SENT")
    assert "tab=SENT" in out
    assert "tab=foo" not in out


def test_inject_param_adds_when_absent():
    out = _inject_param("https://x/a", "q", "SENT")
    assert out.endswith("?q=SENT")


# ---------------------------------------------------------------------------
# filter_unreflected core
# ---------------------------------------------------------------------------


async def test_filter_drops_unreflected_xss_candidate():
    rows = [
        {
            "id": uuid.uuid4(),
            "url": "https://mariadb.org/download?tab=mariadb",
            "parameter": "tab",
        }
    ]
    conn = _FakeConn(rows)
    prober = _ScriptedProber(reflects={})  # nothing reflects → drop

    result = await filter_unreflected(conn, uuid.uuid4(), prober)

    assert result == FilterResult(total=1, dropped=1, kept=0, errors=0, dry_run=False)
    # One UPDATE SQL fired with the FP_CLASS_TAG.
    assert len(conn.executed) == 1
    sql, args = conn.executed[0]
    assert "UPDATE findings" in sql
    assert "rejected" in sql
    assert args[1] == FP_CLASS_TAG


async def test_filter_keeps_reflected_xss_candidate():
    finding_id = uuid.uuid4()
    rows = [
        {
            "id": finding_id,
            "url": "https://acme.example/search?q=hello",
            "parameter": "q",
        }
    ]
    conn = _FakeConn(rows)
    prober = _ScriptedProber(reflects={("/search", "q"): True})

    result = await filter_unreflected(conn, uuid.uuid4(), prober)

    assert result == FilterResult(total=1, dropped=0, kept=1, errors=0, dry_run=False)
    # No UPDATEs when the row reflects.
    assert conn.executed == []


async def test_filter_dry_run_does_not_write():
    rows = [
        {
            "id": uuid.uuid4(),
            "url": "https://x/a?p=v",
            "parameter": "p",
        }
    ]
    conn = _FakeConn(rows)
    prober = _ScriptedProber(reflects={})

    result = await filter_unreflected(conn, uuid.uuid4(), prober, dry_run=True)

    assert result == FilterResult(total=1, dropped=1, kept=0, errors=0, dry_run=True)
    # dry_run path must NOT execute any UPDATEs.
    assert conn.executed == []


async def test_filter_treats_probe_error_as_no_reflection():
    rows = [
        {
            "id": uuid.uuid4(),
            "url": "https://x/a?p=v",
            "parameter": "p",
        }
    ]
    conn = _FakeConn(rows)

    result = await filter_unreflected(conn, uuid.uuid4(), _BoomProber())

    # Probe raised → treat as no-reflection (safe default), drop the row.
    assert result.dropped == 1
    assert result.errors == 1
    assert len(conn.executed) == 1


async def test_filter_zero_rows_returns_empty_summary():
    conn = _FakeConn(rows=[])
    prober = _ScriptedProber(reflects={})

    result = await filter_unreflected(conn, uuid.uuid4(), prober)

    assert result == FilterResult(total=0, dropped=0, kept=0, errors=0, dry_run=False)
    assert conn.executed == []


async def test_filter_mixed_batch_handles_each_independently():
    drop_id = uuid.uuid4()
    keep_id = uuid.uuid4()
    rows = [
        {"id": drop_id, "url": "https://x/a?p=v", "parameter": "p"},
        {"id": keep_id, "url": "https://x/b?q=v", "parameter": "q"},
    ]
    conn = _FakeConn(rows)
    prober = _ScriptedProber(reflects={("/b", "q"): True})

    result = await filter_unreflected(conn, uuid.uuid4(), prober, concurrency=2)

    assert result.total == 2
    assert result.dropped == 1
    assert result.kept == 1
    assert len(conn.executed) == 1
    assert conn.executed[0][1][0] == drop_id  # the dropped row id


@pytest.mark.parametrize("concurrency", [1, 4, 32])
async def test_filter_respects_concurrency_param(concurrency: int):
    rows = [
        {"id": uuid.uuid4(), "url": f"https://x/{i}?p=v", "parameter": "p"}
        for i in range(10)
    ]
    conn = _FakeConn(rows)
    prober = _ScriptedProber(reflects={})

    result = await filter_unreflected(conn, uuid.uuid4(), prober, concurrency=concurrency)

    # Concurrency only affects scheduling, not totals.
    assert result.total == 10
    assert result.dropped == 10
