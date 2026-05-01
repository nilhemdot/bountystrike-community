"""Tests for the recon bounded context.

Covers ScopeFilter logic, the BinaryRunner Protocol contract via a fake
runner, the ScanPersistence SQL surface via a mocked asyncpg connection,
and the end-to-end ReconService.run orchestration.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Iterable
from unittest.mock import AsyncMock

import pytest

from control_plane.domains.recon import (
    BinaryRunner,
    KatanaEndpoint,
    ReconService,
    ScanPersistence,
    ScopeFilter,
)
from control_plane.domains.recon.persistence import HypothesisFinding
from control_plane.domains.recon.service import _classify_parameter
from control_plane.domains.recon.tool_runner import (
    HttpxProbe,
    _to_httpx_probe,
    _to_katana_endpoint,
)


# ---------------------------------------------------------------------------
# 1. ScopeFilter — allow/deny semantics
# ---------------------------------------------------------------------------


def _claims(
    wildcards=("*.acme.com",),
    exact_hosts=("api.partner.example",),
    excl_hosts=("internal.acme.com",),
    excl_paths=("/admin/",),
    default_rps=5,
    relaxed=None,
) -> dict:
    return {
        "targets": {
            "wildcards": list(wildcards),
            "exact_hosts": list(exact_hosts),
        },
        "exclusions": {
            "hostnames": list(excl_hosts),
            "paths": list(excl_paths),
        },
        "rate_limits": {
            "default_rps": default_rps,
            "relaxed_hosts": relaxed or {},
        },
    }


def test_scope_filter_allows_apex_and_subdomain():
    sf = ScopeFilter.from_jwt_claims(_claims())
    assert sf.allows_host("acme.com") is True
    assert sf.allows_host("www.acme.com") is True
    assert sf.allows_host("api.deep.acme.com") is True


def test_scope_filter_blocks_excluded_host():
    sf = ScopeFilter.from_jwt_claims(_claims())
    assert sf.allows_host("internal.acme.com") is False


def test_scope_filter_blocks_off_target():
    sf = ScopeFilter.from_jwt_claims(_claims())
    assert sf.allows_host("evil.com") is False
    assert sf.allows_host("acme.com.evil.com") is False


def test_scope_filter_exact_host_allowed():
    sf = ScopeFilter.from_jwt_claims(_claims())
    assert sf.allows_host("api.partner.example") is True
    assert sf.allows_host("other.partner.example") is False


def test_scope_filter_path_exclusion_prefix():
    sf = ScopeFilter.from_jwt_claims(_claims())
    assert sf.allows_path("/api/v1") is True
    assert sf.allows_path("/admin/users") is False


def test_scope_filter_url_combines_host_and_path():
    sf = ScopeFilter.from_jwt_claims(_claims())
    assert sf.allows_url("https://www.acme.com/search?q=1") is True
    assert sf.allows_url("https://www.acme.com/admin/dash") is False
    assert sf.allows_url("https://internal.acme.com/x") is False


def test_scope_filter_rps_relaxed_override():
    sf = ScopeFilter.from_jwt_claims(
        _claims(default_rps=5, relaxed={"www.acme.com": 50})
    )
    assert sf.rps_for_host("www.acme.com") == 50
    assert sf.rps_for_host("api.acme.com") == 5


def test_scope_filter_katana_regex_built():
    sf = ScopeFilter.from_jwt_claims(_claims())
    regex = sf.katana_scope_regex()
    assert "acme\\.com" in regex
    assert "api\\.partner\\.example" in regex


def test_scope_filter_subfinder_domains_strip_wildcard_prefix():
    sf = ScopeFilter.from_jwt_claims(_claims(wildcards=("*.acme.com", "*.bar.io")))
    assert sf.domains_for_subfinder() == ["acme.com", "bar.io"]


# ---------------------------------------------------------------------------
# 2. tool_runner — JSONL → dataclass coercion
# ---------------------------------------------------------------------------


def test_to_httpx_probe_normalizes_dashed_keys():
    row = {
        "url": "https://www.acme.com",
        "host": "www.acme.com",
        "status-code": "200",
        "title": "Acme",
        "tech": ["nginx", "react"],
    }
    probe = _to_httpx_probe(row)
    assert probe.status_code == 200
    assert probe.tech == ("nginx", "react")
    assert probe.url == "https://www.acme.com"


def test_to_katana_endpoint_collects_form_data_params():
    row = {
        "request": {
            "endpoint": "https://www.acme.com/login",
            "method": "POST",
            "form_data": [{"name": "user"}, {"name": "pass"}],
            "body": {"csrf": ""},
        }
    }
    ep = _to_katana_endpoint(row)
    assert ep.url == "https://www.acme.com/login"
    assert ep.method == "POST"
    assert "csrf" in ep.parameters
    assert "user" in ep.parameters
    assert "pass" in ep.parameters


# ---------------------------------------------------------------------------
# 3. ScanPersistence — exercises the SQL surface against a mocked conn
# ---------------------------------------------------------------------------


async def test_scan_persistence_mark_running():
    conn = AsyncMock()
    persistence = ScanPersistence()
    job_id = uuid.uuid4()
    await persistence.mark_running(conn, job_id)
    sql, *args = conn.execute.call_args.args
    assert "UPDATE scan_jobs" in sql
    assert "running" in sql
    assert args == [job_id]


async def test_scan_persistence_mark_complete_writes_counts():
    conn = AsyncMock()
    persistence = ScanPersistence()
    job_id = uuid.uuid4()
    await persistence.mark_complete(conn, job_id, hosts_found=12, endpoints_found=87)
    sql, *args = conn.execute.call_args.args
    assert "recon_complete" in sql
    assert args == [job_id, 12, 87]


async def test_scan_persistence_insert_recon_assets_zero_on_empty():
    conn = AsyncMock()
    persistence = ScanPersistence()
    n = await persistence.insert_recon_assets(conn, uuid.uuid4(), [])
    assert n == 0
    conn.executemany.assert_not_called()


async def test_scan_persistence_insert_recon_assets_calls_executemany():
    conn = AsyncMock()
    persistence = ScanPersistence()
    probes = [
        HttpxProbe(
            url="https://www.acme.com",
            host="www.acme.com",
            status_code=200,
            title="Acme",
            tech=("nginx", "react"),
            raw={"k": "v"},
        ),
        HttpxProbe(
            url="https://api.acme.com",
            host="api.acme.com",
            status_code=403,
            title="",
            tech=(),
            raw={},
        ),
    ]
    n = await persistence.insert_recon_assets(conn, uuid.uuid4(), probes)
    assert n == 2
    sql, rows = conn.executemany.call_args.args
    assert "INSERT INTO recon_assets" in sql
    assert "ON CONFLICT (job_id, host, url) DO NOTHING" in sql
    assert len(rows) == 2
    # 7 placeholders: id, job_id, host, url, tech, status_code, raw
    assert all(len(r) == 7 for r in rows)
    # tech column comma-joins the tuple; empty tuple → None.
    assert rows[0][4] == "nginx,react"
    assert rows[1][4] is None
    # status_code preserved as int.
    assert rows[0][5] == 200
    assert rows[1][5] == 403


async def test_scan_persistence_insert_recon_assets_skips_hostless_probes():
    conn = AsyncMock()
    persistence = ScanPersistence()
    probes = [
        HttpxProbe(url="", host="", status_code=0, title="", tech=(), raw={}),
        HttpxProbe(
            url="https://x.acme.com",
            host="x.acme.com",
            status_code=200,
            title="",
            tech=(),
            raw={},
        ),
    ]
    n = await persistence.insert_recon_assets(conn, uuid.uuid4(), probes)
    assert n == 1
    rows = conn.executemany.call_args.args[1]
    assert rows[0][2] == "x.acme.com"  # only the real host survived


async def test_scan_persistence_insert_findings_zero_on_empty():
    conn = AsyncMock()
    persistence = ScanPersistence()
    n = await persistence.insert_findings(conn, uuid.uuid4(), "acme", "h1", [])
    assert n == 0
    conn.executemany.assert_not_called()


async def test_scan_persistence_insert_findings_calls_executemany():
    conn = AsyncMock()
    persistence = ScanPersistence()
    findings = [
        HypothesisFinding(
            url="https://www.acme.com/?q=1",
            parameter="q",
            cwe="xss-candidate",
        ),
        HypothesisFinding(
            url="https://www.acme.com/r?u=x",
            parameter="u",
            cwe="open-redirect-candidate",
        ),
    ]
    n = await persistence.insert_findings(conn, uuid.uuid4(), "acme", "h1", findings)
    assert n == 2
    sql, rows = conn.executemany.call_args.args
    assert "INSERT INTO findings" in sql
    assert len(rows) == 2
    # Each row must have exactly 8 placeholder values.
    assert all(len(r) == 8 for r in rows)


# ---------------------------------------------------------------------------
# 4. ReconService — end-to-end with a fake BinaryRunner
# ---------------------------------------------------------------------------


class _FakeRunner:
    """Canned BinaryRunner — verifies arg passing + returns scripted data."""

    def __init__(
        self,
        subfinder_hosts: dict[str, list[str]],
        httpx_probes: list[HttpxProbe],
        katana_endpoints: list[KatanaEndpoint],
    ) -> None:
        self.subfinder_hosts = subfinder_hosts
        self.httpx_probes = httpx_probes
        self.katana_endpoints = katana_endpoints
        self.calls: list[tuple[str, tuple]] = []

    async def subfinder(self, domain: str, rps: int) -> list[str]:
        self.calls.append(("subfinder", (domain, rps)))
        return self.subfinder_hosts.get(domain, [])

    async def httpx(self, hosts: Iterable[str], rps: int) -> list[HttpxProbe]:
        self.calls.append(("httpx", (tuple(hosts), rps)))
        return self.httpx_probes

    async def katana(
        self,
        urls: Iterable[str],
        rps: int,
        scope_regex: str,
    ) -> list[KatanaEndpoint]:
        self.calls.append(("katana", (tuple(urls), rps, scope_regex)))
        return self.katana_endpoints


async def test_recon_service_happy_path_persists_findings():
    sf = ScopeFilter.from_jwt_claims(_claims())
    runner: BinaryRunner = _FakeRunner(
        subfinder_hosts={"acme.com": ["www.acme.com", "internal.acme.com", "api.acme.com"]},
        httpx_probes=[
            HttpxProbe(
                url="https://www.acme.com",
                host="www.acme.com",
                status_code=200,
                title="Acme",
                tech=("nginx",),
                raw={},
            ),
            HttpxProbe(
                url="https://api.acme.com",
                host="api.acme.com",
                status_code=403,  # filtered out — not 2xx/3xx
                title="",
                tech=(),
                raw={},
            ),
        ],
        katana_endpoints=[
            KatanaEndpoint(
                url="https://www.acme.com/search?q=hello",
                method="GET",
                parameters=("q",),
                raw={},
            ),
            KatanaEndpoint(
                url="https://www.acme.com/redirect?next=/home",
                method="GET",
                parameters=("next",),
                raw={},
            ),
            KatanaEndpoint(
                url="https://www.acme.com/admin/dash?u=1",  # excluded path
                method="GET",
                parameters=("u",),
                raw={},
            ),
        ],
    )
    persistence = ScanPersistence()
    conn = AsyncMock()

    service = ReconService(runner, persistence, sf)
    job_id = uuid.uuid4()
    result = await service.run(
        conn,
        job_id=job_id,
        program_handle="acme-corp",
        platform="hackerone",
    )

    # 3 from subfinder − 1 excluded (internal) + 1 exact_host = 3 retained.
    assert result.hosts_found == 3
    # only the live 200 URL fed katana → 2 endpoints retained (admin filtered).
    assert result.endpoints_found == 2
    assert result.findings_inserted == 2

    # Verify the persistence calls happened in order.
    assert any(
        "running" in (call.args[0] if call.args else "") for call in conn.execute.call_args_list
    )
    assert any(
        "recon_complete" in (call.args[0] if call.args else "")
        for call in conn.execute.call_args_list
    )


async def test_recon_service_subfinder_failure_is_swallowed():
    """Per service code: a subfinder error logs + skips, doesn't abort."""
    sf = ScopeFilter.from_jwt_claims(_claims(exact_hosts=()))  # only wildcard

    class _Boom:
        async def subfinder(self, *_, **__):
            raise RuntimeError("kaboom")

        async def httpx(self, *_, **__):
            return []

        async def katana(self, *_, **__):
            return []

    persistence = ScanPersistence()
    conn = AsyncMock()
    service = ReconService(_Boom(), persistence, sf)

    result = await service.run(
        conn, uuid.uuid4(), "acme-corp", "hackerone"
    )
    # No exact_hosts and subfinder skipped → zero hosts overall.
    assert result.hosts_found == 0
    assert result.endpoints_found == 0
    assert result.findings_inserted == 0


async def test_recon_service_zero_hosts_completes_cleanly():
    sf = ScopeFilter.from_jwt_claims(
        _claims(wildcards=(), exact_hosts=())  # no scope = no hosts
    )
    runner = _FakeRunner({}, [], [])
    persistence = ScanPersistence()
    conn = AsyncMock()

    service = ReconService(runner, persistence, sf)
    result = await service.run(conn, uuid.uuid4(), "acme-corp", "hackerone")
    assert (result.hosts_found, result.endpoints_found, result.findings_inserted) == (
        0,
        0,
        0,
    )


# ---------------------------------------------------------------------------
# 5. Parameter classification heuristics
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "param,expected",
    [
        ("redirect_url", "open-redirect-candidate"),
        ("next", "open-redirect-candidate"),
        ("target", "ssrf-candidate"),
        ("user_id", "idor-candidate"),
        ("cmd", "rce-candidate"),
        ("template", "ssti-candidate"),
        ("q", "xss-candidate"),       # default fallthrough
        ("anything_else", "xss-candidate"),
    ],
)
def test_classify_parameter(param: str, expected: str):
    assert _classify_parameter(param) == expected
