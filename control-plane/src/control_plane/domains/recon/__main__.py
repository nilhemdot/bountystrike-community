# SPDX-License-Identifier: AGPL-3.0-or-later

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
import structlog
from politeness_mcp.bucket import TokenBucketLimiter

from control_plane.domains.recon import (
    RealBinaryRunner,
    ReconService,
    ScanPersistence,
    ScopeFilter,
)
from control_plane.domains.recon.probers import HttpxReflectionProber
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

log = structlog.get_logger(__name__)


def _require_env(env: dict[str, str]) -> dict[str, str]:
    missing = [k for k in _REQUIRED_ENV if not env.get(k)]
    if missing:
        raise SystemExit(f"missing required env vars: {', '.join(missing)}")
    return {k: env[k] for k in _REQUIRED_ENV}


def _validate_scope_jwt(token: str, public_key_path: str) -> dict[str, Any]:
    if not Path(public_key_path).exists():
        raise SystemExit(f"SCOPE_JWT_PUBLIC_KEY_PATH not found: {public_key_path}")
    validator = ScopeJWTValidator(public_key_path=public_key_path)
    return validator.validate(token)


async def _run(env: dict[str, str]) -> int:
    public_key_path = env.get("SCOPE_JWT_PUBLIC_KEY_PATH", "keys/scope_jwt_public.pem")
    claims = _validate_scope_jwt(env["SCOPE_JWT"], public_key_path)
    scope_filter = ScopeFilter.from_jwt_claims(claims)

    runner = RealBinaryRunner(
        subfinder_bin=env.get("SUBFINDER_BIN", "subfinder"),
        httpx_bin=env.get("HTTPX_BIN", "httpx"),
        katana_bin=env.get("KATANA_BIN", "katana"),
    )
    persistence = ScanPersistence()
    # One limiter per recon run so all in-process reflection GETs share per-host
    # bucket state (single-process scope by design — see bucket.py). Injecting
    # scope_filter.rps_for_host activates the per-host relaxed_hosts override
    # (plan 01-07). The out-of-process ProjectDiscovery binaries keep their own
    # `-rate-limit` self-limit; this layer gates the prober's egress only.
    limiter = TokenBucketLimiter(default_rps=float(scope_filter.default_rps))
    log.info("recon.politeness.enabled", default_rps=scope_filter.default_rps)
    prober: ReflectionProber = HttpxReflectionProber(
        limiter=limiter, rps_for_host=scope_filter.rps_for_host
    )
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
        sys.stderr.write(f"recon failed: {type(exc).__name__}: {exc}\n")
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
