# SPDX-License-Identifier: AGPL-3.0-or-later

"""Input validation helpers — used at system boundaries.

Pydantic v2 already validates fields by type. These helpers cover the cases
not expressed easily as field types: bounded numeric ranges, regex-anchored
identifiers, deny-list scrubs.
"""

from __future__ import annotations

import re
from typing import Annotated

from pydantic import Field, StringConstraints

# Tightened identifier patterns reused across domains.
JTI_PATTERN = r"^jwt_\d+_[0-9a-f]{16}$"
PROGRAM_HANDLE_PATTERN = r"^[a-z0-9][a-z0-9_-]{1,62}[a-z0-9]$"
OPERATOR_ID_PATTERN = r"^[a-zA-Z0-9_-]{1,64}$"

JtiStr = Annotated[str, StringConstraints(pattern=JTI_PATTERN, min_length=24, max_length=128)]
ProgramHandle = Annotated[str, StringConstraints(pattern=PROGRAM_HANDLE_PATTERN)]
OperatorId = Annotated[str, StringConstraints(pattern=OPERATOR_ID_PATTERN)]

# Bounded numeric types for scoring formulas.
NormalizedScore = Annotated[float, Field(ge=0.0, le=1.0)]
PositiveDuration = Annotated[float, Field(gt=0.0)]


_DENYLIST_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"DROP\s+TABLE", re.IGNORECASE),
    re.compile(r"TRUNCATE\s+TABLE", re.IGNORECASE),
    re.compile(r"\brm\s+-rf\b"),
    re.compile(r"\bshutdown\b", re.IGNORECASE),
    re.compile(r"\breboot\b", re.IGNORECASE),
    re.compile(r"\bformat\s+[a-z]:", re.IGNORECASE),
)


def reject_destructive_payload(text: str) -> None:
    """Raise ``ValueError`` if ``text`` matches a destructive payload pattern.

    Per build plan §6.2 PRQ-3: destructive payloads (DROP/TRUNCATE/rm -rf/
    shutdown/reboot/format) are forbidden in PoC submissions.
    """
    for pattern in _DENYLIST_PATTERNS:
        if pattern.search(text):
            raise ValueError(
                f"destructive payload pattern detected: {pattern.pattern!r}"
            )
