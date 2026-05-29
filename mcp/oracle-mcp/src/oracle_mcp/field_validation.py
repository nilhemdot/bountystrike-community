# SPDX-License-Identifier: AGPL-3.0-or-later

"""Phase 1 field-validation runner for the deterministic oracles.

Loads a fixture file describing N (URL, parameter, expected_verdict) tuples,
dispatches each entry to the matching oracle, and emits a TPR/FPR report.
The runner is shared by Phase 1 exit criteria #1 (XSS — 0 FP, >90% TPR on
20 targets) and #3 (SSRF — interactsh callback on 5 endpoints), and is
trivially extensible to the other 6 oracles.

Fixture format (JSON, list of dicts)::

    [
      {
        "oracle":           "xss",                                # oracle key
        "url":              "http://target.example/search?q=1",
        "param":            "q",
        "expected_verdict": "validated",                          # or "unreproducible"
        "label":            "juice-shop XSS-1",                   # optional, free-form
        "tags":             ["reflected", "html-context"]         # optional
      }
      , ...
    ]

Run-time semantics:

* ``expected_verdict == "validated"``  → must come back "validated" to count
  as a true positive.
* ``expected_verdict == "unreproducible"`` → anything other than "validated"
  counts as a true negative; "validated" counts as a false positive.

The runner deliberately treats ``flaky`` / ``inconclusive`` / ``error`` as
**not validated** in the negative sense, because Phase 1's exit gate is
"never falsely claim a vulnerability". Callers wanting finer-grained
buckets can inspect :attr:`ValidationResult.actual_verdict` directly.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal

from oracle_mcp.result import OracleResult

ExpectedVerdict = Literal["validated", "unreproducible"]
SUPPORTED_ORACLES = (
    "xss", "sqli", "ssrf", "ssrf_imds", "idor", "rce", "ssti", "open_redirect",
)


# ---------------------------------------------------------------------------
# Fixture types
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class FixtureTarget:
    """One row of a field-validation fixture."""

    oracle: str
    url: str
    param: str
    expected_verdict: ExpectedVerdict
    label: str = ""
    tags: tuple[str, ...] = ()

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> FixtureTarget:
        oracle = str(raw.get("oracle") or "").strip().lower()
        if oracle not in SUPPORTED_ORACLES:
            raise ValueError(
                f"fixture row uses unknown oracle {oracle!r}; "
                f"supported = {SUPPORTED_ORACLES}"
            )
        url = str(raw.get("url") or "")
        param = str(raw.get("param") or "")
        if not url or not param:
            raise ValueError("fixture row missing url/param")
        expected = str(raw.get("expected_verdict") or "").lower()
        if expected not in ("validated", "unreproducible"):
            raise ValueError(
                f"expected_verdict must be 'validated' or 'unreproducible', "
                f"got {expected!r}"
            )
        return cls(
            oracle=oracle,
            url=url,
            param=param,
            expected_verdict=expected,  # type: ignore[arg-type]
            label=str(raw.get("label") or ""),
            tags=tuple(str(t) for t in (raw.get("tags") or ())),
        )


def load_fixtures(path: Path | str) -> list[FixtureTarget]:
    """Load + validate a fixture JSON file. Raises on malformed entries."""
    with Path(path).open("r", encoding="utf-8") as f:
        raw = json.load(f)
    if not isinstance(raw, list):
        raise ValueError(f"fixture file must contain a JSON array; got {type(raw).__name__}")
    return [FixtureTarget.from_dict(row) for row in raw]


# ---------------------------------------------------------------------------
# Result + report types
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ValidationResult:
    """Per-target outcome — what the oracle returned vs what was expected."""

    target: FixtureTarget
    actual_verdict: str       # "validated" | "unreproducible" | "flaky" | "inconclusive" | "error"
    correct: bool
    error: str = ""           # populated when actual_verdict == "error"
    evidence: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ValidationReport:
    """Aggregate metrics across all fixture rows."""

    oracle: str
    total: int
    true_positives: int
    false_positives: int
    true_negatives: int
    false_negatives: int
    tpr: float
    fpr: float
    results: tuple[ValidationResult, ...]

    def passes_exit_criterion(
        self,
        *,
        min_tpr: float = 0.90,
        max_fpr: float = 0.0,
    ) -> bool:
        """Phase 1 sign-off gate: TPR ≥ min_tpr AND FPR ≤ max_fpr."""
        return self.tpr >= min_tpr and self.fpr <= max_fpr

    def to_dict(self) -> dict[str, Any]:
        """JSON-serializable snapshot suitable for committing under tests/reports/."""
        return {
            "oracle": self.oracle,
            "total": self.total,
            "true_positives": self.true_positives,
            "false_positives": self.false_positives,
            "true_negatives": self.true_negatives,
            "false_negatives": self.false_negatives,
            "tpr": self.tpr,
            "fpr": self.fpr,
            "results": [
                {
                    "target": asdict(r.target),
                    "actual_verdict": r.actual_verdict,
                    "correct": r.correct,
                    "error": r.error,
                    "evidence": r.evidence,
                }
                for r in self.results
            ],
        }


# ---------------------------------------------------------------------------
# Oracle dispatch
# ---------------------------------------------------------------------------


async def _dispatch_oracle(target: FixtureTarget) -> OracleResult:
    """Invoke the oracle named in ``target.oracle`` against (url, param).

    Imports are deferred so this module loads even when an oracle's
    optional dependencies (e.g. Playwright for XSS) are absent in the
    runtime environment. Test code can monkey-patch this function.
    """
    if target.oracle == "xss":
        from oracle_mcp.oracles.xss import oracle_xss
        return await oracle_xss(target.url, target.param)
    if target.oracle == "sqli":
        from oracle_mcp.oracles.sqli import oracle_sqli
        # Determine payload type from target tags
        payload_type = "postgres" if "postgres" in target.tags else "mysql"
        return await oracle_sqli(target.url, target.param, payload_type=payload_type)
    if target.oracle == "ssrf":
        from oracle_mcp.oracles.ssrf import oracle_ssrf
        return await oracle_ssrf(target.url, target.param)
    if target.oracle == "ssrf_imds":
        from oracle_mcp.oracles.ssrf_imds import oracle_ssrf_imds
        return await oracle_ssrf_imds(target.url, target.param)
    if target.oracle == "idor":
        # IDOR requires two `SessionCredentials` (owner + accessor) that the
        # (url, param) fixture row cannot supply; callers must inject a custom
        # dispatcher via FieldValidationRunner(dispatcher=...).
        raise NotImplementedError(
            "idor oracle requires owner/accessor sessions; "
            "inject a custom dispatcher for field validation"
        )
    if target.oracle == "rce":
        from oracle_mcp.oracles.rce import oracle_rce
        return await oracle_rce(target.url, target.param)
    if target.oracle == "ssti":
        from oracle_mcp.oracles.ssti import oracle_ssti
        return await oracle_ssti(target.url, target.param)
    if target.oracle == "open_redirect":
        from oracle_mcp.oracles.open_redirect import oracle_open_redirect
        return await oracle_open_redirect(target.url, target.param)
    raise ValueError(f"no dispatch entry for oracle {target.oracle!r}")


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


class FieldValidationRunner:
    """Drives one fixture-file run end-to-end and emits a :class:`ValidationReport`.

    Constructor takes an optional ``dispatcher`` to make the runner
    fully unit-testable without hitting Playwright/httpx/Interactsh.
    Defaults to :func:`_dispatch_oracle` which calls the real oracles.
    """

    def __init__(self, dispatcher=_dispatch_oracle) -> None:
        self._dispatch = dispatcher

    async def run(
        self,
        fixtures: list[FixtureTarget],
    ) -> ValidationReport:
        if not fixtures:
            return ValidationReport(
                oracle="(empty)",
                total=0,
                true_positives=0,
                false_positives=0,
                true_negatives=0,
                false_negatives=0,
                tpr=0.0,
                fpr=0.0,
                results=(),
            )

        oracles_seen = {f.oracle for f in fixtures}
        if len(oracles_seen) != 1:
            raise ValueError(
                f"FieldValidationRunner.run expects a homogeneous fixture list; "
                f"saw multiple oracles: {sorted(oracles_seen)}"
            )
        (oracle,) = oracles_seen

        results: list[ValidationResult] = []
        for target in fixtures:
            results.append(await self._evaluate_one(target))

        tp = sum(
            1 for r in results
            if r.target.expected_verdict == "validated" and r.actual_verdict == "validated"
        )
        fp = sum(
            1 for r in results
            if r.target.expected_verdict == "unreproducible" and r.actual_verdict == "validated"
        )
        fn = sum(
            1 for r in results
            if r.target.expected_verdict == "validated" and r.actual_verdict != "validated"
        )
        tn = sum(
            1 for r in results
            if r.target.expected_verdict == "unreproducible" and r.actual_verdict != "validated"
        )

        tpr = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        fpr = fp / (fp + tn) if (fp + tn) > 0 else 0.0

        return ValidationReport(
            oracle=oracle,
            total=len(results),
            true_positives=tp,
            false_positives=fp,
            true_negatives=tn,
            false_negatives=fn,
            tpr=tpr,
            fpr=fpr,
            results=tuple(results),
        )

    async def _evaluate_one(self, target: FixtureTarget) -> ValidationResult:
        try:
            outcome = await self._dispatch(target)
        except Exception as exc:  # noqa: BLE001 — error verdict captures any failure
            return ValidationResult(
                target=target,
                actual_verdict="error",
                correct=False,
                error=f"{type(exc).__name__}: {exc}",
            )

        actual = outcome.verdict
        if target.expected_verdict == "validated":
            correct = actual == "validated"
        else:
            correct = actual != "validated"

        return ValidationResult(
            target=target,
            actual_verdict=actual,
            correct=correct,
            evidence=dict(outcome.evidence) if outcome.evidence else {},
        )


__all__ = [
    "ExpectedVerdict",
    "FieldValidationRunner",
    "FixtureTarget",
    "SUPPORTED_ORACLES",
    "ValidationReport",
    "ValidationResult",
    "load_fixtures",
]
