"""Tests for intigriti-mcp — client + server."""

from __future__ import annotations

import json
from unittest.mock import patch

import httpx
import pytest
import respx

from intigriti_mcp.client import (
    DEFAULT_BASE_URL,
    VALID_SEVERITIES,
    IntigritiClient,
    IntigritiError,
)
from intigriti_mcp.server import _submit_report_impl


@pytest.fixture
def base_kwargs() -> dict:
    return {
        "program_id": "11111111-2222-3333-4444-555555555555",
        "title": "Reflected XSS",
        "endpoint_url": "https://acme.com/search",
        "severity": "medium",
        "vuln_type": "CWE-79",
        "description": "## Summary",
        "proof_of_concept": "1. Visit /search?q=<payload>",
        "impact": "Session theft on click.",
    }


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> IntigritiClient:
    monkeypatch.setenv("INTIGRITI_API_TOKEN", "tok-secret")
    return IntigritiClient()


def _success() -> dict:
    return {"id": "sub-uuid", "state": "Open", "title": "Reflected XSS"}


# -- construction --

def test_requires_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("INTIGRITI_API_TOKEN", raising=False)
    with pytest.raises(RuntimeError, match="INTIGRITI_API_TOKEN"):
        IntigritiClient()


def test_severity_set_includes_exceptional() -> None:
    assert "exceptional" in VALID_SEVERITIES
    assert "informational" in VALID_SEVERITIES


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
async def test_submit_201(client, base_kwargs) -> None:
    route = respx.post(
        f"{DEFAULT_BASE_URL}/v1/submissions"
    ).respond(201, json=_success())
    out = await client.submit_report(**base_kwargs)
    assert route.called
    assert out["submission_id"] == "sub-uuid"
    assert out["status"] == "Open"


@respx.mock
async def test_submit_sends_bearer(client, base_kwargs) -> None:
    route = respx.post(
        f"{DEFAULT_BASE_URL}/v1/submissions"
    ).respond(201, json=_success())
    await client.submit_report(**base_kwargs)
    sent = route.calls[0].request
    assert sent.headers["authorization"] == "Bearer tok-secret"


@respx.mock
async def test_submit_body_shape_includes_required_fields(client, base_kwargs) -> None:
    route = respx.post(
        f"{DEFAULT_BASE_URL}/v1/submissions"
    ).respond(201, json=_success())
    await client.submit_report(**base_kwargs)
    body = json.loads(route.calls[0].request.content)
    for k in (
        "programId",
        "title",
        "endpointUrl",
        "severity",
        "type",
        "description",
        "proofOfConcept",
        "impact",
    ):
        assert k in body


@respx.mock
async def test_extra_appended_no_contract_overwrite(client, base_kwargs) -> None:
    route = respx.post(
        f"{DEFAULT_BASE_URL}/v1/submissions"
    ).respond(201, json=_success())
    base_kwargs["extra"] = {
        "title": "OVERWRITE-ATTEMPT",  # should be ignored
        "customField": "custom-value",
    }
    await client.submit_report(**base_kwargs)
    body = json.loads(route.calls[0].request.content)
    assert body["title"] == "Reflected XSS"  # contract field preserved
    assert body["customField"] == "custom-value"  # extra appended


# -- 4xx no retry --

@respx.mock
async def test_submit_400_no_retry(client, base_kwargs) -> None:
    route = respx.post(
        f"{DEFAULT_BASE_URL}/v1/submissions"
    ).respond(400, json={"error": "invalid"})
    with pytest.raises(IntigritiError) as info:
        await client.submit_report(**base_kwargs)
    assert info.value.status_code == 400
    assert route.call_count == 1


# -- 5xx retry --

@respx.mock
async def test_submit_5xx_then_succeeds(client, base_kwargs) -> None:
    with patch("intigriti_mcp.client.RETRY_BACKOFF_S", (0.0, 0.0)):
        route = respx.post(
            f"{DEFAULT_BASE_URL}/v1/submissions"
        ).mock(
            side_effect=[
                httpx.Response(503),
                httpx.Response(201, json=_success()),
            ]
        )
        out = await client.submit_report(**base_kwargs)
    assert out["submission_id"] == "sub-uuid"
    assert route.call_count == 2


@respx.mock
async def test_submit_5xx_gives_up(client, base_kwargs) -> None:
    with patch("intigriti_mcp.client.RETRY_BACKOFF_S", (0.0, 0.0)):
        route = respx.post(
            f"{DEFAULT_BASE_URL}/v1/submissions"
        ).respond(503, json={"error": "down"})
        with pytest.raises(IntigritiError):
            await client.submit_report(**base_kwargs)
    assert route.call_count == 3


# -- server impl --

@respx.mock
async def test_server_impl_ok_true(client, base_kwargs) -> None:
    respx.post(
        f"{DEFAULT_BASE_URL}/v1/submissions"
    ).respond(201, json=_success())
    out = await _submit_report_impl(client, **base_kwargs)
    assert out["ok"] is True


@respx.mock
async def test_server_impl_ok_false_on_4xx(client, base_kwargs) -> None:
    respx.post(
        f"{DEFAULT_BASE_URL}/v1/submissions"
    ).respond(403, json={"error": "forbidden"})
    out = await _submit_report_impl(client, **base_kwargs)
    assert out["ok"] is False
    assert out["status_code"] == 403


# ---------------------------------------------------------------------------
# Submit-URL override — Intigriti has no public researcher submission API,
# so callers must point INTIGRITI_SUBMIT_URL at a relay they operate.
# ---------------------------------------------------------------------------


@respx.mock
async def test_default_url_is_documented_dead_endpoint(client, base_kwargs) -> None:
    """Default ``submit_report`` POSTs to a path that Intigriti will 404.

    The module docstring explains why: Intigriti has no documented
    POST /submissions endpoint for researchers; submissions go through
    the web UI. The test pins this contract so a future maintainer who
    "fixes" the URL surfaces the platform-level limitation in CI.
    """
    route = respx.post(f"{DEFAULT_BASE_URL}/v1/submissions").respond(
        404, json={"error": "Not Found"}
    )
    with pytest.raises(IntigritiError) as info:
        await client.submit_report(**base_kwargs)
    assert info.value.status_code == 404
    assert route.call_count == 1


@respx.mock
async def test_submit_url_override_routes_to_relay(
    client, base_kwargs, monkeypatch: pytest.MonkeyPatch
) -> None:
    relay = "https://relay.example.com/intigriti-submit"
    monkeypatch.setattr("intigriti_mcp.client.SUBMIT_URL_OVERRIDE", relay)
    route = respx.post(relay).respond(
        201, json={"id": "relay-uuid", "state": "received"}
    )
    out = await client.submit_report(**base_kwargs)
    assert route.called
    assert out["submission_id"] == "relay-uuid"


# ---------------------------------------------------------------------------
# Audit-fix coverage — env-var path, URL guard, host-mismatch auth strip,
# body truncation. CRITICAL findings from the post-ship audit.
# ---------------------------------------------------------------------------


@respx.mock
async def test_env_var_override_takes_effect_at_call_time(
    client, base_kwargs, monkeypatch: pytest.MonkeyPatch
) -> None:
    """INTIGRITI_SUBMIT_URL set AFTER module import must take effect.

    Pre-fix: SUBMIT_URL_OVERRIDE was captured at import time, so any
    deploy that exported the env var post-import got the inert default.
    The fix re-reads the env on every submit_report call.
    """
    relay = "https://env-relay.example.com/intake"
    monkeypatch.setattr("intigriti_mcp.client.SUBMIT_URL_OVERRIDE", "")
    monkeypatch.setenv("INTIGRITI_SUBMIT_URL", relay)
    route = respx.post(relay).respond(
        201, json={"id": "env-uuid", "state": "received"}
    )
    out = await client.submit_report(**base_kwargs)
    assert route.called
    assert out["submission_id"] == "env-uuid"


def test_construction_rejects_metadata_ip_base_url() -> None:
    from intigriti_mcp._url_guard import UrlGuardError

    with pytest.raises(UrlGuardError):
        IntigritiClient(api_token="t", base_url="https://169.254.169.254/")


def test_construction_rejects_http_base_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from intigriti_mcp._url_guard import UrlGuardError

    monkeypatch.delenv("BS_PLATFORM_ALLOW_HTTP", raising=False)
    with pytest.raises(UrlGuardError):
        IntigritiClient(api_token="t", base_url="http://api.intigriti.com/")


@respx.mock
async def test_override_url_with_metadata_ip_rejected(
    client, base_kwargs, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A poisoned INTIGRITI_SUBMIT_URL pointing at AWS IMDS must be
    rejected at submit time, not exfil the Bearer."""
    monkeypatch.setattr(
        "intigriti_mcp.client.SUBMIT_URL_OVERRIDE", "https://169.254.169.254/exfil"
    )
    with pytest.raises(ValueError, match="URL guard"):
        await client.submit_report(**base_kwargs)


@respx.mock
async def test_override_url_strips_auth_when_host_differs(
    client, base_kwargs, monkeypatch: pytest.MonkeyPatch
) -> None:
    relay = "https://relay.example.com/intake"
    monkeypatch.setattr("intigriti_mcp.client.SUBMIT_URL_OVERRIDE", relay)
    route = respx.post(relay).respond(
        201, json={"id": "relay-uuid", "state": "received"}
    )
    await client.submit_report(**base_kwargs)
    sent = route.calls[0].request
    assert "authorization" not in {k.lower() for k in sent.headers.keys()}


@respx.mock
async def test_override_url_keeps_auth_on_same_host(
    client, base_kwargs, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Override URL on the configured base host keeps the Bearer."""
    same_host = (
        "https://api.intigriti.com/external/researcher/v2/submissions"
    )
    monkeypatch.setattr("intigriti_mcp.client.SUBMIT_URL_OVERRIDE", same_host)
    route = respx.post(same_host).respond(
        201, json={"id": "same-uuid", "state": "received"}
    )
    await client.submit_report(**base_kwargs)
    sent = route.calls[0].request
    assert sent.headers["authorization"] == "Bearer tok-secret"


@respx.mock
async def test_error_body_truncated(client, base_kwargs) -> None:
    from intigriti_mcp.client import MAX_ERROR_BODY_BYTES

    huge = {"err": "x" * 100_000}
    respx.post(f"{DEFAULT_BASE_URL}/v1/submissions").respond(400, json=huge)
    with pytest.raises(IntigritiError) as info:
        await client.submit_report(**base_kwargs)
    body_repr = (
        info.value.body
        if isinstance(info.value.body, str)
        else json.dumps(info.value.body)
    )
    assert len(body_repr) <= MAX_ERROR_BODY_BYTES + 64
    assert "TRUNCATED" in body_repr


# ---------------------------------------------------------------------------
# 429 retry coverage.
# ---------------------------------------------------------------------------


@respx.mock
async def test_429_retried_then_succeeds(client, base_kwargs) -> None:
    with patch("intigriti_mcp.client.RETRY_BACKOFF_S", (0.0, 0.0)):
        route = respx.post(f"{DEFAULT_BASE_URL}/v1/submissions").mock(
            side_effect=[
                httpx.Response(429, headers={"Retry-After": "0"}),
                httpx.Response(201, json={"id": "rl-1", "state": "Open"}),
            ]
        )
        out = await client.submit_report(**base_kwargs)
    assert out["submission_id"] == "rl-1"
    assert route.call_count == 2


@respx.mock
async def test_429_gives_up_after_max_retries(client, base_kwargs) -> None:
    with patch("intigriti_mcp.client.RETRY_BACKOFF_S", (0.0, 0.0)):
        route = respx.post(f"{DEFAULT_BASE_URL}/v1/submissions").respond(
            429, headers={"Retry-After": "0"}, json={"error": "rate limit"}
        )
        with pytest.raises(IntigritiError) as info:
            await client.submit_report(**base_kwargs)
    assert info.value.status_code == 429
    assert "rate-limited" in str(info.value)
    assert route.call_count == 3
