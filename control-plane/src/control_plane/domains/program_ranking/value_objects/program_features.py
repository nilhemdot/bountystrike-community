"""ProgramFeatures value object — materialized program signals consumed by score_program()."""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from control_plane.core.shared import ValueObject


class ProgramFeatures(ValueObject):
    """Materialized program signals consumed by score_program().

    Frozen value object: a snapshot of program signals at scoring time.
    """

    handle: str
    platform: str
    payout_min: float = 0.0
    payout_max: float = 0.0
    bounty_paid_ratio: float = 0.0
    triage_acceptance_rate: float = 0.0
    dup_rate: float = 0.0
    last_modified_at: datetime | None = None
    asset_distribution: dict[str, int] = Field(default_factory=dict)
