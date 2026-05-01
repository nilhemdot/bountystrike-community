"""Tests for h1-mcp — client + server submission paths.

Live H1 API is not exercised; httpx requests are mocked with respx.
The MAX_RETRIES retry loop is exercised by counting interceptor calls.
The HTTP Basic auth shape is verified directly against the request
header so a regression in encoding would surface immediately.
"""

from __future__ import annotations

import base64
import json
from unittest.mock import patch

import httpx
import pytest
import respx

from h1_mcp.client import (
    DEFAULT_BASE_URL,
    H1_SEVERITIES,
    HackerOneClient,
    HackerOneError,
)
from h1_mcp.server import _submit_report_impl


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def base_kwargs() -> dict:
    return {
        "team_handle": "acme-corp",
        "title": "Reflected XSS in /search",
        "vulnerability_information": (
            "## Summary\n\nReflected XSS via the q parameter.\n\n"
            "## Reproduction\n\n1. Navigate to /search?q=<payload>"
        ),
        "impact": "Account takeover via session theft on click.",
        "severity_rating": "medium",
        "weakness_id": 79,
    }


@pytest.fixture
def client_with_env(monkeypatch: pytest.MonkeyPatch) -> HackerOneClient:
    monkeypatch.setenv("H1_API_USERNAME", "alice")
    monkeypatch.setenv("H1_API_TOKEN", "tok-secret")
    return HackerOneClient()


def _success_payload(report_id: str = "12345", title: str = "x") -> dict:
    return {
        "data": {
            "id": report_id,
            "type": "report",
            "attributes": {
                "title": title,
                "state": "new",
                "created_at": "2026-05-01T00:00:00.000Z",
            },
        }
    }


# ---------------------------------------------------------------------------
# Client construction
# ---------------------------------------------------------------------------


def test_client_requires_username(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("H1_API_USERNAME", raising=False)
    monkeypatch.setenv("H1_API_TOKEN", "tok")
    with pytest.raises(RuntimeError, match="H1_API_USERNAME"):
        HackerOneClient()


def test_client_requires_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("H1_API_USERNAME", "alice")
    monkeypatch.delenv("H1_API_TOKEN", raising=False)
    with pytest.raises(RuntimeError, match="H1_API_TOKEN"):
        HackerOneClient()


def test_client_explicit_overrides_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("H1_API_USERNAME", raising=False)
    monkeypatch.delenv("H1_API_TOKEN", raising=False)
    c = HackerOneClient(username="bob", api_token="explicit")
    expected = "Basic " + base64.b64encode(b"bob:explicit").decode()
    assert c._headers()["Authorization"] == expected


# ---------------------------------------------------------------------------
# Argument validation
# ---------------------------------------------------------------------------


@respx.mock
async def test_rejects_missing_team_handle(client_with_env, base_kwargs) -> None:
    base_kwargs["team_handle"] = ""
    with pytest.raises(ValueError, match="team_handle"):
        await client_with_env.submit_report(**base_kwargs)


@respx.mock
async def test_rejects_long_title(client_with_env, base_kwargs) -> None:
    base_kwargs["title"] = "x" * 201
    with pytest.raises(ValueError, match="title"):
        await client_with_env.submit_report(**base_kwargs)


@respx.mock
async def test_rejects_unknown_severity(client_with_env, base_kwargs) -> None:
    base_kwargs["severity_rating"] = "informational"  # not in H1's set
    with pytest.raises(ValueError, match="severity_rating"):
        await client_with_env.submit_report(**base_kwargs)


@respx.mock
async def test_accepts_zero_weakness_id(client_with_env, base_kwargs) -> None:
    """``weakness_id=0`` is H1's documented unspecified-weakness sentinel
    (per https://api.hackerone.com/hacker-resources example). Must pass
    the validator and reach the wire as the integer ``0``."""
    route = respx.post(f"{DEFAULT_BASE_URL}/v1/hackers/reports").respond(
        201, json=_success_payload()
    )
    base_kwargs["weakness_id"] = 0
    await client_with_env.submit_report(**base_kwargs)
    sent_body = json.loads(route.calls[0].request.content)
    assert sent_body["data"]["attributes"]["weakness_id"] == 0


@respx.mock
async def test_rejects_negative_weakness_id(client_with_env, base_kwargs) -> None:
    base_kwargs["weakness_id"] = -1
    with pytest.raises(ValueError, match="weakness_id"):
        await client_with_env.submit_report(**base_kwargs)


@respx.mock
async def test_rejects_negative_structured_scope_id(client_with_env, base_kwargs) -> None:
    base_kwargs["structured_scope_id"] = -1
    with pytest.raises(ValueError, match="structured_scope_id"):
        await client_with_env.submit_report(**base_kwargs)


@respx.mock
async def test_structured_scope_id_propagates_to_body(client_with_env, base_kwargs) -> None:
    route = respx.post(f"{DEFAULT_BASE_URL}/v1/hackers/reports").respond(
        201, json=_success_payload()
    )
    base_kwargs["structured_scope_id"] = 287
    await client_with_env.submit_report(**base_kwargs)
    sent_body = json.loads(route.calls[0].request.content)
    assert sent_body["data"]["attributes"]["structured_scope_id"] == 287


@respx.mock
async def test_structured_scope_id_omitted_when_none(client_with_env, base_kwargs) -> None:
    route = respx.post(f"{DEFAULT_BASE_URL}/v1/hackers/reports").respond(
        201, json=_success_payload()
    )
    await client_with_env.submit_report(**base_kwargs)
    sent_body = json.loads(route.calls[0].request.content)
    assert "structured_scope_id" not in sent_body["data"]["attributes"]


def test_h1_severities_set_excludes_informational() -> None:
    assert "informational" not in H1_SEVERITIES
    assert "none" in H1_SEVERITIES


# ---------------------------------------------------------------------------
# 201 success path
# ---------------------------------------------------------------------------


@respx.mock
async def test_submit_201_returns_structured_dict(client_with_env, base_kwargs) -> None:
    route = respx.post(f"{DEFAULT_BASE_URL}/v1/hackers/reports").respond(
        201,
        json=_success_payload("99999", base_kwargs["title"]),
    )
    out = await client_with_env.submit_report(**base_kwargs)
    assert route.called
    assert out["submission_id"] == "99999"
    assert out["state"] == "new"
    assert out["title"] == base_kwargs["title"]
    assert out["created_at"] == "2026-05-01T00:00:00.000Z"


@respx.mock
async def test_submit_sends_basic_auth(client_with_env, base_kwargs) -> None:
    route = respx.post(f"{DEFAULT_BASE_URL}/v1/hackers/reports").respond(
        201, json=_success_payload()
    )
    await client_with_env.submit_report(**base_kwargs)
    sent = route.calls[0].request
    expected = "Basic " + base64.b64encode(b"alice:tok-secret").decode()
    assert sent.headers["authorization"] == expected
    assert sent.headers["content-type"] == "application/json"


@respx.mock
async def test_submit_body_jsonapi_shape(client_with_env, base_kwargs) -> None:
    route = respx.post(f"{DEFAULT_BASE_URL}/v1/hackers/reports").respond(
        201, json=_success_payload()
    )
    await client_with_env.submit_report(**base_kwargs)
    sent_body = json.loads(route.calls[0].request.content)
    assert sent_body == {
        "data": {
            "type": "report",
            "attributes": {
                "team_handle": "acme-corp",
                "title": base_kwargs["title"],
                "vulnerability_information": base_kwargs[
                    "vulnerability_information"
                ],
                "impact": base_kwargs["impact"],
                "severity_rating": "medium",
                "weakness_id": 79,
            },
        }
    }


@respx.mock
async def test_weakness_id_omitted_when_none(client_with_env, base_kwargs) -> None:
    base_kwargs["weakness_id"] = None
    route = respx.post(f"{DEFAULT_BASE_URL}/v1/hackers/reports").respond(
        201, json=_success_payload()
    )
    await client_with_env.submit_report(**base_kwargs)
    sent_body = json.loads(route.calls[0].request.content)
    assert "weakness_id" not in sent_body["data"]["attributes"]


# ---------------------------------------------------------------------------
# 4xx — caller must fix, no retry
# ---------------------------------------------------------------------------


@respx.mock
async def test_submit_400_raises_no_retry(client_with_env, base_kwargs) -> None:
    err = {
        "errors": [
            {
                "status": "400",
                "title": "Invalid",
                "detail": "team_handle does not exist",
            }
        ]
    }
    route = respx.post(f"{DEFAULT_BASE_URL}/v1/hackers/reports").respond(
        400, json=err
    )
    with pytest.raises(HackerOneError) as info:
        await client_with_env.submit_report(**base_kwargs)
    assert info.value.status_code == 400
    assert info.value.body == err
    assert route.call_count == 1


@respx.mock
async def test_submit_401_raises_no_retry(client_with_env, base_kwargs) -> None:
    route = respx.post(f"{DEFAULT_BASE_URL}/v1/hackers/reports").respond(
        401, json={"errors": [{"status": "401", "title": "Unauthorized"}]}
    )
    with pytest.raises(HackerOneError):
        await client_with_env.submit_report(**base_kwargs)
    assert route.call_count == 1


@respx.mock
async def test_submit_422_validation_no_retry(client_with_env, base_kwargs) -> None:
    route = respx.post(f"{DEFAULT_BASE_URL}/v1/hackers/reports").respond(
        422, json={"errors": [{"status": "422", "detail": "title too short"}]}
    )
    with pytest.raises(HackerOneError) as info:
        await client_with_env.submit_report(**base_kwargs)
    assert info.value.status_code == 422
    assert route.call_count == 1


# ---------------------------------------------------------------------------
# 5xx — retried up to MAX_RETRIES
# ---------------------------------------------------------------------------


@respx.mock
async def test_submit_5xx_retries_then_succeeds(client_with_env, base_kwargs) -> None:
    with patch("h1_mcp.client.RETRY_BACKOFF_S", (0.0, 0.0)):
        route = respx.post(f"{DEFAULT_BASE_URL}/v1/hackers/reports").mock(
            side_effect=[
                httpx.Response(503),
                httpx.Response(201, json=_success_payload("13")),
            ]
        )
        out = await client_with_env.submit_report(**base_kwargs)
    assert out["submission_id"] == "13"
    assert route.call_count == 2


@respx.mock
async def test_submit_5xx_retries_then_gives_up(client_with_env, base_kwargs) -> None:
    with patch("h1_mcp.client.RETRY_BACKOFF_S", (0.0, 0.0)):
        route = respx.post(f"{DEFAULT_BASE_URL}/v1/hackers/reports").respond(
            503, json={"error": "down"}
        )
        with pytest.raises(HackerOneError) as info:
            await client_with_env.submit_report(**base_kwargs)
    assert info.value.status_code == 503
    assert route.call_count == 3  # initial + 2 retries


@respx.mock
async def test_submit_network_error_retries(client_with_env, base_kwargs) -> None:
    with patch("h1_mcp.client.RETRY_BACKOFF_S", (0.0, 0.0)):
        respx.post(f"{DEFAULT_BASE_URL}/v1/hackers/reports").mock(
            side_effect=httpx.ConnectError("conn refused")
        )
        with pytest.raises(HackerOneError) as info:
            await client_with_env.submit_report(**base_kwargs)
    assert info.value.status_code is None
    assert "network error" in str(info.value)


# ---------------------------------------------------------------------------
# Server impl — wraps client errors as ok=False
# ---------------------------------------------------------------------------


@respx.mock
async def test_server_impl_returns_ok_true_on_success(client_with_env, base_kwargs) -> None:
    respx.post(f"{DEFAULT_BASE_URL}/v1/hackers/reports").respond(
        201, json=_success_payload("777")
    )
    out = await _submit_report_impl(client_with_env, **base_kwargs)
    assert out["ok"] is True
    assert out["submission_id"] == "777"


@respx.mock
async def test_server_impl_returns_ok_false_on_4xx(client_with_env, base_kwargs) -> None:
    respx.post(f"{DEFAULT_BASE_URL}/v1/hackers/reports").respond(
        403, json={"errors": [{"status": "403", "title": "Forbidden"}]}
    )
    out = await _submit_report_impl(client_with_env, **base_kwargs)
    assert out["ok"] is False
    assert out["status_code"] == 403


# ---------------------------------------------------------------------------
# Sanity: malformed success payload
# ---------------------------------------------------------------------------


@respx.mock
async def test_submit_rejects_payload_missing_data(client_with_env, base_kwargs) -> None:
    respx.post(f"{DEFAULT_BASE_URL}/v1/hackers/reports").respond(
        201, json={"unexpected": "shape"}
    )
    with pytest.raises(HackerOneError, match="missing 'data'"):
        await client_with_env.submit_report(**base_kwargs)


# ---------------------------------------------------------------------------
# Audit-fix coverage — base_url URL guard, body truncation, non-JSON 2xx.
# ---------------------------------------------------------------------------


def test_construction_rejects_metadata_ip_base_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("H1_API_USERNAME", "alice")
    monkeypatch.setenv("H1_API_TOKEN", "tok")
    from h1_mcp._url_guard import UrlGuardError

    with pytest.raises(UrlGuardError):
        HackerOneClient(base_url="https://169.254.169.254/")


def test_construction_rejects_http_base_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("H1_API_USERNAME", "alice")
    monkeypatch.setenv("H1_API_TOKEN", "tok")
    monkeypatch.delenv("BS_PLATFORM_ALLOW_HTTP", raising=False)
    from h1_mcp._url_guard import UrlGuardError

    with pytest.raises(UrlGuardError):
        HackerOneClient(base_url="http://api.hackerone.com/")


@respx.mock
async def test_error_body_truncated(client_with_env, base_kwargs) -> None:
    from h1_mcp.client import MAX_ERROR_BODY_BYTES

    huge = {"errors": [{"detail": "x" * 100_000}]}
    respx.post(f"{DEFAULT_BASE_URL}/v1/hackers/reports").respond(400, json=huge)
    with pytest.raises(HackerOneError) as info:
        await client_with_env.submit_report(**base_kwargs)
    body_repr = (
        info.value.body
        if isinstance(info.value.body, str)
        else json.dumps(info.value.body)
    )
    assert len(body_repr) <= MAX_ERROR_BODY_BYTES + 64
    assert "TRUNCATED" in body_repr


@respx.mock
async def test_non_json_2xx_raises_typed_error(client_with_env, base_kwargs) -> None:
    respx.post(f"{DEFAULT_BASE_URL}/v1/hackers/reports").respond(
        201, content="<html>oops</html>", headers={"content-type": "text/html"}
    )
    with pytest.raises(HackerOneError, match="non-JSON 2xx body"):
        await client_with_env.submit_report(**base_kwargs)


# ---------------------------------------------------------------------------
# 429 retry with Retry-After honor (audit reviewer 1, MEDIUM).
# ---------------------------------------------------------------------------


def test_parse_retry_after_seconds() -> None:
    from h1_mcp.client import RETRY_AFTER_CAP_SEC, _parse_retry_after

    assert _parse_retry_after("12") == 12.0
    # Capped at RETRY_AFTER_CAP_SEC.
    assert _parse_retry_after("99999") == RETRY_AFTER_CAP_SEC
    # Negative rejected.
    assert _parse_retry_after("-1") is None
    # Empty / garbage returns None.
    assert _parse_retry_after("") is None
    assert _parse_retry_after("not-a-number") is None


@respx.mock
async def test_429_retried_then_succeeds(client_with_env, base_kwargs) -> None:
    with patch("h1_mcp.client.RETRY_BACKOFF_S", (0.0, 0.0)):
        route = respx.post(f"{DEFAULT_BASE_URL}/v1/hackers/reports").mock(
            side_effect=[
                httpx.Response(429, headers={"Retry-After": "0"}),
                httpx.Response(201, json=_success_payload("rl-1")),
            ]
        )
        out = await client_with_env.submit_report(**base_kwargs)
    assert out["submission_id"] == "rl-1"
    assert route.call_count == 2


@respx.mock
async def test_429_gives_up_after_max_retries(client_with_env, base_kwargs) -> None:
    with patch("h1_mcp.client.RETRY_BACKOFF_S", (0.0, 0.0)):
        route = respx.post(f"{DEFAULT_BASE_URL}/v1/hackers/reports").respond(
            429, headers={"Retry-After": "0"}, json={"errors": [{"status": "429"}]}
        )
        with pytest.raises(HackerOneError) as info:
            await client_with_env.submit_report(**base_kwargs)
    assert info.value.status_code == 429
    assert "rate-limited" in str(info.value)
    assert route.call_count == 3  # initial + 2 retries
