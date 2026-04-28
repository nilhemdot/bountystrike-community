"""Tests for `control_plane.integrations.h1_client`.

We use `respx` to mock the HackerOne API. Three pages exercise the pagination
loop, then we verify `since` filter injection and 401/429/500 error mapping.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx
from control_plane.integrations.h1_client import (
    DEFAULT_BASE_URL,
    H1AuthError,
    H1RateLimitError,
    H1ServerError,
    HackerOneClient,
)

FIXTURES = Path(__file__).parent / "fixtures"


def _load_page() -> dict[str, Any]:
    return json.loads((FIXTURES / "h1_org_assets_page.json").read_text())


def _make_page(page_number: int, total_pages: int, item_id: int) -> dict[str, Any]:
    is_last = page_number >= total_pages
    base = f"{DEFAULT_BASE_URL}/v1/organizations/77/assets"
    return {
        "data": [
            {
                "id": str(item_id),
                "type": "asset",
                "attributes": {
                    "asset_type": "URL",
                    "identifier": f"target-{item_id}.example.com",
                    "last_modified_at": "2026-04-21T00:00:00Z",
                    "program_handles": ["acme-corp"],
                    "tags": [],
                },
            }
        ],
        "links": {
            "self": f"{base}?page%5Bnumber%5D={page_number}",
            "next": None if is_last else f"{base}?page%5Bnumber%5D={page_number + 1}",
        },
    }


@pytest.fixture
def client() -> HackerOneClient:
    """Real client wired to a respx-mocked transport."""
    return HackerOneClient(
        username="test-user",
        api_token="test-token",
        retries=0,
    )


@pytest.mark.asyncio
@respx.mock(base_url=DEFAULT_BASE_URL)
async def test_pagination_three_pages(respx_mock: respx.Router, client: HackerOneClient) -> None:
    page_route = respx_mock.get("/v1/organizations/77/assets")
    page_route.side_effect = [
        httpx.Response(200, json=_make_page(1, 3, 1001)),
        httpx.Response(200, json=_make_page(2, 3, 1002)),
        httpx.Response(200, json=_make_page(3, 3, 1003)),
    ]

    try:
        assets = await client.fetch_org_assets("77")
    finally:
        await client.aclose()

    assert len(assets) == 3
    assert {a.identifier for a in assets} == {
        "target-1001.example.com",
        "target-1002.example.com",
        "target-1003.example.com",
    }
    assert page_route.call_count == 3


@pytest.mark.asyncio
@respx.mock(base_url=DEFAULT_BASE_URL)
async def test_since_filter_injected(respx_mock: respx.Router, client: HackerOneClient) -> None:
    route = respx_mock.get("/v1/organizations/77/assets").mock(
        return_value=httpx.Response(200, json=_load_page())
    )

    try:
        await client.fetch_org_assets("77", since=datetime(2026, 4, 1, 0, 0, 0, tzinfo=UTC))
    finally:
        await client.aclose()

    assert route.called
    sent = route.calls.last.request
    assert "filter%5Bupdated_at__gt%5D=2026-04-01T00%3A00%3A00Z" in str(sent.url)
    assert "page%5Bsize%5D=100" in str(sent.url)
    assert "page%5Bnumber%5D=1" in str(sent.url)


@pytest.mark.asyncio
@respx.mock(base_url=DEFAULT_BASE_URL)
async def test_full_page_parses_three_assets(
    respx_mock: respx.Router, client: HackerOneClient
) -> None:
    respx_mock.get("/v1/organizations/77/assets").mock(
        return_value=httpx.Response(200, json=_load_page())
    )

    try:
        assets = await client.fetch_org_assets("77")
    finally:
        await client.aclose()

    assert len(assets) == 3
    by_id = {a.identifier: a for a in assets}
    assert "*.acme.com" in by_id
    assert "api.acme.com" in by_id
    assert "com.acme.app" in by_id
    assert by_id["*.acme.com"].program_handles == ["acme-corp"]
    assert by_id["*.acme.com"].tags == ["primary", "production"]
    assert by_id["*.acme.com"].last_modified_at is not None


@pytest.mark.asyncio
@respx.mock(base_url=DEFAULT_BASE_URL)
async def test_401_raises_auth_error(respx_mock: respx.Router, client: HackerOneClient) -> None:
    respx_mock.get("/v1/organizations/77/assets").mock(
        return_value=httpx.Response(401, json={"errors": [{"detail": "unauthorized"}]})
    )

    with pytest.raises(H1AuthError):
        try:
            await client.fetch_org_assets("77")
        finally:
            await client.aclose()


@pytest.mark.asyncio
@respx.mock(base_url=DEFAULT_BASE_URL)
async def test_429_raises_rate_limit_error(
    respx_mock: respx.Router, client: HackerOneClient
) -> None:
    respx_mock.get("/v1/organizations/77/assets").mock(
        return_value=httpx.Response(429, json={"errors": [{"detail": "rate limited"}]})
    )

    with pytest.raises(H1RateLimitError):
        try:
            await client.fetch_org_assets("77")
        finally:
            await client.aclose()


@pytest.mark.asyncio
@respx.mock(base_url=DEFAULT_BASE_URL)
async def test_500_raises_server_error(respx_mock: respx.Router, client: HackerOneClient) -> None:
    respx_mock.get("/v1/organizations/77/assets").mock(
        return_value=httpx.Response(500, json={"errors": [{"detail": "boom"}]})
    )

    with pytest.raises(H1ServerError):
        try:
            await client.fetch_org_assets("77")
        finally:
            await client.aclose()


def test_missing_credentials_raises() -> None:
    with pytest.raises(ValueError, match="H1_USERNAME"):
        HackerOneClient(username=None, api_token=None)
