"""Tests for bugcrowd-mcp — client + server."""

from __future__ import annotations

import json
from unittest.mock import patch

import httpx
import pytest
import respx

from bugcrowd_mcp.client import (
    DEFAULT_API_VERSION,
    DEFAULT_BASE_URL,
    SEVERITY_TO_INT,
    BugcrowdClient,
    BugcrowdError,
)
from bugcrowd_mcp.server import _submit_report_impl


@pytest.fixture
def base_kwargs() -> dict:
    return {
        "target": "https://acme.com/login",
        "title": "Reflected XSS",
        "description": "## Summary\n\nReflected XSS via q.",
        "severity": "medium",
    }


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> BugcrowdClient:
    monkeypatch.setenv("BUGCROWD_API_TOKEN", "tok-secret")
    return BugcrowdClient()


def _success_top_level() -> dict:
    return {
        "submission_id": "uuid-aaa",
        "status": "needs_review",
        "title": "Reflected XSS",
    }


def _success_nested() -> dict:
    return {
        "submission": {
            "id": "uuid-bbb",
            "status": "needs_review",
            "title": "Reflected XSS",
        }
    }


# -- construction --

def test_requires_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("BUGCROWD_API_TOKEN", raising=False)
    with pytest.raises(RuntimeError, match="BUGCROWD_API_TOKEN"):
        BugcrowdClient()


# -- severity map --

@pytest.mark.parametrize(
    "name,expected",
    [
        ("critical", 1),
        ("high", 2),
        ("medium", 3),
        ("low", 4),
        ("informational", 5),
    ],
)
def test_severity_mapping(name: str, expected: int) -> None:
    assert SEVERITY_TO_INT[name] == expected


# -- validation --

@respx.mock
async def test_rejects_missing_target(client, base_kwargs) -> None:
    base_kwargs["target"] = ""
    with pytest.raises(ValueError, match="target"):
        await client.submit_report(**base_kwargs)


@respx.mock
async def test_rejects_long_title(client, base_kwargs) -> None:
    base_kwargs["title"] = "x" * 201
    with pytest.raises(ValueError, match="title"):
        await client.submit_report(**base_kwargs)


@respx.mock
async def test_rejects_unknown_severity(client, base_kwargs) -> None:
    base_kwargs["severity"] = "spicy"
    with pytest.raises(ValueError, match="severity"):
        await client.submit_report(**base_kwargs)


# -- 201 happy paths --

@respx.mock
async def test_submit_201_top_level_response(client, base_kwargs) -> None:
    route = respx.post(f"{DEFAULT_BASE_URL}/submissions").respond(
        201, json=_success_top_level()
    )
    out = await client.submit_report(**base_kwargs)
    assert route.called
    assert out["submission_id"] == "uuid-aaa"
    assert out["status"] == "needs_review"


@respx.mock
async def test_submit_201_nested_response(client, base_kwargs) -> None:
    respx.post(f"{DEFAULT_BASE_URL}/submissions").respond(
        201, json=_success_nested()
    )
    out = await client.submit_report(**base_kwargs)
    assert out["submission_id"] == "uuid-bbb"


@respx.mock
async def test_submit_sends_token_auth_and_api_version(client, base_kwargs) -> None:
    route = respx.post(f"{DEFAULT_BASE_URL}/submissions").respond(
        201, json=_success_top_level()
    )
    await client.submit_report(**base_kwargs)
    sent = route.calls[0].request
    assert sent.headers["authorization"] == "Token tok-secret"
    assert sent.headers["x-bugcrowd-api-version"] == DEFAULT_API_VERSION
    assert sent.headers["content-type"] == "application/json"


@respx.mock
async def test_submit_body_shape_severity_int(client, base_kwargs) -> None:
    route = respx.post(f"{DEFAULT_BASE_URL}/submissions").respond(
        201, json=_success_top_level()
    )
    base_kwargs["severity"] = "high"
    await client.submit_report(**base_kwargs)
    body = json.loads(route.calls[0].request.content)
    assert body == {
        "submission": {
            "target": base_kwargs["target"],
            "title": base_kwargs["title"],
            "description": base_kwargs["description"],
            "severity": 2,  # high → P2 → 2
        }
    }


@respx.mock
async def test_submit_includes_vrt_id_when_set(client, base_kwargs) -> None:
    route = respx.post(f"{DEFAULT_BASE_URL}/submissions").respond(
        201, json=_success_top_level()
    )
    base_kwargs["vrt_id"] = "server_security_misconfiguration.web_socket_misconfiguration"
    await client.submit_report(**base_kwargs)
    body = json.loads(route.calls[0].request.content)
    assert body["submission"]["vrt_id"] == base_kwargs["vrt_id"]


# -- 4xx no retry --

@respx.mock
async def test_submit_400_no_retry(client, base_kwargs) -> None:
    route = respx.post(f"{DEFAULT_BASE_URL}/submissions").respond(
        400, json={"error": "missing target"}
    )
    with pytest.raises(BugcrowdError) as info:
        await client.submit_report(**base_kwargs)
    assert info.value.status_code == 400
    assert route.call_count == 1


# -- 5xx retry --

@respx.mock
async def test_submit_5xx_then_succeeds(client, base_kwargs) -> None:
    with patch("bugcrowd_mcp.client.RETRY_BACKOFF_S", (0.0, 0.0)):
        route = respx.post(f"{DEFAULT_BASE_URL}/submissions").mock(
            side_effect=[
                httpx.Response(503),
                httpx.Response(201, json=_success_top_level()),
            ]
        )
        out = await client.submit_report(**base_kwargs)
    assert out["submission_id"] == "uuid-aaa"
    assert route.call_count == 2


@respx.mock
async def test_submit_5xx_gives_up(client, base_kwargs) -> None:
    with patch("bugcrowd_mcp.client.RETRY_BACKOFF_S", (0.0, 0.0)):
        route = respx.post(f"{DEFAULT_BASE_URL}/submissions").respond(
            503, json={"error": "down"}
        )
        with pytest.raises(BugcrowdError):
            await client.submit_report(**base_kwargs)
    assert route.call_count == 3


@respx.mock
async def test_submit_network_error_retries(client, base_kwargs) -> None:
    with patch("bugcrowd_mcp.client.RETRY_BACKOFF_S", (0.0, 0.0)):
        respx.post(f"{DEFAULT_BASE_URL}/submissions").mock(
            side_effect=httpx.ConnectError("conn refused")
        )
        with pytest.raises(BugcrowdError) as info:
            await client.submit_report(**base_kwargs)
    assert info.value.status_code is None


# -- server impl --

@respx.mock
async def test_server_impl_ok_true(client, base_kwargs) -> None:
    respx.post(f"{DEFAULT_BASE_URL}/submissions").respond(
        201, json=_success_top_level()
    )
    out = await _submit_report_impl(client, **base_kwargs)
    assert out["ok"] is True
    assert out["submission_id"] == "uuid-aaa"


@respx.mock
async def test_server_impl_ok_false_on_4xx(client, base_kwargs) -> None:
    respx.post(f"{DEFAULT_BASE_URL}/submissions").respond(
        422, json={"error": "validation"}
    )
    out = await _submit_report_impl(client, **base_kwargs)
    assert out["ok"] is False
    assert out["status_code"] == 422
