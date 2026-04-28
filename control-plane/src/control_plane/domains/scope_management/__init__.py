"""Scope management bounded context.

Owns the lifecycle of bug-bounty *programs* and their *scopes*: ingestion from
upstream platforms (HackerOne org-assets, arkadiyt federation feed), canonical
normalization, change detection, and JWT issuance for downstream operators.

Public surface re-exports the value objects, services, events, and integration
clients that callers outside the bounded context legitimately need.
"""

from __future__ import annotations

from .events.scope_events import (
    PayoutChangedEvent,
    ProgramPausedEvent,
    ScopeAddedEvent,
    ScopeChangedEvent,
    ScopeRemovedEvent,
)
from .integrations.arkadiyt import ArkadiytClient, FederationProgram
from .integrations.hackerone import (
    H1Asset,
    H1AuthError,
    H1ClientError,
    H1RateLimitError,
    H1ServerError,
    HackerOneClient,
)
from .integrations.normalize import (
    CanonicalScope,
    normalize_bugcrowd_target,
    normalize_h1_org_asset,
    normalize_immunefi_impact,
    normalize_intigriti_scope,
    normalize_yeswehack_program,
)
from .services.ingest_service import (
    detect_scope_changes,
    ingest_arkadiyt_all,
    ingest_h1_org_assets,
)
from .services.jwt_issuer import (
    DEFAULT_EXPIRY_SECONDS,
    ISSUER,
    MAX_EXPIRY_SECONDS,
    ScopeJWTIssuer,
    ScopeJWTValidator,
)
from .value_objects.canonical_scope import CanonicalScope as CanonicalScopeVO
from .value_objects.platform import Platform
from .value_objects.targets import RateLimits, ScopeExclusions, ScopeTargets

__all__ = [
    # value objects
    "CanonicalScope",
    "CanonicalScopeVO",
    "Platform",
    "RateLimits",
    "ScopeExclusions",
    "ScopeTargets",
    # events
    "PayoutChangedEvent",
    "ProgramPausedEvent",
    "ScopeAddedEvent",
    "ScopeChangedEvent",
    "ScopeRemovedEvent",
    # services
    "DEFAULT_EXPIRY_SECONDS",
    "ISSUER",
    "MAX_EXPIRY_SECONDS",
    "ScopeJWTIssuer",
    "ScopeJWTValidator",
    "detect_scope_changes",
    "ingest_arkadiyt_all",
    "ingest_h1_org_assets",
    # integrations
    "ArkadiytClient",
    "FederationProgram",
    "H1Asset",
    "H1AuthError",
    "H1ClientError",
    "H1RateLimitError",
    "H1ServerError",
    "HackerOneClient",
    "normalize_bugcrowd_target",
    "normalize_h1_org_asset",
    "normalize_immunefi_impact",
    "normalize_intigriti_scope",
    "normalize_yeswehack_program",
]
