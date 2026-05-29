# SPDX-License-Identifier: AGPL-3.0-or-later

"""RS256 scope JWT issuer + validator.

Per build plan §4.9: 4096-bit RSA keypair, max 168h expiry, claims include
``program_handle``, ``platform``, ``targets`` (wildcards/exact_hosts/ips/
android/ios), ``exclusions``, ``rate_limits``, ``engagement_id``. ``jti`` is
required for revocation.

Boundary types come from :mod:`control_plane.core.security`:
:data:`~control_plane.core.security.OperatorId` validates the operator
identifier we embed in ``sub``, and :data:`~control_plane.core.security.JtiStr`
constrains the generated token id.
"""

from __future__ import annotations

import secrets
import time
from pathlib import Path
from typing import Any

import jwt
from pydantic import TypeAdapter

from control_plane.core.security import JtiStr, OperatorId

from ..value_objects.platform import Platform
from ..value_objects.targets import RateLimits, ScopeExclusions, ScopeTargets

ISSUER = "bountystrike-v5-control-plane"
MAX_EXPIRY_SECONDS = 168 * 3600
DEFAULT_EXPIRY_SECONDS = 24 * 3600

# Module-level adapters validate the typed-string aliases without each call
# paying the construction cost.
_OPERATOR_ID_ADAPTER: TypeAdapter[OperatorId] = TypeAdapter(OperatorId)
_JTI_ADAPTER: TypeAdapter[JtiStr] = TypeAdapter(JtiStr)


def _generate_jti() -> JtiStr:
    """Mint a JTI matching the ``^jwt_\\d+_[0-9a-f]{16}$`` regex enforced by
    :data:`~control_plane.core.security.JtiStr`."""
    candidate = f"jwt_{int(time.time())}_{secrets.token_hex(8)}"
    return _JTI_ADAPTER.validate_python(candidate)


class ScopeJWTIssuer:
    """Mints RS256 scope JWTs from a private key on disk."""

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
    ) -> tuple[str, JtiStr]:
        if expiry_seconds > MAX_EXPIRY_SECONDS:
            raise ValueError(
                f"expiry_seconds={expiry_seconds} exceeds max {MAX_EXPIRY_SECONDS} (168h)"
            )
        if expiry_seconds <= 0:
            raise ValueError("expiry_seconds must be positive")

        validated_operator: OperatorId = _OPERATOR_ID_ADAPTER.validate_python(operator_id)

        now = int(time.time())
        jti = _generate_jti()
        exclusions = exclusions or ScopeExclusions()
        rate_limits = rate_limits or RateLimits()
        payload: dict[str, Any] = {
            "jti": jti,
            "iss": ISSUER,
            "sub": f"operator:{validated_operator}",
            "iat": now,
            "exp": now + expiry_seconds,
            "program_handle": program_handle,
            "platform": platform,
            "targets": {
                "wildcards": list(targets.wildcards),
                "exact_hosts": list(targets.exact_hosts),
                "ips": list(targets.ips),
                "android_packages": list(targets.android_packages),
                "ios_bundles": list(targets.ios_bundles),
            },
            "exclusions": {
                "hostnames": list(exclusions.hostnames),
                "paths": list(exclusions.paths),
                "notes": exclusions.notes,
            },
            "rate_limits": {
                "default_rps": rate_limits.default_rps,
                "relaxed_hosts": dict(rate_limits.relaxed_hosts),
            },
            "engagement_id": engagement_id or f"eng_{now}_{secrets.token_hex(8)}",
        }

        token = jwt.encode(payload, self._private_key, algorithm="RS256")
        return token, jti


class ScopeJWTValidator:
    """Validates RS256 scope JWTs against a public key + revocation list."""

    def __init__(
        self, public_key_path: str | Path, revoked_jtis: set[str] | None = None
    ) -> None:
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


__all__ = [
    "DEFAULT_EXPIRY_SECONDS",
    "ISSUER",
    "MAX_EXPIRY_SECONDS",
    "ScopeJWTIssuer",
    "ScopeJWTValidator",
]
