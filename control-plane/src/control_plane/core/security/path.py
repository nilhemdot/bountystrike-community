# SPDX-License-Identifier: AGPL-3.0-or-later

"""Path sanitization — defense against directory traversal.

Always use ``secure_path`` when an external string influences a filesystem path.
Returned path is guaranteed to live inside ``allowed_root``.
"""

from __future__ import annotations

from pathlib import Path


class PathTraversalError(ValueError):
    """Raised when a candidate path resolves outside the allowed root."""


def secure_path(candidate: str | Path, allowed_root: str | Path) -> Path:
    """Resolve ``candidate`` relative to ``allowed_root`` and verify containment.

    Symlinks ARE NOT followed by ``Path.resolve(strict=False)`` for components
    that don't exist; for evidence-store paths this is fine because we generate
    them ourselves. For paths from untrusted sources, callers should additionally
    refuse symlinked roots.
    """
    root = Path(allowed_root).resolve()
    full = (root / Path(candidate)).resolve()

    try:
        full.relative_to(root)
    except ValueError as err:
        raise PathTraversalError(
            f"path {candidate!r} resolves outside allowed root {root}"
        ) from err

    return full
