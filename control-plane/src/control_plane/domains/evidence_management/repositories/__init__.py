"""Repositories for the evidence_management bounded context."""

from __future__ import annotations

from .blob_store import LocalFsBlobStore

__all__ = ["LocalFsBlobStore"]
