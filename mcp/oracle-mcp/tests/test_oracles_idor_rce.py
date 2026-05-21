"""Tests for Phase 1.1c oracles: IDOR and RCE.

All httpx calls are fully mocked — no real network activity occurs.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from oracle_mcp.result import OracleResult
from oracle_mcp.security import DestructivePayloadError

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_http_response(status_code: int, text: str) -> MagicMock:
    """Return a MagicMock mimicking an httpx.Response."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.text = text
    return resp


def _make_async_client_mock(*responses) -> MagicMock:
    """Return a mock httpx.AsyncClient whose get() returns *responses* in order.

    Each element of *responses* is returned as-is from successive ``get()``
    calls.  After the list is exhausted the last value is repeated.
    """
    client = AsyncMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)

    if len(responses) == 1:
        client.get = AsyncMock(return_value=responses[0])
    else:
        client.get = AsyncMock(side_effect=list(responses))

    return client


# ---------------------------------------------------------------------------
# IDOR tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_idor_validated():
    """Accessor gets 200 with overlapping body → verdict 'validated'."""
    from oracle_mcp.oracles.idor import SessionCredentials, oracle_idor

    owner_resp = _make_http_response(200, "user_name acme_account profile_data")
    accessor_resp = _make_http_response(
        200, "user_name acme_account different_token extra_field"
    )
    mock_client = _make_async_client_mock(owner_resp, accessor_resp)

    with patch("oracle_mcp.oracles.idor.httpx.AsyncClient", return_value=mock_client):
        result = await oracle_idor(
            resource_url="http://example.com/api/users/42/profile",
            owner_session=SessionCredentials(
                headers={"Authorization": "Bearer token_a"}, cookies={}
            ),
            accessor_session=SessionCredentials(
                headers={"Authorization": "Bearer token_b"}, cookies={}
            ),
        )

    assert isinstance(result, OracleResult)
    assert result.verdict == "validated"
    assert result.oracle_method == "idor_cross_account"
    assert result.evidence["accessor_status"] == 200
    assert result.evidence["jaccard_similarity"] >= 0.3


@pytest.mark.asyncio
async def test_idor_accessor_denied():
    """Accessor gets 403 → verdict 'unreproducible'."""
    from oracle_mcp.oracles.idor import SessionCredentials, oracle_idor

    owner_resp = _make_http_response(200, "user_name acme_account")
    accessor_resp = _make_http_response(403, "Forbidden")
    mock_client = _make_async_client_mock(owner_resp, accessor_resp)

    with patch("oracle_mcp.oracles.idor.httpx.AsyncClient", return_value=mock_client):
        result = await oracle_idor(
            resource_url="http://example.com/api/users/42/profile",
            owner_session=SessionCredentials(headers={}, cookies={}),
            accessor_session=SessionCredentials(headers={}, cookies={}),
        )

    assert result.verdict == "unreproducible"
    assert result.reason == "accessor correctly denied"


@pytest.mark.asyncio
async def test_idor_owner_wrong_status():
    """Owner returns 404 when 200 is expected → verdict 'inconclusive'."""
    from oracle_mcp.oracles.idor import SessionCredentials, oracle_idor

    owner_resp = _make_http_response(404, "Not Found")
    mock_client = _make_async_client_mock(owner_resp)

    with patch("oracle_mcp.oracles.idor.httpx.AsyncClient", return_value=mock_client):
        result = await oracle_idor(
            resource_url="http://example.com/api/users/42/profile",
            owner_session=SessionCredentials(headers={}, cookies={}),
            accessor_session=SessionCredentials(headers={}, cookies={}),
            expected_owner_status=200,
        )

    assert result.verdict == "inconclusive"
    assert "404" in (result.reason or "")
    assert "200" in (result.reason or "")


@pytest.mark.asyncio
async def test_idor_low_similarity():
    """Accessor gets 200 but completely different body → verdict 'inconclusive'."""
    from oracle_mcp.oracles.idor import SessionCredentials, oracle_idor

    owner_resp = _make_http_response(200, "alpha beta gamma delta")
    accessor_resp = _make_http_response(
        200, "completely different response without any shared words whatsoever xyz"
    )
    mock_client = _make_async_client_mock(owner_resp, accessor_resp)

    with patch("oracle_mcp.oracles.idor.httpx.AsyncClient", return_value=mock_client):
        result = await oracle_idor(
            resource_url="http://example.com/api/users/42/profile",
            owner_session=SessionCredentials(headers={}, cookies={}),
            accessor_session=SessionCredentials(headers={}, cookies={}),
        )

    assert result.verdict == "inconclusive"
    assert result.evidence["jaccard_similarity"] < 0.3


# ---------------------------------------------------------------------------
# RCE tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rce_unix_validated():
    """First injection style (unix_semicolon_echo) causes marker reflection → 'validated'."""
    from oracle_mcp.oracles.rce import oracle_rce

    fixed_nonce = "deadbeef12345678"
    marker = f"{fixed_nonce}_rce_marker"
    marker_resp = _make_http_response(200, f"output: {marker}\n")
    mock_client = _make_async_client_mock(marker_resp)

    with (
        patch(
            "oracle_mcp.oracles.rce.secrets.token_hex", return_value=fixed_nonce
        ),
        patch("oracle_mcp.oracles.rce.httpx.AsyncClient", return_value=mock_client),
    ):
        result = await oracle_rce(
            url="http://example.com/cmd?input=hello",
            param="input",
        )

    assert isinstance(result, OracleResult)
    assert result.verdict == "validated"
    assert result.oracle_method == "rce_echo_marker"
    assert result.evidence["injection_style"] == "unix_semicolon_echo"
    assert result.evidence["nonce"] == fixed_nonce


@pytest.mark.asyncio
async def test_rce_unreproducible():
    """All 4 injection styles return body without the marker → 'unreproducible'."""
    from oracle_mcp.oracles.rce import oracle_rce

    fixed_nonce = "aabbccdd11223344"
    no_marker_resp = _make_http_response(200, "some normal response without marker")
    mock_client = _make_async_client_mock(
        no_marker_resp, no_marker_resp, no_marker_resp, no_marker_resp
    )

    with (
        patch(
            "oracle_mcp.oracles.rce.secrets.token_hex", return_value=fixed_nonce
        ),
        patch("oracle_mcp.oracles.rce.httpx.AsyncClient", return_value=mock_client),
    ):
        result = await oracle_rce(
            url="http://example.com/cmd?input=hello",
            param="input",
        )

    assert result.verdict == "unreproducible"
    assert result.oracle_method == "rce_echo_marker"


@pytest.mark.asyncio
async def test_rce_destructive_rejected():
    """oracle_rce with a destructive URL must raise DestructivePayloadError."""
    from oracle_mcp.oracles.rce import oracle_rce

    with pytest.raises(DestructivePayloadError):
        await oracle_rce(url="DROP TABLE findings", param="q")


@pytest.mark.asyncio
async def test_idor_destructive_rejected():
    """oracle_idor with a destructive resource_url must raise DestructivePayloadError."""
    from oracle_mcp.oracles.idor import SessionCredentials, oracle_idor

    with pytest.raises(DestructivePayloadError):
        await oracle_idor(
            resource_url="DROP TABLE users",
            owner_session=SessionCredentials(headers={}, cookies={}),
            accessor_session=SessionCredentials(headers={}, cookies={}),
        )
