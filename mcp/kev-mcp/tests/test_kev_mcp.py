"""Tests for kev-mcp — CISA KEV loader, EPSS client, cache, server tools."""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta

import httpx
import pytest
import respx

from kev_mcp.cache import KevCache
from kev_mcp.epss import DEFAULT_EPSS_URL, EpssClient, EpssScore
from kev_mcp.loader import (
    DEFAULT_FEED_URL,
    CisaKevLoader,
    KevEntry,
    _parse_entry,
)


# ---------------------------------------------------------------------------
# 1. Loader — _parse_entry
# ---------------------------------------------------------------------------


def test_parse_entry_happy_path():
    raw = {
        "cveID": "CVE-2024-1234",
        "vendorProject": "Acme",
        "product": "Widget",
        "dateAdded": "2024-06-15",
        "shortDescription": "Bad bug.",
        "knownRansomwareCampaignUse": "Known",
    }
    entry = _parse_entry(raw)
    assert entry is not None
    assert entry.cve_id == "CVE-2024-1234"
    assert entry.vendor_project == "Acme"
    assert entry.date_added == date(2024, 6, 15)
    assert entry.known_ransomware_use is True


def test_parse_entry_unknown_ransomware_is_false():
    raw = {
        "cveID": "CVE-2024-1234",
        "dateAdded": "2024-06-15",
        "knownRansomwareCampaignUse": "Unknown",
    }
    entry = _parse_entry(raw)
    assert entry is not None
    assert entry.known_ransomware_use is False


@pytest.mark.parametrize(
    "raw",
    [
        {},  # missing CVE id
        {"cveID": "", "dateAdded": "2024-06-15"},
        {"cveID": "CVE-2024-1234", "dateAdded": ""},
        {"cveID": "CVE-2024-1234", "dateAdded": "garbage"},
    ],
)
def test_parse_entry_returns_none_for_malformed_rows(raw):
    assert _parse_entry(raw) is None


def test_kev_entry_age_hours_uses_explicit_now():
    entry = KevEntry(
        cve_id="CVE-X",
        vendor_project="V",
        product="P",
        date_added=date(2024, 6, 15),
        short_description="",
        known_ransomware_use=False,
    )
    later = datetime(2024, 6, 16, 12, 0, 0)
    assert entry.age_hours(later) == pytest.approx(36.0)


# ---------------------------------------------------------------------------
# 2. Loader — fetch (respx-mocked HTTP)
# ---------------------------------------------------------------------------


@respx.mock
async def test_loader_fetch_parses_feed():
    payload = {
        "vulnerabilities": [
            {
                "cveID": "CVE-2024-0001",
                "vendorProject": "A",
                "product": "P1",
                "dateAdded": "2024-01-01",
                "shortDescription": "first",
                "knownRansomwareCampaignUse": "Known",
            },
            {
                "cveID": "CVE-2024-0002",
                "vendorProject": "B",
                "product": "P2",
                "dateAdded": "2024-02-01",
                "shortDescription": "second",
                "knownRansomwareCampaignUse": "Unknown",
            },
        ]
    }
    respx.get(DEFAULT_FEED_URL).mock(
        return_value=httpx.Response(200, json=payload)
    )
    entries = await CisaKevLoader().fetch()
    assert len(entries) == 2
    assert entries[0].cve_id == "CVE-2024-0001"
    assert entries[1].known_ransomware_use is False


@respx.mock
async def test_loader_skips_malformed_rows_without_aborting():
    payload = {
        "vulnerabilities": [
            {"cveID": "CVE-2024-0001", "dateAdded": "2024-01-01"},
            "not a dict",
            {"cveID": ""},
            {"cveID": "CVE-2024-0002", "dateAdded": "2024-02-01"},
        ]
    }
    respx.get(DEFAULT_FEED_URL).mock(
        return_value=httpx.Response(200, json=payload)
    )
    entries = await CisaKevLoader().fetch()
    assert {e.cve_id for e in entries} == {"CVE-2024-0001", "CVE-2024-0002"}


@respx.mock
async def test_loader_returns_empty_on_malformed_top_level():
    respx.get(DEFAULT_FEED_URL).mock(
        return_value=httpx.Response(200, json={"vulnerabilities": "oops"})
    )
    entries = await CisaKevLoader().fetch()
    assert entries == []


@respx.mock
async def test_loader_raises_on_http_error():
    respx.get(DEFAULT_FEED_URL).mock(return_value=httpx.Response(503))
    with pytest.raises(httpx.HTTPError):
        await CisaKevLoader().fetch()


# ---------------------------------------------------------------------------
# 3. EpssClient — batching + parsing
# ---------------------------------------------------------------------------


@respx.mock
async def test_epss_lookup_parses_data_array():
    respx.get(DEFAULT_EPSS_URL).mock(
        return_value=httpx.Response(200, json={
            "data": [
                {"cve": "CVE-2024-0001", "epss": "0.123",
                 "percentile": "0.456", "date": "2024-08-01"},
                {"cve": "CVE-2024-0002", "epss": "0.789",
                 "percentile": "0.999", "date": "2024-08-01"},
            ]
        })
    )
    client = EpssClient()
    result = await client.lookup(["CVE-2024-0001", "CVE-2024-0002"])
    assert result["CVE-2024-0001"].epss == pytest.approx(0.123)
    assert result["CVE-2024-0002"].percentile == pytest.approx(0.999)


@respx.mock
async def test_epss_lookup_drops_unparseable_scores():
    respx.get(DEFAULT_EPSS_URL).mock(
        return_value=httpx.Response(200, json={
            "data": [
                {"cve": "CVE-2024-0001", "epss": "0.10", "percentile": "0.5"},
                {"cve": "", "epss": "0.99"},                # missing CVE id
                {"cve": "CVE-2024-0003", "epss": "garbage"},  # unparseable
            ]
        })
    )
    result = await EpssClient().lookup(["CVE-2024-0001", "CVE-2024-0003"])
    assert set(result) == {"CVE-2024-0001"}


async def test_epss_lookup_empty_input_short_circuits():
    """No httpx call when caller hands us no CVEs — important for cost control."""
    client = EpssClient()
    assert await client.lookup([]) == {}
    assert await client.lookup(["", " "]) == {}


# ---------------------------------------------------------------------------
# 4. Cache — TTL semantics + lookups
# ---------------------------------------------------------------------------


class _StubLoader:
    def __init__(self, batches: list[list[KevEntry]]) -> None:
        self._batches = list(batches)
        self.fetch_calls = 0

    async def fetch(self) -> list[KevEntry]:
        self.fetch_calls += 1
        if self._batches:
            return self._batches.pop(0)
        return []


def _entry(cve: str, dt: date) -> KevEntry:
    return KevEntry(
        cve_id=cve,
        vendor_project="V",
        product="P",
        date_added=dt,
        short_description="",
        known_ransomware_use=False,
    )


async def test_cache_lazy_load_on_first_access():
    loader = _StubLoader([[_entry("CVE-1", date(2024, 1, 1))]])
    cache = KevCache(loader, ttl_seconds=60.0, clock=lambda: 0.0)  # type: ignore[arg-type]
    entries = await cache.get_entries()
    assert len(entries) == 1
    assert loader.fetch_calls == 1


async def test_cache_returns_cached_within_ttl():
    loader = _StubLoader([
        [_entry("CVE-1", date(2024, 1, 1))],
        [_entry("CVE-2", date(2024, 2, 1))],  # would be returned on refresh
    ])
    fake_time = [0.0]
    cache = KevCache(loader, ttl_seconds=60.0, clock=lambda: fake_time[0])  # type: ignore[arg-type]
    await cache.get_entries()
    fake_time[0] = 30.0  # within TTL
    second = await cache.get_entries()
    assert second[0].cve_id == "CVE-1"
    assert loader.fetch_calls == 1


async def test_cache_refreshes_after_ttl_expires():
    loader = _StubLoader([
        [_entry("CVE-1", date(2024, 1, 1))],
        [_entry("CVE-2", date(2024, 2, 1))],
    ])
    fake_time = [0.0]
    cache = KevCache(loader, ttl_seconds=60.0, clock=lambda: fake_time[0])  # type: ignore[arg-type]
    await cache.get_entries()
    fake_time[0] = 60.0  # boundary: TTL reached
    second = await cache.get_entries()
    assert second[0].cve_id == "CVE-2"
    assert loader.fetch_calls == 2


async def test_cache_lookup_is_case_insensitive():
    loader = _StubLoader([[_entry("CVE-2024-1234", date(2024, 1, 1))]])
    cache = KevCache(loader, ttl_seconds=60.0, clock=lambda: 0.0)  # type: ignore[arg-type]
    found = await cache.lookup("cve-2024-1234")
    assert found is not None
    assert found.cve_id == "CVE-2024-1234"


async def test_cache_lookup_returns_none_for_missing():
    loader = _StubLoader([[_entry("CVE-1", date(2024, 1, 1))]])
    cache = KevCache(loader, ttl_seconds=60.0, clock=lambda: 0.0)  # type: ignore[arg-type]
    assert await cache.lookup("CVE-NOT-IN-FEED") is None
    assert await cache.lookup("") is None


async def test_cache_force_refresh_replaces_snapshot():
    loader = _StubLoader([
        [_entry("CVE-1", date(2024, 1, 1))],
        [_entry("CVE-2", date(2024, 2, 1))],
    ])
    cache = KevCache(loader, ttl_seconds=86400.0, clock=lambda: 0.0)  # type: ignore[arg-type]
    await cache.get_entries()
    await cache.force_refresh()
    entries = await cache.get_entries()
    assert entries[0].cve_id == "CVE-2"
    assert loader.fetch_calls == 2


# ---------------------------------------------------------------------------
# 5. Server tools — exercised against a stubbed cache + respx-mocked EPSS
# ---------------------------------------------------------------------------


_FROZEN_NOW = datetime(2026, 4, 29, 12, 0, 0)
_FROZEN_TODAY = _FROZEN_NOW.date()


class _FrozenDatetime(datetime):
    """``datetime`` subclass whose ``utcnow`` returns ``_FROZEN_NOW``.

    Used to make age-window assertions deterministic regardless of
    wall-clock time when the suite runs.
    """

    @classmethod
    def utcnow(cls) -> datetime:  # type: ignore[override]
        return _FROZEN_NOW


@pytest.fixture(autouse=True)
def reset_server_module(monkeypatch: pytest.MonkeyPatch):
    """Reset module-level cache between tests so each gets a fresh state."""
    import kev_mcp.server as srv

    today_entry = _entry("CVE-RECENT", _FROZEN_TODAY)
    yesterday_entry = _entry("CVE-1D-OLD", _FROZEN_TODAY - timedelta(days=1))
    old_entry = _entry("CVE-OLD", _FROZEN_TODAY - timedelta(days=30))

    loader = _StubLoader([[today_entry, yesterday_entry, old_entry]])
    srv.cache = KevCache(loader, ttl_seconds=60.0, clock=lambda: 0.0)  # type: ignore[arg-type]
    monkeypatch.setattr(srv, "datetime", _FrozenDatetime)
    monkeypatch.setattr(
        srv.epss_client, "lookup", _epss_lookup_stub
    )


async def _epss_lookup_stub(cve_ids):
    return {
        "CVE-RECENT": EpssScore(
            cve="CVE-RECENT", epss=0.91, percentile=0.99, date="2024-08-01"
        ),
        "CVE-1D-OLD": EpssScore(
            cve="CVE-1D-OLD", epss=0.42, percentile=0.80, date="2024-08-01"
        ),
    }


async def test_server_kev_get_recent_filters_by_window():
    from kev_mcp.server import kev_get_recent

    result = await kev_get_recent(hours=48)
    assert result["window_hours"] == 48
    cves = [r["cve_id"] for r in result["entries"]]
    assert "CVE-RECENT" in cves
    assert "CVE-1D-OLD" in cves
    assert "CVE-OLD" not in cves


async def test_server_kev_get_recent_sorts_by_epss_desc():
    from kev_mcp.server import kev_get_recent

    result = await kev_get_recent(hours=72)
    epss_scores = [r["epss"] for r in result["entries"]]
    # None always sorts to bottom; higher EPSS first.
    not_none = [e for e in epss_scores if e is not None]
    assert not_none == sorted(not_none, reverse=True)


async def test_server_kev_get_recent_rejects_non_positive_hours():
    from kev_mcp.server import kev_get_recent

    result = await kev_get_recent(hours=0)
    assert "error" in result


async def test_server_kev_lookup_hit():
    from kev_mcp.server import kev_lookup

    result = await kev_lookup("CVE-RECENT")
    assert result["cve_id"] == "CVE-RECENT"
    assert result["epss"] == pytest.approx(0.91)


async def test_server_kev_lookup_case_insensitive():
    from kev_mcp.server import kev_lookup

    result = await kev_lookup("cve-recent")
    assert result["cve_id"] == "CVE-RECENT"


async def test_server_kev_lookup_miss_returns_error_marker():
    from kev_mcp.server import kev_lookup

    result = await kev_lookup("CVE-NOT-IN-FEED")
    assert result == {"error": "not_found", "cve_id": "CVE-NOT-IN-FEED"}


async def test_server_kev_lookup_empty_input_returns_error():
    from kev_mcp.server import kev_lookup

    result = await kev_lookup("")
    assert "error" in result


async def test_server_kev_status_unloaded_then_loaded():
    import kev_mcp.server as srv

    # Reset cache to unloaded state.
    srv.cache._snapshot = None  # type: ignore[attr-defined]

    unloaded = await srv.kev_status()
    assert unloaded["loaded"] is False
    assert unloaded["entry_count"] == 0

    # Loading happens lazily on first get_entries() call.
    await srv.cache.get_entries()
    loaded = await srv.kev_status()
    assert loaded["loaded"] is True
    assert loaded["entry_count"] == 3


async def test_server_kev_get_recent_succeeds_when_epss_lookup_fails(
    monkeypatch: pytest.MonkeyPatch,
):
    """EPSS API down must not poison the KEV-only data path."""
    import kev_mcp.server as srv

    async def boom(_cves):
        raise httpx.ConnectError("epss down")

    monkeypatch.setattr(srv.epss_client, "lookup", boom)

    from kev_mcp.server import kev_get_recent
    result = await kev_get_recent(hours=72)
    assert result["count"] >= 1
    assert all(r["epss"] is None for r in result["entries"])


# ---------------------------------------------------------------------------
# 6. JSON-serializability of tool returns (MCP requires this)
# ---------------------------------------------------------------------------


async def test_tool_returns_are_json_serializable():
    from kev_mcp.server import kev_get_recent, kev_lookup, kev_status

    a = await kev_get_recent(hours=72)
    b = await kev_lookup("CVE-RECENT")
    c = await kev_status()
    for payload in (a, b, c):
        json.dumps(payload)  # raises TypeError if not serializable
