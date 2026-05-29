# SPDX-License-Identifier: AGPL-3.0-or-later

"""OperatorProfile value object — operator skill + budget profile feeding f_fit."""

from __future__ import annotations

from pydantic import Field

from control_plane.core.shared import ValueObject


class OperatorProfile(ValueObject):
    """Operator skill + budget profile feeding f_fit.

    Frozen value object — equality by value, hashable. Pydantic v2 validates
    fields on construction.
    """

    skill_vector: dict[str, float] = Field(default_factory=dict)
    time_budget_hours: float = 40.0
    cost_budget_usd: float = 50.0
    asset_type_pref: dict[str, float] = Field(default_factory=dict)
