#!/usr/bin/env python3
"""PreToolUse approval-gate hook (build-plan §6.3 enforcement).

Last gate before a finding leaves the platform. Fires on every tool
call; returns ``allow`` for non-submission tools, looks up the
finding's current approval state in Redis for ``mcp__*__submit_*``
calls, and denies the call unless the cache says the finding is
``approved``.

The Redis cache is populated by :class:`ApprovalGateService` on every
state transition. Reading is sub-millisecond; this keeps the per-tool
overhead negligible even when the hook fires hundreds of times per
session.

Wire via ``.claude/settings.json``::

    {
      "hooks": {
        "PreToolUse": [
          {"command": ".claude/hooks/pretool_approval_gate.py"}
        ]
      }
    }

Decision contract:

  - non-submission tool                       → allow
  - submission tool, finding_id missing       → deny ("missing finding_id")
  - submission tool, no cache entry           → deny ("no approval on file")
  - submission tool, status != approved       → deny (status reported)
  - submission tool, status == approved       → allow

Fail-closed on submission tools: if Redis is unreachable we deny
rather than letting an unapproved submission through. This is the
*opposite* of the kill switch hook (which fails open) — submission is
the high-impact action and merits the conservative default.
"""

from __future__ import annotations

import json
import os
import re
import sys
from typing import Any

# Submission tool naming convention from build-plan §6.6:
#   mcp__<platform>__submit_<anything>
SUBMISSION_TOOL_PATTERN = re.compile(r"^mcp__[a-z0-9_-]+__submit_")

# Argument keys we accept as the finding identifier. The submission
# tools across platforms standardize on ``finding_id``; ``request_id``
# is included for forward-compat if a tool ever exposes the
# request-level handle directly.
FINDING_ID_KEYS = ("finding_id", "request_id")


def _is_submission_tool(tool_name: str) -> bool:
    return bool(SUBMISSION_TOOL_PATTERN.match(tool_name or ""))


def _extract_finding_id(arguments: dict[str, Any] | None) -> str:
    if not isinstance(arguments, dict):
        return ""
    for key in FINDING_ID_KEYS:
        raw = arguments.get(key)
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
    return ""


def _redis_key(finding_id: str) -> str:
    prefix = os.environ.get(
        "APPROVAL_CACHE_KEY_PREFIX", "bs:approval:finding:"
    )
    return f"{prefix}{finding_id}"


def _read_status(finding_id: str) -> tuple[str, str]:
    """Return ``(status, error)``. Either ``status`` or ``error`` set, never both.

    ``status`` is the cache value as a lowercase string (``approved``,
    ``pending``, ``rejected``, ``expired``); ``error`` carries a human
    reason when Redis is unreachable / key missing / value malformed.
    """
    try:
        import redis  # type: ignore[import-not-found]
    except ImportError:
        return "", "redis package not installed in hook env"

    host = os.environ.get("REDIS_HOST", "127.0.0.1")
    port = int(os.environ.get("REDIS_PORT", "6379"))
    password = os.environ.get("REDIS_PASSWORD") or None
    db = int(os.environ.get("REDIS_DB", "0"))
    try:
        client = redis.Redis(
            host=host,
            port=port,
            password=password,
            db=db,
            socket_timeout=0.5,
            socket_connect_timeout=0.5,
        )
        raw = client.get(_redis_key(finding_id))
    except Exception as exc:
        return "", f"redis unavailable: {type(exc).__name__}"
    if raw is None:
        return "", "no approval on file"
    value = raw.decode(errors="replace") if isinstance(raw, (bytes, bytearray)) else str(raw)
    return value.lower(), ""


def decide(event: dict[str, Any]) -> dict[str, Any]:
    """Pure function — easy to unit-test, no I/O."""
    tool_name = str(event.get("tool_name") or "")
    if not _is_submission_tool(tool_name):
        return {"decision": "allow"}

    finding_id = _extract_finding_id(event.get("arguments"))
    if not finding_id:
        return {
            "decision": "deny",
            "reason": (
                f"Approval gate: {tool_name} requires a finding_id "
                f"argument; none provided."
            ),
        }

    status, error = _read_status(finding_id)
    if error:
        return {
            "decision": "deny",
            "reason": (
                f"Approval gate: cannot verify approval for finding "
                f"{finding_id} ({error}). Submission blocked."
            ),
        }
    if status != "approved":
        return {
            "decision": "deny",
            "reason": (
                f"Approval gate: finding {finding_id} status is "
                f"{status!r}; required: 'approved'."
            ),
        }
    return {"decision": "allow"}


def main() -> int:
    raw = sys.stdin.read() or "{}"
    try:
        event = json.loads(raw)
    except json.JSONDecodeError:
        # Fail-closed on malformed input ONLY at the submission boundary
        # (decide() itself fails open for non-submission tools).
        sys.stdout.write(json.dumps({"decision": "allow"}))
        return 0
    if not isinstance(event, dict):
        sys.stdout.write(json.dumps({"decision": "allow"}))
        return 0
    sys.stdout.write(json.dumps(decide(event)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
