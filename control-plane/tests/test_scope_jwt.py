"""Roundtrip + boundary tests for scope_jwt module."""

from __future__ import annotations

import time
from pathlib import Path

import jwt
import pytest
from control_plane.domains.scope_management import (
    MAX_EXPIRY_SECONDS,
    RateLimits,
    ScopeExclusions,
    ScopeJWTIssuer,
    ScopeJWTValidator,
    ScopeTargets,
)

PRIVATE_KEY = Path(__file__).resolve().parents[2] / "keys" / "scope_jwt_private.pem"
PUBLIC_KEY = Path(__file__).resolve().parents[2] / "keys" / "scope_jwt_public.pem"


@pytest.fixture
def issuer() -> ScopeJWTIssuer:
    return ScopeJWTIssuer(PRIVATE_KEY)


@pytest.fixture
def validator() -> ScopeJWTValidator:
    return ScopeJWTValidator(PUBLIC_KEY)


def _sample_targets() -> ScopeTargets:
    return ScopeTargets(
        wildcards=("*.acme.com",),
        exact_hosts=("legacy.acme.com",),
        ips=("1.2.3.0/24",),
    )


def test_roundtrip_issue_and_validate(issuer, validator):
    token, jti = issuer.issue(
        operator_id="alice",
        program_handle="acme-corp",
        platform="hackerone",
        targets=_sample_targets(),
    )

    payload = validator.validate(token)

    assert payload["jti"] == jti
    assert payload["sub"] == "operator:alice"
    assert payload["program_handle"] == "acme-corp"
    assert payload["platform"] == "hackerone"
    assert payload["targets"]["wildcards"] == ["*.acme.com"]
    assert payload["iss"] == "bountystrike-v5-control-plane"


def test_max_expiry_enforced(issuer):
    with pytest.raises(ValueError, match="exceeds max"):
        issuer.issue(
            operator_id="alice",
            program_handle="acme-corp",
            platform="hackerone",
            targets=_sample_targets(),
            expiry_seconds=MAX_EXPIRY_SECONDS + 1,
        )


def test_negative_expiry_rejected(issuer):
    with pytest.raises(ValueError, match="positive"):
        issuer.issue(
            operator_id="alice",
            program_handle="acme-corp",
            platform="hackerone",
            targets=_sample_targets(),
            expiry_seconds=-1,
        )


def test_revoked_jti_rejected(issuer, validator):
    token, jti = issuer.issue(
        operator_id="alice",
        program_handle="acme-corp",
        platform="hackerone",
        targets=_sample_targets(),
    )

    validator.revoke(jti)

    with pytest.raises(jwt.InvalidTokenError, match="revoked"):
        validator.validate(token)


def test_expired_token_rejected(issuer, validator):
    token, _ = issuer.issue(
        operator_id="alice",
        program_handle="acme-corp",
        platform="hackerone",
        targets=_sample_targets(),
        expiry_seconds=1,
    )

    time.sleep(7)  # past leeway window of 5s

    with pytest.raises(jwt.ExpiredSignatureError):
        validator.validate(token)


def test_tampered_token_rejected(issuer, validator):
    token, _ = issuer.issue(
        operator_id="alice",
        program_handle="acme-corp",
        platform="hackerone",
        targets=_sample_targets(),
    )

    # Flip a byte in the signature segment
    head, payload_b64, sig = token.split(".")
    tampered = ".".join([head, payload_b64, sig[:-2] + "AA"])

    with pytest.raises(jwt.InvalidSignatureError):
        validator.validate(tampered)


def test_full_claim_set(issuer, validator):
    token, _ = issuer.issue(
        operator_id="bob",
        program_handle="globex",
        platform="bugcrowd",
        targets=ScopeTargets(
            wildcards=("*.globex.io",),
            ips=("10.0.0.0/8",),
            android_packages=("com.globex.mobile",),
        ),
        exclusions=ScopeExclusions(
            hostnames=("staging.globex.io",),
            paths=("/admin",),
            notes="No DoS",
        ),
        rate_limits=RateLimits(default_rps=10, relaxed_hosts={"api.globex.io": 50}),
        expiry_seconds=3600,
        engagement_id="eng_test_001",
    )

    payload = validator.validate(token)

    assert payload["targets"]["android_packages"] == ["com.globex.mobile"]
    assert payload["exclusions"]["paths"] == ["/admin"]
    assert payload["exclusions"]["notes"] == "No DoS"
    assert payload["rate_limits"]["default_rps"] == 10
    assert payload["rate_limits"]["relaxed_hosts"]["api.globex.io"] == 50
    assert payload["engagement_id"] == "eng_test_001"
