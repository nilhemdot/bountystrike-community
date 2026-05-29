# SPDX-License-Identifier: AGPL-3.0-or-later

"""OracleResult — uniform return type for all 8 oracles.

Per build plan §5.2: every oracle returns a verdict in
{validated, unreproducible, flaky, inconclusive} plus an evidence dict.
``evidence_management`` (Phase 1.2) is responsible for hashing,
signing, and persisting these results — the oracle is stateless.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

# Per spec the parent task asked for {validated, unreproducible, flaky}
# but build plan §5.2.3 also uses "inconclusive" (SQLi weak signal). We
# accept all four; the validator-agent maps inconclusive→flaky upstream.
Verdict = Literal["validated", "unreproducible", "flaky", "inconclusive"]


class OracleResult(BaseModel):
    """Result of a single oracle invocation.

    ``evidence`` is a free-form dict holding oracle-specific payload data
    (timing samples, OAST callback metadata, dialog message, etc.). The
    evidence-mcp service hashes and signs it downstream.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    verdict: Verdict
    oracle_method: str = Field(
        ...,
        description="Which oracle path produced the verdict, e.g. 'sqli_timing_welch'.",
    )
    evidence: dict[str, Any] = Field(default_factory=dict)
    reason: str | None = Field(
        default=None,
        description="Human-readable rationale (esp. for unreproducible / inconclusive).",
    )
