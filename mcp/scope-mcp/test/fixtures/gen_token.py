"""Fixture: mint a scope JWT via the Python issuer so the TS verifier can
validate it. Used by mcp/scope-mcp/test/interop.test.ts.

Usage:
    uv run --project /path/to/control-plane python gen_token.py [private_key_path]

Emits a single JSON line on stdout: {"token": "...", "jti": "...", "issued_at": "..."}
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from control_plane.scope_jwt import (
    RateLimits,
    ScopeExclusions,
    ScopeJWTIssuer,
    ScopeTargets,
)


def main() -> int:
    repo_root = Path(__file__).resolve().parents[4]
    default_key = repo_root / "keys" / "scope_jwt_private.pem"
    key_path = Path(sys.argv[1]) if len(sys.argv) > 1 else default_key

    issuer = ScopeJWTIssuer(key_path)
    token, jti = issuer.issue(
        operator_id="alice",
        program_handle="acme-corp",
        platform="hackerone",
        targets=ScopeTargets(
            wildcards=["*.acme.com"],
            exact_hosts=["legacy.acme.com"],
            ips=["1.2.3.0/24"],
            android_packages=["com.acme.app"],
            ios_bundles=[],
        ),
        exclusions=ScopeExclusions(
            hostnames=["staging-internal.acme.com"],
            paths=["/admin", "/internal"],
            notes="No DoS",
        ),
        rate_limits=RateLimits(default_rps=5, relaxed_hosts={"api.acme.com": 20}),
        expiry_seconds=3600,
        engagement_id=None,
    )
    issued_at = (
        time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(int(time.time()))) + "Z"
    )
    sys.stdout.write(
        json.dumps({"token": token, "jti": jti, "issued_at": issued_at}) + "\n"
    )
    sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
