"""Typed oracle-data payload — populated by the verifier per oracle method.

Replaces the loosely-typed ``oracle_data: dict`` in the build-plan dataclass
with an explicit value object. The original ``oracle_data`` JSONB column on
``evidence_artifacts`` is populated by serialising this VO via
``model_dump(mode='json')``.
"""

from __future__ import annotations

from typing import Any, ClassVar, Literal

from control_plane.core.shared import ValueObject
from pydantic import ConfigDict, Field

OracleVerdict = Literal["validated", "unreproducible", "flaky"]


class OracleData(ValueObject):
    """Verifier-emitted oracle payload.

    Fields
    ------
    verdict
        One of ``validated`` / ``unreproducible`` / ``flaky`` (build plan §3.2,
        anti-slop verifier verdicts).
    oracle_method
        Identifier of the oracle that produced the verdict (e.g.
        ``ssrf-oast``, ``sqli-timing``, ``xss-playwright``).
    oast_callback
        Out-of-band callback metadata captured by Interactsh / Collaborator.
        Typed as a free-form dict because per-oracle shapes diverge.
    attempts
        Number of independent reruns the verifier performed.
    cleanup_confirmed
        ``True`` when post-PoC cleanup (kill processes, drop temp data) was
        observed; gates submission per PRQ-1.
    validator_model
        The model id used by the validator agent (intentionally distinct from
        the exploit-agent model; build plan §3.1).
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    verdict: OracleVerdict
    oracle_method: str = Field(min_length=1, max_length=64)
    oast_callback: dict[str, Any] = Field(default_factory=dict)
    attempts: int = Field(ge=1, le=64)
    cleanup_confirmed: bool
    validator_model: str = Field(min_length=1, max_length=128)


__all__ = ["OracleData", "OracleVerdict"]
