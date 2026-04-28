"""RS256 scope JWT issuer + validator.

Per build plan §4.9: 4096-bit RSA keypair, max 168h expiry, claims include
program_handle, platform, targets (wildcards/exact_hosts/ips/android/ios),
exclusions, rate_limits, engagement_id. JTI required for revocation.
"""

from __future__ import annotations

import secrets
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import jwt

ISSUER = "bountystrike-v5-control-plane"
MAX_EXPIRY_SECONDS = 168 * 3600
DEFAULT_EXPIRY_SECONDS = 24 * 3600

Platform = Literal["hackerone", "bugcrowd", "intigriti", "yeswehack", "immunefi"]


@dataclass
class ScopeTargets:
    wildcards: list[str] = field(default_factory=list)
    exact_hosts: list[str] = field(default_factory=list)
    ips: list[str] = field(default_factory=list)
    android_packages: list[str] = field(default_factory=list)
    ios_bundles: list[str] = field(default_factory=list)


@dataclass
class ScopeExclusions:
    hostnames: list[str] = field(default_factory=list)
    paths: list[str] = field(default_factory=list)
    notes: str = ""


@dataclass
class RateLimits:
    default_rps: int = 5
    relaxed_hosts: dict[str, int] = field(default_factory=dict)


def _generate_jti() -> str:
    return f"jwt_{int(time.time())}_{secrets.token_hex(8)}"


class ScopeJWTIssuer:
    def __init__(self, private_key_path: str | Path) -> None:
        self._private_key = Path(private_key_path).read_bytes()

    def issue(
        self,
        operator_id: str,
        program_handle: str,
        platform: Platform,
        targets: ScopeTargets,
        exclusions: ScopeExclusions | None = None,
        rate_limits: RateLimits | None = None,
        expiry_seconds: int = DEFAULT_EXPIRY_SECONDS,
        engagement_id: str | None = None,
    ) -> tuple[str, str]:
        if expiry_seconds > MAX_EXPIRY_SECONDS:
            raise ValueError(
                f"expiry_seconds={expiry_seconds} exceeds max {MAX_EXPIRY_SECONDS} (168h)"
            )
        if expiry_seconds <= 0:
            raise ValueError("expiry_seconds must be positive")

        now = int(time.time())
        jti = _generate_jti()
        payload: dict[str, Any] = {
            "jti": jti,
            "iss": ISSUER,
            "sub": f"operator:{operator_id}",
            "iat": now,
            "exp": now + expiry_seconds,
            "program_handle": program_handle,
            "platform": platform,
            "targets": {
                "wildcards": targets.wildcards,
                "exact_hosts": targets.exact_hosts,
                "ips": targets.ips,
                "android_packages": targets.android_packages,
                "ios_bundles": targets.ios_bundles,
            },
            "exclusions": {
                "hostnames": (exclusions or ScopeExclusions()).hostnames,
                "paths": (exclusions or ScopeExclusions()).paths,
                "notes": (exclusions or ScopeExclusions()).notes,
            },
            "rate_limits": {
                "default_rps": (rate_limits or RateLimits()).default_rps,
                "relaxed_hosts": (rate_limits or RateLimits()).relaxed_hosts,
            },
            "engagement_id": engagement_id or f"eng_{now}_{secrets.token_hex(8)}",
        }

        token = jwt.encode(payload, self._private_key, algorithm="RS256")
        return token, jti


class ScopeJWTValidator:
    def __init__(self, public_key_path: str | Path, revoked_jtis: set[str] | None = None) -> None:
        self._public_key = Path(public_key_path).read_bytes()
        self._revoked: set[str] = revoked_jtis or set()

    def revoke(self, jti: str) -> None:
        self._revoked.add(jti)

    def validate(self, token: str) -> dict[str, Any]:
        payload = jwt.decode(
            token,
            self._public_key,
            algorithms=["RS256"],
            issuer=ISSUER,
            options={"require": ["exp", "iss", "sub", "jti", "iat"]},
            leeway=5,
        )
        jti = payload["jti"]
        if jti in self._revoked:
            raise jwt.InvalidTokenError(f"jti {jti} revoked")
        return payload
