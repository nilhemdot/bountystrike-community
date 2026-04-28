"""Canonical scope record — platform-agnostic shape of a single scope row.

The integration normalizers all return this :class:`TypedDict` so the rest of
the bounded context can treat HackerOne / Bugcrowd / Intigriti / YesWeHack /
Immunefi assets uniformly.

We keep this as a ``TypedDict`` (rather than a Pydantic value object) because
the dict shape flows straight into SQLAlchemy ``INSERT … VALUES`` and into
``scope_changes.old_value`` / ``new_value`` JSONB columns without conversion.
"""

from __future__ import annotations

from typing import TypedDict


class CanonicalScope(TypedDict):
    """Canonical, platform-agnostic representation of one scope entry.

    Shape::

        {
            "program_handle":   str,
            "asset_type":       str,
            "identifier":       str,
            "in_scope":         bool,
            "exclusion_reason": str | None,
            "tags":             list[str],
        }
    """

    program_handle: str
    asset_type: str
    identifier: str
    in_scope: bool
    exclusion_reason: str | None
    tags: list[str]


__all__ = ["CanonicalScope"]
