# SPDX-License-Identifier: AGPL-3.0-or-later

"""HuntOutcome value object — per-(program, operator, scan) confirmed-rate row.

Persisted to hunt_outcomes via the repository layer; consumed by the
calibration service to compute Spearman ρ between EV rank and find-rate.
"""

from __future__ import annotations

from datetime import datetime

from control_plane.core.shared import ValueObject


class HuntOutcome(ValueObject):
    """One scan_job's outcome attributed to (program_handle, operator_id).

    ev_rank is the rank of the program in the EV-ranked list at scan-start
    time (1 = top-ranked). Used by calibration_service to correlate
    predicted rank with actual find-rate (confirmed_count / submitted_count).
    """

    program_handle: str
    operator_id: str
    scan_job_id: str | None
    ev_rank: int | None
    submitted_count: int
    confirmed_count: int
    period_start: datetime | None = None
    period_end: datetime | None = None

    @property
    def find_rate(self) -> float:
        """confirmed/submitted; 0.0 when nothing was submitted."""
        if self.submitted_count <= 0:
            return 0.0
        return self.confirmed_count / self.submitted_count
