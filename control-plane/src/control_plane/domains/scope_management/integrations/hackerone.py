# SPDX-License-Identifier: AGPL-3.0-or-later

"""HackerOne April-2026 org-assets API async client.

Reference: ``docs/research/02-routing-ev.md`` §HackerOne (April 16 2026
deprecation).

Endpoint
--------
``GET /v1/organizations/{org_id}/assets``

Pagination
----------
``page[size]`` (max 100) + ``page[number]``. We loop until the JSON:API
``links.next`` becomes null.

Change-event mode
-----------------
``filter[updated_at__gt]={iso8601}`` — pulls only assets touched since
``since``.

Auth
----
HTTP Basic with ``H1_USERNAME`` + ``H1_API_TOKEN`` env vars.

Field migration vs the deprecated ``structured_scopes`` endpoint:

* ``asset_identifier`` -> ``identifier``
* ``updated_at`` -> ``last_modified_at``
* New ``program_handles[]`` (one asset, many programs)
* New ``tags``, ``notes``
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, Field

DEFAULT_BASE_URL = "https://api.hackerone.com"
DEFAULT_PAGE_SIZE = 100
DEFAULT_TIMEOUT = httpx.Timeout(10.0, connect=30.0, read=60.0, write=60.0, pool=10.0)
DEFAULT_RETRIES = 2


class H1Asset(BaseModel):
    """Normalized HackerOne org asset (April 2026 schema)."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    identifier: str = Field(..., alias="asset_identifier")
    asset_type: str
    last_modified_at: datetime | None = Field(default=None, alias="updated_at")
    program_handles: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    notes: str | None = None
    raw: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def from_jsonapi(cls, item: dict[str, Any]) -> H1Asset:
        """Build from a JSON:API resource object.

        H1 returns ``{"id": "...", "type": "asset", "attributes": {...},
        "relationships": {...}}``. Attributes carry the canonical field names
        (``identifier`` / ``last_modified_at``); we keep aliases for the
        deprecated names so legacy fixtures still parse.
        """
        attributes = dict(item.get("attributes") or {})
        relationships = item.get("relationships") or {}

        program_handles: list[str] = list(attributes.pop("program_handles", []) or [])
        if not program_handles:
            programs = relationships.get("programs") or {}
            data = programs.get("data") or []
            program_handles = [p.get("attributes", {}).get("handle") or p.get("id") for p in data]
            program_handles = [p for p in program_handles if p]

        # Pydantic resolves alias vs. canonical automatically thanks to
        # ``populate_by_name=True``.
        payload: dict[str, Any] = dict(attributes)
        payload["program_handles"] = program_handles
        payload.setdefault("tags", attributes.get("tags") or [])
        payload["raw"] = item
        return cls.model_validate(payload)


class HackerOneClient:
    """Async HackerOne org-assets client.

    Re-uses a single ``httpx.AsyncClient`` across requests. Caller is
    responsible for ``await client.aclose()`` (or use as an async context
    manager).
    """

    def __init__(
        self,
        username: str | None = None,
        api_token: str | None = None,
        *,
        base_url: str = DEFAULT_BASE_URL,
        timeout: httpx.Timeout | None = None,
        retries: int = DEFAULT_RETRIES,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        username = username or os.environ.get("H1_USERNAME")
        api_token = api_token or os.environ.get("H1_API_TOKEN")
        if not username or not api_token:
            raise ValueError(
                "HackerOne client requires H1_USERNAME and H1_API_TOKEN "
                "(env vars or constructor args)"
            )

        if transport is None:
            transport = httpx.AsyncHTTPTransport(retries=retries)

        self._client = httpx.AsyncClient(
            base_url=base_url,
            auth=(username, api_token),
            timeout=timeout or DEFAULT_TIMEOUT,
            transport=transport,
            headers={
                "Accept": "application/json",
                "User-Agent": "BountyStrike/v5 (scope-ingestor)",
            },
        )

    async def __aenter__(self) -> HackerOneClient:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._client.aclose()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def fetch_org_assets(
        self,
        org_id: str,
        *,
        since: datetime | None = None,
        page_size: int = DEFAULT_PAGE_SIZE,
    ) -> list[H1Asset]:
        """Fetch all assets for an org (loops over every page)."""
        return [a async for a in self.iter_org_assets(org_id, since=since, page_size=page_size)]

    async def iter_org_assets(
        self,
        org_id: str,
        *,
        since: datetime | None = None,
        page_size: int = DEFAULT_PAGE_SIZE,
    ) -> AsyncIterator[H1Asset]:
        """Yield assets for ``org_id`` page by page."""
        page_number = 1
        path = f"/v1/organizations/{org_id}/assets"
        while True:
            params: dict[str, str] = {
                "page[size]": str(page_size),
                "page[number]": str(page_number),
            }
            if since is not None:
                params["filter[updated_at__gt]"] = _to_iso8601(since)

            response = await self._client.get(path, params=params)
            self._raise_for_status(response, org_id=org_id, page=page_number)
            payload = response.json()

            for item in payload.get("data") or []:
                yield H1Asset.from_jsonapi(item)

            links = payload.get("links") or {}
            next_link = links.get("next")
            if not next_link:
                return
            page_number += 1

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    @staticmethod
    def _raise_for_status(response: httpx.Response, *, org_id: str, page: int) -> None:
        if response.is_success:
            return
        msg = (
            f"HackerOne org-assets request failed: status={response.status_code} "
            f"org_id={org_id} page={page}"
        )
        if response.status_code == 401:
            raise H1AuthError(msg)
        if response.status_code == 429:
            raise H1RateLimitError(msg)
        if response.status_code >= 500:
            raise H1ServerError(msg)
        raise H1ClientError(msg)


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class H1ClientError(RuntimeError):
    """Base error raised by :class:`HackerOneClient`."""


class H1AuthError(H1ClientError):
    """401 / 403."""


class H1RateLimitError(H1ClientError):
    """429."""


class H1ServerError(H1ClientError):
    """5xx."""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _to_iso8601(value: datetime) -> str:
    """Render a :class:`datetime` as a strict RFC3339/ISO-8601 string with ``Z``."""
    if value.tzinfo is None:
        return value.isoformat() + "Z"
    return value.isoformat().replace("+00:00", "Z")


__all__ = [
    "DEFAULT_BASE_URL",
    "H1Asset",
    "H1AuthError",
    "H1ClientError",
    "H1RateLimitError",
    "H1ServerError",
    "HackerOneClient",
]
