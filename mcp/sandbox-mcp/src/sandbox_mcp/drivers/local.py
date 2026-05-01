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
        if not claims.get(DEV_MODE_JWT_CLAIM):
            raise RuntimeError(
                f"LocalSubprocessDriver disabled: scope JWT lacks "
                f"`{DEV_MODE_JWT_CLAIM}=true` claim. Production tokens "
                f"NEVER carry this claim — the dev gate prevents "
                f"accidental subprocess exec in a real engagement."
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

        try:
            stdout_b, stderr_b = await asyncio.wait_for(
                proc.communicate(input=request.stdin_bytes),
                timeout=timeout,
            )
        except TimeoutError:
            proc.kill()
            try:
                stdout_b, stderr_b = await proc.communicate()
            except Exception:
                stdout_b, stderr_b = b"", b""
            verdict = Verdict.TIMEOUT
            exit_code = None
        else:
            verdict = (
                Verdict.SUCCESS if proc.returncode == 0 else Verdict.CRASH
            )
            exit_code = proc.returncode

        duration_ms = int((time.monotonic() - started) * 1000)
        stdout_b = (stdout_b or b"")[:MAX_OUTPUT_BYTES]
        stderr_b = (stderr_b or b"")[:MAX_OUTPUT_BYTES]
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
