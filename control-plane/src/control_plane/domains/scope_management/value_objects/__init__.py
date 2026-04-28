"""Value objects for the scope_management bounded context.

All VOs are immutable (`ValueObject` = frozen Pydantic). They model the
program-handle/platform-typed scope data that flows from the ingestion services
through the JWT issuer down to operators.
"""

from __future__ import annotations

from .canonical_scope import CanonicalScope
from .platform import Platform
from .targets import RateLimits, ScopeExclusions, ScopeTargets

__all__ = [
    "CanonicalScope",
    "Platform",
    "RateLimits",
    "ScopeExclusions",
    "ScopeTargets",
]
