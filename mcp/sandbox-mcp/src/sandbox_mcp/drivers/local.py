# SPDX-License-Identifier: AGPL-3.0-or-later

"""LocalSubprocessDriver — DEV-ONLY subprocess driver.

This driver provides NO isolation: the command runs as the host user in
the host filesystem and the host network namespace. It exists for unit
tests and for replaying validated PoCs in a fully trusted local env.

Activation is gated by TWO independent checks:

  1. ``BS_SANDBOX_DEV_MODE=1`` env on the server process.
  2. ``dev_mode_sandbox=true`` claim in the per-run scope JWT.

Both must hold. The exploit-agent's production scope JWT NEVER carries
``dev_mode_sandbox=true``; that flag is only ever issued by the local
``gen_scope_jwt`` helper for development workflows.

If either check fails, ``run`` raises ``RuntimeError`` BEFORE any
subprocess is spawned. The error is meant to be loud — a deploy that
silently falls back to this driver is a critical incident.
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
import hashlib
import json
import os
import time
import uuid
from typing import Any

from sandbox_mcp.types import (
    DEFAULT_TIMEOUT_SEC,
    MAX_OUTPUT_BYTES,
    MAX_TIMEOUT_SEC,
    RunRequest,
    RunResult,
    Verdict,
)

DEV_MODE_ENV = "BS_SANDBOX_DEV_MODE"
DEV_MODE_JWT_CLAIM = "dev_mode_sandbox"

# Streaming chunk size — small enough to bound peak memory + check
# the cap promptly, large enough to keep syscall overhead negligible.
_READ_CHUNK_BYTES = 8192


async def _bounded_read(reader, max_bytes: int) -> bytes:
    """Read up to ``max_bytes`` from ``reader``; drain the rest to keep
    the OS pipe from blocking the subprocess.

    Without this, ``proc.communicate()`` buffers the *entire* stdout +
    stderr in memory before the existing post-read truncation runs —
    a runaway PoC emitting many GB OOMs the orchestrator. Streaming
    with an in-process cap bounds peak memory at ``max_bytes`` per
    stream regardless of subprocess output volume. (Audit reviewer 4,
    HIGH.)
    """
    buf = bytearray()
    overflow = 0
    while True:
        chunk = await reader.read(_READ_CHUNK_BYTES)
        if not chunk:
            break
        remaining = max_bytes - len(buf)
        if remaining > 0:
            buf.extend(chunk[:remaining])
        # else: drop the rest. We MUST keep reading so the pipe drains
        # and the subprocess does not deadlock writing to a full pipe.
        if remaining < len(chunk):
            overflow += len(chunk) - max(0, remaining)
    if overflow:
        # Sentinel marker so the audit trail records that truncation
        # happened (and how much).
        marker = f"\n<TRUNCATED:{overflow} bytes>".encode()
        if len(buf) + len(marker) <= max_bytes:
            buf.extend(marker)
    return bytes(buf)


def _decode_jwt_claims_unverified(token: str) -> dict[str, Any]:
    """Read JWT claims without signature verification.

    The driver only needs to read the ``dev_mode_sandbox`` claim. A
    proper RS256 verification happens upstream in scope-mcp before the
    orchestrator ever reaches this driver — duplicating it here would
    require the public key in the sandbox-mcp env, which we deliberately
    avoid (least-privilege).
    """
    parts = token.split(".")
    if len(parts) != 3:
        raise ValueError("malformed JWT: expected 3 segments")
    body = parts[1] + "=" * (-len(parts[1]) % 4)
    decoded = base64.urlsafe_b64decode(body)
    claims = json.loads(decoded)
    if not isinstance(claims, dict):
        raise ValueError("JWT body is not a JSON object")
    return claims


class LocalSubprocessDriver:
    """Subprocess driver — explicit DEV use only."""

    name = "local-subprocess"

    def _assert_dev_mode(self, scope_token: str) -> None:
        if os.environ.get(DEV_MODE_ENV) != "1":
            raise RuntimeError(
                f"LocalSubprocessDriver disabled: {DEV_MODE_ENV} env is not 1. "
                "This driver provides NO isolation and must never run in "
                "production. Configure SANDBOX_DRIVER=docker (or firecracker) "
                "for any non-dev deployment."
            )
        try:
            claims = _decode_jwt_claims_unverified(scope_token)
        except Exception as exc:
            raise RuntimeError(f"could not parse scope token: {exc!r}") from exc
        # Strict bool check — accepting any truthy value would let a
        # JWT carrying e.g. ``"dev_mode_sandbox": "false"`` (the string
        # ``"false"`` is non-empty and therefore truthy) bypass the
        # gate. Production tokens never carry the claim at all; the
        # dev path always sets it to literal ``true``.
        # (Audit reviewer 4, LOW.)
        if claims.get(DEV_MODE_JWT_CLAIM) is not True:
            raise RuntimeError(
                f"LocalSubprocessDriver disabled: scope JWT lacks "
                f"`{DEV_MODE_JWT_CLAIM}=true` (literal boolean) claim. "
                f"Production tokens NEVER carry this claim — the dev "
                f"gate prevents accidental subprocess exec in a real "
                f"engagement."
            )

    async def run(self, request: RunRequest) -> RunResult:
        self._assert_dev_mode(request.scope_token)

        timeout = max(1, min(MAX_TIMEOUT_SEC, request.timeout_sec or DEFAULT_TIMEOUT_SEC))
        run_id = f"local-{uuid.uuid4().hex[:12]}"
        started = time.monotonic()

        # Restricted env: pass through PATH only, plus request.env.
        env = {"PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin")}
        env.update({k: v for k, v in (request.env or {}).items() if isinstance(v, str)})

        try:
            proc = await asyncio.create_subprocess_shell(
                request.command,
                stdin=asyncio.subprocess.PIPE if request.stdin_bytes else None,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
            )
        except Exception as exc:
            duration_ms = int((time.monotonic() - started) * 1000)
            return RunResult(
                verdict=Verdict.ERROR,
                finding_id=request.finding_id,
                run_id=run_id,
                duration_ms=duration_ms,
                stdout="",
                stderr="",
                exit_code=None,
                content_hash_hex=hashlib.sha256(b"").hexdigest(),
                egress_attempts=(),
                blocked_egress=(),
                error=f"spawn failed: {type(exc).__name__}: {exc}",
            )

        # Stream stdout / stderr concurrently with the wait, capping
        # each at ``MAX_OUTPUT_BYTES`` so a runaway subprocess cannot
        # OOM the orchestrator regardless of output volume.
        stdout_task = asyncio.create_task(
            _bounded_read(proc.stdout, MAX_OUTPUT_BYTES)
        )
        stderr_task = asyncio.create_task(
            _bounded_read(proc.stderr, MAX_OUTPUT_BYTES)
        )

        # Optional stdin — write-then-close so the subprocess sees EOF
        # without blocking us on a partial drain.
        if request.stdin_bytes and proc.stdin is not None:
            try:
                proc.stdin.write(request.stdin_bytes)
                await proc.stdin.drain()
                proc.stdin.close()
            except Exception:
                pass

        try:
            await asyncio.wait_for(proc.wait(), timeout=timeout)
            verdict = (
                Verdict.SUCCESS if proc.returncode == 0 else Verdict.CRASH
            )
            exit_code = proc.returncode
        except TimeoutError:
            proc.kill()
            with contextlib.suppress(Exception):
                await proc.wait()
            verdict = Verdict.TIMEOUT
            exit_code = None

        # Drain the readers (process is dead; readers will hit EOF).
        # Bound the drain itself so a stuck pipe can't hang us.
        try:
            stdout_b = await asyncio.wait_for(stdout_task, timeout=2.0)
        except (TimeoutError, Exception):
            stdout_task.cancel()
            stdout_b = b""
        try:
            stderr_b = await asyncio.wait_for(stderr_task, timeout=2.0)
        except (TimeoutError, Exception):
            stderr_task.cancel()
            stderr_b = b""

        duration_ms = int((time.monotonic() - started) * 1000)
        # _bounded_read already enforces the cap; this slice is
        # belt-and-braces in case the truncation marker pushes past it.
        stdout_b = stdout_b[:MAX_OUTPUT_BYTES]
        stderr_b = stderr_b[:MAX_OUTPUT_BYTES]
        content_hash_hex = hashlib.sha256(stdout_b + stderr_b).hexdigest()

        return RunResult(
            verdict=verdict,
            finding_id=request.finding_id,
            run_id=run_id,
            duration_ms=duration_ms,
            stdout=stdout_b.decode("utf-8", errors="replace"),
            stderr=stderr_b.decode("utf-8", errors="replace"),
            exit_code=exit_code,
            content_hash_hex=content_hash_hex,
            egress_attempts=(),  # subprocess driver does not observe egress
            blocked_egress=(),
            error=None,
        )

    async def snapshot(self, run_id: str) -> dict:
        # Subprocess driver has no per-run filesystem.
        return {"supported": False, "run_id": run_id, "driver": self.name}


__all__ = ["LocalSubprocessDriver", "DEV_MODE_ENV", "DEV_MODE_JWT_CLAIM"]
