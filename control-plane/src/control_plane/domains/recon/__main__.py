"""CLI entrypoint for the recon-agent runtime container.

Wraps :class:`ReconService` so an orchestrator-launched container can
execute one full recon cycle without writing any glue Python at the
call-site. All inputs come from environment variables; the contract is
documented in ``.claude/agents/recon.md`` §Inputs.

Required env::

    SCOPE_JWT             RS256 scope JWT (validated against
                          SCOPE_JWT_PUBLIC_KEY_PATH)
    PROGRAM_HANDLE        e.g. "acme-corp"
    PLATFORM              e.g. "hackerone"
    DATABASE_URL          asyncpg URL (postgresql[+asyncpg]://...)
    SCAN_JOB_ID           UUID of the pre-created scan_jobs row

Optional env::

    SCOPE_JWT_PUBLIC_KEY_PATH   default: keys/scope_jwt_public.pem
    SUBFINDER_BIN / HTTPX_BIN / KATANA_BIN
                                override binary paths (else PATH lookup)

Exit codes::
    0   recon_complete written to scan_jobs
    1   missing/invalid env, JWT validation failure, or DB connect error
    2   recon ran but ReconService raised mid-flight (already marked
        recon_failed in scan_jobs)
"""

from __future__ import annotations

import asyncio
import os
import sys
import uuid
from pathlib import Path
from typing import Any

import asyncpg
import httpx

from control_plane.domains.recon import (
    RealBinaryRunner,
    ReconService,
    ScanPersistence,
    ScopeFilter,
)
from control_plane.domains.recon.service import ReflectionProber
from control_plane.domains.scope_management.services.jwt_issuer import (
    ScopeJWTValidator,
)

_REQUIRED_ENV = (
    "SCOPE_JWT",
    "PROGRAM_HANDLE",
    "PLATFORM",
    "DATABASE_URL",
    "SCAN_JOB_ID",
)

_REFLECTION_PROBE_TIMEOUT_SEC = 8.0


class HttpxReflectionProber:
    """Production reflection prober — single GET, substring match.

    Uses a short timeout so slow targets default to "no reflection" (drop).
    The exploit-agent's WebFetch probe is the catch-net for borderline cases
    flagged by validator; this prober's job is to drop the obvious FPs.
    """

    name = "httpx"

    def __init__(self, timeout_sec: float = _REFLECTION_PROBE_TIMEOUT_SEC) -> None:
        self._timeout_sec = timeout_sec

    async def probe(self, url: str, parameter: str, sentinel: str) -> bool:
        del parameter  # only the URL + sentinel matter for the substring check
        async with httpx.AsyncClient(
            timeout=self._timeout_sec, follow_redirects=True
        ) as client:
            response = await client.get(url)
            return sentinel in response.text


def _require_env(env: dict[str, str]) -> dict[str, str]:
    missing = [k for k in _REQUIRED_ENV if not env.get(k)]
    if missing:
        raise SystemExit(
            f"missing required env vars: {', '.join(missing)}"
        )
    return {k: env[k] for k in _REQUIRED_ENV}


def _validate_scope_jwt(token: str, public_key_path: str) -> dict[str, Any]:
    if not Path(public_key_path).exists():
        raise SystemExit(
            f"SCOPE_JWT_PUBLIC_KEY_PATH not found: {public_key_path}"
        )
    validator = ScopeJWTValidator(public_key_path=public_key_path)
    return validator.validate(token)


async def _run(env: dict[str, str]) -> int:
    public_key_path = env.get(
        "SCOPE_JWT_PUBLIC_KEY_PATH", "keys/scope_jwt_public.pem"
    )
    claims = _validate_scope_jwt(env["SCOPE_JWT"], public_key_path)
    scope_filter = ScopeFilter.from_jwt_claims(claims)

    runner = RealBinaryRunner(
        subfinder_bin=env.get("SUBFINDER_BIN", "subfinder"),
        httpx_bin=env.get("HTTPX_BIN", "httpx"),
        katana_bin=env.get("KATANA_BIN", "katana"),
    )
    persistence = ScanPersistence()
    prober: ReflectionProber = HttpxReflectionProber()
    service = ReconService(runner, persistence, scope_filter, prober=prober)

    dsn = env["DATABASE_URL"].replace("+asyncpg", "")
    conn = await asyncpg.connect(dsn)
    try:
        result = await service.run(
            conn,
            job_id=uuid.UUID(env["SCAN_JOB_ID"]),
            program_handle=env["PROGRAM_HANDLE"],
            platform=env["PLATFORM"],
        )
    except Exception as exc:  # service already marked recon_failed
        sys.stderr.write(
            f"recon failed: {type(exc).__name__}: {exc}\n"
        )
        return 2
    finally:
        await conn.close()

    sys.stdout.write(
        f"recon_complete hosts={result.hosts_found} "
        f"endpoints={result.endpoints_found} "
        f"findings={result.findings_inserted}\n"
    )
    return 0


def main(argv: list[str] | None = None, env: dict[str, str] | None = None) -> int:
    """Synchronous wrapper — the container ENTRYPOINT calls this."""
    del argv  # CLI takes no positional args; everything is env
    env_map = dict(env if env is not None else os.environ)
    _require_env(env_map)
    return asyncio.run(_run(env_map))


if __name__ == "__main__":  # pragma: no cover — exercised by container start
    raise SystemExit(main())
