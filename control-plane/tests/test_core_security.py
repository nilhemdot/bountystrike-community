"""Tests for core/security utilities."""

from __future__ import annotations

import pytest
from control_plane.core.security import (
    JtiStr,
    NormalizedScore,
    OperatorId,
    PathTraversalError,
    ProgramHandle,
    reject_destructive_payload,
    secure_path,
)
from pydantic import BaseModel, ValidationError


def test_secure_path_resolves_inside_root(tmp_path):
    target = secure_path("evidence/foo.bin", tmp_path)
    assert str(target).startswith(str(tmp_path.resolve()))


def test_secure_path_rejects_traversal(tmp_path):
    with pytest.raises(PathTraversalError):
        secure_path("../../etc/passwd", tmp_path)


def test_secure_path_rejects_absolute_outside(tmp_path):
    with pytest.raises(PathTraversalError):
        secure_path("/etc/passwd", tmp_path)


def test_secure_path_allows_nested(tmp_path):
    nested = tmp_path / "a" / "b"
    nested.mkdir(parents=True)
    target = secure_path("a/b/file.bin", tmp_path)
    assert target == (nested / "file.bin").resolve()


class _Sample(BaseModel):
    jti: JtiStr
    operator: OperatorId
    program: ProgramHandle
    score: NormalizedScore


def test_jti_pattern_accepts_valid():
    obj = _Sample(
        jti="jwt_1745800000_a7f3deadbeef0011",
        operator="alice",
        program="acme-corp",
        score=0.5,
    )
    assert obj.jti.startswith("jwt_")


def test_jti_pattern_rejects_invalid():
    with pytest.raises(ValidationError):
        _Sample(
            jti="not-a-jti",
            operator="alice",
            program="acme-corp",
            score=0.5,
        )


def test_program_handle_pattern():
    with pytest.raises(ValidationError):
        _Sample(
            jti="jwt_1745800000_a7f3deadbeef0011",
            operator="alice",
            program="-bad-",
            score=0.5,
        )


def test_normalized_score_bounds():
    with pytest.raises(ValidationError):
        _Sample(
            jti="jwt_1745800000_a7f3deadbeef0011",
            operator="alice",
            program="acme-corp",
            score=1.5,
        )


def test_destructive_payload_rejected():
    for bad in [
        "DROP TABLE users",
        "; rm -rf /",
        "SHUTDOWN",
        "TRUNCATE TABLE findings",
    ]:
        with pytest.raises(ValueError, match="destructive payload"):
            reject_destructive_payload(bad)


def test_destructive_payload_allows_safe():
    reject_destructive_payload("SELECT 1")
    reject_destructive_payload("benign poc text")
