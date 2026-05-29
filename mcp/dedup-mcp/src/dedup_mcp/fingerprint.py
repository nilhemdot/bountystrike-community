# SPDX-License-Identifier: AGPL-3.0-or-later

"""Finding fingerprint — pure normalization + SHA-256."""

from __future__ import annotations

import hashlib
import re


def _normalize_host(host: str) -> str:
    host = host.lower().rstrip(".")
    host = re.sub(r":80$", "", host)
    host = re.sub(r":443$", "", host)
    return host


def _normalize_path(path: str) -> str:
    # Strip query and fragment before splitting — urlparse("//x") treats "//x" as netloc
    p = path.split("?", 1)[0].split("#", 1)[0]
    p = re.sub(r"/+", "/", p)
    return p.lower() or "/"


def compute_fingerprint(
    platform: str,
    program_handle: str,
    vuln_type: str,
    host: str,
    path: str,
) -> str:
    """Return SHA-256 hex of null-delimited normalized finding key.

    Null-byte separators prevent component-boundary collisions
    (e.g. "xss\x00/a" vs "x\x00ss/a").
    """
    parts = "\x00".join([
        platform.lower(),
        program_handle.lower(),
        vuln_type.lower(),
        _normalize_host(host),
        _normalize_path(path),
    ])
    return hashlib.sha256(parts.encode()).hexdigest()


__all__ = ["compute_fingerprint", "_normalize_host", "_normalize_path"]
