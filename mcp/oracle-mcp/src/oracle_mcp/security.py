"""Defense-in-depth: reject destructive payloads before they hit any target.

Mirrors ``control_plane.core.security.reject_destructive_payload``. The
oracle service is independent of the control-plane workspace package, so
we keep this guard local rather than introducing a heavy dependency.

Build plan §6.2 PRQ-3: destructive payloads (DROP/TRUNCATE/rm -rf/
shutdown/reboot/format) MUST NOT be submitted to bug-bounty programs.
Even though oracles run inside scope-gated sandbox VMs, the guard at
the oracle entry point is a belt-and-braces measure.
"""

from __future__ import annotations

import re

_DENYLIST_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"DROP\s+TABLE", re.IGNORECASE),
    re.compile(r"TRUNCATE\s+TABLE", re.IGNORECASE),
    re.compile(r"\brm\s+-rf\b"),
    re.compile(r"\bshutdown\b", re.IGNORECASE),
    re.compile(r"\breboot\b", re.IGNORECASE),
    re.compile(r"\bformat\s+[a-z]:", re.IGNORECASE),
    re.compile(r":(){\s*:\|:&\s*};:"),  # fork bomb
    re.compile(r"mkfs\.[a-z0-9]+", re.IGNORECASE),
    re.compile(r"dd\s+if=/dev/(zero|random|urandom)", re.IGNORECASE),
)


class DestructivePayloadError(ValueError):
    """Raised when a payload matches a denylist pattern."""


def reject_destructive_payload(text: str | None) -> None:
    """Raise ``DestructivePayloadError`` if ``text`` is a destructive payload.

    Args:
        text: payload string about to be sent to the target. ``None`` is a no-op.
    """
    if not text:
        return
    for pattern in _DENYLIST_PATTERNS:
        if pattern.search(text):
            raise DestructivePayloadError(
                f"destructive payload pattern detected: {pattern.pattern!r}"
            )
