# SPDX-License-Identifier: AGPL-3.0-or-later

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Protocol, runtime_checkable

import aioboto3
from control_plane.domains.evidence_management.value_objects import R2Key


def _write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


@runtime_checkable
class BlobStore(Protocol):
    """Async blob-store interface for evidence artifacts.

    Implementations: ``LocalFsBlobStore`` (dev/test), ``R2BlobStore``
    (Cloudflare R2 / S3-compat).
    """

    async def put(self, r2_key: R2Key, data: bytes) -> None: ...
    async def get(self, r2_key: R2Key) -> bytes: ...
    async def exists(self, r2_key: R2Key) -> bool: ...


class LocalFsBlobStore:
    """Filesystem-backed blob store for dev/test."""

    def __init__(self, evidence_root: str | Path) -> None:
        self._root = Path(evidence_root)

    async def put(self, r2_key: R2Key, data: bytes) -> None:
        """Write ``data`` to the blob store under ``r2_key``."""
        path = r2_key.under(self._root)
        await asyncio.to_thread(_write, path, data)

    async def get(self, r2_key: R2Key) -> bytes:
        """Read and return bytes stored under ``r2_key``."""
        path = r2_key.under(self._root)
        return await asyncio.to_thread(path.read_bytes)

    async def exists(self, r2_key: R2Key) -> bool:
        """Return True if the blob exists."""
        path = r2_key.under(self._root)
        return await asyncio.to_thread(path.exists)


class R2BlobStore:
    """Cloudflare R2 (S3-compatible) blob store using ``aioboto3``.

    Cloudflare R2 implements the S3 API at
    ``https://{account_id}.r2.cloudflarestorage.com``. The constructor
    accepts an explicit ``endpoint_url`` to support both:
      * **production** — pass a Cloudflare R2 endpoint;
      * **moto tests** — pass ``None`` so boto3 uses the default AWS
        endpoint, which ``moto.mock_aws()`` intercepts.

    A fresh aioboto3 client is opened per call. That is sufficient for
    Phase 1 volume (one PUT per validated finding); a pooled long-lived
    client is a Phase 2 optimization.
    """

    def __init__(
        self,
        bucket: str,
        *,
        endpoint_url: str | None,
        access_key_id: str,
        secret_access_key: str,
        region: str = "auto",
    ) -> None:
        if not bucket:
            raise ValueError("bucket must be a non-empty string")
        self._bucket = bucket
        self._endpoint_url = endpoint_url
        self._access_key_id = access_key_id
        self._secret_access_key = secret_access_key
        self._region = region
        self._session = aioboto3.Session()

    # ------------------------------------------------------------------
    # Constructors
    # ------------------------------------------------------------------

    @classmethod
    def from_env(cls) -> R2BlobStore:
        """Build the store from environment variables.

        Required env::

            R2_BUCKET                   e.g. "bountystrike-evidence"
            R2_ACCOUNT_ID               Cloudflare account id
            R2_ACCESS_KEY_ID            R2 API token access key
            R2_SECRET_ACCESS_KEY        R2 API token secret

        Optional::

            R2_ENDPOINT_URL             Override (else derived from account id)
            R2_REGION                   Default "auto"
        """
        bucket = os.environ.get("R2_BUCKET", "")
        account_id = os.environ.get("R2_ACCOUNT_ID", "")
        endpoint_url = os.environ.get("R2_ENDPOINT_URL") or (
            f"https://{account_id}.r2.cloudflarestorage.com" if account_id else None
        )
        return cls(
            bucket=bucket,
            endpoint_url=endpoint_url,
            access_key_id=os.environ.get("R2_ACCESS_KEY_ID", ""),
            secret_access_key=os.environ.get("R2_SECRET_ACCESS_KEY", ""),
            region=os.environ.get("R2_REGION", "auto"),
        )

    # ------------------------------------------------------------------
    # Internal client lifecycle
    # ------------------------------------------------------------------

    @asynccontextmanager
    async def _client(self) -> AsyncIterator:
        """Yield an aioboto3 S3 client; closes it on exit."""
        # aioboto3.Session.client() returns an async-context-manager at runtime,
        # but its stubs do not expose __aenter__/__aexit__.
        async with self._session.client(  # pyright: ignore[reportGeneralTypeIssues]
            "s3",
            endpoint_url=self._endpoint_url,
            aws_access_key_id=self._access_key_id,
            aws_secret_access_key=self._secret_access_key,
            region_name=self._region,
        ) as client:
            yield client

    # ------------------------------------------------------------------
    # BlobStore Protocol surface
    # ------------------------------------------------------------------

    async def put(self, r2_key: R2Key, data: bytes) -> None:
        async with self._client() as client:
            await client.put_object(
                Bucket=self._bucket,
                Key=r2_key.key,
                Body=data,
            )

    async def get(self, r2_key: R2Key) -> bytes:
        async with self._client() as client:
            response = await client.get_object(Bucket=self._bucket, Key=r2_key.key)
            async with response["Body"] as stream:
                return await stream.read()

    async def exists(self, r2_key: R2Key) -> bool:
        async with self._client() as client:
            try:
                await client.head_object(Bucket=self._bucket, Key=r2_key.key)
            except client.exceptions.ClientError as exc:
                # head_object returns 404 → ClientError with Error.Code "404"
                error = (
                    exc.response.get("Error", {}) if hasattr(exc, "response") else {}
                )
                if str(error.get("Code")) in {"404", "NoSuchKey"}:
                    return False
                raise
            return True

    async def delete(self, r2_key: R2Key) -> None:
        """Delete the object at ``r2_key``. Idempotent (S3 DeleteObject semantics).

        Used by smoke / integration tests to keep buckets clean. Not part of
        the :class:`BlobStore` Protocol — production code never deletes
        evidence artifacts.
        """
        async with self._client() as client:
            await client.delete_object(Bucket=self._bucket, Key=r2_key.key)


__all__ = ["BlobStore", "LocalFsBlobStore", "R2BlobStore"]
