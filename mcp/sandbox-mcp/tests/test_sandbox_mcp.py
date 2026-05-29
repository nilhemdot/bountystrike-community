# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for sandbox-mcp — types, driver gates, server dispatch.

The LocalSubprocessDriver is exercised end-to-end via real subprocess
spawn (it's the only driver that can run without external infra). The
DockerDriver is exercised at the protocol-gate level (refuse to run
without sidecar). The server-side dispatch layer is tested with a fake
driver to confirm request shaping + result serialisation.
"""

from __future__ import annotations

import base64
import json
from unittest.mock import AsyncMock

import pytest
from sandbox_mcp.drivers.docker import DOCKER_FORCE_ENV
from sandbox_mcp.drivers.local import (
    DEV_MODE_ENV,
    DEV_MODE_JWT_CLAIM,
    LocalSubprocessDriver,
    _decode_jwt_claims_unverified,
)
from sandbox_mcp.server import (
    _build_request,
    _result_to_dict,
    _run_code_impl,
    _run_poc_template_impl,
)
from sandbox_mcp.types import (
    DEFAULT_TIMEOUT_SEC,
    MAX_TIMEOUT_SEC,
    RunRequest,
    RunResult,
    Verdict,
)


def _make_jwt(claims: dict) -> str:
    """Build a JWT-shaped token with the given claims (no signature)."""
    header = base64.urlsafe_b64encode(b'{"alg":"none"}').rstrip(b"=").decode()
    body = base64.urlsafe_b64encode(json.dumps(claims).encode()).rstrip(b"=").decode()
    return f"{header}.{body}.notasignature"


# ---------------------------------------------------------------------------
# Type sanity
# ---------------------------------------------------------------------------


def test_run_request_is_frozen() -> None:
    req = RunRequest(
        finding_id="f1",
        scope_token="t",
        egress_allowlist=("a",),
        command="echo hi",
    )
    with pytest.raises(Exception):  # noqa: B017 - dataclass(frozen=True) raises FrozenInstanceError
        # dataclass(frozen=True) raises FrozenInstanceError
        req.command = "rm -rf"  # type: ignore[misc]


def test_run_request_defaults() -> None:
    req = RunRequest(
        finding_id="f1",
        scope_token="t",
        egress_allowlist=(),
        command="x",
    )
    assert req.timeout_sec == DEFAULT_TIMEOUT_SEC
    assert req.cleanup is True
    assert req.template_id is None


# ---------------------------------------------------------------------------
# JWT claim parser
# ---------------------------------------------------------------------------


def test_decode_jwt_claims_roundtrip() -> None:
    token = _make_jwt({"sub": "x", "dev_mode_sandbox": True})
    claims = _decode_jwt_claims_unverified(token)
    assert claims["dev_mode_sandbox"] is True


def test_decode_jwt_rejects_malformed() -> None:
    with pytest.raises(ValueError):
        _decode_jwt_claims_unverified("not.a.jwt.too.many")


# ---------------------------------------------------------------------------
# LocalSubprocessDriver — gate enforcement
# ---------------------------------------------------------------------------


async def test_local_driver_refuses_without_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(DEV_MODE_ENV, raising=False)
    driver = LocalSubprocessDriver()
    req = RunRequest(
        finding_id="f1",
        scope_token=_make_jwt({DEV_MODE_JWT_CLAIM: True}),
        egress_allowlist=(),
        command="echo hi",
    )
    with pytest.raises(RuntimeError, match=DEV_MODE_ENV):
        await driver.run(req)


async def test_local_driver_refuses_without_jwt_claim(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(DEV_MODE_ENV, "1")
    driver = LocalSubprocessDriver()
    req = RunRequest(
        finding_id="f1",
        scope_token=_make_jwt({"sub": "x"}),  # no dev_mode_sandbox claim
        egress_allowlist=(),
        command="echo hi",
    )
    with pytest.raises(RuntimeError, match=DEV_MODE_JWT_CLAIM):
        await driver.run(req)


async def test_local_driver_runs_when_both_gates_open(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(DEV_MODE_ENV, "1")
    driver = LocalSubprocessDriver()
    req = RunRequest(
        finding_id="f1",
        scope_token=_make_jwt({DEV_MODE_JWT_CLAIM: True}),
        egress_allowlist=(),
        command="echo hello-sandbox",
    )
    result = await driver.run(req)
    assert result.verdict == Verdict.SUCCESS
    assert "hello-sandbox" in result.stdout
    assert result.exit_code == 0
    assert len(result.content_hash_hex) == 64


async def test_local_driver_captures_nonzero_exit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(DEV_MODE_ENV, "1")
    driver = LocalSubprocessDriver()
    req = RunRequest(
        finding_id="f1",
        scope_token=_make_jwt({DEV_MODE_JWT_CLAIM: True}),
        egress_allowlist=(),
        command="exit 7",
    )
    result = await driver.run(req)
    assert result.verdict == Verdict.CRASH
    assert result.exit_code == 7


async def test_local_driver_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(DEV_MODE_ENV, "1")
    driver = LocalSubprocessDriver()
    req = RunRequest(
        finding_id="f1",
        scope_token=_make_jwt({DEV_MODE_JWT_CLAIM: True}),
        egress_allowlist=(),
        command="sleep 10",
        timeout_sec=1,
    )
    result = await driver.run(req)
    assert result.verdict == Verdict.TIMEOUT


async def test_local_driver_strips_host_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(DEV_MODE_ENV, "1")
    monkeypatch.setenv("MY_SECRET", "should-not-leak")
    driver = LocalSubprocessDriver()
    req = RunRequest(
        finding_id="f1",
        scope_token=_make_jwt({DEV_MODE_JWT_CLAIM: True}),
        egress_allowlist=(),
        command='echo "MY_SECRET=${MY_SECRET:-unset}"',
    )
    result = await driver.run(req)
    assert result.verdict == Verdict.SUCCESS
    assert "MY_SECRET=unset" in result.stdout


async def test_local_driver_snapshot_unsupported(monkeypatch: pytest.MonkeyPatch) -> None:
    driver = LocalSubprocessDriver()
    snap = await driver.snapshot("run-1")
    assert snap == {"supported": False, "run_id": "run-1", "driver": "local-subprocess"}


# ---------------------------------------------------------------------------
# DockerDriver — preflight gate
# ---------------------------------------------------------------------------


async def test_docker_driver_refuses_without_egress_gate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("BS_EGRESS_GATE_URL", raising=False)
    monkeypatch.delenv(DOCKER_FORCE_ENV, raising=False)
    # Re-import to pick up the env edit on module-level constant.
    import importlib

    import sandbox_mcp.drivers.docker as docker_mod
    importlib.reload(docker_mod)
    driver = docker_mod.DockerDriver()
    req = RunRequest(
        finding_id="f1",
        scope_token="t",
        egress_allowlist=(),
        command="echo hi",
    )
    with pytest.raises(NotImplementedError):
        await driver.run(req)


# ---------------------------------------------------------------------------
# Server dispatch — _build_request shaping
# ---------------------------------------------------------------------------


def test_build_request_clamps_timeout_to_ceiling() -> None:
    req = _build_request(
        finding_id="f1",
        scope_token="t",
        egress_allowlist=["x"],
        command="echo",
        template_id=None,
        stdin=None,
        env=None,
        timeout_sec=99999,
        cleanup=True,
    )
    assert req.timeout_sec == MAX_TIMEOUT_SEC


def test_build_request_rejects_empty_finding_id() -> None:
    with pytest.raises(ValueError):
        _build_request(
            finding_id="",
            scope_token="t",
            egress_allowlist=[],
            command="echo",
            template_id=None,
            stdin=None,
            env=None,
            timeout_sec=10,
            cleanup=True,
        )


def test_build_request_rejects_non_string_egress() -> None:
    with pytest.raises(ValueError):
        _build_request(
            finding_id="f1",
            scope_token="t",
            egress_allowlist=[1, 2],  # type: ignore[list-item]
            command="echo",
            template_id=None,
            stdin=None,
            env=None,
            timeout_sec=10,
            cleanup=True,
        )


# ---------------------------------------------------------------------------
# Server dispatch — _run_code_impl + _run_poc_template_impl with fake driver
# ---------------------------------------------------------------------------


def _make_fake_result(stdout: str = "ok") -> RunResult:
    return RunResult(
        verdict=Verdict.SUCCESS,
        finding_id="f1",
        run_id="run-1",
        duration_ms=10,
        stdout=stdout,
        stderr="",
        exit_code=0,
        content_hash_hex="aa" * 32,
        egress_attempts=(),
        blocked_egress=(),
        error=None,
    )


async def test_run_code_impl_passes_args_through() -> None:
    driver = AsyncMock()
    driver.run.return_value = _make_fake_result()
    result = await _run_code_impl(
        driver,
        finding_id="f1",
        scope_token="t",
        egress_allowlist=["api.x"],
        command="curl https://api.x/",
    )
    assert result["verdict"] == "success"
    sent: RunRequest = driver.run.call_args.args[0]
    assert sent.finding_id == "f1"
    assert sent.command == "curl https://api.x/"
    assert sent.egress_allowlist == ("api.x",)


async def test_run_poc_template_impl_chains_steps_with_set_e() -> None:
    driver = AsyncMock()
    driver.run.return_value = _make_fake_result()
    await _run_poc_template_impl(
        driver,
        finding_id="f1",
        scope_token="t",
        egress_allowlist=["api.x"],
        template_id="curl_chain",
        steps=["curl -s http://1/", "curl -s http://2/"],
    )
    sent: RunRequest = driver.run.call_args.args[0]
    assert sent.command.startswith("set -e\n")
    assert "curl -s http://1/" in sent.command
    assert "curl -s http://2/" in sent.command
    assert sent.template_id == "curl_chain"


async def test_run_poc_template_impl_rejects_empty_steps() -> None:
    driver = AsyncMock()
    with pytest.raises(ValueError):
        await _run_poc_template_impl(
            driver,
            finding_id="f1",
            scope_token="t",
            egress_allowlist=[],
            template_id="x",
            steps=[],
        )


def test_result_to_dict_serialises_verdict_enum() -> None:
    out = _result_to_dict(_make_fake_result(stdout="hi"))
    assert out["verdict"] == "success"
    assert out["stdout"] == "hi"
    assert isinstance(out["egress_attempts"], list)


# ---------------------------------------------------------------------------
# Driver selection
# ---------------------------------------------------------------------------


def test_select_driver_unset_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    import sandbox_mcp.server as srv

    monkeypatch.delenv("SANDBOX_DRIVER", raising=False)
    monkeypatch.setattr(srv, "_driver", None)
    with pytest.raises(RuntimeError, match="SANDBOX_DRIVER"):
        srv._select_driver()


def test_select_driver_local(monkeypatch: pytest.MonkeyPatch) -> None:
    import sandbox_mcp.server as srv

    monkeypatch.setenv("SANDBOX_DRIVER", "local")
    monkeypatch.setattr(srv, "_driver", None)
    drv = srv._select_driver()
    assert isinstance(drv, LocalSubprocessDriver)


def test_select_driver_unknown_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    import sandbox_mcp.server as srv

    monkeypatch.setenv("SANDBOX_DRIVER", "pixie-dust")
    monkeypatch.setattr(srv, "_driver", None)
    with pytest.raises(RuntimeError, match="unknown"):
        srv._select_driver()


def test_select_driver_firecracker_not_implemented(monkeypatch: pytest.MonkeyPatch) -> None:
    import sandbox_mcp.server as srv

    monkeypatch.setenv("SANDBOX_DRIVER", "firecracker")
    monkeypatch.setattr(srv, "_driver", None)
    with pytest.raises(RuntimeError, match="FirecrackerDriver"):
        srv._select_driver()


# ---------------------------------------------------------------------------
# Audit-fix coverage — strict bool gate, bounded streaming output.
# ---------------------------------------------------------------------------


async def test_local_driver_rejects_string_false_dev_claim(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``"dev_mode_sandbox": "false"`` (string, truthy) MUST NOT bypass
    the gate. Pre-fix, the gate used ``if not claims.get(...)`` which
    rejected only falsey values; the literal string ``"false"`` is
    non-empty and therefore truthy → would have allowed exec."""
    monkeypatch.setenv(DEV_MODE_ENV, "1")
    driver = LocalSubprocessDriver()
    req = RunRequest(
        finding_id="f1",
        scope_token=_make_jwt({DEV_MODE_JWT_CLAIM: "false"}),
        egress_allowlist=(),
        command="echo hi",
    )
    with pytest.raises(RuntimeError, match=DEV_MODE_JWT_CLAIM):
        await driver.run(req)


async def test_local_driver_rejects_truthy_non_bool_dev_claim(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``1`` is truthy — but the claim must be the literal boolean
    ``true``, not any truthy value."""
    monkeypatch.setenv(DEV_MODE_ENV, "1")
    driver = LocalSubprocessDriver()
    req = RunRequest(
        finding_id="f1",
        scope_token=_make_jwt({DEV_MODE_JWT_CLAIM: 1}),
        egress_allowlist=(),
        command="echo hi",
    )
    with pytest.raises(RuntimeError, match=DEV_MODE_JWT_CLAIM):
        await driver.run(req)


async def test_local_driver_caps_runaway_stdout(monkeypatch: pytest.MonkeyPatch) -> None:
    """A subprocess emitting more than MAX_OUTPUT_BYTES of stdout must
    not OOM the orchestrator. Pre-fix, ``proc.communicate()`` buffered
    the entire output before truncation. Post-fix, the bounded
    streaming reader caps in-memory bytes at MAX_OUTPUT_BYTES."""
    monkeypatch.setenv(DEV_MODE_ENV, "1")
    from sandbox_mcp.types import MAX_OUTPUT_BYTES

    driver = LocalSubprocessDriver()
    # Emit ~ 2 × MAX_OUTPUT_BYTES via a tight loop. The truncation
    # marker is appended inside the cap, so the final bytes are <=
    # MAX_OUTPUT_BYTES (the slice in run() enforces a hard ceiling).
    target_bytes = 2 * MAX_OUTPUT_BYTES
    cmd = f"yes A | head -c {target_bytes}"
    req = RunRequest(
        finding_id="f1",
        scope_token=_make_jwt({DEV_MODE_JWT_CLAIM: True}),
        egress_allowlist=(),
        command=cmd,
        timeout_sec=10,
    )
    result = await driver.run(req)
    # Result must exist + be capped. encode() length is what matters
    # for the memory bound, since stdout decode keeps the same byte
    # count under the replace-error policy for ASCII.
    assert len(result.stdout.encode("utf-8")) <= MAX_OUTPUT_BYTES
    assert result.verdict in {Verdict.SUCCESS, Verdict.CRASH}
