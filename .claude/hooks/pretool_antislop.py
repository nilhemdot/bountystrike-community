#!/usr/bin/env python3
"""PreToolUse anti-slop hook (build-plan §2.3.8 reporter rules).

Fires before every ``Write`` call. When the target path matches a report
file (``reports/<finding_id>.md`` or ``reports/<finding_id>_*.md``),
inspect the proposed content for the four anti-slop rules:

  1. Banned filler words / phrases — "leverages", "delve", "unveil",
     "furthermore", "moreover", "it is important to note",
     "holistic approach". Reject on any hit.
  2. Word count cap — 600 for standard reports, 1000 for critical chain
     reports. Critical detected via title containing ``critical`` or
     CVSS hint ``9.x`` / ``10.0``.
  3. Artifact provenance — at least one reference to an artifact / audit
     anchor (``artifact_id``, ``audit_ref``, ``evidence_hash``,
     ``chain_hash``, or a ``sha256:`` prefix). Reports without provenance
     are slop.
  4. Redaction discipline — auth tokens / PII patterns must be wrapped in
     ``<REDACTED:sha256:8>`` / ``<PII:redacted>`` placeholders. Bare
     occurrences are rejected.

Wire via ``.claude/settings.json``::

    {
      "hooks": {
        "PreToolUse": [
          {"command": ".claude/hooks/pretool_antislop.py"}
        ]
      }
    }

Decision contract:
  - non-Write tool                                    → allow
  - Write outside ``reports/*.md``                    → allow
  - Write to ``reports/*.md`` with violations         → deny + reasons
  - Write to ``reports/*.md`` clean                   → allow

Fail-open on malformed input — drift in the hook protocol must not wedge
unrelated writes. The kill switch hook covers true emergencies.
"""

from __future__ import annotations

import json
import re
import sys
from typing import Any

WRITE_TOOL_NAMES = ("Write", "Edit", "MultiEdit")

REPORT_PATH_PATTERN = re.compile(r"(^|/)reports/[^/]+\.md$")

# Banned filler words / phrases (build-plan §2.3.8). Matched
# case-insensitively as whole words.
BANNED_TOKENS: tuple[str, ...] = (
    "leverages",
    "leverage",
    "delve",
    "delves",
    "unveil",
    "unveils",
    "furthermore",
    "moreover",
    "it is important to note",
    "holistic approach",
)

# Word-count caps.
STANDARD_WORD_CAP = 600
CRITICAL_WORD_CAP = 1000

CRITICAL_HINTS: tuple[str, ...] = (
    "critical",
    "cvss:9.",
    "cvss: 9.",
    "cvss:10",
    "cvss: 10",
    "severity: critical",
    "severity:critical",
)

ARTIFACT_PATTERN = re.compile(
    r"\b("
    r"artifact_[a-f0-9]+"
    r"|audit_ref"
    r"|audit_2[0-9]{9}_[a-z_]+_[a-f0-9]{8}"
    r"|evidence_hash"
    r"|chain_hash"
    r"|sha256:[a-f0-9]{8,}"
    r")\b",
    re.IGNORECASE,
)

# Token / PII regexes — fired only outside REDACTED placeholders. The
# placeholder itself looks like ``<REDACTED:sha256:8>`` or
# ``<PII:redacted>``.
REDACTED_PLACEHOLDER = re.compile(
    r"<(REDACTED:[a-z0-9:]+|PII:redacted)>", re.IGNORECASE
)

TOKEN_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("AWS access key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("JWT", re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b")),
    (
        "long bearer token",
        re.compile(r"\b(?:[A-Za-z0-9_-]{40,}|gh[pousr]_[A-Za-z0-9_]{36,})\b"),
    ),
    ("email PII", re.compile(r"\b[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}\b", re.IGNORECASE)),
)

# Tokens we recognise as the placeholder syntax — never flag these even
# though they look like long alphanumeric runs.
PLACEHOLDER_LITERAL = re.compile(r"<(REDACTED|PII):[^>]*>", re.IGNORECASE)


def _word_count(text: str) -> int:
    return len(re.findall(r"\b[\w'-]+\b", text))


def _is_critical(text: str) -> bool:
    lower = text.lower()
    return any(h in lower for h in CRITICAL_HINTS)


def _find_banned(text: str) -> list[str]:
    """Return banned tokens that appear in *text* (case-insensitive)."""
    lower = text.lower()
    hits: list[str] = []
    for token in BANNED_TOKENS:
        # Whole-word match for single words; substring for phrases.
        if " " in token:
            if token in lower:
                hits.append(token)
        else:
            if re.search(rf"\b{re.escape(token)}\b", lower):
                hits.append(token)
    return hits


def _scan_unredacted_secrets(text: str) -> list[str]:
    """Return PII / token labels that appear OUTSIDE redacted placeholders.

    We strip placeholder spans first so e.g. ``<REDACTED:sha256:8>`` does
    not flag the trailing ``sha256:8`` literal.
    """
    stripped = PLACEHOLDER_LITERAL.sub("<X>", text)
    found: list[str] = []
    for label, pattern in TOKEN_PATTERNS:
        if pattern.search(stripped):
            found.append(label)
    return found


def _has_provenance(text: str) -> bool:
    return ARTIFACT_PATTERN.search(text) is not None


def _is_report_path(file_path: str) -> bool:
    if not file_path:
        return False
    return bool(REPORT_PATH_PATTERN.search(file_path))


def _extract_write_payload(args: dict[str, Any]) -> tuple[str, str] | None:
    """Pull (file_path, content) for Write/Edit/MultiEdit shapes.

    Returns ``None`` when the call shape doesn't carry a content body we
    can inspect (e.g. partial edits) — caller treats that as ``allow``.
    """
    file_path = str(args.get("file_path") or "")
    if not file_path:
        return None

    if "content" in args and isinstance(args["content"], str):
        return file_path, args["content"]

    # Edit ⇒ inspect the new_string only (the bit Claude is writing).
    if "new_string" in args and isinstance(args["new_string"], str):
        return file_path, args["new_string"]

    # MultiEdit ⇒ concatenate all new_strings; if any chunk introduces a
    # violation we want to catch it.
    if isinstance(args.get("edits"), list):
        chunks: list[str] = []
        for edit in args["edits"]:
            if isinstance(edit, dict) and isinstance(edit.get("new_string"), str):
                chunks.append(edit["new_string"])
        if chunks:
            return file_path, "\n".join(chunks)

    return None


def evaluate(file_path: str, content: str) -> dict[str, Any]:
    """Return the Claude Code hook decision for one report write.

    Pure function — easy to unit-test, no I/O. Always inspects the
    ``content`` text. Caller is responsible for short-circuiting on
    non-report paths.
    """
    violations: list[str] = []

    banned = _find_banned(content)
    if banned:
        violations.append(
            "banned filler tokens: " + ", ".join(sorted(set(banned)))
        )

    cap = CRITICAL_WORD_CAP if _is_critical(content) else STANDARD_WORD_CAP
    wc = _word_count(content)
    if wc > cap:
        violations.append(f"word count {wc} exceeds cap {cap}")

    if not _has_provenance(content):
        violations.append(
            "no artifact / audit reference (need artifact_id, audit_ref, "
            "evidence_hash, chain_hash, or sha256:<hex>)"
        )

    secrets = _scan_unredacted_secrets(content)
    if secrets:
        violations.append(
            "unredacted token/PII detected: " + ", ".join(sorted(set(secrets))) +
            " — wrap with <REDACTED:sha256:8> or <PII:redacted>"
        )

    if violations:
        return {
            "decision": "deny",
            "reason": (
                f"Anti-slop hook rejected report {file_path}: "
                + "; ".join(violations)
            ),
        }
    return {"decision": "allow"}


def decide(event: dict[str, Any]) -> dict[str, Any]:
    tool_name = str(event.get("tool_name") or "")
    if tool_name not in WRITE_TOOL_NAMES:
        return {"decision": "allow"}

    args = event.get("arguments")
    if not isinstance(args, dict):
        return {"decision": "allow"}

    payload = _extract_write_payload(args)
    if payload is None:
        return {"decision": "allow"}
    file_path, content = payload

    if not _is_report_path(file_path):
        return {"decision": "allow"}

    return evaluate(file_path, content)


def main() -> int:
    raw = sys.stdin.read() or "{}"
    try:
        event = json.loads(raw)
    except json.JSONDecodeError:
        sys.stdout.write(json.dumps({"decision": "allow"}))
        return 0
    if not isinstance(event, dict):
        sys.stdout.write(json.dumps({"decision": "allow"}))
        return 0
    sys.stdout.write(json.dumps(decide(event)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
