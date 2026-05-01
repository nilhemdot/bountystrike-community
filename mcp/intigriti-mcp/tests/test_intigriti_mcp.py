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
        f"{DEFAULT_BASE_URL}/core/researcher/v1/submissions"
    ).respond(201, json=_success())
    out = await client.submit_report(**base_kwargs)
    assert route.called
    assert out["submission_id"] == "sub-uuid"
    assert out["status"] == "Open"


@respx.mock
async def test_submit_sends_bearer(client, base_kwargs) -> None:
    route = respx.post(
        f"{DEFAULT_BASE_URL}/core/researcher/v1/submissions"
    ).respond(201, json=_success())
    await client.submit_report(**base_kwargs)
    sent = route.calls[0].request
    assert sent.headers["authorization"] == "Bearer tok-secret"


@respx.mock
async def test_submit_body_shape_includes_required_fields(client, base_kwargs) -> None:
    route = respx.post(
        f"{DEFAULT_BASE_URL}/core/researcher/v1/submissions"
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
        f"{DEFAULT_BASE_URL}/core/researcher/v1/submissions"
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
        f"{DEFAULT_BASE_URL}/core/researcher/v1/submissions"
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
            f"{DEFAULT_BASE_URL}/core/researcher/v1/submissions"
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
            f"{DEFAULT_BASE_URL}/core/researcher/v1/submissions"
        ).respond(503, json={"error": "down"})
        with pytest.raises(IntigritiError):
            await client.submit_report(**base_kwargs)
    assert route.call_count == 3


# -- server impl --

@respx.mock
async def test_server_impl_ok_true(client, base_kwargs) -> None:
    respx.post(
        f"{DEFAULT_BASE_URL}/core/researcher/v1/submissions"
    ).respond(201, json=_success())
    out = await _submit_report_impl(client, **base_kwargs)
    assert out["ok"] is True


@respx.mock
async def test_server_impl_ok_false_on_4xx(client, base_kwargs) -> None:
    respx.post(
        f"{DEFAULT_BASE_URL}/core/researcher/v1/submissions"
    ).respond(403, json={"error": "forbidden"})
    out = await _submit_report_impl(client, **base_kwargs)
    assert out["ok"] is False
    assert out["status_code"] == 403
