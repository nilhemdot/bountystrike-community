"""Tests for the BlobStore composition root (``make_blob_store``)."""

from __future__ import annotations

import pytest

from control_plane.domains.evidence_management.repositories import (
    LocalFsBlobStore,
    R2BlobStore,
    make_blob_store,
)


def test_default_backend_is_local(tmp_path):
    store = make_blob_store(env={"EVIDENCE_ROOT": str(tmp_path)})
    assert isinstance(store, LocalFsBlobStore)


def test_explicit_local_backend(tmp_path):
    store = make_blob_store(env={
        "EVIDENCE_BACKEND": "local",
        "EVIDENCE_ROOT": str(tmp_path),
    })
    assert isinstance(store, LocalFsBlobStore)


def test_local_backend_default_root_when_unset():
    """No EVIDENCE_ROOT → defaults to ./evidence (relative to cwd)."""
    store = make_blob_store(env={"EVIDENCE_BACKEND": "local"})
    assert isinstance(store, LocalFsBlobStore)


def test_r2_backend_with_account_id_derives_endpoint():
    store = make_blob_store(env={
        "EVIDENCE_BACKEND": "r2",
        "R2_BUCKET": "evidence",
        "R2_ACCOUNT_ID": "abc123",
        "R2_ACCESS_KEY_ID": "k",
        "R2_SECRET_ACCESS_KEY": "s",
    })
    assert isinstance(store, R2BlobStore)
    assert store._endpoint_url == "https://abc123.r2.cloudflarestorage.com"


def test_r2_backend_endpoint_url_overrides_account_id():
    store = make_blob_store(env={
        "EVIDENCE_BACKEND": "r2",
        "R2_BUCKET": "evidence",
        "R2_ACCOUNT_ID": "abc123",
        "R2_ENDPOINT_URL": "http://localhost:9000",
        "R2_ACCESS_KEY_ID": "k",
        "R2_SECRET_ACCESS_KEY": "s",
    })
    assert isinstance(store, R2BlobStore)
    assert store._endpoint_url == "http://localhost:9000"


def test_r2_backend_missing_bucket_lists_in_error():
    with pytest.raises(ValueError, match="R2_BUCKET"):
        make_blob_store(env={
            "EVIDENCE_BACKEND": "r2",
            "R2_ACCOUNT_ID": "abc",
            "R2_ACCESS_KEY_ID": "k",
            "R2_SECRET_ACCESS_KEY": "s",
        })


def test_r2_backend_missing_endpoint_and_account_id_lists_both_in_error():
    with pytest.raises(ValueError, match="R2_ACCOUNT_ID or R2_ENDPOINT_URL"):
        make_blob_store(env={
            "EVIDENCE_BACKEND": "r2",
            "R2_BUCKET": "evidence",
            "R2_ACCESS_KEY_ID": "k",
            "R2_SECRET_ACCESS_KEY": "s",
        })


def test_r2_backend_aggregates_all_missing_vars_in_one_error():
    with pytest.raises(ValueError) as excinfo:
        make_blob_store(env={"EVIDENCE_BACKEND": "r2"})
    msg = str(excinfo.value)
    for required in (
        "R2_BUCKET", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY",
        "R2_ACCOUNT_ID or R2_ENDPOINT_URL",
    ):
        assert required in msg


def test_unknown_backend_raises():
    with pytest.raises(ValueError, match="must be 'local' or 'r2'"):
        make_blob_store(env={"EVIDENCE_BACKEND": "minio"})


def test_r2_region_passed_through(monkeypatch):
    store = make_blob_store(env={
        "EVIDENCE_BACKEND": "r2",
        "R2_BUCKET": "evidence",
        "R2_ACCOUNT_ID": "abc",
        "R2_ACCESS_KEY_ID": "k",
        "R2_SECRET_ACCESS_KEY": "s",
        "R2_REGION": "wnam",
    })
    assert store._region == "wnam"
