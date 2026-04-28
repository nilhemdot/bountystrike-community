"""Federation L0 client — `arkadiyt/bounty-targets-data`.

Pulls JSON snapshots for HackerOne, Bugcrowd, Intigriti, YesWeHack and Immunefi
from `raw.githubusercontent.com`. The repo is updated every 30 min and is the
unauthenticated baseline before higher tiers (rix4uni / bbscope / Trickest).

Reference: `docs/research/02-routing-ev.md` §Federation layers.
"""

from __future__ import annotations

import asyncio
from typing import Any, Literal

import httpx
from pydantic import BaseModel, ConfigDict, Field

DEFAULT_BASE_URL = (
    "https://raw.githubusercontent.com/arkadiyt/bounty-targets-data/main/data"
)

Platform = Literal["hackerone", "bugcrowd", "intigriti", "yeswehack", "immunefi"]

# Maps platform -> filename in the upstream repo.
FEED_FILES: dict[Platform, str] = {
    "hackerone": "h1_data.json",
    "bugcrowd": "bugcrowd_data.json",
    "intigriti": "intigriti_data.json",
    "yeswehack": "yeswehack_data.json",
    "immunefi": "immunefi_data.json",
}

DEFAULT_TIMEOUT = httpx.Timeout(10.0, connect=30.0, read=60.0, write=60.0, pool=10.0)


class FederationProgram(BaseModel):
    """Lightweight per-program record extracted from a feed file.

    The upstream JSON shape varies per platform; we normalize the keys we care
    about and stash the raw record in `raw` so callers can recover platform-
    specific detail downstream.
    """

    model_config = ConfigDict(extra="ignore")

    platform: Platform
    handle: str
    name: str | None = None
    url: str | None = None
    offers_bounties: bool | None = None
    targets_in_scope: list[dict[str, Any]] = Field(default_factory=list)
    targets_out_of_scope: list[dict[str, Any]] = Field(default_factory=list)
    raw: dict[str, Any] = Field(default_factory=dict)


class ArkadiytClient:
    """Async federation client for the `arkadiyt/bounty-targets-data` repo."""

    def __init__(
        self,
        *,
        base_url: str = DEFAULT_BASE_URL,
        timeout: httpx.Timeout | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if transport is None:
            transport = httpx.AsyncHTTPTransport(retries=2)
        self._client = httpx.AsyncClient(
            base_url=base_url,
            timeout=timeout or DEFAULT_TIMEOUT,
            transport=transport,
            headers={"User-Agent": "BountyStrike/v5 (scope-ingestor)"},
        )

    async def __aenter__(self) -> ArkadiytClient:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._client.aclose()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def fetch_platform(self, platform: Platform) -> list[FederationProgram]:
        """Download a single platform feed and parse it into typed programs."""
        filename = FEED_FILES[platform]
        response = await self._client.get(f"/{filename}")
        response.raise_for_status()
        payload = response.json()
        return _parse_feed(platform, payload)

    async def fetch_all(self) -> dict[Platform, list[FederationProgram]]:
        """Fetch all 5 feeds concurrently."""
        platforms: list[Platform] = list(FEED_FILES.keys())
        tasks = [self.fetch_platform(p) for p in platforms]
        results = await asyncio.gather(*tasks, return_exceptions=False)
        return dict(zip(platforms, results, strict=True))


# ---------------------------------------------------------------------------
# Per-platform parsers
# ---------------------------------------------------------------------------


def _parse_feed(platform: Platform, payload: Any) -> list[FederationProgram]:
    """Dispatch a platform-specific parser over the raw feed payload."""
    if not isinstance(payload, list):
        return []

    parsers = {
        "hackerone": _parse_h1,
        "bugcrowd": _parse_bugcrowd,
        "intigriti": _parse_intigriti,
        "yeswehack": _parse_yeswehack,
        "immunefi": _parse_immunefi,
    }
    parser = parsers[platform]
    out: list[FederationProgram] = []
    for record in payload:
        if not isinstance(record, dict):
            continue
        try:
            out.append(parser(record))
        except (KeyError, ValueError, TypeError):
            # Drop records we can't parse rather than fail the whole feed.
            continue
    return out


def _parse_h1(record: dict[str, Any]) -> FederationProgram:
    handle = record.get("handle") or record.get("name") or ""
    return FederationProgram(
        platform="hackerone",
        handle=handle,
        name=record.get("name") or handle,
        url=record.get("url"),
        offers_bounties=record.get("offers_bounties"),
        targets_in_scope=list((record.get("targets") or {}).get("in_scope") or []),
        targets_out_of_scope=list((record.get("targets") or {}).get("out_of_scope") or []),
        raw=record,
    )


def _parse_bugcrowd(record: dict[str, Any]) -> FederationProgram:
    handle = record.get("code") or record.get("name") or ""
    return FederationProgram(
        platform="bugcrowd",
        handle=handle,
        name=record.get("name") or handle,
        url=record.get("url"),
        offers_bounties=bool(record.get("max_payout")),
        targets_in_scope=list((record.get("targets") or {}).get("in_scope") or []),
        targets_out_of_scope=list((record.get("targets") or {}).get("out_of_scope") or []),
        raw=record,
    )


def _parse_intigriti(record: dict[str, Any]) -> FederationProgram:
    handle = record.get("handle") or record.get("id") or record.get("name") or ""
    return FederationProgram(
        platform="intigriti",
        handle=str(handle),
        name=record.get("name"),
        url=record.get("url"),
        offers_bounties=bool(record.get("max_bounty")),
        targets_in_scope=list((record.get("targets") or {}).get("in_scope") or []),
        targets_out_of_scope=list((record.get("targets") or {}).get("out_of_scope") or []),
        raw=record,
    )


def _parse_yeswehack(record: dict[str, Any]) -> FederationProgram:
    handle = record.get("slug") or record.get("id") or record.get("name") or ""
    return FederationProgram(
        platform="yeswehack",
        handle=str(handle),
        name=record.get("title") or record.get("name"),
        url=record.get("url"),
        offers_bounties=bool(record.get("bounty_reward_min")),
        targets_in_scope=list(record.get("scopes") or []),
        targets_out_of_scope=list(record.get("out_of_scope") or []),
        raw=record,
    )


def _parse_immunefi(record: dict[str, Any]) -> FederationProgram:
    handle = record.get("id") or record.get("project") or record.get("name") or ""
    return FederationProgram(
        platform="immunefi",
        handle=str(handle),
        name=record.get("project") or record.get("name"),
        url=record.get("url"),
        offers_bounties=bool(record.get("maxBounty") or record.get("max_bounty")),
        targets_in_scope=list(record.get("assets") or record.get("inScope") or []),
        targets_out_of_scope=list(record.get("outOfScope") or []),
        raw=record,
    )


__all__ = [
    "ArkadiytClient",
    "FEED_FILES",
    "FederationProgram",
    "Platform",
]
