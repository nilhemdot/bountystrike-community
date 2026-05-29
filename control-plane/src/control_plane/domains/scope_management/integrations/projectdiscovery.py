# SPDX-License-Identifier: AGPL-3.0-or-later

"""Federation VDP client — ``projectdiscovery/public-bugbounty-programs``.

Adds the VDP (vulnerability-disclosure-program) coverage layer on top of the
arkadiyt baseline and the authenticated bbscope depth. These programs have no
payout, so they upsert with ``platform="projectdiscovery"`` and a ``vdp`` tag
on every asset.

Trap #8: programs live in ``dist/data.json`` under the top-level ``programs``
key, NOT in the legacy flat list file the older docs point at.
"""

from __future__ import annotations

import os
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, Field

DEFAULT_DATA_URL = (
    "https://raw.githubusercontent.com/projectdiscovery/"
    "public-bugbounty-programs/main/dist/data.json"
)

DEFAULT_TIMEOUT = httpx.Timeout(10.0, connect=30.0, read=60.0, write=60.0, pool=10.0)


class PDProgram(BaseModel):
    """One VDP program entry from ``dist/data.json``."""

    model_config = ConfigDict(extra="ignore")

    name: str
    url: str | None = None
    bounty: bool = False
    swag: bool = False
    domains: list[str] = Field(default_factory=list)


class PDData(BaseModel):
    """Top-level ``dist/data.json`` shape — programs under the ``programs`` key."""

    model_config = ConfigDict(extra="ignore")

    programs: list[PDProgram] = Field(default_factory=list)


class ProjectDiscoveryClient:
    """Async client for the projectdiscovery public VDP list."""

    def __init__(
        self,
        *,
        data_url: str | None = None,
        timeout: httpx.Timeout | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        # Base URL is env-overridable so mirrors/forks can be pointed at.
        self._url = data_url or os.environ.get("PROJECTDISCOVERY_DATA_URL", DEFAULT_DATA_URL)
        if transport is None:
            transport = httpx.AsyncHTTPTransport(retries=2)
        self._client = httpx.AsyncClient(
            timeout=timeout or DEFAULT_TIMEOUT,
            transport=transport,
            headers={"User-Agent": "BountyStrike/v5 (scope-ingestor)"},
        )

    async def __aenter__(self) -> ProjectDiscoveryClient:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._client.aclose()

    async def fetch_programs(self) -> list[PDProgram]:
        """Download ``dist/data.json`` and parse the ``programs`` array."""
        response = await self._client.get(self._url)
        response.raise_for_status()
        payload: Any = response.json()
        return PDData.model_validate(payload).programs


__all__ = [
    "DEFAULT_DATA_URL",
    "PDData",
    "PDProgram",
    "ProjectDiscoveryClient",
]
