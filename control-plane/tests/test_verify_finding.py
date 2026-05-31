# SPDX-License-Identifier: AGPL-3.0-or-later
"""Unit tests for the deterministic-verifier bridge (plan 01-06).

No DB / network / Playwright / scipy: a fake asyncpg pool+conn records the SQL
executed, the oracle is replaced with a fake coroutine, and a fake evidence
service captures ``record()`` calls. This exercises EVERY branch of
``VerifyFindingService.verify`` deterministically — including the moat invariant
(no ``validated`` without an evidence row) and the audit-added failure paths.

The ``VerifyFindingService`` targets asyncpg/Postgres ($1::uuid casts, now()).
The fakes ignore SQL text, so dialect is irrelevant here; the live-Postgres path
and the XSS field-validation harness (AC-8) are deploy-time gates documented in
the SUMMARY (oracles are stateless probes untouched by the 01-01 DB rebuild).
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from control_plane.domains.validation import VerifyFindingService, resolve_oracle
from control_plane.domains.validation.services import verify_service
from oracle_mcp.result import OracleResult

FID = "11111111-1111-1111-1111-111111111111"
JOB = "22222222-2222-2222-2222-222222222222"


class FakeConn:
    """Records executed SQL; returns a canned claim row and scope jti."""

    def __init__(self, claim_row: dict[str, Any] | None, jti: str | None = "jti-xyz") -> None:
        self._claim_row = claim_row
        self._jti = jti
        self.executed: list[str] = []

    async def fetchrow(self, sql: str, *args: Any) -> dict[str, Any] | None:
        return self._claim_row

    async def fetchval(self, sql: str, *args: Any) -> str | None:
        return self._jti

    async def execute(self, sql: str, *args: Any) -> str:
        self.executed.append(sql)
        return "UPDATE 1"


class _Acquire:
    def __init__(self, conn: FakeConn) -> None:
        self._conn = conn

    async def __aenter__(self) -> FakeConn:
        return self._conn

    async def __aexit__(self, *exc: object) -> bool:
        return False


class FakePool:
    """Returns the SAME FakeConn on every acquire (state persists across writes)."""

    def __init__(self, conn: FakeConn) -> None:
        self._conn = conn

    def acquire(self) -> _Acquire:
        return _Acquire(self._conn)


class FakeEvidence:
    """Captures record() calls; returns a record()-shaped dict."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def record(self, **kwargs: Any) -> dict[str, str]:
        self.calls.append(kwargs)
        return {
            "artifact_id": "art-1",
            "r2_key": "r2/key",
            "content_hash_hex": "deadbeef",
            "chain_hash_hex": "chain1",
        }


def _row(**overrides: Any) -> dict[str, Any]:
    base = {
        "id": FID,
        "job_id": JOB,
        "program_handle": "acme",
        "platform": "hackerone",
        "cwe": "CWE-79",
        "url": "http://target.test/?q=1",
        "parameter": "q",
    }
    base.update(overrides)
    return base


def _spec_returning(result: OracleResult) -> SimpleNamespace:
    async def coro(**_kwargs: Any) -> OracleResult:
        return result

    return SimpleNamespace(oracle_id="fake", coro=coro, kwargs=lambda u, p: {"url": u, "param": p})


def _spec_raising(exc: Exception) -> SimpleNamespace:
    async def coro(**_kwargs: Any) -> OracleResult:
        raise exc

    return SimpleNamespace(oracle_id="fake", coro=coro, kwargs=lambda u, p: {"url": u, "param": p})


# --------------------------------------------------------------------------- #
# AC-3 — dispatch table (pure, no DB)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("cwe", "expected"),
    [
        ("CWE-79", "oracle_xss"),
        ("xss-candidate", "oracle_xss"),
        ("CWE-89", "oracle_sqli"),
        ("sqli-candidate", "oracle_sqli"),
        ("CWE-918", "oracle_ssrf"),
        ("CWE-1336", "oracle_ssti"),
        ("ssti", "oracle_ssti"),
        ("CWE-601", "oracle_open_redirect"),
        ("open-redirect", "oracle_open_redirect"),
    ],
)
def test_dispatch_resolves(cwe: str, expected: str) -> None:
    spec = resolve_oracle(cwe)
    assert spec is not None
    assert spec.oracle_id == expected


@pytest.mark.parametrize(
    "cwe", ["CWE-94", "CWE-74", "CWE-639", "CWE-78", "ssrf-imds", "", None, "x"]
)
def test_dispatch_unsupported_is_none(cwe: str | None) -> None:
    # audit S3: CWE-94 / CWE-74 (generic injection) deliberately resolve to None.
    assert resolve_oracle(cwe) is None


# --------------------------------------------------------------------------- #
# AC-1 — validated -> evidence + status flip
# --------------------------------------------------------------------------- #
async def test_validated_records_evidence_and_flips_status(monkeypatch: pytest.MonkeyPatch) -> None:
    conn = FakeConn(_row())
    ev = FakeEvidence()
    result = OracleResult(verdict="validated", oracle_method="xss_dom_mutation")
    monkeypatch.setattr(verify_service, "resolve_oracle", lambda cwe: _spec_returning(result))

    out = await VerifyFindingService(pool=FakePool(conn), evidence_service=ev).verify(FID)

    assert out["result"] == "validated"
    assert out["evidence_hash"] == "deadbeef"
    assert len(ev.calls) == 1
    assert ev.calls[0]["oracle_verdict"] == "validated"
    assert ev.calls[0]["oracle_method"] == "xss_dom_mutation"
    assert any("status='validated'" in sql for sql in conn.executed)


# --------------------------------------------------------------------------- #
# AC-2 — non-validated -> rejected, NO evidence (moat invariant)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("verdict", ["unreproducible", "flaky", "inconclusive"])
async def test_rejected_writes_no_evidence(monkeypatch: pytest.MonkeyPatch, verdict: str) -> None:
    conn = FakeConn(_row(cwe="CWE-89"))
    ev = FakeEvidence()
    result = OracleResult(verdict=verdict, oracle_method="sqli_timing_welch")
    monkeypatch.setattr(verify_service, "resolve_oracle", lambda cwe: _spec_returning(result))

    out = await VerifyFindingService(pool=FakePool(conn), evidence_service=ev).verify(FID)

    assert out["result"] == "rejected"
    assert out["verdict"] == verdict
    assert len(ev.calls) == 0  # MOAT: no evidence on a non-validated verdict
    assert any("status='rejected'" in sql for sql in conn.executed)
    assert not any("status='validated'" in sql for sql in conn.executed)


# --------------------------------------------------------------------------- #
# AC-4 — unsupported cwe -> parked, no oracle, no evidence
# --------------------------------------------------------------------------- #
async def test_unsupported_cwe_noop() -> None:
    conn = FakeConn(_row(cwe="CWE-639"))
    ev = FakeEvidence()

    out = await VerifyFindingService(pool=FakePool(conn), evidence_service=ev).verify(FID)

    assert out["result"] == "unsupported_cwe"
    assert len(ev.calls) == 0
    # status stays validation_pending (set by CLAIM); no further write.
    assert conn.executed == []


# --------------------------------------------------------------------------- #
# AC-5 — already-claimed / non-hypothesis -> benign no-op
# --------------------------------------------------------------------------- #
async def test_already_claimed_noop() -> None:
    conn = FakeConn(None)  # CLAIM matches 0 rows
    ev = FakeEvidence()

    out = await VerifyFindingService(pool=FakePool(conn), evidence_service=ev).verify(FID)

    assert out["result"] == "noop_unclaimed"
    assert len(ev.calls) == 0
    assert conn.executed == []


# --------------------------------------------------------------------------- #
# AC-9 — transient oracle error releases the claim, re-raises (audit M1)
# --------------------------------------------------------------------------- #
async def test_oracle_error_releases_claim(monkeypatch: pytest.MonkeyPatch) -> None:
    conn = FakeConn(_row())
    ev = FakeEvidence()
    monkeypatch.setattr(
        verify_service, "resolve_oracle", lambda cwe: _spec_raising(RuntimeError("interactsh down"))
    )

    with pytest.raises(RuntimeError):
        await VerifyFindingService(pool=FakePool(conn), evidence_service=ev).verify(FID)

    assert any("status='hypothesis'" in sql for sql in conn.executed)  # claim released
    assert len(ev.calls) == 0
    assert not any("status='validated'" in sql for sql in conn.executed)


# --------------------------------------------------------------------------- #
# AC-10 — validated + missing scope jti -> parked, never rejected (audit M2)
# --------------------------------------------------------------------------- #
async def test_validated_missing_jti_parks_not_rejects(monkeypatch: pytest.MonkeyPatch) -> None:
    conn = FakeConn(_row(job_id=None))  # no job -> no scope jti
    ev = FakeEvidence()
    result = OracleResult(verdict="validated", oracle_method="xss_dom_mutation")
    monkeypatch.setattr(verify_service, "resolve_oracle", lambda cwe: _spec_returning(result))

    out = await VerifyFindingService(pool=FakePool(conn), evidence_service=ev).verify(FID)

    assert out["result"] == "blocked_missing_scope_jti"
    assert len(ev.calls) == 0  # record() never called with an empty jti
    assert not any("status='rejected'" in sql for sql in conn.executed)
    assert not any("status='validated'" in sql for sql in conn.executed)


async def test_validated_jti_null_in_scan_jobs_parks(monkeypatch: pytest.MonkeyPatch) -> None:
    conn = FakeConn(_row(), jti=None)  # job exists but scope_jwt_jti is NULL
    ev = FakeEvidence()
    result = OracleResult(verdict="validated", oracle_method="xss_dom_mutation")
    monkeypatch.setattr(verify_service, "resolve_oracle", lambda cwe: _spec_returning(result))

    out = await VerifyFindingService(pool=FakePool(conn), evidence_service=ev).verify(FID)

    assert out["result"] == "blocked_missing_scope_jti"
    assert len(ev.calls) == 0


# --------------------------------------------------------------------------- #
# AC-11 — null url/parameter never reaches the oracle (audit S1)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("missing", [{"parameter": None}, {"url": None}, {"parameter": ""}])
async def test_missing_oracle_input_noop(missing: dict[str, Any]) -> None:
    # real resolve_oracle returns the XSS spec; the input guard must fire first.
    conn = FakeConn(_row(**missing))
    ev = FakeEvidence()

    out = await VerifyFindingService(pool=FakePool(conn), evidence_service=ev).verify(FID)

    assert out["result"] == "missing_input"
    assert len(ev.calls) == 0
    assert conn.executed == []
