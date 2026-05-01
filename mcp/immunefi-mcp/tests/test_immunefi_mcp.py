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
    assert VALID_SEVERITIES == {
        "informational",
        "low",
        "medium",
        "high",
        "critical",
    }


def test_asset_type_set() -> None:
    assert VALID_ASSET_TYPES == {
        "smart_contract",
        "website_and_application",
        "blockchain",
        "other",
    }


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
async def test_submit_body_shape(client_anon, base_kwargs) -> None:
    route = respx.post(f"{DEFAULT_BASE_URL}/v1/reports").respond(
        201, json=_success()
    )
    await client_anon.submit_report(**base_kwargs)
    body = json.loads(route.calls[0].request.content)
    for k in (
        "programme",
        "title",
        "severity",
        "asset_type",
        "asset",
        "impact",
        "vulnerability_details",
        "proof_of_concept",
    ):
        assert k in body


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
