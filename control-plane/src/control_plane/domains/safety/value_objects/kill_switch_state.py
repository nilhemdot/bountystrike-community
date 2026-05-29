# SPDX-License-Identifier: AGPL-3.0-or-later

"""Kill switch state enum.

Build-plan §6.6 escalating tiers (T1 → T3):

  - **inactive**          ─ business as usual
  - **halt_submissions**  ─ T1: block all `mcp__*__submit_*` tool calls;
                            scans + validation continue
  - **halt_scans**        ─ T2: block network-touching tool calls
                            (subfinder/httpx/katana/nuclei/curl/etc.);
                            no new outbound traffic; submissions also
                            halted (T1 is implied by T2)
  - **halt_all**          ─ T3: block every tool call; supervisor sends
                            SIGTERM; sessions terminate cleanly
"""

from __future__ import annotations

from enum import StrEnum


class KillSwitchState(StrEnum):
    """Kill switch tiers, ordered by severity."""

    INACTIVE = "inactive"
    HALT_SUBMISSIONS = "halt_submissions"   # T1
    HALT_SCANS = "halt_scans"               # T2 (implies T1)
    HALT_ALL = "halt_all"                   # T3 (implies T2 + T1)

    @property
    def blocks_submissions(self) -> bool:
        return self in {
            KillSwitchState.HALT_SUBMISSIONS,
            KillSwitchState.HALT_SCANS,
            KillSwitchState.HALT_ALL,
        }

    @property
    def blocks_scans(self) -> bool:
        return self in {
            KillSwitchState.HALT_SCANS,
            KillSwitchState.HALT_ALL,
        }

    @property
    def blocks_all(self) -> bool:
        return self == KillSwitchState.HALT_ALL


__all__ = ["KillSwitchState"]
