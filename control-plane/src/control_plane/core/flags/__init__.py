"""Feature-flag primitives for BountyStrike control plane.

Built on the OpenFeature SDK with a custom Unleash provider (no official
OpenFeature -> Unleash Python provider exists; see Unleash/unleash#3912 and
docs/learnings/feature-flags.md). Solo/CI use an in-memory provider (no network).

SECURITY — READ THIS:
    `tier-enterprise` (and any tier flag) is a ROLLOUT / CONFIG GATE, NOT an
    AUTHORIZATION BOUNDARY. Entitlement MUST be enforced server-side against the
    tenant's signed plan / JWT. NEVER treat `is_enabled("tier-enterprise")` as the
    authorization check — doing so is a privilege-escalation vector. The flag
    decides rollout; the signed plan decides entitlement.

    Evaluation context is UNTRUSTED input. Tier decisions must not key off
    caller-supplied context fields as the trust source.

    Community/solo in-memory defaults ship `tier-enterprise=False`. Setting an
    in-memory enterprise flag to True is dev-only.

All flag lookups FAIL CLOSED: on any error or malformed provider response,
`is_enabled` returns the supplied default (False for tier gates) and never raises.
"""

from control_plane.core.flags.client import configure_flags, get_client, is_enabled
from control_plane.core.flags.provider import UnleashProvider

__all__ = ["configure_flags", "get_client", "is_enabled", "UnleashProvider"]
