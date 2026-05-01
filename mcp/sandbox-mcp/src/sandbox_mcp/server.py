"""FastMCP server for sandbox-mcp.

Exposes three MCP tools:
  - run_code(...)           — single-command sandbox execution
  - run_poc_template(...)   — multi-step PoC chain in the same sandbox
  - snapshot_filesystem(...) — driver-dependent post-run snapshot

Driver selection via ``SANDBOX_DRIVER`` env (``local`` | ``docker`` |
``firecracker``). Default is ``unset`` — the server refuses to run a
sandbox call until a driver is explicitly chosen, defence-in-depth
against an accidental fallback to LocalSubprocessDriver.

Transport: stdio (default FastMCP transport).
Entry point: ``sandbox-mcp`` CLI script (see pyproject.toml).
"""

from __future__ import annotations

import os
from typing import Any

from mcp.server.fastmcp import FastMCP

from sandbox_mcp.drivers.docker import DockerDriver
from sandbox_mcp.drivers.local import LocalSubprocessDriver
from sandbox_mcp.drivers.protocol import Driver
from sandbox_mcp.types import (
    DEFAULT_TIMEOUT_SEC,
    MAX_TIMEOUT_SEC,
    RunRequest,
    RunResult,
    Verdict,
)

mcp = FastMCP("sandbox-mcp")

DRIVER_ENV = "SANDBOX_DRIVER"
_driver: Driver | None = None


def _select_driver() -> Driver:
    global _driver
    if _driver is not None:
        return _driver
    name = (os.environ.get(DRIVER_ENV) or "").lower()
    if name == "local":
        _driver = LocalSubprocessDriver()
    elif name == "docker":
        _driver = DockerDriver()
    elif name == "firecracker":
        # Production target; not implemented in this MCP yet.
        raise RuntimeError(
            "FirecrackerDriver is not yet implemented; see "
            "infra/sandbox/firecracker/ (build-plan §6.5 hardening task)."
        )
    elif not name:
        raise RuntimeError(
            f"{DRIVER_ENV} env is unset. Choose one of: local, docker, "
            "firecracker. ``local`` is dev-only and refuses to run "
            "without BS_SANDBOX_DEV_MODE=1 + dev_mode_sandbox JWT claim."
        )
    else:
        raise RuntimeError(f"unknown {DRIVER_ENV}={name!r}")
    return _driver


def _build_request(
    finding_id: str,
    scope_token: str,
    egress_allowlist: list[str],
    command: str,
    template_id: str | None,
    stdin: str | None,
    env: dict[str, str] | None,
    timeout_sec: int,
    cleanup: bool,
) -> RunRequest:
    if not finding_id:
        raise ValueError("finding_id is required")
    if not scope_token:
        raise ValueError("scope_token is required")
    if not command:
        raise ValueError("command is required")
    if not isinstance(egress_allowlist, list) or not all(
        isinstance(h, str) for h in egress_allowlist
    ):
        raise ValueError("egress_allowlist must be a list[str]")
    timeout = max(1, min(MAX_TIMEOUT_SEC, int(timeout_sec or DEFAULT_TIMEOUT_SEC)))
    return RunRequest(
        finding_id=finding_id,
        scope_token=scope_token,
        egress_allowlist=tuple(egress_allowlist),
        command=command,
        template_id=template_id,
        stdin_bytes=stdin.encode() if stdin else None,
        env=dict(env or {}),
        timeout_sec=timeout,
        cleanup=bool(cleanup),
    )


def _result_to_dict(result: RunResult) -> dict[str, Any]:
    return {
        "verdict": result.verdict.value,
        "finding_id": result.finding_id,
        "run_id": result.run_id,
        "duration_ms": result.duration_ms,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "exit_code": result.exit_code,
        "content_hash_hex": result.content_hash_hex,
        "egress_attempts": list(result.egress_attempts),
        "blocked_egress": list(result.blocked_egress),
        "error": result.error,
    }


# ---------------------------------------------------------------------------
# Testable implementation layer
# ---------------------------------------------------------------------------


async def _run_code_impl(
    driver: Driver,
    *,
    finding_id: str,
    scope_token: str,
    egress_allowlist: list[str],
    command: str,
    stdin: str | None = None,
    env: dict[str, str] | None = None,
    timeout_sec: int = DEFAULT_TIMEOUT_SEC,
    cleanup: bool = True,
) -> dict:
    request = _build_request(
        finding_id, scope_token, egress_allowlist, command, None,
        stdin, env, timeout_sec, cleanup,
    )
    result = await driver.run(request)
    return _result_to_dict(result)


async def _run_poc_template_impl(
    driver: Driver,
    *,
    finding_id: str,
    scope_token: str,
    egress_allowlist: list[str],
    template_id: str,
    steps: list[str],
    timeout_sec: int = DEFAULT_TIMEOUT_SEC,
    cleanup: bool = True,
) -> dict:
    if not steps or not all(isinstance(s, str) for s in steps):
        raise ValueError("steps must be a non-empty list[str]")
    # Compose the steps as a `set -e; ...` shell pipeline. Every step
    # runs in the same sandboxed shell session — required for chains
    # that depend on prior step output (e.g. token harvest → reuse).
    composed = "set -e\n" + "\n".join(steps)
    request = _build_request(
        finding_id, scope_token, egress_allowlist, composed, template_id,
        None, None, timeout_sec, cleanup,
    )
    result = await driver.run(request)
    return _result_to_dict(result)


async def _snapshot_filesystem_impl(driver: Driver, run_id: str) -> dict:
    return await driver.snapshot(run_id)


# ---------------------------------------------------------------------------
# MCP tools
# ---------------------------------------------------------------------------


@mcp.tool()
async def run_code(
    finding_id: str,
    scope_token: str,
    egress_allowlist: list[str],
    command: str,
    stdin: str | None = None,
    env: dict[str, str] | None = None,
    timeout_sec: int = DEFAULT_TIMEOUT_SEC,
    cleanup: bool = True,
) -> dict:
    """Run a single shell command inside the sandbox.

    Args:
        finding_id: UUID of the parent findings row (used as audit key).
        scope_token: RS256 scope JWT — driver verifies before resource alloc.
        egress_allowlist: Hostnames the sandbox may reach. Driver
            enforces deny-by-default.
        command: Shell command to execute.
        stdin: Optional stdin bytes (UTF-8).
        env: Extra env vars; host env is otherwise stripped to PATH only.
        timeout_sec: Wall-clock budget; clamped to MAX_TIMEOUT_SEC (600s).
        cleanup: Tear down the container/VM after the run.

    Returns:
        ``{verdict, finding_id, run_id, duration_ms, stdout, stderr,
        exit_code, content_hash_hex, egress_attempts, blocked_egress, error}``.
    """
    driver = _select_driver()
    return await _run_code_impl(
        driver,
        finding_id=finding_id,
        scope_token=scope_token,
        egress_allowlist=egress_allowlist,
        command=command,
        stdin=stdin,
        env=env,
        timeout_sec=timeout_sec,
        cleanup=cleanup,
    )


@mcp.tool()
async def run_poc_template(
    finding_id: str,
    scope_token: str,
    egress_allowlist: list[str],
    template_id: str,
    steps: list[str],
    timeout_sec: int = DEFAULT_TIMEOUT_SEC,
    cleanup: bool = True,
) -> dict:
    """Run a multi-step PoC chain inside a single sandbox session.

    Steps execute sequentially in the same shell; the whole chain aborts
    on the first non-zero exit (``set -e``). Use for chained exploits
    (e.g. SSRF → IMDS token → STS credentials).

    Args:
        template_id: Names the chain template; informational + used
            by hooks for per-template hardening.
        steps: Ordered list of shell commands.

    Returns: same shape as ``run_code``.
    """
    driver = _select_driver()
    return await _run_poc_template_impl(
        driver,
        finding_id=finding_id,
        scope_token=scope_token,
        egress_allowlist=egress_allowlist,
        template_id=template_id,
        steps=steps,
        timeout_sec=timeout_sec,
        cleanup=cleanup,
    )


@mcp.tool()
async def snapshot_filesystem(run_id: str) -> dict:
    """Snapshot the post-run filesystem for the given ``run_id``.

    Driver-dependent: LocalSubprocessDriver returns
    ``{supported: False}``; DockerDriver/FirecrackerDriver return a
    content-addressable snapshot ID and r2_key.
    """
    driver = _select_driver()
    return await _snapshot_filesystem_impl(driver, run_id)


def main() -> None:
    """Run the sandbox-mcp FastMCP server (stdio transport)."""
    mcp.run()


if __name__ == "__main__":
    main()
