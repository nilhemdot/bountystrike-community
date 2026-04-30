"""FastMCP server for kev-mcp.

Exposes three tools (build-plan §4.7 prescribes two; ``kev_status`` is
an operational add-on for cache freshness checks):

* ``kev_get_recent(hours=72)``
* ``kev_lookup(cve_id)``
* ``kev_status()``

Transport: stdio (default FastMCP transport). Entry point:
``kev-mcp`` CLI script (see pyproject.toml).
"""

from __future__ import annotations

import os
from datetime import datetime

from mcp.server.fastmcp import FastMCP

from .cache import DEFAULT_TTL_SECONDS, KevCache
from .epss import EpssClient
from .loader import DEFAULT_FEED_URL, CisaKevLoader

# ---------------------------------------------------------------------------
# Module-level state (lazy-built, swappable in tests)
# ---------------------------------------------------------------------------

KEV_FEED_URL = os.environ.get("KEV_FEED_URL", DEFAULT_FEED_URL)
KEV_CACHE_TTL_SECONDS = float(
    os.environ.get("KEV_CACHE_TTL_SECONDS", str(DEFAULT_TTL_SECONDS))
)

cache = KevCache(
    loader=CisaKevLoader(feed_url=KEV_FEED_URL),
    ttl_seconds=KEV_CACHE_TTL_SECONDS,
)
epss_client = EpssClient()


# ---------------------------------------------------------------------------
# FastMCP server
# ---------------------------------------------------------------------------

mcp = FastMCP("kev-mcp")


@mcp.tool()
async def kev_get_recent(hours: int = 72) -> dict:
    """Return CISA KEV entries added in the last *hours*, EPSS-merged.

    Args:
        hours: Lookback window in hours. Defaults to 72 per build-plan
            §4.7 — the "first-mover" window where EPSS-driven attention
            is highest. Caller may widen for batch ranking jobs.

    Returns:
        ``{"window_hours": int, "count": int, "entries": [...]}``
        where each entry is::

            {
              "cve_id":              str,
              "vendor_project":      str,
              "product":             str,
              "date_added":          "YYYY-MM-DD",
              "age_hours":           float,
              "short_description":   str,
              "known_ransomware":    bool,
              "epss":                float | None,
              "epss_percentile":     float | None,
              "epss_date":           str | None,
            }

        Sorted by ``epss`` descending (None → bottom).
    """
    if hours <= 0:
        return {"error": "hours must be positive", "window_hours": hours}

    entries = await cache.get_entries()
    now = datetime.utcnow()
    cutoff = float(hours)
    recent = [e for e in entries if e.age_hours(now) <= cutoff]

    # Best-effort EPSS merge — if FIRST.org is down we still return the
    # KEV rows without scores rather than failing the whole tool.
    cve_ids = [e.cve_id for e in recent]
    try:
        epss_map = await epss_client.lookup(cve_ids)
    except Exception:
        epss_map = {}

    rows = []
    for e in recent:
        score = epss_map.get(e.cve_id)
        rows.append({
            "cve_id": e.cve_id,
            "vendor_project": e.vendor_project,
            "product": e.product,
            "date_added": e.date_added.isoformat(),
            "age_hours": round(e.age_hours(now), 2),
            "short_description": e.short_description,
            "known_ransomware": e.known_ransomware_use,
            "epss": score.epss if score else None,
            "epss_percentile": score.percentile if score else None,
            "epss_date": score.date if score else None,
        })

    rows.sort(
        key=lambda r: (r["epss"] is None, -(r["epss"] or 0.0)),
    )
    return {"window_hours": hours, "count": len(rows), "entries": rows}


@mcp.tool()
async def kev_lookup(cve_id: str) -> dict:
    """Return one KEV entry plus its current EPSS score, or ``not_found``.

    Args:
        cve_id: CVE identifier (e.g. ``CVE-2024-1234``). Case-insensitive.
    """
    if not cve_id or not cve_id.strip():
        return {"error": "cve_id is required"}

    entry = await cache.lookup(cve_id)
    if entry is None:
        return {"error": "not_found", "cve_id": cve_id}

    try:
        epss_map = await epss_client.lookup([entry.cve_id])
    except Exception:
        epss_map = {}
    score = epss_map.get(entry.cve_id)

    return {
        "cve_id": entry.cve_id,
        "vendor_project": entry.vendor_project,
        "product": entry.product,
        "date_added": entry.date_added.isoformat(),
        "age_hours": round(entry.age_hours(), 2),
        "short_description": entry.short_description,
        "known_ransomware": entry.known_ransomware_use,
        "epss": score.epss if score else None,
        "epss_percentile": score.percentile if score else None,
        "epss_date": score.date if score else None,
    }


@mcp.tool()
async def kev_status() -> dict:
    """Cache freshness + entry count. Cheap — safe for health checks."""
    snap = cache.snapshot
    if snap is None:
        return {
            "loaded": False,
            "entry_count": 0,
            "ttl_seconds": KEV_CACHE_TTL_SECONDS,
            "feed_url": KEV_FEED_URL,
        }
    age_seconds = (
        snap.fetched_at and (cache._clock() - snap.fetched_at)
    )
    return {
        "loaded": True,
        "entry_count": len(snap.entries),
        "age_seconds": round(age_seconds, 3),
        "ttl_seconds": KEV_CACHE_TTL_SECONDS,
        "stale": age_seconds >= KEV_CACHE_TTL_SECONDS,
        "feed_url": KEV_FEED_URL,
    }


def main() -> None:
    """Run the kev-mcp FastMCP server (stdio transport)."""
    mcp.run()


if __name__ == "__main__":
    main()
