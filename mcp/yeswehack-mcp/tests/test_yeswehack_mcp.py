"""Tests for yeswehack-mcp — client + server submission paths.

Live YWH API is not exercised; httpx requests are mocked with respx.
The MAX_RETRIES retry loop is exercised by counting interceptor calls.
"""

from __future__ import annotations

from unittest.mock import patch

import httpx
import pytest
import respx

from yeswehack_mcp.client import (
    DEFAULT_BASE_URL,
    YesWeHackClient,
    YesWeHackError,
)
from yeswehack_mcp.server import _submit_report_impl


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def base_kwargs() -> dict:
    return {
        "program_slug": "acme",
        "title": "Reflected XSS in /search",
        "scope": "https://acme.com/search",
        "vulnerability_type": "CWE-79",
        "severity": "medium",
        "cvss_vector": "CVSS:3.1/AV:N/AC:L/PR:N/UI:R/S:C/C:L/I:L/A:N",
        "description": "## Summary\n\nReflected XSS via q parameter.",
        "exploit_information": "1. Visit /search?q=<payload>",
    }


@pytest.fixture
def client_with_mock(monkeypatch: pytest.MonkeyPatch) -> YesWeHackClient:
    monkeypatch.setenv("YESWEHACK_API_TOKEN", "tok-123")
    return YesWeHackClient()


# ---------------------------------------------------------------------------
# Client construction
# ---------------------------------------------------------------------------


def test_client_requires_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("YESWEHACK_API_TOKEN", raising=False)
    with pytest.raises(RuntimeError, match="YESWEHACK_API_TOKEN"):
        YesWeHackClient()


def test_client_explicit_token_overrides_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("YESWEHACK_API_TOKEN", raising=False)
    client = YesWeHackClient(api_token="explicit")
    # Bearer header carries the explicit token.
    assert client._headers()["Authorization"] == "Bearer explicit"


# ---------------------------------------------------------------------------
# Argument validation
# ---------------------------------------------------------------------------


@respx.mock
async def test_rejects_missing_program_slug(client_with_mock, base_kwargs) -> None:
    base_kwargs["program_slug"] = ""
    with pytest.raises(ValueError, match="program_slug"):
        await client_with_mock.submit_report(**base_kwargs)


@respx.mock
async def test_rejects_long_title(client_with_mock, base_kwargs) -> None:
    base_kwargs["title"] = "x" * 201
    with pytest.raises(ValueError, match="title"):
        await client_with_mock.submit_report(**base_kwargs)


@respx.mock
async def test_rejects_unknown_severity(client_with_mock, base_kwargs) -> None:
    base_kwargs["severity"] = "spicy"
    with pytest.raises(ValueError, match="severity"):
        await client_with_mock.submit_report(**base_kwargs)


# ---------------------------------------------------------------------------
# 201 success path
# ---------------------------------------------------------------------------


@respx.mock
async def test_submit_201_returns_structured_dict(client_with_mock, base_kwargs) -> None:
    route = respx.post(
        f"{DEFAULT_BASE_URL}/api/v1/programs/acme/reports"
    ).respond(
        201,
        json={"id": 8675309, "title": base_kwargs["title"], "state": "ASKED"},
    )
    out = await client_with_mock.submit_report(**base_kwargs)
    assert route.called
    assert out["submission_id"] == 8675309
    assert out["state"] == "ASKED"
    assert out["title"] == base_kwargs["title"]


@respx.mock
async def test_submit_sends_bearer_auth(client_with_mock, base_kwargs) -> None:
    route = respx.post(
        f"{DEFAULT_BASE_URL}/api/v1/programs/acme/reports"
    ).respond(201, json={"id": 1, "title": "x", "state": "ASKED"})
    await client_with_mock.submit_report(**base_kwargs)
    sent = route.calls[0].request
    assert sent.headers["authorization"] == "Bearer tok-123"
    assert sent.headers["content-type"] == "application/json"


@respx.mock
async def test_submit_body_includes_required_fields(client_with_mock, base_kwargs) -> None:
    route = respx.post(
        f"{DEFAULT_BASE_URL}/api/v1/programs/acme/reports"
    ).respond(201, json={"id": 1, "title": "x", "state": "ASKED"})
    await client_with_mock.submit_report(**base_kwargs)
    import json
    sent_body = json.loads(route.calls[0].request.content)
    for key in (
        "title",
        "scope",
        "vulnerability_type",
        "severity",
        "cvss",
        "description",
        "exploit_information",
    ):
        assert key in sent_body


# ---------------------------------------------------------------------------
# 4xx — caller must fix, no retry
# ---------------------------------------------------------------------------


@respx.mock
async def test_submit_400_raises_no_retry(client_with_mock, base_kwargs) -> None:
    route = respx.post(
        f"{DEFAULT_BASE_URL}/api/v1/programs/acme/reports"
    ).respond(400, json={"error": "title too short"})
    with pytest.raises(YesWeHackError) as info:
        await client_with_mock.submit_report(**base_kwargs)
    assert info.value.status_code == 400
    assert info.value.body == {"error": "title too short"}
    # Did not retry on 4xx.
    assert route.call_count == 1


@respx.mock
async def test_submit_401_raises_no_retry(client_with_mock, base_kwargs) -> None:
    route = respx.post(
        f"{DEFAULT_BASE_URL}/api/v1/programs/acme/reports"
    ).respond(401, json={"error": "unauthorized"})
    with pytest.raises(YesWeHackError):
        await client_with_mock.submit_report(**base_kwargs)
    assert route.call_count == 1


# ---------------------------------------------------------------------------
# 5xx — retried up to MAX_RETRIES
# ---------------------------------------------------------------------------


@respx.mock
async def test_submit_5xx_retries_then_succeeds(client_with_mock, base_kwargs) -> None:
    # First call fails, second succeeds.
    with patch("yeswehack_mcp.client.RETRY_BACKOFF_S", (0.0, 0.0)):
        route = respx.post(
            f"{DEFAULT_BASE_URL}/api/v1/programs/acme/reports"
        ).mock(
            side_effect=[
                httpx.Response(503),
                httpx.Response(201, json={"id": 9, "title": "x", "state": "ASKED"}),
            ]
        )
        out = await client_with_mock.submit_report(**base_kwargs)
    assert out["submission_id"] == 9
    assert route.call_count == 2


@respx.mock
async def test_submit_5xx_retries_then_gives_up(client_with_mock, base_kwargs) -> None:
    with patch("yeswehack_mcp.client.RETRY_BACKOFF_S", (0.0, 0.0)):
        route = respx.post(
            f"{DEFAULT_BASE_URL}/api/v1/programs/acme/reports"
        ).respond(503, json={"error": "down"})
        with pytest.raises(YesWeHackError) as info:
            await client_with_mock.submit_report(**base_kwargs)
    assert info.value.status_code == 503
    # Initial call + 2 retries.
    assert route.call_count == 3


@respx.mock
async def test_submit_network_error_retries(client_with_mock, base_kwargs) -> None:
    with patch("yeswehack_mcp.client.RETRY_BACKOFF_S", (0.0, 0.0)):
        respx.post(
            f"{DEFAULT_BASE_URL}/api/v1/programs/acme/reports"
        ).mock(side_effect=httpx.ConnectError("conn refused"))
        with pytest.raises(YesWeHackError) as info:
            await client_with_mock.submit_report(**base_kwargs)
    assert info.value.status_code is None
    assert "network error" in str(info.value)


# ---------------------------------------------------------------------------
# Server impl — wraps client errors as ok=False
# ---------------------------------------------------------------------------


@respx.mock
async def test_server_impl_returns_ok_true_on_success(client_with_mock, base_kwargs) -> None:
    respx.post(
        f"{DEFAULT_BASE_URL}/api/v1/programs/acme/reports"
    ).respond(201, json={"id": 1, "title": "x", "state": "ASKED"})
    out = await _submit_report_impl(client_with_mock, **base_kwargs)
    assert out["ok"] is True
    assert out["submission_id"] == 1


@respx.mock
async def test_server_impl_returns_ok_false_on_4xx(client_with_mock, base_kwargs) -> None:
    respx.post(
        f"{DEFAULT_BASE_URL}/api/v1/programs/acme/reports"
    ).respond(403, json={"error": "forbidden"})
    out = await _submit_report_impl(client_with_mock, **base_kwargs)
    assert out["ok"] is False
    assert out["status_code"] == 403
    assert out["body"] == {"error": "forbidden"}


# ---------------------------------------------------------------------------
# Audit-fix coverage — base_url URL guard, body truncation, non-JSON 2xx.
# ---------------------------------------------------------------------------


def test_construction_rejects_metadata_ip_base_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("YESWEHACK_API_TOKEN", "tok")
    from yeswehack_mcp._url_guard import UrlGuardError

    with pytest.raises(UrlGuardError):
        YesWeHackClient(base_url="https://169.254.169.254/")


def test_construction_rejects_http_base_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("YESWEHACK_API_TOKEN", "tok")
    monkeypatch.delenv("BS_PLATFORM_ALLOW_HTTP", raising=False)
    from yeswehack_mcp._url_guard import UrlGuardError

    with pytest.raises(UrlGuardError):
        YesWeHackClient(base_url="http://api.yeswehack.com/")


@respx.mock
async def test_error_body_truncated(client_with_mock, base_kwargs) -> None:
    import json as _json

    from yeswehack_mcp.client import MAX_ERROR_BODY_BYTES

    huge = {"err": "x" * 100_000}
    respx.post(
        f"{DEFAULT_BASE_URL}/api/v1/programs/acme/reports"
    ).respond(400, json=huge)
    with pytest.raises(YesWeHackError) as info:
        await client_with_mock.submit_report(**base_kwargs)
    body_repr = (
        info.value.body
        if isinstance(info.value.body, str)
        else _json.dumps(info.value.body)
    )
    assert len(body_repr) <= MAX_ERROR_BODY_BYTES + 64
    assert "TRUNCATED" in body_repr


@respx.mock
async def test_non_json_2xx_raises_typed_error(client_with_mock, base_kwargs) -> None:
    respx.post(
        f"{DEFAULT_BASE_URL}/api/v1/programs/acme/reports"
    ).respond(201, content="<html>oops</html>", headers={"content-type": "text/html"})
    with pytest.raises(YesWeHackError, match="non-JSON 2xx body"):
        await client_with_mock.submit_report(**base_kwargs)
