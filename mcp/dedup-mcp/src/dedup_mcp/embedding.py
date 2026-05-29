# SPDX-License-Identifier: AGPL-3.0-or-later

"""Embedding client for semantic dedup.

Default backend: OpenAI ``text-embedding-3-large`` (1536 dims).

The schema column is ``vector(1536)`` (infra/sql/01_schema.sql:169) — any
backend swapped in here MUST emit 1536-dim float lists or the pgvector
insert will fail.

Pluggable: ``Embedder`` protocol allows tests to inject a fake.
"""

from __future__ import annotations

import os
from typing import Protocol

import httpx

EMBEDDING_DIM = 1536
_OPENAI_URL = "https://api.openai.com/v1/embeddings"
_DEFAULT_MODEL = "text-embedding-3-large"


class Embedder(Protocol):
    async def embed(self, text: str) -> list[float]:
        """Return a 1536-dim float list for ``text``."""
        ...


class OpenAIEmbedder:
    def __init__(
        self,
        api_key: str | None = None,
        model: str = _DEFAULT_MODEL,
        timeout_s: float = 10.0,
    ) -> None:
        self._api_key = api_key or os.environ.get("OPENAI_API_KEY", "")
        if not self._api_key:
            raise RuntimeError("OPENAI_API_KEY is not set")
        self._model = model
        self._timeout_s = timeout_s

    async def embed(self, text: str) -> list[float]:
        if not text:
            raise ValueError("embed input must be non-empty")
        async with httpx.AsyncClient(timeout=self._timeout_s) as client:
            resp = await client.post(
                _OPENAI_URL,
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                json={"model": self._model, "input": text, "dimensions": EMBEDDING_DIM},
            )
            resp.raise_for_status()
            data = resp.json()
        vec = data["data"][0]["embedding"]
        if len(vec) != EMBEDDING_DIM:
            raise RuntimeError(
                f"embedding dim mismatch: got {len(vec)}, expected {EMBEDDING_DIM}"
            )
        return vec

    async def embed_many(self, texts: list[str]) -> list[list[float]]:
        """Batch-embed via OpenAI's array-input API.

        OpenAI embeddings accept up to 2048 inputs per call. Sending
        them one-by-one (as ``embed`` does) hits per-minute request
        limits at 1000+ findings; the recall fixture runner uses this
        method instead. Production ``register_embedding`` stays on the
        single-input ``embed`` path because it processes one finding
        at a time.
        """
        if not texts:
            return []
        for t in texts:
            if not t:
                raise ValueError("embed input must be non-empty")
        out: list[list[float]] = []
        # 256 keeps each request's payload + response well under the
        # 32 MB OpenAI ceiling and the SDK's typical timeouts.
        batch_size = 256
        # Use a longer timeout than the single-shot path because each
        # batched request returns up to 256 × 1536 floats.
        async with httpx.AsyncClient(timeout=max(self._timeout_s * 6, 60.0)) as client:
            for start in range(0, len(texts), batch_size):
                chunk = texts[start:start + batch_size]
                resp = await client.post(
                    _OPENAI_URL,
                    headers={
                        "Authorization": f"Bearer {self._api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": self._model,
                        "input": chunk,
                        "dimensions": EMBEDDING_DIM,
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                # OpenAI guarantees response order matches input order
                # via the per-item ``index`` field — sort defensively.
                for item in sorted(data["data"], key=lambda d: d["index"]):
                    vec = item["embedding"]
                    if len(vec) != EMBEDDING_DIM:
                        raise RuntimeError(
                            f"embedding dim mismatch: got {len(vec)}, "
                            f"expected {EMBEDDING_DIM}"
                        )
                    out.append(vec)
        return out


def build_finding_text(title: str, description: str, parameter: str | None) -> str:
    """Assemble the text the embedder sees for a finding.

    Schema (research/03-verifier-antislop.md §Semantic Dedup):
    ``title + description + affected parameter``. The parameter is
    appended as ``param=<name>`` so empty params don't bleed into the
    description.
    """
    if not title and not description:
        raise ValueError("at least one of title/description must be non-empty")
    parts = [title.strip(), description.strip()]
    if parameter:
        parts.append(f"param={parameter.strip()}")
    return "\n\n".join(p for p in parts if p)


__all__ = [
    "EMBEDDING_DIM",
    "Embedder",
    "OpenAIEmbedder",
    "build_finding_text",
]
