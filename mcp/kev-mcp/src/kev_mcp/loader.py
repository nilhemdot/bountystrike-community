# SPDX-License-Identifier: AGPL-3.0-or-later

"""CISA Known Exploited Vulnerabilities loader.

Fetches the public CISA KEV JSON feed, parses into typed entries, and
exposes them in a list shape the cache layer can index.

Feed: https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

import httpx
import structlog

log = structlog.get_logger("kev_mcp.loader")

DEFAULT_FEED_URL = (
    "https://www.cisa.gov/sites/default/files/feeds/"
    "known_exploited_vulnerabilities.json"
)


@dataclass(frozen=True, slots=True)
class KevEntry:
    """Normalized CISA KEV row (build-plan §4.7 shape)."""

    cve_id: str
    vendor_project: str
    product: str
    date_added: date
    short_description: str
    known_ransomware_use: bool
    raw: dict[str, Any] = field(default_factory=dict)

    def age_hours(self, now: datetime | None = None) -> float:
        """Hours since this CVE was added to the KEV catalog."""
        ref = now or datetime.utcnow()
        delta = ref - datetime.combine(self.date_added, datetime.min.time())
        return delta.total_seconds() / 3600.0


def _parse_entry(raw: dict[str, Any]) -> KevEntry | None:
    """Coerce one ``vulnerabilities[]`` row into a :class:`KevEntry`.

    Returns ``None`` for rows missing the bare-minimum CVE id or
    parseable ``dateAdded`` — keeps malformed rows from poisoning the
    cache without aborting the whole load.
    """
    cve_id = str(raw.get("cveID") or "").strip()
    if not cve_id:
        return None
    date_str = str(raw.get("dateAdded") or "").strip()
    try:
        date_added = date.fromisoformat(date_str)
    except ValueError:
        return None

    ransom_field = str(raw.get("knownRansomwareCampaignUse") or "").strip().lower()
    return KevEntry(
        cve_id=cve_id,
        vendor_project=str(raw.get("vendorProject") or ""),
        product=str(raw.get("product") or ""),
        date_added=date_added,
        short_description=str(raw.get("shortDescription") or ""),
        known_ransomware_use=ransom_field == "known",
        raw=raw,
    )


class CisaKevLoader:
    """Fetches + parses the CISA KEV feed.

    Args:
        feed_url: Override only for tests (e.g. file:// URL).
        http_client: Inject a pre-configured httpx.AsyncClient for tests.
    """

    def __init__(
        self,
        feed_url: str = DEFAULT_FEED_URL,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._url = feed_url
        self._client = http_client
        self._owns_client = http_client is None

    async def fetch(self) -> list[KevEntry]:
        """Hit the live feed and return the parsed catalog."""
        client = self._client or httpx.AsyncClient(timeout=30.0)
        try:
            response = await client.get(self._url)
            response.raise_for_status()
            payload = response.json()
        finally:
            if self._owns_client and self._client is None:
                await client.aclose()

        rows = payload.get("vulnerabilities") or []
        if not isinstance(rows, list):
            log.warning("kev.feed.malformed_top_level", type=type(rows).__name__)
            return []

        out: list[KevEntry] = []
        skipped = 0
        for raw in rows:
            if not isinstance(raw, dict):
                skipped += 1
                continue
            entry = _parse_entry(raw)
            if entry is None:
                skipped += 1
                continue
            out.append(entry)
        log.info("kev.feed.parsed", entries=len(out), skipped=skipped)
        return out


__all__ = ["CisaKevLoader", "DEFAULT_FEED_URL", "KevEntry"]
