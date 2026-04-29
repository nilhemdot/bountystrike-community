"""Content-addressable hash value object — SHA-256 over evidence bytes.

The hash is the canonical *content address* for blob-store keys (R2/SeaweedFS)
and for the ``evidence_artifacts.content_hash`` column. Storage refs use the
``sha256:{hex}`` format so future migrations to other algorithms remain
non-ambiguous.
"""

from __future__ import annotations

import hashlib
import re
from typing import ClassVar, Self

from pydantic import ConfigDict, Field

from control_plane.core.shared import ValueObject

_HEX_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_STORAGE_REF_PATTERN = re.compile(r"^sha256:([0-9a-f]{64})$")
_PREFIX_LEN = 12


class ContentHash(ValueObject):
    """Immutable SHA-256 digest of evidence bytes.

    Stored as the lowercase 64-char hex string. Use :meth:`from_bytes` or
    :meth:`from_parts` to construct; :attr:`storage_ref` formats it as
    ``sha256:{hex}`` for blob-key composition.
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    hex: str = Field(pattern=_HEX_PATTERN.pattern, min_length=64, max_length=64)

    @classmethod
    def from_bytes(cls, data: bytes) -> Self:
        """Compute SHA-256 over ``data`` and wrap as a :class:`ContentHash`."""
        digest = hashlib.sha256(data).hexdigest()
        return cls(hex=digest)

    @classmethod
    def from_parts(cls, *parts: bytes) -> Self:
        """Compute SHA-256 over the concatenation of ``parts``.

        Caller is responsible for inserting any inter-part separators it cares
        about (the function does NOT add separators); this keeps the digest
        deterministic for upstream callers like
        :meth:`EvidenceArtifact.create`.
        """
        hasher = hashlib.sha256()
        for part in parts:
            hasher.update(part)
        return cls(hex=hasher.hexdigest())

    @classmethod
    def from_storage_ref(cls, ref: str) -> Self:
        """Parse ``sha256:{hex}`` storage refs back into a :class:`ContentHash`."""
        match = _STORAGE_REF_PATTERN.match(ref)
        if match is None:
            raise ValueError(f"invalid storage ref: {ref!r}")
        return cls(hex=match.group(1))

    @property
    def prefix(self) -> str:
        """First 12 hex chars — short, log-friendly identifier."""
        return self.hex[:_PREFIX_LEN]

    @property
    def storage_ref(self) -> str:
        """Canonical storage reference: ``sha256:{hex}``."""
        return f"sha256:{self.hex}"

    @property
    def raw(self) -> bytes:
        """Raw 32-byte digest (for ``BYTEA`` columns / hash-chain math)."""
        return bytes.fromhex(self.hex)

    def __str__(self) -> str:  # pragma: no cover — trivial
        return self.storage_ref


__all__ = ["ContentHash"]
