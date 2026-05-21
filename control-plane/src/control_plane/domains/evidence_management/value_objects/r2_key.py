"""R2 / blob-store key value object.

Per build plan §5.3 the canonical evidence key is::

    {platform}/{program}/{finding_id}/{sha256_hex}

This module:

* Validates each component (no path separators, no leading dots, ASCII only).
* Sanitises the assembled key against ``core.security.secure_path`` whenever
  the LocalFsBlobStore mounts the key under an ``evidence_root`` directory —
  this is the defence-in-depth line against directory traversal even though
  every component is already validated.
"""

from __future__ import annotations

import re
import uuid
from pathlib import Path
from typing import ClassVar, Self

from control_plane.core.security import ProgramHandle, secure_path
from control_plane.core.shared import ValueObject
from pydantic import ConfigDict, Field

from .content_hash import ContentHash

# `platform` is a low-cardinality slug (e.g. "hackerone", "bugcrowd").
_PLATFORM_PATTERN = re.compile(r"^[a-z][a-z0-9_-]{1,31}$")
# Matches Pydantic `ProgramHandle`'s constraint — duplicated locally because
# Pydantic-constrained types don't accept compile-time `re.compile`.
_HANDLE_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{1,62}[a-z0-9]$")


class R2Key(ValueObject):
    """Immutable blob-store key.

    Construct via :meth:`compute`; the resulting :attr:`key` is always
    ``{platform}/{program}/{finding_id}/{sha256_hex}`` with each component
    sanity-checked.
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    platform: str = Field(pattern=_PLATFORM_PATTERN.pattern, min_length=2, max_length=32)
    program: str = Field(pattern=_HANDLE_PATTERN.pattern, min_length=3, max_length=64)
    finding_id: str
    sha256_hex: str = Field(pattern=r"^[0-9a-f]{64}$", min_length=64, max_length=64)

    @classmethod
    def compute(
        cls,
        platform: str,
        program_handle: ProgramHandle,
        finding_id: uuid.UUID,
        content_hash: ContentHash,
    ) -> Self:
        """Build the canonical ``{platform}/{program}/{finding_id}/{hex}`` key."""
        # `ProgramHandle` is `Annotated[str, ...]`; stringification matches the
        # pattern guarantees made by core.security.validation.
        return cls(
            platform=platform.lower(),
            program=str(program_handle),
            finding_id=str(finding_id),
            sha256_hex=content_hash.hex,
        )

    @property
    def key(self) -> str:
        """The flat string blob-store key."""
        return f"{self.platform}/{self.program}/{self.finding_id}/{self.sha256_hex}"

    def under(self, evidence_root: str | Path) -> Path:
        """Resolve this key as a sanitized filesystem path under ``evidence_root``.

        Used by :class:`~..repositories.blob_store.LocalFsBlobStore`. Raises
        :class:`PathTraversalError` if the assembled path resolves outside the
        allowed root.
        """
        return secure_path(self.key, evidence_root)

    def __str__(self) -> str:  # pragma: no cover — trivial
        return self.key


__all__ = ["R2Key"]
