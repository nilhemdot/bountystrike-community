"""Tests for the recon container CLI entrypoint."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from control_plane.domains.recon import __main__ as recon_main


def _full_env(**overrides) -> dict[str, str]:
    base = {
        "SCOPE_JWT": "header.payload.sig",
        "PROGRAM_HANDLE": "acme-corp",
        "PLATFORM": "hackerone",
        "DATABASE_URL": "postgresql+asyncpg://x:y@h/db",
        "SCAN_JOB_ID": str(uuid.uuid4()),
        "SCOPE_JWT_PUBLIC_KEY_PATH": "/nope/key.pem",
    }
    base.update(overrides)
    return base


def test_require_env_lists_all_missing_vars():
    with pytest.raises(SystemExit) as excinfo:
        recon_main._require_env({"SCOPE_JWT": "x"})
    msg = str(excinfo.value)
    for missing in ("PROGRAM_HANDLE", "PLATFORM", "DATABASE_URL", "SCAN_JOB_ID"):
        assert missing in msg


def test_require_env_passes_when_complete():
    env = _full_env()
    out = recon_main._require_env(env)
    assert set(out) == {
        "SCOPE_JWT", "PROGRAM_HANDLE", "PLATFORM",
        "DATABASE_URL", "SCAN_JOB_ID",
    }


def test_validate_scope_jwt_aborts_when_key_missing(tmp_path):
    missing = tmp_path / "does_not_exist.pem"
    with pytest.raises(SystemExit, match="SCOPE_JWT_PUBLIC_KEY_PATH"):
        recon_main._validate_scope_jwt("tok", str(missing))


def test_main_aborts_when_required_env_missing():
    with pytest.raises(SystemExit, match="missing required env"):
        recon_main.main(env={"SCOPE_JWT": "x"})


async def test_run_happy_path_invokes_recon_service(monkeypatch, tmp_path):
    """End-to-end: validate JWT → connect DB → run service → exit 0."""
    env = _full_env(SCOPE_JWT_PUBLIC_KEY_PATH=str(tmp_path / "pub.pem"))

    fake_claims = {
        "targets": {"wildcards": ["*.acme.com"]},
        "exclusions": {},
        "rate_limits": {"default_rps": 5},
    }

    monkeypatch.setattr(
        recon_main, "_validate_scope_jwt", lambda *_a, **_kw: fake_claims
    )

    fake_conn = AsyncMock()

    async def fake_connect(_dsn):
        return fake_conn

    monkeypatch.setattr(recon_main.asyncpg, "connect", fake_connect)

    fake_run = AsyncMock(
        return_value=MagicMock(hosts_found=4, endpoints_found=12, findings_inserted=7)
    )
    with patch.object(recon_main.ReconService, "run", fake_run):
        rc = await recon_main._run(env)

    assert rc == 0
    fake_run.assert_awaited_once()
    fake_conn.close.assert_awaited_once()


async def test_run_returns_2_when_service_raises(monkeypatch, tmp_path):
    env = _full_env(SCOPE_JWT_PUBLIC_KEY_PATH=str(tmp_path / "pub.pem"))

    monkeypatch.setattr(
        recon_main, "_validate_scope_jwt", lambda *_a, **_kw: {"targets": {}}
    )

    fake_conn = AsyncMock()

    async def fake_connect(_dsn):
        return fake_conn

    monkeypatch.setattr(recon_main.asyncpg, "connect", fake_connect)

    async def boom(*_a, **_kw):
        raise RuntimeError("recon imploded")

    with patch.object(recon_main.ReconService, "run", boom):
        rc = await recon_main._run(env)

    assert rc == 2
    fake_conn.close.assert_awaited_once()
