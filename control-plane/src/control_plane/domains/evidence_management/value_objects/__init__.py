# SPDX-License-Identifier: AGPL-3.0-or-later

"""Value objects for the evidence_management bounded context."""

from __future__ import annotations

from .content_hash import ContentHash
from .oracle_data import OracleData, OracleVerdict
from .r2_key import R2Key

__all__ = ["ContentHash", "OracleData", "OracleVerdict", "R2Key"]
