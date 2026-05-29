# SPDX-License-Identifier: AGPL-3.0-or-later

"""EPSS v4 lookup client.

EPSS = Exploit Prediction Scoring System (probability of exploitation
in next 30 days, 0.0 – 1.0). FIRST.org publishes daily updates at
https://api.first.org/data/v1/epss?cve=CVE-X,CVE-Y,...

Batch lookups are a single GET; the API accepts hundreds of CVEs in
one query, which keeps the live KEV-merge cheap.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

import httpx
import structlog

log = structlog.get_logger("kev_mcp.epss")

DEFAULT_EPSS_URL = "https://api.first.org/data/v1/epss"
# FIRST.org rejects very long query strings; keep batches sane.
MAX_BATCH = 100


@dataclass(frozen=True, slots=True)
class EpssScore:
    """One row from the EPSS API."""

    cve: str
    epss: float
    percentile: float
    date: str  # YYYY-MM-DD as returned by the API


class EpssClient:
    """Lookup EPSS scores for a list of CVEs."""

    def __init__(
        self,
        url: str = DEFAULT_EPSS_URL,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._url = url
        self._client = http_client
        self._owns_client = http_client is None

    async def lookup(self, cve_ids: Iterable[str]) -> dict[str, EpssScore]:
        """Return ``{cve_id: EpssScore}`` for as many of the inputs as resolve.

        CVEs that EPSS doesn't have a score for are silently omitted
        from the result map — call sites should not assume every input
        appears in the output.
        """
        ids = sorted({c.strip() for c in cve_ids if c and c.strip()})
        if not ids:
            return {}

        client = self._client or httpx.AsyncClient(timeout=30.0)
        out: dict[str, EpssScore] = {}
        try:
            for start in range(0, len(ids), MAX_BATCH):
                batch = ids[start : start + MAX_BATCH]
                response = await client.get(
                    self._url,
                    params={"cve": ",".join(batch)},
                )
                response.raise_for_status()
                payload = response.json()
                for raw in payload.get("data") or []:
                    if not isinstance(raw, dict):
                        continue
                    score = _parse_score(raw)
                    if score is not None:
                        out[score.cve] = score
        finally:
            if self._owns_client and self._client is None:
                await client.aclose()

        log.info("epss.lookup.done", requested=len(ids), resolved=len(out))
        return out


def _parse_score(raw: dict) -> EpssScore | None:
    cve = str(raw.get("cve") or "").strip()
    if not cve:
        return None
    try:
        epss = float(raw.get("epss") or 0.0)
        percentile = float(raw.get("percentile") or 0.0)
    except (TypeError, ValueError):
        return None
    return EpssScore(
        cve=cve,
        epss=epss,
        percentile=percentile,
        date=str(raw.get("date") or ""),
    )


__all__ = ["DEFAULT_EPSS_URL", "EpssClient", "EpssScore", "MAX_BATCH"]
