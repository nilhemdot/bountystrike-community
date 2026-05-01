"""CVSS v3.1 / v4.0 score computation via the ``cvss`` PyPI package.

Why the third-party library: implementing CVSS v4 correctly is ~300 lines
of MacroVector lookup math. The ``cvss`` package is the FIRST-published
reference and has a hard dep on nothing beyond the stdlib — keeping it
gives us correctness for free and isolates us from spec drift.

Vector autodetection: v3.1 vectors begin with ``CVSS:3.1/`` and v4 with
``CVSS:4.0/`` — so the dispatcher trivially routes by prefix.
"""

from __future__ import annotations

from cvss import CVSS3, CVSS4

# Bug bounty platforms map severity off the score thresholds. These match
# the FIRST published bands; HackerOne/Bugcrowd both follow them today.
SEVERITY_BANDS: tuple[tuple[float, str], ...] = (
    (9.0, "critical"),
    (7.0, "high"),
    (4.0, "medium"),
    (0.1, "low"),
    (0.0, "informational"),
)


def severity_from_score(score: float) -> str:
    """Map a numeric base score to its named severity.

    Returns the lower-case label as used by H1/Bugcrowd report fields.
    """
    if score < 0 or score > 10:
        raise ValueError(f"score out of range: {score}")
    for threshold, label in SEVERITY_BANDS:
        if score >= threshold:
            return label
    return "informational"


def detect_version(vector: str) -> str:
    """Return ``'3.1'`` / ``'4.0'`` from the vector prefix.

    Raises ValueError on unrecognised prefix — we deliberately do NOT
    fall through to v2 (which Bugcrowd / H1 still allow as legacy):
    callers should explicitly pass v3.1+ vectors. v2 will never be
    accepted from a 2026 oracle output.
    """
    head = vector.split("/", 1)[0]
    if head == "CVSS:3.1":
        return "3.1"
    if head == "CVSS:4.0":
        return "4.0"
    raise ValueError(
        f"unsupported CVSS prefix {head!r}; expected 'CVSS:3.1' or 'CVSS:4.0'"
    )


def compute(vector: str) -> dict:
    """Compute the base score for a CVSS v3.1 or v4.0 vector.

    Args:
        vector: full vector string starting with ``CVSS:3.1/`` or
            ``CVSS:4.0/``.

    Returns:
        ``{vector, version, base_score, severity}``.

    Raises:
        ValueError: prefix not recognised, or vector is malformed.
    """
    version = detect_version(vector)
    if version == "3.1":
        impl = CVSS3(vector)
    else:
        impl = CVSS4(vector)
    score = float(impl.base_score)
    return {
        "vector": vector,
        "version": version,
        "base_score": round(score, 1),
        "severity": severity_from_score(score),
    }


__all__ = [
    "SEVERITY_BANDS",
    "compute",
    "detect_version",
    "severity_from_score",
]
