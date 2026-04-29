"""Tests for dedup-mcp — fingerprint + server logic (no live Postgres)."""

from __future__ import annotations

import hashlib
from unittest.mock import AsyncMock

import pytest

from dedup_mcp.fingerprint import _normalize_host, _normalize_path, compute_fingerprint
from dedup_mcp.server import _check_duplicate_impl, _register_finding_impl


# ---------------------------------------------------------------------------
# _normalize_host
# ---------------------------------------------------------------------------


def test_normalize_host_lowercase() -> None:
    assert _normalize_host("EXAMPLE.COM") == "example.com"


def test_normalize_host_strips_trailing_dot() -> None:
    assert _normalize_host("example.com.") == "example.com"


def test_normalize_host_strips_port_80() -> None:
    assert _normalize_host("example.com:80") == "example.com"


def test_normalize_host_strips_port_443() -> None:
    assert _normalize_host("example.com:443") == "example.com"


def test_normalize_host_keeps_nonstandard_port() -> None:
    assert _normalize_host("example.com:8443") == "example.com:8443"


# ---------------------------------------------------------------------------
# _normalize_path
# ---------------------------------------------------------------------------


def test_normalize_path_strips_query() -> None:
    assert _normalize_path("/api/v1/users?debug=1") == "/api/v1/users"


def test_normalize_path_strips_fragment() -> None:
    assert _normalize_path("/page#section") == "/page"


def test_normalize_path_collapses_slashes() -> None:
    assert _normalize_path("//api//v1") == "/api/v1"


def test_normalize_path_lowercase() -> None:
    assert _normalize_path("/API/V1") == "/api/v1"


def test_normalize_path_empty_returns_slash() -> None:
    assert _normalize_path("") == "/"


def test_normalize_path_query_only_returns_slash() -> None:
    assert _normalize_path("?foo=bar") == "/"


# ---------------------------------------------------------------------------
# compute_fingerprint
# ---------------------------------------------------------------------------


def test_fingerprint_is_64_char_hex() -> None:
    fp = compute_fingerprint("hackerone", "acme", "xss", "example.com", "/search")
    assert len(fp) == 64
    assert all(c in "0123456789abcdef" for c in fp)


def test_fingerprint_deterministic() -> None:
    fp1 = compute_fingerprint("hackerone", "acme", "xss", "example.com", "/search")
    fp2 = compute_fingerprint("hackerone", "acme", "xss", "example.com", "/search")
    assert fp1 == fp2


def test_fingerprint_normalizes_port_443() -> None:
    fp_plain = compute_fingerprint("h1", "p", "xss", "example.com", "/x")
    fp_port = compute_fingerprint("h1", "p", "xss", "example.com:443", "/x")
    assert fp_plain == fp_port


def test_fingerprint_normalizes_query_string() -> None:
    fp_clean = compute_fingerprint("h1", "p", "xss", "example.com", "/search")
    fp_dirty = compute_fingerprint("h1", "p", "xss", "example.com", "/search?q=ignored")
    assert fp_clean == fp_dirty


def test_fingerprint_different_vuln_types_differ() -> None:
    fp_xss = compute_fingerprint("h1", "p", "xss", "example.com", "/search")
    fp_sqli = compute_fingerprint("h1", "p", "sqli", "example.com", "/search")
    assert fp_xss != fp_sqli


def test_fingerprint_different_paths_differ() -> None:
    fp_a = compute_fingerprint("h1", "p", "xss", "example.com", "/a")
    fp_b = compute_fingerprint("h1", "p", "xss", "example.com", "/b")
    assert fp_a != fp_b


def test_fingerprint_null_separator_prevents_collision() -> None:
    # "xss" + "/a" vs "x" + "ss/a" would collide without null separators
    fp1 = compute_fingerprint("h1", "p", "xss", "host", "/a")
    fp2 = compute_fingerprint("h1", "p", "x", "ss/a", "host")
    assert fp1 != fp2


# ---------------------------------------------------------------------------
# _check_duplicate_impl (mock store)
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_store() -> AsyncMock:
    return AsyncMock()


async def test_check_duplicate_not_dup(mock_store: AsyncMock) -> None:
    mock_store.lookup.return_value = None
    result = await _check_duplicate_impl(
        mock_store, "hackerone", "acme", "xss", "example.com", "/search"
    )
    assert result["is_dup"] is False
    assert len(result["fingerprint_hex"]) == 64
    assert "finding_id" not in result


async def test_check_duplicate_is_dup(mock_store: AsyncMock) -> None:
    mock_store.lookup.return_value = {
        "finding_id": "abc-123",
        "first_seen_at": "2026-04-28T00:00:00+00:00",
    }
    result = await _check_duplicate_impl(
        mock_store, "hackerone", "acme", "xss", "example.com", "/search"
    )
    assert result["is_dup"] is True
    assert result["finding_id"] == "abc-123"
    assert result["first_seen_at"] == "2026-04-28T00:00:00+00:00"


async def test_check_duplicate_fingerprint_matches_compute(mock_store: AsyncMock) -> None:
    mock_store.lookup.return_value = None
    expected_fp = compute_fingerprint("hackerone", "acme", "xss", "example.com", "/search")
    result = await _check_duplicate_impl(
        mock_store, "hackerone", "acme", "xss", "example.com", "/search"
    )
    assert result["fingerprint_hex"] == expected_fp
    mock_store.lookup.assert_called_once_with(expected_fp)


# ---------------------------------------------------------------------------
# _register_finding_impl (mock store)
# ---------------------------------------------------------------------------


async def test_register_finding_new(mock_store: AsyncMock) -> None:
    mock_store.register.return_value = {
        "registered": True,
        "finding_id": "fid-001",
        "first_seen_at": "2026-04-29T00:00:00+00:00",
    }
    result = await _register_finding_impl(
        mock_store, "hackerone", "acme", "xss", "example.com", "/search", "fid-001"
    )
    assert result["registered"] is True
    assert result["finding_id"] == "fid-001"
    assert len(result["fingerprint_hex"]) == 64


async def test_register_finding_duplicate_returns_original(mock_store: AsyncMock) -> None:
    mock_store.register.return_value = {
        "registered": False,
        "finding_id": "original-fid",
        "first_seen_at": "2026-04-28T00:00:00+00:00",
    }
    result = await _register_finding_impl(
        mock_store, "hackerone", "acme", "xss", "example.com", "/search", "new-fid"
    )
    assert result["registered"] is False
    assert result["finding_id"] == "original-fid"


async def test_register_finding_passes_correct_fingerprint(mock_store: AsyncMock) -> None:
    mock_store.register.return_value = {
        "registered": True,
        "finding_id": "fid-999",
        "first_seen_at": "2026-04-29T00:00:00+00:00",
    }
    expected_fp = compute_fingerprint("h1", "prog", "sqli", "api.example.com", "/users")
    await _register_finding_impl(
        mock_store, "h1", "prog", "sqli", "api.example.com", "/users", "fid-999"
    )
    mock_store.register.assert_called_once_with(
        expected_fp, "h1", "prog", "sqli", "fid-999"
    )
