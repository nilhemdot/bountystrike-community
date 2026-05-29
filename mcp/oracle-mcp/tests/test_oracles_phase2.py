# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for the three Phase 1.1b oracles: SSTI, Open Redirect, SSRF→IMDS.

All httpx calls are fully mocked — no real network activity happens.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from oracle_mcp.result import OracleResult
from oracle_mcp.security import DestructivePayloadError

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_http_response(text: str = "", status_code: int = 200) -> MagicMock:
    """Return a MagicMock that looks like an httpx.Response with a .text body."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.text = text
    return resp


def _make_async_client_mock(response: MagicMock) -> AsyncMock:
    """Return an AsyncMock httpx.AsyncClient that always returns *response* for GET."""
    inner = AsyncMock()
    inner.get = AsyncMock(return_value=response)

    ctx = AsyncMock()
    ctx.__aenter__ = AsyncMock(return_value=inner)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return ctx


# ---------------------------------------------------------------------------
# SSTI tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ssti_jinja2_validated():
    """Jinja2 payload returns expected product in body → validated."""
    from oracle_mcp.oracles.ssti import oracle_ssti

    # Patch randint so a=7, b=6 → expected=42
    with patch("oracle_mcp.oracles.ssti.random.randint", side_effect=[7, 6]):
        response = _make_http_response(text="Result: 42")
        client_mock = _make_async_client_mock(response)

        with patch("oracle_mcp.oracles.ssti.httpx.AsyncClient", return_value=client_mock):
            result = await oracle_ssti(
                url="http://example.com/render?tpl=hello",
                param="tpl",
                timeout_seconds=5.0,
            )

    assert isinstance(result, OracleResult)
    assert result.verdict == "validated"
    assert result.oracle_method == "ssti_math_eval"
    assert result.evidence["dialect"] == "jinja2"
    assert result.evidence["expected"] == "42"


@pytest.mark.asyncio
async def test_ssti_unreproducible():
    """All 7 dialects return body without expected value → unreproducible."""
    from oracle_mcp.oracles.ssti import oracle_ssti

    # Patch randint so a=11, b=12 → expected=132; body never contains it
    with patch("oracle_mcp.oracles.ssti.random.randint", side_effect=[11, 12]):
        response = _make_http_response(text="no match here")
        client_mock = _make_async_client_mock(response)

        with patch("oracle_mcp.oracles.ssti.httpx.AsyncClient", return_value=client_mock):
            result = await oracle_ssti(
                url="http://example.com/render?tpl=hello",
                param="tpl",
                timeout_seconds=5.0,
            )

    assert result.verdict == "unreproducible"
    assert result.oracle_method == "ssti_math_eval"


@pytest.mark.asyncio
async def test_ssti_destructive_rejected():
    """oracle_ssti with a destructive URL must raise DestructivePayloadError."""
    from oracle_mcp.oracles.ssti import oracle_ssti

    with pytest.raises(DestructivePayloadError):
        await oracle_ssti(url="DROP TABLE users", param="tpl")


# ---------------------------------------------------------------------------
# Open Redirect tests
# ---------------------------------------------------------------------------


def _make_redirect_response(
    history_urls: list[str],
    final_url: str,
    status_code: int = 200,
) -> MagicMock:
    """Return a mock httpx.Response with redirect history and final URL."""
    # Build history: list of responses, each with .url
    history = []
    for h_url in history_urls:
        h_resp = MagicMock()
        h_resp.url = h_url
        history.append(h_resp)

    resp = MagicMock()
    resp.status_code = status_code
    resp.history = history
    resp.url = final_url
    resp.text = ""
    return resp


@pytest.mark.asyncio
async def test_open_redirect_validated():
    """Redirect chain ends at target host → validated."""
    from oracle_mcp.oracles.open_redirect import oracle_open_redirect

    # history: one redirect from injected URL; final: target
    redirect_resp = _make_redirect_response(
        history_urls=["http://example.com/redirect?next=https%3A%2F%2Fexample.com"],
        final_url="https://example.com",
    )
    client_mock = _make_async_client_mock(redirect_resp)

    with patch("oracle_mcp.oracles.open_redirect.httpx.AsyncClient", return_value=client_mock):
        result = await oracle_open_redirect(
            url="http://example.com/redirect?next=safe",
            param="next",
            target="https://example.com",
            timeout_seconds=5.0,
        )

    assert isinstance(result, OracleResult)
    assert result.verdict == "validated"
    assert result.oracle_method == "open_redirect_follow"
    assert result.evidence["final_url"] == "https://example.com"


@pytest.mark.asyncio
async def test_open_redirect_stays_on_origin():
    """Redirect goes back to same origin as original URL (not the target) → unreproducible."""
    from oracle_mcp.oracles.open_redirect import oracle_open_redirect

    # Original URL is on vulnerable.example.com; target is attacker.example.com.
    # After injection the server redirects back to vulnerable.example.com (on-origin),
    # rather than following the open redirect to attacker.example.com.
    redirect_resp = _make_redirect_response(
        history_urls=["http://vulnerable.example.com/redirect?next=http%3A%2F%2Fattacker.example.com"],
        final_url="http://vulnerable.example.com/home",
    )
    client_mock = _make_async_client_mock(redirect_resp)

    with patch("oracle_mcp.oracles.open_redirect.httpx.AsyncClient", return_value=client_mock):
        result = await oracle_open_redirect(
            url="http://vulnerable.example.com/redirect?next=safe",
            param="next",
            target="http://attacker.example.com",
            timeout_seconds=5.0,
        )

    assert result.verdict == "unreproducible"
    assert "origin" in (result.reason or "")


@pytest.mark.asyncio
async def test_open_redirect_no_redirect():
    """No redirects (2xx direct) → unreproducible with reason 'no redirect'."""
    from oracle_mcp.oracles.open_redirect import oracle_open_redirect

    # history is empty → direct response
    direct_resp = _make_redirect_response(
        history_urls=[],
        final_url="http://example.com/redirect",
    )
    client_mock = _make_async_client_mock(direct_resp)

    with patch("oracle_mcp.oracles.open_redirect.httpx.AsyncClient", return_value=client_mock):
        result = await oracle_open_redirect(
            url="http://example.com/redirect?next=safe",
            param="next",
            target="https://example.com",
            timeout_seconds=5.0,
        )

    assert result.verdict == "unreproducible"
    assert result.reason == "no redirect"


@pytest.mark.asyncio
async def test_open_redirect_destructive_rejected():
    """oracle_open_redirect with a destructive URL must raise DestructivePayloadError."""
    from oracle_mcp.oracles.open_redirect import oracle_open_redirect

    with pytest.raises(DestructivePayloadError):
        await oracle_open_redirect(url="DROP TABLE users", param="next")


# ---------------------------------------------------------------------------
# SSRF→IMDS tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ssrf_imds_aws_validated():
    """Response body contains 'ami-id' when AWS IMDS URL injected → validated."""
    from oracle_mcp.oracles.ssrf_imds import oracle_ssrf_imds

    response = _make_http_response(text="ami-id: ami-0abcdef1234567890\ninstance-id: i-1234")
    client_mock = _make_async_client_mock(response)

    with patch("oracle_mcp.oracles.ssrf_imds.httpx.AsyncClient", return_value=client_mock):
        result = await oracle_ssrf_imds(
            url="http://example.com/fetch?target=http://safe.example",
            param="target",
            timeout_seconds=5.0,
        )

    assert isinstance(result, OracleResult)
    assert result.verdict == "validated"
    assert result.oracle_method == "ssrf_imds_cloud_marker"
    assert result.evidence["provider"] == "aws"
    assert result.evidence["marker"] == "ami-id"


@pytest.mark.asyncio
async def test_ssrf_imds_unreproducible():
    """All 3 providers return body without markers → unreproducible."""
    from oracle_mcp.oracles.ssrf_imds import oracle_ssrf_imds

    response = _make_http_response(text="<html>403 Forbidden</html>")
    client_mock = _make_async_client_mock(response)

    with patch("oracle_mcp.oracles.ssrf_imds.httpx.AsyncClient", return_value=client_mock):
        result = await oracle_ssrf_imds(
            url="http://example.com/fetch?target=http://safe.example",
            param="target",
            timeout_seconds=5.0,
        )

    assert result.verdict == "unreproducible"
    assert result.oracle_method == "ssrf_imds_cloud_marker"


@pytest.mark.asyncio
async def test_ssrf_imds_destructive_rejected():
    """oracle_ssrf_imds with a destructive URL must raise DestructivePayloadError."""
    from oracle_mcp.oracles.ssrf_imds import oracle_ssrf_imds

    with pytest.raises(DestructivePayloadError):
        await oracle_ssrf_imds(url="DROP TABLE users", param="target")
