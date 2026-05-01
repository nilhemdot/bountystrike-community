"""Tests for bugcrowd-mcp — JSON:API submission shape."""

from __future__ import annotations

import json
from unittest.mock import patch

import httpx
import pytest
import respx

from bugcrowd_mcp.client import (
    DEFAULT_BASE_URL,
    SEVERITY_TO_INT,
    BugcrowdClient,
    BugcrowdError,
)
from bugcrowd_mcp.server import _submit_report_impl


_PROGRAM_UUID = "11111111-2222-3333-4444-555555555555"
_TARGET_UUID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
_SUBMISSION_UUID = "99999999-9999-9999-9999-999999999999"


@pytest.fixture
def base_kwargs() -> dict:
    return {
        "program_id": _PROGRAM_UUID,
        "title": "Reflected XSS",
        "description": "## Summary\n\nReflected XSS via q.",
        "severity": "medium",
    }


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> BugcrowdClient:
    monkeypatch.setenv("BUGCROWD_API_TOKEN", "tok-secret")
    return BugcrowdClient()


def _success_jsonapi(severity_int: int = 3) -> dict:
    return {
        "data": {
            "type": "submission",
            "id": _SUBMISSION_UUID,
            "attributes": {
                "title": "Reflected XSS",
                "description": "...",
                "state": "new",
                "severity": severity_int,
                "created_at": "2026-05-01T00:00:00Z",
            },
            "relationships": {
                "program": {"data": {"type": "program", "id": _PROGRAM_UUID}}
            },
        },
        "included": [],
    }


# -- construction --


def test_requires_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("BUGCROWD_API_TOKEN", raising=False)
    with pytest.raises(RuntimeError, match="BUGCROWD_API_TOKEN"):
        BugcrowdClient()


def test_auth_scheme_default(client: BugcrowdClient) -> None:
    assert client._headers()["Authorization"] == "Token tok-secret"


def test_auth_scheme_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BUGCROWD_API_TOKEN", "tok-secret")
    c = BugcrowdClient(auth_scheme="Bearer")
    assert c._headers()["Authorization"] == "Bearer tok-secret"


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
async def test_rejects_missing_program_id(client, base_kwargs) -> None:
    base_kwargs["program_id"] = ""
    with pytest.raises(ValueError, match="program_id"):
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


# -- 201 happy path --


@respx.mock
async def test_submit_201_returns_jsonapi_id(client, base_kwargs) -> None:
    route = respx.post(f"{DEFAULT_BASE_URL}/submissions").respond(
        201, json=_success_jsonapi(severity_int=3)
    )
    out = await client.submit_report(**base_kwargs)
    assert route.called
    assert out["submission_id"] == _SUBMISSION_UUID
    assert out["status"] == "new"
    assert out["severity"] == 3


@respx.mock
async def test_submit_sends_token_auth(client, base_kwargs) -> None:
    route = respx.post(f"{DEFAULT_BASE_URL}/submissions").respond(
        201, json=_success_jsonapi()
    )
    await client.submit_report(**base_kwargs)
    sent = route.calls[0].request
    assert sent.headers["authorization"] == "Token tok-secret"
    assert sent.headers["content-type"] == "application/json"


@respx.mock
async def test_submit_body_is_jsonapi_with_severity_int(client, base_kwargs) -> None:
    route = respx.post(f"{DEFAULT_BASE_URL}/submissions").respond(
        201, json=_success_jsonapi(severity_int=2)
    )
    base_kwargs["severity"] = "high"
    await client.submit_report(**base_kwargs)
    body = json.loads(route.calls[0].request.content)
    assert body == {
        "data": {
            "type": "submission",
            "attributes": {
                "title": base_kwargs["title"],
                "description": base_kwargs["description"],
                "severity": 2,
            },
            "relationships": {
                "program": {
                    "data": {"type": "program", "id": _PROGRAM_UUID}
                }
            },
        }
    }


@respx.mock
async def test_submit_includes_vrt_id(client, base_kwargs) -> None:
    route = respx.post(f"{DEFAULT_BASE_URL}/submissions").respond(
        201, json=_success_jsonapi()
    )
    base_kwargs["vrt_id"] = "cross_site_scripting_xss.reflected"
    await client.submit_report(**base_kwargs)
    body = json.loads(route.calls[0].request.content)
    assert (
        body["data"]["attributes"]["vrt_id"]
        == "cross_site_scripting_xss.reflected"
    )


@respx.mock
async def test_submit_includes_target_relationship(client, base_kwargs) -> None:
    route = respx.post(f"{DEFAULT_BASE_URL}/submissions").respond(
        201, json=_success_jsonapi()
    )
    base_kwargs["target_id"] = _TARGET_UUID
    await client.submit_report(**base_kwargs)
    body = json.loads(route.calls[0].request.content)
    assert body["data"]["relationships"]["target"] == {
        "data": {"type": "target", "id": _TARGET_UUID}
    }


@respx.mock
async def test_submit_omits_target_when_unset(client, base_kwargs) -> None:
    route = respx.post(f"{DEFAULT_BASE_URL}/submissions").respond(
        201, json=_success_jsonapi()
    )
    await client.submit_report(**base_kwargs)
    body = json.loads(route.calls[0].request.content)
    assert "target" not in body["data"]["relationships"]


# -- 4xx no retry --


@respx.mock
async def test_submit_400_no_retry(client, base_kwargs) -> None:
    route = respx.post(f"{DEFAULT_BASE_URL}/submissions").respond(
        400, json={"errors": [{"status": "400", "title": "bad request"}]}
    )
    with pytest.raises(BugcrowdError) as info:
        await client.submit_report(**base_kwargs)
    assert info.value.status_code == 400
    assert route.call_count == 1


@respx.mock
async def test_submit_422_validation_no_retry(client, base_kwargs) -> None:
    route = respx.post(f"{DEFAULT_BASE_URL}/submissions").respond(
        422, json={"errors": [{"status": "422", "title": "validation"}]}
    )
    with pytest.raises(BugcrowdError) as info:
        await client.submit_report(**base_kwargs)
    assert info.value.status_code == 422
    assert route.call_count == 1


# -- 5xx retry --


@respx.mock
async def test_submit_5xx_then_succeeds(client, base_kwargs) -> None:
    with patch("bugcrowd_mcp.client.RETRY_BACKOFF_S", (0.0, 0.0)):
        route = respx.post(f"{DEFAULT_BASE_URL}/submissions").mock(
            side_effect=[
                httpx.Response(503),
                httpx.Response(201, json=_success_jsonapi()),
            ]
        )
        out = await client.submit_report(**base_kwargs)
    assert out["submission_id"] == _SUBMISSION_UUID
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


# -- malformed success payload --


@respx.mock
async def test_submit_rejects_payload_missing_data(client, base_kwargs) -> None:
    respx.post(f"{DEFAULT_BASE_URL}/submissions").respond(
        201, json={"unexpected": "shape"}
    )
    with pytest.raises(BugcrowdError, match="missing 'data'"):
        await client.submit_report(**base_kwargs)


# -- server impl --


@respx.mock
async def test_server_impl_ok_true(client, base_kwargs) -> None:
    respx.post(f"{DEFAULT_BASE_URL}/submissions").respond(
        201, json=_success_jsonapi()
    )
    out = await _submit_report_impl(client, **base_kwargs)
    assert out["ok"] is True
    assert out["submission_id"] == _SUBMISSION_UUID


@respx.mock
async def test_server_impl_ok_false_on_4xx(client, base_kwargs) -> None:
    respx.post(f"{DEFAULT_BASE_URL}/submissions").respond(
        422, json={"errors": [{"status": "422"}]}
    )
    out = await _submit_report_impl(client, **base_kwargs)
    assert out["ok"] is False
    assert out["status_code"] == 422


# ---------------------------------------------------------------------------
# Audit-fix coverage — base_url URL guard, body truncation, non-JSON 2xx.
# ---------------------------------------------------------------------------


def test_construction_rejects_metadata_ip_base_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BUGCROWD_API_TOKEN", "tok")
    from bugcrowd_mcp._url_guard import UrlGuardError

    with pytest.raises(UrlGuardError):
        BugcrowdClient(base_url="https://169.254.169.254/")


def test_construction_rejects_http_base_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BUGCROWD_API_TOKEN", "tok")
    monkeypatch.delenv("BS_PLATFORM_ALLOW_HTTP", raising=False)
    from bugcrowd_mcp._url_guard import UrlGuardError

    with pytest.raises(UrlGuardError):
        BugcrowdClient(base_url="http://api.bugcrowd.com/")


@respx.mock
async def test_error_body_truncated(client, base_kwargs) -> None:
    from bugcrowd_mcp.client import MAX_ERROR_BODY_BYTES

    huge = {"errors": [{"detail": "x" * 100_000}]}
    respx.post(f"{DEFAULT_BASE_URL}/submissions").respond(400, json=huge)
    with pytest.raises(BugcrowdError) as info:
        await client.submit_report(**base_kwargs)
    body_repr = (
        info.value.body
        if isinstance(info.value.body, str)
        else json.dumps(info.value.body)
    )
    assert len(body_repr) <= MAX_ERROR_BODY_BYTES + 64
    assert "TRUNCATED" in body_repr


@respx.mock
async def test_non_json_2xx_raises_typed_error(client, base_kwargs) -> None:
    respx.post(f"{DEFAULT_BASE_URL}/submissions").respond(
        201, content="<html>oops</html>", headers={"content-type": "text/html"}
    )
    with pytest.raises(BugcrowdError, match="non-JSON 2xx body"):
        await client.submit_report(**base_kwargs)
