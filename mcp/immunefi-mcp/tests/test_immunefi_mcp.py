"""Tests for immunefi-mcp — client + server."""

from __future__ import annotations

import json
from unittest.mock import patch

import httpx
import pytest
import respx
from immunefi_mcp.client import (
    DEFAULT_BASE_URL,
    VALID_ASSET_TYPES,
    VALID_SEVERITIES,
    ImmunefiClient,
    ImmunefiError,
)
from immunefi_mcp.server import _submit_report_impl


@pytest.fixture
def base_kwargs() -> dict:
    return {
        "programme": "lendingpool-x",
        "title": "Reentrancy in withdraw()",
        "severity": "critical",
        "asset_type": "smart_contract",
        "asset": "0xabcdef0123456789abcdef0123456789abcdef01",
        "impact": "Drain of vault funds.",
        "vulnerability_details": "## Summary\n\nReentrancy via fallback.",
        "proof_of_concept": "1. Deploy attacker contract.",
    }


@pytest.fixture
def client_anon(monkeypatch: pytest.MonkeyPatch) -> ImmunefiClient:
    # Default anonymous client (no IMMUNEFI_API_TOKEN).
    monkeypatch.delenv("IMMUNEFI_API_TOKEN", raising=False)
    return ImmunefiClient()


@pytest.fixture
def client_authed(monkeypatch: pytest.MonkeyPatch) -> ImmunefiClient:
    monkeypatch.setenv("IMMUNEFI_API_TOKEN", "tok-secret")
    return ImmunefiClient()


def _success() -> dict:
    return {
        "id": "rep-uuid",
        "status": "received",
        "title": "Reentrancy in withdraw()",
    }


# -- construction --

def test_anonymous_construction_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    """Auth is OPTIONAL — construction without env must succeed."""
    monkeypatch.delenv("IMMUNEFI_API_TOKEN", raising=False)
    c = ImmunefiClient()
    assert "Authorization" not in c._headers()


def test_authed_construction_sets_bearer(client_authed) -> None:
    assert client_authed._headers()["Authorization"] == "Bearer tok-secret"


def test_severity_set() -> None:
    assert {
        "informational",
        "low",
        "medium",
        "high",
        "critical",
    } == VALID_SEVERITIES


def test_asset_type_set() -> None:
    assert {
        "smart_contract",
        "website_and_application",
        "blockchain",
        "other",
    } == VALID_ASSET_TYPES


# -- validation --

@respx.mock
async def test_rejects_missing_programme(client_anon, base_kwargs) -> None:
    base_kwargs["programme"] = ""
    with pytest.raises(ValueError, match="programme"):
        await client_anon.submit_report(**base_kwargs)


@respx.mock
async def test_rejects_long_title(client_anon, base_kwargs) -> None:
    base_kwargs["title"] = "x" * 201
    with pytest.raises(ValueError, match="title"):
        await client_anon.submit_report(**base_kwargs)


@respx.mock
async def test_rejects_unknown_severity(client_anon, base_kwargs) -> None:
    base_kwargs["severity"] = "spicy"
    with pytest.raises(ValueError, match="severity"):
        await client_anon.submit_report(**base_kwargs)


@respx.mock
async def test_rejects_unknown_asset_type(client_anon, base_kwargs) -> None:
    base_kwargs["asset_type"] = "unicorn"
    with pytest.raises(ValueError, match="asset_type"):
        await client_anon.submit_report(**base_kwargs)


# -- 201 happy path --

@respx.mock
async def test_submit_201_anonymous(client_anon, base_kwargs) -> None:
    route = respx.post(f"{DEFAULT_BASE_URL}/v1/reports").respond(
        201, json=_success()
    )
    out = await client_anon.submit_report(**base_kwargs)
    assert route.called
    assert out["submission_id"] == "rep-uuid"
    # Anonymous: no Authorization header sent.
    assert "authorization" not in route.calls[0].request.headers


@respx.mock
async def test_submit_201_authenticated(client_authed, base_kwargs) -> None:
    route = respx.post(f"{DEFAULT_BASE_URL}/v1/reports").respond(
        201, json=_success()
    )
    await client_authed.submit_report(**base_kwargs)
    assert route.calls[0].request.headers["authorization"] == "Bearer tok-secret"


@respx.mock
async def test_submit_body_field_values(client_anon, base_kwargs) -> None:
    """Tighter than a key-presence check — assert each field's *value*
    matches the input. Audit reviewer 1 flagged key-only assertions
    as a false-green risk for regressions that drop / swap fields."""
    route = respx.post(f"{DEFAULT_BASE_URL}/v1/reports").respond(
        201, json=_success()
    )
    await client_anon.submit_report(**base_kwargs)
    body = json.loads(route.calls[0].request.content)
    assert body == {
        "programme": base_kwargs["programme"],
        "title": base_kwargs["title"],
        "severity": base_kwargs["severity"].lower(),
        "asset_type": base_kwargs["asset_type"].lower(),
        "asset": base_kwargs["asset"],
        "impact": base_kwargs["impact"],
        "vulnerability_details": base_kwargs["vulnerability_details"],
        "proof_of_concept": base_kwargs["proof_of_concept"],
    }


@respx.mock
async def test_submit_url_override(client_anon, base_kwargs) -> None:
    custom = "https://programme.example.com/relay/submit"
    route = respx.post(custom).respond(201, json=_success())
    base_kwargs["submit_url"] = custom
    await client_anon.submit_report(**base_kwargs)
    assert route.called


@respx.mock
async def test_extra_appended_no_contract_overwrite(client_anon, base_kwargs) -> None:
    route = respx.post(f"{DEFAULT_BASE_URL}/v1/reports").respond(
        201, json=_success()
    )
    base_kwargs["extra"] = {
        "title": "OVERWRITE-ATTEMPT",
        "wallet_address_for_payout": "0xdeadbeef",
    }
    await client_anon.submit_report(**base_kwargs)
    body = json.loads(route.calls[0].request.content)
    assert body["title"] == "Reentrancy in withdraw()"
    assert body["wallet_address_for_payout"] == "0xdeadbeef"


# -- 4xx no retry --

@respx.mock
async def test_submit_400_no_retry(client_anon, base_kwargs) -> None:
    route = respx.post(f"{DEFAULT_BASE_URL}/v1/reports").respond(
        400, json={"error": "invalid"}
    )
    with pytest.raises(ImmunefiError) as info:
        await client_anon.submit_report(**base_kwargs)
    assert info.value.status_code == 400
    assert route.call_count == 1


# -- 5xx retry --

@respx.mock
async def test_submit_5xx_then_succeeds(client_anon, base_kwargs) -> None:
    with patch("immunefi_mcp.client.RETRY_BACKOFF_S", (0.0, 0.0)):
        route = respx.post(f"{DEFAULT_BASE_URL}/v1/reports").mock(
            side_effect=[
                httpx.Response(503),
                httpx.Response(201, json=_success()),
            ]
        )
        out = await client_anon.submit_report(**base_kwargs)
    assert out["submission_id"] == "rep-uuid"
    assert route.call_count == 2


# -- server impl --

@respx.mock
async def test_server_impl_ok_true(client_anon, base_kwargs) -> None:
    respx.post(f"{DEFAULT_BASE_URL}/v1/reports").respond(201, json=_success())
    out = await _submit_report_impl(client_anon, **base_kwargs)
    assert out["ok"] is True


@respx.mock
async def test_server_impl_ok_false_on_4xx(client_anon, base_kwargs) -> None:
    respx.post(f"{DEFAULT_BASE_URL}/v1/reports").respond(
        429, json={"error": "rate limit"}
    )
    out = await _submit_report_impl(client_anon, **base_kwargs)
    assert out["ok"] is False
    assert out["status_code"] == 429


# ---------------------------------------------------------------------------
# Audit-fix coverage — URL guard, base_url validation, body truncation,
# Authorization stripping on override host mismatch (CRITICAL findings
# from the post-ship audit).
# ---------------------------------------------------------------------------


def test_construction_rejects_metadata_ip(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A misconfigured IMMUNEFI_BASE_URL pointing at the AWS metadata
    service must fail loudly at client construction — not silently send
    the Bearer to 169.254.169.254 on the first submit."""
    from immunefi_mcp._url_guard import UrlGuardError

    with pytest.raises(UrlGuardError):
        ImmunefiClient(api_token="t", base_url="https://169.254.169.254/")


def test_construction_rejects_http_in_production(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """http:// base URL is rejected in production (BS_PLATFORM_ALLOW_HTTP unset)."""
    from immunefi_mcp._url_guard import UrlGuardError

    monkeypatch.delenv("BS_PLATFORM_ALLOW_HTTP", raising=False)
    with pytest.raises(UrlGuardError):
        ImmunefiClient(api_token="t", base_url="http://api.immunefi.com/")


def test_construction_rejects_file_scheme() -> None:
    from immunefi_mcp._url_guard import UrlGuardError

    with pytest.raises(UrlGuardError):
        ImmunefiClient(api_token="t", base_url="file:///etc/passwd")


@respx.mock
async def test_submit_url_with_metadata_ip_rejected(
    client_authed, base_kwargs
) -> None:
    """LLM-controllable submit_url MUST not reach the AWS metadata IP."""
    base_kwargs["submit_url"] = "https://169.254.169.254/exfil"
    with pytest.raises(ValueError, match="URL guard"):
        await client_authed.submit_report(**base_kwargs)


@respx.mock
async def test_submit_url_with_file_scheme_rejected(
    client_authed, base_kwargs
) -> None:
    base_kwargs["submit_url"] = "file:///tmp/exfil"
    with pytest.raises(ValueError, match="URL guard"):
        await client_authed.submit_report(**base_kwargs)


@respx.mock
async def test_override_url_strips_auth_when_host_differs(
    client_authed, base_kwargs
) -> None:
    """Authorization header MUST NOT be sent to a relay on a different
    host than the configured base URL — the Bearer is for Immunefi, not
    the relay."""
    relay = "https://relay.example.com/intake"
    route = respx.post(relay).respond(
        201, json={"id": "rep-uuid", "status": "received", "title": "x"}
    )
    base_kwargs["submit_url"] = relay
    await client_authed.submit_report(**base_kwargs)
    sent = route.calls[0].request
    # CRITICAL: Bearer must be stripped because host != api.immunefi.com
    assert "authorization" not in {k.lower() for k in sent.headers}


@respx.mock
async def test_override_url_keeps_auth_when_host_matches(
    client_authed, base_kwargs
) -> None:
    """Override URL on the SAME host (e.g. a path on api.immunefi.com)
    keeps the Bearer — that is a legitimate per-programme path on the
    same platform."""
    same_host = "https://api.immunefi.com/programmes/foo/submit"
    route = respx.post(same_host).respond(
        201, json={"id": "rep-uuid", "status": "received", "title": "x"}
    )
    base_kwargs["submit_url"] = same_host
    await client_authed.submit_report(**base_kwargs)
    sent = route.calls[0].request
    assert sent.headers["authorization"] == "Bearer tok-secret"


@respx.mock
async def test_error_body_truncated_to_max_size(client_anon, base_kwargs) -> None:
    """A multi-MB error body MUST be capped before reaching MCP stdio."""
    from immunefi_mcp.client import MAX_ERROR_BODY_BYTES

    huge = {"err": "x" * 100_000}
    respx.post(f"{DEFAULT_BASE_URL}/v1/reports").respond(400, json=huge)
    with pytest.raises(ImmunefiError) as info:
        await client_anon.submit_report(**base_kwargs)
    body_repr = (
        info.value.body
        if isinstance(info.value.body, str)
        else json.dumps(info.value.body)
    )
    assert len(body_repr) <= MAX_ERROR_BODY_BYTES + 64
    assert "TRUNCATED" in body_repr


@respx.mock
async def test_non_json_2xx_raises_typed_error(client_anon, base_kwargs) -> None:
    """An empty / non-JSON 2xx body must raise ImmunefiError, not the
    raw json.JSONDecodeError — preserves the typed-error contract that
    callers depend on."""
    respx.post(f"{DEFAULT_BASE_URL}/v1/reports").respond(
        201, content="<html>oops</html>", headers={"content-type": "text/html"}
    )
    with pytest.raises(ImmunefiError, match="non-JSON 2xx body"):
        await client_anon.submit_report(**base_kwargs)


# ---------------------------------------------------------------------------
# 429 retry coverage.
# ---------------------------------------------------------------------------


@respx.mock
async def test_429_retried_then_succeeds(client_anon, base_kwargs) -> None:
    with patch("immunefi_mcp.client.RETRY_BACKOFF_S", (0.0, 0.0)):
        route = respx.post(f"{DEFAULT_BASE_URL}/v1/reports").mock(
            side_effect=[
                httpx.Response(429, headers={"Retry-After": "0"}),
                httpx.Response(201, json=_success()),
            ]
        )
        out = await client_anon.submit_report(**base_kwargs)
    assert out["submission_id"] == "rep-uuid"
    assert route.call_count == 2


@respx.mock
async def test_429_gives_up_after_max_retries(client_anon, base_kwargs) -> None:
    with patch("immunefi_mcp.client.RETRY_BACKOFF_S", (0.0, 0.0)):
        route = respx.post(f"{DEFAULT_BASE_URL}/v1/reports").respond(
            429, headers={"Retry-After": "0"}, json={"error": "rate limit"}
        )
        with pytest.raises(ImmunefiError) as info:
            await client_anon.submit_report(**base_kwargs)
    assert info.value.status_code == 429
    assert "rate-limited" in str(info.value)
    assert route.call_count == 3
