"""FastMCP server for kev-mcp.

Exposes four tools (build-plan §4.7 prescribes ``kev_get_recent`` and
``kev_match_program``; ``kev_lookup`` and ``kev_status`` are
operational add-ons for one-shot CVE lookup and cache health checks):

* ``kev_get_recent(hours=72)``
* ``kev_match_program(tech_stack, ...)``
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


def _normalize_tech_token(raw: str) -> str:
    """Lower-case and strip the ``/version`` suffix from a tech token.

    httpx ``-tech-detect`` output looks like ``nginx/1.25``, ``Node.js``,
    ``WordPress 6.4``. Reduces to ``nginx`` / ``node.js`` / ``wordpress``
    so substring containment against KEV ``vendor_project`` / ``product``
    is symmetric.
    """
    token = raw.strip().lower()
    if not token:
        return ""
    # Drop "/version" or " version" suffix.
    for sep in ("/", " "):
        idx = token.find(sep)
        if idx > 0:
            token = token[:idx]
            break
    return token


def _tech_matches_kev(tech_norm: set[str], vendor_project: str, product: str) -> bool:
    """Bidirectional substring match between tech tokens and KEV row.

    Either direction counts as a hit:

      - tech token is a substring of vendor/product (``"nginx"`` ↔
        ``"NGINX, Inc."``)
      - vendor/product is a substring of tech token (rare but happens
        for niche products that show up as a parent name)
    """
    if not tech_norm:
        return False
    vp = vendor_project.lower()
    pr = product.lower()
    for tok in tech_norm:
        if not tok:
            continue
        if tok in vp or tok in pr or vp in tok or pr in tok:
            return True
    return False


@mcp.tool()
async def kev_match_program(
    tech_stack: list[str],
    max_age_hours: float | None = None,
    min_epss: float = 0.0,
) -> dict:
    """Cross-reference a program's detected tech stack against CISA KEV.

    Build-plan §4.7: given a list of technology fingerprints (e.g. from
    ``httpx -tech-detect`` or Trickest's ``server-report.csv``), return
    the KEV entries whose ``vendor_project`` / ``product`` overlaps any
    fingerprint. Each match is EPSS-merged so callers can rank by
    exploitation likelihood without a second tool call.

    Args:
        tech_stack: List of tech tokens (e.g.
            ``["nginx/1.25", "WordPress 6.4", "FastAPI"]``). Versions
            are stripped before matching; matching is case-insensitive
            and bidirectional substring.
        max_age_hours: If set, drop KEV rows older than this many hours
            (the freshness window where first-mover advantage is
            highest). ``None`` = no age filter.
        min_epss: Drop matches whose EPSS is below this threshold. Rows
            with no EPSS score are kept iff ``min_epss`` is 0.

    Returns:
        ``{"tech_stack": [...], "count": int, "matches": [...]}``
        where each match carries the same shape as ``kev_get_recent``
        rows. Sorted by EPSS desc (None → bottom), then age asc.
    """
    if not isinstance(tech_stack, list):
        return {"error": "tech_stack must be a list of strings", "matches": []}

    tech_norm = {
        _normalize_tech_token(t)
        for t in tech_stack
        if isinstance(t, str) and t.strip()
    }
    tech_norm.discard("")
    if not tech_norm:
        return {"tech_stack": tech_stack, "count": 0, "matches": []}

    entries = await cache.get_entries()
    now = datetime.utcnow()
    matched = [
        e for e in entries
        if _tech_matches_kev(tech_norm, e.vendor_project, e.product)
    ]

    if max_age_hours is not None:
        cutoff = float(max_age_hours)
        matched = [e for e in matched if e.age_hours(now) <= cutoff]

    cve_ids = [e.cve_id for e in matched]
    try:
        epss_map = await epss_client.lookup(cve_ids) if cve_ids else {}
    except Exception:
        epss_map = {}

    rows: list[dict] = []
    for e in matched:
        score = epss_map.get(e.cve_id)
        epss_val = score.epss if score else None
        if min_epss > 0 and (epss_val is None or epss_val < min_epss):
            continue
        rows.append({
            "cve_id": e.cve_id,
            "vendor_project": e.vendor_project,
            "product": e.product,
            "date_added": e.date_added.isoformat(),
            "age_hours": round(e.age_hours(now), 2),
            "short_description": e.short_description,
            "known_ransomware": e.known_ransomware_use,
            "epss": epss_val,
            "epss_percentile": score.percentile if score else None,
            "epss_date": score.date if score else None,
        })

    rows.sort(
        key=lambda r: (
            r["epss"] is None,
            -(r["epss"] or 0.0),
            r["age_hours"],
        ),
    )
    return {"tech_stack": tech_stack, "count": len(rows), "matches": rows}


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
