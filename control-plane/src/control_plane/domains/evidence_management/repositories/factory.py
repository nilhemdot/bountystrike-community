# SPDX-License-Identifier: AGPL-3.0-or-later

"""BlobStore composition root.

Picks a concrete :class:`BlobStore` implementation from environment
variables. Call :func:`make_blob_store` once at application startup and
inject the result into anything that records evidence artifacts.

Env contract::

    EVIDENCE_BACKEND     "local" (default) | "r2"
    EVIDENCE_ROOT        local-only: directory for the LocalFsBlobStore
                         (default: ./evidence)
    R2_BUCKET            r2-only: R2 bucket name
    R2_ACCOUNT_ID        r2-only: Cloudflare account id (used to derive
                         the endpoint when R2_ENDPOINT_URL is unset)
    R2_ACCESS_KEY_ID     r2-only
    R2_SECRET_ACCESS_KEY r2-only
    R2_ENDPOINT_URL      r2-only optional override
    R2_REGION            r2-only optional, default "auto"
"""

from __future__ import annotations

import os

from .blob_store import BlobStore, LocalFsBlobStore, R2BlobStore


def make_blob_store(env: dict[str, str] | None = None) -> BlobStore:
    """Return the concrete blob store selected by ``EVIDENCE_BACKEND``.

    Args:
        env: Optional env mapping (defaults to ``os.environ``). Tests
            should pass an explicit dict so monkey-patching ``os.environ``
            is unnecessary.

    Raises:
        ValueError: when ``EVIDENCE_BACKEND`` is unset to an unknown
            value, or required R2 vars are missing in ``r2`` mode.
    """
    e = dict(env if env is not None else os.environ)
    backend = (e.get("EVIDENCE_BACKEND") or "local").strip().lower()

    if backend == "local":
        root = e.get("EVIDENCE_ROOT") or "./evidence"
        return LocalFsBlobStore(root)

    if backend == "r2":
        bucket = e.get("R2_BUCKET", "")
        access_key_id = e.get("R2_ACCESS_KEY_ID", "")
        secret_access_key = e.get("R2_SECRET_ACCESS_KEY", "")
        account_id = e.get("R2_ACCOUNT_ID", "")
        endpoint_url = e.get("R2_ENDPOINT_URL") or (
            f"https://{account_id}.r2.cloudflarestorage.com" if account_id else None
        )
        missing = [
            name for name, value in (
                ("R2_BUCKET", bucket),
                ("R2_ACCESS_KEY_ID", access_key_id),
                ("R2_SECRET_ACCESS_KEY", secret_access_key),
            ) if not value
        ]
        # Either R2_ACCOUNT_ID or R2_ENDPOINT_URL is required, not both.
        if not endpoint_url:
            missing.append("R2_ACCOUNT_ID or R2_ENDPOINT_URL")
        if missing:
            raise ValueError(
                f"EVIDENCE_BACKEND=r2 requires {', '.join(missing)}"
            )
        return R2BlobStore(
            bucket=bucket,
            endpoint_url=endpoint_url,
            access_key_id=access_key_id,
            secret_access_key=secret_access_key,
            region=e.get("R2_REGION", "auto"),
        )

    raise ValueError(
        f"EVIDENCE_BACKEND must be 'local' or 'r2', got {backend!r}"
    )


__all__ = ["make_blob_store"]
