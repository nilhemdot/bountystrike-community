"""Value objects for the approval-gate bounded context.

Build-plan §6.3 fixes the four tiers and their entry conditions; we
preserve those exact thresholds in :func:`classify_tier`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Literal


class ApprovalTier(StrEnum):
    """Build-plan §6.3 evidence-gate tiers, ordered by required scrutiny."""

    T0 = "T0"   # Automated — no human required
    T1 = "T1"   # Coordinator (LLM) review
    T2 = "T2"   # Single operator
    T3 = "T3"   # Two-person review

    @property
    def required_approvals(self) -> int:
        """Distinct-actor approvals required to clear the request."""
        return {
            ApprovalTier.T0: 0,   # auto-clears
            ApprovalTier.T1: 1,   # coordinator (LLM-acting-as-operator)
            ApprovalTier.T2: 1,   # one human
            ApprovalTier.T3: 2,   # two distinct humans
        }[self]

    @property
    def review_sla_seconds(self) -> int:
        """Per build-plan §6.3 timeouts."""
        return {
            ApprovalTier.T0: 0,            # immediate auto-advance
            ApprovalTier.T1: 5 * 60,       # 5 min — internal LLM
            ApprovalTier.T2: 15 * 60,      # 15 min
            ApprovalTier.T3: 30 * 60,      # 30 min
        }[self]


# Bug-class tags the classifier matches against. We keep a frozenset so
# call-sites can `bug_class in CRITICAL_CHAIN_BUG_CLASSES` without a
# string comparison loop.
CREDENTIAL_THEFT_BUG_CLASSES: frozenset[str] = frozenset({
    "credential-theft",
    "account-takeover",
    "session-hijack",
    "auth-bypass",
})

PII_BUG_CLASSES: frozenset[str] = frozenset({
    "pii-exposure",
    "info-disclosure-pii",
})

SMART_CONTRACT_CRITICAL_BUG_CLASSES: frozenset[str] = frozenset({
    "smart-contract-critical",
    "reentrancy-critical",
    "fund-drainage",
})

OracleVerdict = Literal[
    "validated", "unreproducible", "flaky", "inconclusive", "error",
]


@dataclass(frozen=True, slots=True)
class ApprovalContext:
    """Inputs the tier classifier needs to make a decision.

    All fields are required — refusing to default-value the more
    consequential signals (CVSS, hop_count, pii_record_count) forces
    the caller to gather the data; otherwise it's too easy to silently
    classify a critical finding as T0.
    """

    cvss: float
    """CVSS v4 base score (0.0 – 10.0)."""

    similarity: float
    """Max cosine similarity vs prior findings on this program (0.0 – 1.0)."""

    bug_class: str
    """e.g. "xss", "credential-theft", "smart-contract-critical"."""

    oracle_verdict: OracleVerdict
    """Final oracle verdict for the finding."""

    evidence_hash_present: bool
    """True iff content-addressable evidence artifact exists in the store."""

    sandbox_execution: bool = False
    """True iff exploit invocation requires running PoC in a microVM."""

    hop_count: int = 1
    """Length of the exploit chain in distinct steps. 3+ → novel chain."""

    pii_record_count: int = 0
    """Estimated PII rows exposed by the exploit. >10 → T3."""

    platform: str = ""
    """Originating bug-bounty platform (e.g. "hackerone", "immunefi")."""

    tags: frozenset[str] = field(default_factory=frozenset)
    """Free-form tags used to flag novel-chain semantics, etc."""


@dataclass(frozen=True, slots=True)
class ApprovalDecision:
    """One operator's vote on an :class:`ApprovalRequest`."""

    actor: str
    """Stable operator identifier — must be unique per real human."""

    approved: bool
    """True for approve, False for reject."""

    reason: str
    """Free-form note. Empty strings are not allowed by the service."""

    timestamp: float
    """``time.time()`` epoch seconds when the decision was recorded."""


__all__ = [
    "ApprovalContext",
    "ApprovalDecision",
    "ApprovalTier",
    "CREDENTIAL_THEFT_BUG_CLASSES",
    "OracleVerdict",
    "PII_BUG_CLASSES",
    "SMART_CONTRACT_CRITICAL_BUG_CLASSES",
]
