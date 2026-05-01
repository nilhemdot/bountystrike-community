"""Tests for semantic dedup tier — embedder + tier classification + search.

Live Postgres is not exercised; ``DedupStore.semantic_search`` is mocked.
A live integration suite belongs in ``tests/integration/`` once the
1000-finding fixture lands (Phase 2 §10.4 exit criterion).
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from dedup_mcp.embedding import EMBEDDING_DIM, build_finding_text
from dedup_mcp.server import (
    SEMANTIC_DISPLAY_THRESHOLD,
    SEMANTIC_T2_THRESHOLD,
    SEMANTIC_T3_THRESHOLD,
    _check_semantic_duplicate_impl,
    _classify_tier,
    _register_embedding_impl,
)


# ---------------------------------------------------------------------------
# build_finding_text
# ---------------------------------------------------------------------------


def test_build_finding_text_full() -> None:
    text = build_finding_text("XSS in /search", "Reflected XSS via q param.", "q")
    assert "XSS in /search" in text
    assert "Reflected XSS" in text
    assert "param=q" in text


def test_build_finding_text_no_param() -> None:
    text = build_finding_text("Title", "Body", None)
    assert "param=" not in text


def test_build_finding_text_strips_whitespace() -> None:
    text = build_finding_text("  Title  ", "  Body  ", "  q  ")
    assert text == "Title\n\nBody\n\nparam=q"


def test_build_finding_text_requires_content() -> None:
    with pytest.raises(ValueError):
        build_finding_text("", "", None)


# ---------------------------------------------------------------------------
# _classify_tier
# ---------------------------------------------------------------------------


def test_classify_tier_no_match() -> None:
    assert _classify_tier(0.0) == "no_match"
    assert _classify_tier(SEMANTIC_DISPLAY_THRESHOLD - 0.01) == "no_match"


def test_classify_tier_display() -> None:
    assert _classify_tier(SEMANTIC_DISPLAY_THRESHOLD) == "display"
    assert _classify_tier(SEMANTIC_T2_THRESHOLD - 0.01) == "display"


def test_classify_tier_t2() -> None:
    assert _classify_tier(SEMANTIC_T2_THRESHOLD) == "t2"
    assert _classify_tier(SEMANTIC_T3_THRESHOLD - 0.01) == "t2"


def test_classify_tier_t3() -> None:
    assert _classify_tier(SEMANTIC_T3_THRESHOLD) == "t3"
    assert _classify_tier(0.99) == "t3"
    assert _classify_tier(1.0) == "t3"


# ---------------------------------------------------------------------------
# _check_semantic_duplicate_impl
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_store() -> AsyncMock:
    store = AsyncMock()
    return store


@pytest.fixture
def mock_embedder() -> AsyncMock:
    emb = AsyncMock()
    emb.embed.return_value = [0.1] * EMBEDDING_DIM
    return emb


async def test_check_semantic_duplicate_no_match(
    mock_store: AsyncMock, mock_embedder: AsyncMock
) -> None:
    mock_store.semantic_search.return_value = []
    result = await _check_semantic_duplicate_impl(
        mock_store, mock_embedder, "acme", "Title", "Body", "q"
    )
    assert result == {"tier": "no_match", "top_similarity": 0.0, "matches": []}


async def test_check_semantic_duplicate_display_tier(
    mock_store: AsyncMock, mock_embedder: AsyncMock
) -> None:
    mock_store.semantic_search.return_value = [
        {"finding_id": "fid1", "cwe": "xss-candidate", "similarity": 0.80}
    ]
    result = await _check_semantic_duplicate_impl(
        mock_store, mock_embedder, "acme", "Title", "Body", "q"
    )
    assert result["tier"] == "display"
    assert result["top_similarity"] == 0.80
    assert len(result["matches"]) == 1


async def test_check_semantic_duplicate_t2_tier(
    mock_store: AsyncMock, mock_embedder: AsyncMock
) -> None:
    mock_store.semantic_search.return_value = [
        {"finding_id": "fid1", "cwe": "xss-candidate", "similarity": 0.88}
    ]
    result = await _check_semantic_duplicate_impl(
        mock_store, mock_embedder, "acme", "Title", "Body", "q"
    )
    assert result["tier"] == "t2"


async def test_check_semantic_duplicate_t3_tier(
    mock_store: AsyncMock, mock_embedder: AsyncMock
) -> None:
    mock_store.semantic_search.return_value = [
        {"finding_id": "fid1", "cwe": "xss-candidate", "similarity": 0.97}
    ]
    result = await _check_semantic_duplicate_impl(
        mock_store, mock_embedder, "acme", "Title", "Body", "q"
    )
    assert result["tier"] == "t3"


async def test_check_semantic_duplicate_passes_program_handle(
    mock_store: AsyncMock, mock_embedder: AsyncMock
) -> None:
    mock_store.semantic_search.return_value = []
    await _check_semantic_duplicate_impl(
        mock_store, mock_embedder, "acme-corp", "T", "D", None
    )
    call_kwargs = mock_store.semantic_search.call_args.kwargs
    assert call_kwargs["program_handle"] == "acme-corp"


async def test_check_semantic_duplicate_uses_embedding_dim(
    mock_store: AsyncMock, mock_embedder: AsyncMock
) -> None:
    mock_store.semantic_search.return_value = []
    await _check_semantic_duplicate_impl(
        mock_store, mock_embedder, "acme", "T", "D", None
    )
    sent_embedding = mock_store.semantic_search.call_args.kwargs["embedding"]
    assert len(sent_embedding) == EMBEDDING_DIM


async def test_check_semantic_duplicate_returns_top_match_first(
    mock_store: AsyncMock, mock_embedder: AsyncMock
) -> None:
    mock_store.semantic_search.return_value = [
        {"finding_id": "f1", "cwe": "xss", "similarity": 0.92},
        {"finding_id": "f2", "cwe": "xss", "similarity": 0.78},
    ]
    result = await _check_semantic_duplicate_impl(
        mock_store, mock_embedder, "acme", "T", "D", None
    )
    assert result["tier"] == "t2"
    assert result["top_similarity"] == 0.92
    assert result["matches"][0]["finding_id"] == "f1"


# ---------------------------------------------------------------------------
# _register_embedding_impl
# ---------------------------------------------------------------------------


async def test_register_embedding_stores_vector(
    mock_store: AsyncMock, mock_embedder: AsyncMock
) -> None:
    result = await _register_embedding_impl(
        mock_store, mock_embedder, "fid-001", "Title", "Body", "q"
    )
    assert result == {"finding_id": "fid-001", "embedding_stored": True, "dim": EMBEDDING_DIM}
    mock_store.store_embedding.assert_called_once()
    call_args = mock_store.store_embedding.call_args
    assert call_args.args[0] == "fid-001"
    assert len(call_args.args[1]) == EMBEDDING_DIM


async def test_register_embedding_concatenates_text_correctly(
    mock_store: AsyncMock, mock_embedder: AsyncMock
) -> None:
    await _register_embedding_impl(
        mock_store, mock_embedder, "fid-002", "T", "D", "p"
    )
    embedded_text = mock_embedder.embed.call_args.args[0]
    assert "T" in embedded_text
    assert "D" in embedded_text
    assert "param=p" in embedded_text
