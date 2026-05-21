#!/usr/bin/env python3
"""Generate (or reuse) RS256 key pair and issue a BountyStrike v5 scope JWT.

Usage:
    python scripts/gen_scope_jwt.py [options]

    Required env or flags:
        --program     PROGRAM_HANDLE  (or PROGRAM_HANDLE env var)
        --platform    PLATFORM        (default: hackerone)

    Optional:
        --operator    OPERATOR_ID     (default: dev-operator)
        --wildcards   "*.example.com,*.api.example.com"
        --hosts       "app.example.com,cdn.example.com"
        --hours       EXPIRY_HOURS    (default: 24, max: 168)
        --rps         DEFAULT_RPS     (default: 5)
        --out         PATH            (write JWT to file instead of stdout)
        --keygen      Force regenerate key pair even if keys exist

Keys are read from / written to:
    keys/scope_jwt_private.pem
    keys/scope_jwt_public.pem
(relative to the repo root, detected from this script's location)
"""

from __future__ import annotations

import argparse
import json
import os
import secrets
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# Optional imports — fail with helpful message
# ---------------------------------------------------------------------------
try:
    import jwt as pyjwt
except ImportError:
    print("ERROR: PyJWT not installed. Run: pip install PyJWT cryptography", file=sys.stderr)
    sys.exit(1)

try:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
except ImportError:
    print("ERROR: cryptography not installed. Run: pip install cryptography", file=sys.stderr)
    sys.exit(1)

# ---------------------------------------------------------------------------
# Constants (mirror scope-mcp/src/jwt.ts)
# ---------------------------------------------------------------------------
ISSUER = "bountystrike-v5-control-plane"
ALGORITHM = "RS256"
MAX_EXPIRY_SECONDS = 168 * 3600

REPO_ROOT = Path(__file__).resolve().parent.parent
PRIVATE_KEY_PATH = REPO_ROOT / "keys" / "scope_jwt_private.pem"
PUBLIC_KEY_PATH  = REPO_ROOT / "keys" / "scope_jwt_public.pem"


# ---------------------------------------------------------------------------
# Key management
# ---------------------------------------------------------------------------

def generate_key_pair() -> tuple[bytes, bytes]:
    """Generate RSA-2048 key pair; return (private_pem, public_pem)."""
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return private_pem, public_pem


def ensure_keys(force: bool = False) -> tuple[bytes, bytes]:
    """Return (private_pem, public_pem), generating if absent or forced."""
    if not force and PRIVATE_KEY_PATH.exists() and PUBLIC_KEY_PATH.exists():
        return PRIVATE_KEY_PATH.read_bytes(), PUBLIC_KEY_PATH.read_bytes()

    print("Generating RSA-2048 key pair...", file=sys.stderr)
    PRIVATE_KEY_PATH.parent.mkdir(parents=True, exist_ok=True)
    private_pem, public_pem = generate_key_pair()
    PRIVATE_KEY_PATH.write_bytes(private_pem)
    PUBLIC_KEY_PATH.write_bytes(public_pem)
    PRIVATE_KEY_PATH.chmod(0o600)
    print(f"  private → {PRIVATE_KEY_PATH}", file=sys.stderr)
    print(f"  public  → {PUBLIC_KEY_PATH}", file=sys.stderr)
    return private_pem, public_pem


# ---------------------------------------------------------------------------
# JWT issuance
# ---------------------------------------------------------------------------

def issue_scope_jwt(
    private_pem: bytes,
    operator_id: str,
    program_handle: str,
    platform: str,
    wildcards: list[str],
    exact_hosts: list[str],
    default_rps: int,
    expiry_hours: float,
) -> dict:
    """Issue a scope JWT; return {token, jti, issued_at, expires_at}."""
    expiry_seconds = int(expiry_hours * 3600)
    if expiry_seconds > MAX_EXPIRY_SECONDS:
        raise ValueError(f"expiry_hours={expiry_hours} exceeds maximum 168h")

    now = int(time.time())
    jti = f"jwt_{now}_{secrets.token_hex(8)}"
    engagement_id = f"eng_{now}_{secrets.token_hex(8)}"

    payload = {
        "jti": jti,
        "iss": ISSUER,
        "sub": f"operator:{operator_id}",
        "iat": now,
        "exp": now + expiry_seconds,
        "program_handle": program_handle,
        "platform": platform,
        "targets": {
            "wildcards": wildcards,
            "exact_hosts": exact_hosts,
            "ips": [],
            "android_packages": [],
            "ios_bundles": [],
        },
        "exclusions": {
            "hostnames": [],
            "paths": [],
            "notes": "",
        },
        "rate_limits": {
            "default_rps": default_rps,
            "relaxed_hosts": {},
        },
        "engagement_id": engagement_id,
    }

    token = pyjwt.encode(payload, private_pem, algorithm=ALGORITHM)
    return {
        "token": token,
        "jti": jti,
        "issued_at": datetime.fromtimestamp(now, UTC).isoformat(),
        "expires_at": datetime.fromtimestamp(now + expiry_seconds, UTC).isoformat(),
        "payload_preview": {
            k: payload[k] for k in ("sub", "program_handle", "platform", "targets", "rate_limits")
        },
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        "--program",
        default=os.environ.get("PROGRAM_HANDLE"),
        help="Program handle (required)",
    )
    p.add_argument("--platform",  default=os.environ.get("PLATFORM", "hackerone"))
    p.add_argument("--operator",  default="dev-operator")
    p.add_argument(
        "--wildcards",
        default="",
        help="Comma-separated wildcard targets, e.g. *.example.com",
    )
    p.add_argument("--hosts",     default="", help="Comma-separated exact hosts")
    p.add_argument("--hours",     type=float, default=24.0, help="Expiry hours (max 168)")
    p.add_argument("--rps",       type=int,   default=5,    help="Default rate limit RPS")
    p.add_argument(
        "--out",
        default=None,
        help="Write JWT token to file (token only, no JSON)",
    )
    p.add_argument("--keygen",    action="store_true", help="Force regenerate key pair")
    return p.parse_args()


def main() -> None:
    args = _parse_args()

    if not args.program:
        print("ERROR: --program or PROGRAM_HANDLE env var required", file=sys.stderr)
        sys.exit(1)

    private_pem, _ = ensure_keys(force=args.keygen)

    wildcards   = [w.strip() for w in args.wildcards.split(",") if w.strip()]
    exact_hosts = [h.strip() for h in args.hosts.split(",")     if h.strip()]

    if not wildcards and not exact_hosts:
        # Default: treat program as an exact host for dev convenience
        exact_hosts = [f"{args.program}.example.com"]
        print(f"No targets specified — defaulting to exact_host={exact_hosts[0]}", file=sys.stderr)

    result = issue_scope_jwt(
        private_pem=private_pem,
        operator_id=args.operator,
        program_handle=args.program,
        platform=args.platform,
        wildcards=wildcards,
        exact_hosts=exact_hosts,
        default_rps=args.rps,
        expiry_hours=args.hours,
    )

    if args.out:
        Path(args.out).write_text(result["token"])
        print(f"JWT written to {args.out}", file=sys.stderr)
        print(f"  jti={result['jti']}", file=sys.stderr)
        print(f"  expires={result['expires_at']}", file=sys.stderr)
    else:
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
