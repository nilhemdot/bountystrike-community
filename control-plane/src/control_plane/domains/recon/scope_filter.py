"""Scope-aware allow/deny filter parsed from a scope JWT's claims.

The filter is the single authority on whether a host or URL path may be
touched during recon. Every external call in :mod:`tool_runner` and
:mod:`service` consults it, so a malformed claim or out-of-scope target
can never leak into the toolchain.
"""

from __future__ import annotations

import re
from typing import Any, ClassVar
from urllib.parse import urlparse

from pydantic import ConfigDict, Field

from control_plane.core.shared import ValueObject


def _wildcard_to_regex(wildcard: str) -> str:
    """Translate ``*.example.com`` → anchored regex matching that suffix.

    Plain hostnames (no leading ``*.``) are matched exactly. Both the bare
    apex (``example.com``) and any subdomain are accepted for ``*.example.com``,
    matching the standard bounty-program scope semantics.
    """
    wc = wildcard.strip().lower()
    if wc.startswith("*."):
        apex = re.escape(wc[2:])
        return rf"^([a-z0-9_-]+\.)*{apex}$"
    return rf"^{re.escape(wc)}$"


class ScopeFilter(ValueObject):
    """Allow/deny filter built from a scope JWT's ``targets``/``exclusions``.

    Construct via :meth:`from_jwt_claims`; instances are immutable and
    safe to share across coroutines.
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    wildcards: tuple[str, ...] = Field(default_factory=tuple)
    exact_hosts: tuple[str, ...] = Field(default_factory=tuple)
    exclusion_hosts: tuple[str, ...] = Field(default_factory=tuple)
    exclusion_paths: tuple[str, ...] = Field(default_factory=tuple)
    default_rps: int = 5
    relaxed_hosts: dict[str, int] = Field(default_factory=dict)

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    @classmethod
    def from_jwt_claims(cls, claims: dict[str, Any]) -> ScopeFilter:
        """Build a filter from a validated scope JWT payload."""
        targets = claims.get("targets") or {}
        exclusions = claims.get("exclusions") or {}
        rate_limits = claims.get("rate_limits") or {}
        return cls(
            wildcards=tuple(targets.get("wildcards") or ()),
            exact_hosts=tuple(targets.get("exact_hosts") or ()),
            exclusion_hosts=tuple(exclusions.get("hostnames") or ()),
            exclusion_paths=tuple(exclusions.get("paths") or ()),
            default_rps=int(rate_limits.get("default_rps") or 5),
            relaxed_hosts=dict(rate_limits.get("relaxed_hosts") or {}),
        )

    # ------------------------------------------------------------------
    # Allow/deny
    # ------------------------------------------------------------------

    def allows_host(self, host: str) -> bool:
        """Return True iff *host* is in scope and not excluded."""
        h = host.strip().lower()
        if not h or h in {e.lower() for e in self.exclusion_hosts}:
            return False
        if h in {x.lower() for x in self.exact_hosts}:
            return True
        return any(re.match(_wildcard_to_regex(w), h) for w in self.wildcards)

    def allows_path(self, path: str) -> bool:
        """Return True iff *path* does not match any exclusion prefix."""
        p = path or "/"
        return not any(p.startswith(prefix) for prefix in self.exclusion_paths)

    def allows_url(self, url: str) -> bool:
        """Convenience: allow iff host AND path both pass."""
        parsed = urlparse(url)
        if not parsed.hostname:
            return False
        return self.allows_host(parsed.hostname) and self.allows_path(parsed.path or "/")

    # ------------------------------------------------------------------
    # Tool-config helpers
    # ------------------------------------------------------------------

    def rps_for_host(self, host: str) -> int:
        """Per-host RPS override falls back to ``default_rps``."""
        return int(self.relaxed_hosts.get(host.lower(), self.default_rps))

    def katana_scope_regex(self) -> str:
        """Combined regex string passed to ``katana -scope`` to keep the
        crawler inside the JWT's allowed surface.

        Empty regex is returned only when the filter has zero allowed
        hosts; callers must treat that as a fatal error rather than
        passing an empty regex to katana (which would crawl the world).
        """
        parts = [_wildcard_to_regex(w) for w in self.wildcards]
        parts.extend(rf"^{re.escape(h.lower())}$" for h in self.exact_hosts)
        # katana wants a single regex; OR-join via alternation.
        return "|".join(p.lstrip("^").rstrip("$") for p in parts) if parts else ""

    def domains_for_subfinder(self) -> list[str]:
        """Apex domains to feed to ``subfinder -d`` (one per wildcard)."""
        return [w.removeprefix("*.").lower() for w in self.wildcards]


__all__ = ["ScopeFilter"]
