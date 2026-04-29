"""Tests for the three Phase 1.1a oracles: XSS, SSRF, SQLi.

Playwright and httpx calls are fully mocked — no real network or browser
activity happens in these tests.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest  # noqa: E402 — pytest before third-party per ruff isort config
from oracle_mcp.result import OracleResult
from oracle_mcp.security import DestructivePayloadError

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_playwright_mock(marker_value: int = 1) -> MagicMock:
    """Return a nested mock that mimics the async_playwright() context manager.

    Chain: async_playwright().__aenter__() -> p
           p.chromium.launch() -> browser
           browser.new_page()  -> page
           page.goto(url)      -> None
           page.evaluate(expr) -> marker_value
           page.close()        -> None
           browser.close()     -> None
    """
    page = AsyncMock()
    page.goto = AsyncMock(return_value=None)
    page.evaluate = AsyncMock(return_value=marker_value)
    page.close = AsyncMock(return_value=None)

    browser = AsyncMock()
    browser.new_page = AsyncMock(return_value=page)
    browser.close = AsyncMock(return_value=None)

    chromium = AsyncMock()
    chromium.launch = AsyncMock(return_value=browser)

    p = MagicMock()
    p.chromium = chromium

    ctx = AsyncMock()
    ctx.__aenter__ = AsyncMock(return_value=p)
    ctx.__aexit__ = AsyncMock(return_value=False)

    return ctx


def _make_playwright_timeout_mock() -> MagicMock:
    """Return a playwright mock where page.goto raises PlaywrightTimeout."""
    from playwright.async_api import TimeoutError as PlaywrightTimeout

    page = AsyncMock()
    page.goto = AsyncMock(side_effect=PlaywrightTimeout("nav timed out"))
    page.evaluate = AsyncMock(return_value=0)
    page.close = AsyncMock(return_value=None)

    browser = AsyncMock()
    browser.new_page = AsyncMock(return_value=page)
    browser.close = AsyncMock(return_value=None)

    chromium = AsyncMock()
    chromium.launch = AsyncMock(return_value=browser)

    p = MagicMock()
    p.chromium = chromium

    ctx = AsyncMock()
    ctx.__aenter__ = AsyncMock(return_value=p)
    ctx.__aexit__ = AsyncMock(return_value=False)

    return ctx


# ---------------------------------------------------------------------------
# XSS tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_xss_validates():
    """All 3 attempts trigger XSS → verdict should be 'validated'."""
    from oracle_mcp.oracles.xss import oracle_xss

    mock_ctx = _make_playwright_mock(marker_value=1)

    with patch("oracle_mcp.oracles.xss.async_playwright", return_value=mock_ctx):
        result = await oracle_xss(
            url="http://example.com/search?q=hello",
            param="q",
            timeout_ms=2000,
        )

    assert isinstance(result, OracleResult)
    assert result.verdict == "validated"
    assert result.oracle_method == "xss_dom_mutation"
    assert result.evidence["successes"] == 3


@pytest.mark.asyncio
async def test_xss_unreproducible_on_timeout():
    """All 3 attempts time out → verdict should be 'unreproducible'."""
    from oracle_mcp.oracles.xss import oracle_xss

    mock_ctx = _make_playwright_timeout_mock()

    with patch("oracle_mcp.oracles.xss.async_playwright", return_value=mock_ctx):
        result = await oracle_xss(
            url="http://example.com/search?q=hello",
            param="q",
            timeout_ms=500,
        )

    assert result.verdict == "unreproducible"
    assert result.evidence["successes"] == 0


@pytest.mark.asyncio
async def test_xss_flaky_on_mixed():
    """1-of-3 attempts succeed → verdict should be 'flaky'."""
    from oracle_mcp.oracles.xss import oracle_xss
    from playwright.async_api import TimeoutError as PlaywrightTimeout

    call_count = 0

    page = AsyncMock()

    async def goto_side_effect(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise PlaywrightTimeout("timeout")

    page.goto = AsyncMock(side_effect=goto_side_effect)
    page.evaluate = AsyncMock(return_value=1)
    page.close = AsyncMock(return_value=None)

    browser = AsyncMock()
    browser.new_page = AsyncMock(return_value=page)
    browser.close = AsyncMock(return_value=None)

    chromium = AsyncMock()
    chromium.launch = AsyncMock(return_value=browser)

    p = MagicMock()
    p.chromium = chromium

    ctx = AsyncMock()
    ctx.__aenter__ = AsyncMock(return_value=p)
    ctx.__aexit__ = AsyncMock(return_value=False)

    with patch("oracle_mcp.oracles.xss.async_playwright", return_value=ctx):
        result = await oracle_xss(
            url="http://example.com/search?q=hello",
            param="q",
        )

    assert result.verdict == "flaky"


# ---------------------------------------------------------------------------
# SSRF tests
# ---------------------------------------------------------------------------


def _make_interactsh_client_mock(interactions: list) -> MagicMock:
    """Return an AsyncMock InteractshClient with scripted poll_interactions."""
    from oracle_mcp.oast import InteractshToken

    token = InteractshToken(
        token="bsdeadbeefcafe",
        server="https://oast.fun",
        registered_at=0.0,
    )

    client = AsyncMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    client.register_token = AsyncMock(return_value=token)
    client.poll_interactions = AsyncMock(return_value=interactions)
    client.deregister = AsyncMock(return_value=None)

    return client


@pytest.mark.asyncio
async def test_ssrf_validated():
    """One interaction returned → verdict should be 'validated'."""
    from oracle_mcp.oast import Interaction
    from oracle_mcp.oracles.ssrf import oracle_ssrf

    fake_interaction = Interaction(
        interaction_type="http",
        source_ip="10.0.0.1",
        timestamp="2024-01-01T00:00:00Z",
    )
    mock_client = _make_interactsh_client_mock([fake_interaction])

    mock_response = MagicMock()
    mock_response.status_code = 200

    with (
        patch("oracle_mcp.oracles.ssrf.get_default_client", return_value=mock_client),
        patch(
            "oracle_mcp.oracles.ssrf.httpx.AsyncClient",
            return_value=AsyncMock(
                __aenter__=AsyncMock(
                    return_value=AsyncMock(
                        get=AsyncMock(return_value=mock_response)
                    )
                ),
                __aexit__=AsyncMock(return_value=False),
            ),
        ),
    ):
        result = await oracle_ssrf(
            url="http://example.com/fetch?target=http://safe.example",
            param="target",
            poll_timeout_seconds=1.0,
        )

    assert result.verdict == "validated"
    assert result.oracle_method == "ssrf_oast_interactsh"
    assert result.evidence["interaction_type"] == "http"
    assert result.evidence["interaction_count"] == 1


@pytest.mark.asyncio
async def test_ssrf_unreproducible():
    """No interactions returned → verdict should be 'unreproducible'."""
    from oracle_mcp.oracles.ssrf import oracle_ssrf

    mock_client = _make_interactsh_client_mock([])

    mock_response = MagicMock()
    mock_response.status_code = 200

    with (
        patch("oracle_mcp.oracles.ssrf.get_default_client", return_value=mock_client),
        patch(
            "oracle_mcp.oracles.ssrf.httpx.AsyncClient",
            return_value=AsyncMock(
                __aenter__=AsyncMock(
                    return_value=AsyncMock(
                        get=AsyncMock(return_value=mock_response)
                    )
                ),
                __aexit__=AsyncMock(return_value=False),
            ),
        ),
    ):
        result = await oracle_ssrf(
            url="http://example.com/fetch?target=http://safe.example",
            param="target",
            poll_timeout_seconds=1.0,
        )

    assert result.verdict == "unreproducible"
    assert "no out-of-band" in (result.reason or "")


# ---------------------------------------------------------------------------
# SQLi tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sqli_validated():
    """Baseline ~0.05s x7, inject ~5.1s x7 → validated (p << 0.01)."""
    from oracle_mcp.oracles.sqli import oracle_sqli

    baseline_elapsed = [0.05] * 7
    inject_elapsed = [5.1] * 7
    elapsed_sequence = baseline_elapsed + inject_elapsed
    call_idx = {"n": 0}

    def mock_perf_counter():
        # Each _timed_get calls perf_counter twice (before and after get).
        idx = call_idx["n"] // 2
        is_end = call_idx["n"] % 2 == 1
        call_idx["n"] += 1
        if not is_end:
            return 0.0
        if idx < len(elapsed_sequence):
            return elapsed_sequence[idx]
        return elapsed_sequence[-1]

    async_client_instance = AsyncMock()
    async_client_instance.get = AsyncMock(return_value=MagicMock(status_code=200))
    async_client_instance.__aenter__ = AsyncMock(return_value=async_client_instance)
    async_client_instance.__aexit__ = AsyncMock(return_value=False)

    with (
        patch(
            "oracle_mcp.oracles.sqli.httpx.AsyncClient",
            return_value=async_client_instance,
        ),
        patch(
            "oracle_mcp.oracles.sqli.time.perf_counter",
            side_effect=mock_perf_counter,
        ),
    ):
        result = await oracle_sqli(
            url="http://example.com/items?id=1",
            param="id",
            baseline_n=7,
            inject_n=7,
            delay_seconds=5.0,
            alpha=0.01,
        )

    assert result.verdict == "validated"
    assert result.oracle_method == "sqli_timing_welch"
    assert result.evidence["p_value"] is not None
    assert result.evidence["p_value"] < 0.01


@pytest.mark.asyncio
async def test_sqli_inconclusive():
    """No timing difference → inconclusive."""
    from oracle_mcp.oracles.sqli import oracle_sqli

    # All responses take 0.05s — no detectable difference.
    elapsed_sequence = [0.05] * 14
    call_idx = {"n": 0}

    def mock_perf_counter():
        idx = call_idx["n"] // 2
        is_end = call_idx["n"] % 2 == 1
        call_idx["n"] += 1
        if not is_end:
            return 0.0
        if idx < len(elapsed_sequence):
            return elapsed_sequence[idx]
        return elapsed_sequence[-1]

    async_client_instance = AsyncMock()
    async_client_instance.get = AsyncMock(return_value=MagicMock(status_code=200))
    async_client_instance.__aenter__ = AsyncMock(return_value=async_client_instance)
    async_client_instance.__aexit__ = AsyncMock(return_value=False)

    with (
        patch(
            "oracle_mcp.oracles.sqli.httpx.AsyncClient",
            return_value=async_client_instance,
        ),
        patch(
            "oracle_mcp.oracles.sqli.time.perf_counter",
            side_effect=mock_perf_counter,
        ),
    ):
        result = await oracle_sqli(
            url="http://example.com/items?id=1",
            param="id",
            baseline_n=7,
            inject_n=7,
            delay_seconds=5.0,
            alpha=0.01,
        )

    assert result.verdict == "inconclusive"


# ---------------------------------------------------------------------------
# Destructive payload rejection
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_destructive_payload_rejected_xss():
    """oracle_xss with a destructive URL must raise DestructivePayloadError."""
    from oracle_mcp.oracles.xss import oracle_xss

    with pytest.raises(DestructivePayloadError):
        await oracle_xss(url="DROP TABLE users", param="q")


@pytest.mark.asyncio
async def test_destructive_payload_rejected_ssrf():
    """oracle_ssrf with a destructive URL must raise DestructivePayloadError."""
    from oracle_mcp.oracles.ssrf import oracle_ssrf

    with pytest.raises(DestructivePayloadError):
        await oracle_ssrf(url="DROP TABLE users", param="target")


@pytest.mark.asyncio
async def test_destructive_payload_rejected_sqli():
    """oracle_sqli with a destructive URL must raise DestructivePayloadError."""
    from oracle_mcp.oracles.sqli import oracle_sqli

    with pytest.raises(DestructivePayloadError):
        await oracle_sqli(url="DROP TABLE users", param="id")
