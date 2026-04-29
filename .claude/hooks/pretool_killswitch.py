#!/usr/bin/env python3
"""PreToolUse kill-switch hook (Layer 2 of build-plan §6.6).

Reads the kill switch flag from Redis at the start of every tool call
and emits a Claude Code hook decision (allow / deny) based on the
current tier and the tool being invoked.

Wire via `.claude/settings.json`:

    {
      "hooks": {
        "PreToolUse": [
          {"command": ".claude/hooks/pretool_killswitch.py"}
        ]
      }
    }

Operates synchronously — Claude Code hooks are subprocess-based, no
event loop. The Python redis client (sync) is the simplest fit.

Fail-open policy: if Redis is unreachable the hook *allows* the call.
This is the build-plan §6.6 stance ("fail open for kill switch check
only") — Layer 3 (supervisor SIGTERM) is the safety net for the
Redis-down scenario.

Exit code is always 0 (the actual decision is in stdout JSON).
"""

from __future__ import annotations

import json
import os
import sys

# Categories the build-plan §6.6 escalation map cares about. Adding a
# new tool here is intentionally cheap — start by tagging anything
# network-touching as "network" and anything platform-submission as
# "submit", and let the kill-switch tiers gate the rest.
_NETWORK_TOOLS_PREFIXES = (
    "Bash",
    "WebFetch",
    "mcp__pd-tools__",
    "mcp__burp__",
    "mcp__caido__",
    "mcp__shodan__",
    "mcp__hexstrike__",
    "mcp__oracle-mcp__",
    "mcp__recon-mcp__",
)
_SUBMIT_TOOL_PATTERNS = (
    # Per build-plan §6.6: anything matching mcp__*__submit_*.
    "submit_",
)


def _classify(tool_name: str) -> str:
    """Return ``"submit"`` | ``"network"`` | ``"other"`` for the tool name."""
    lowered = tool_name.lower()
    if any(p in lowered for p in _SUBMIT_TOOL_PATTERNS):
        return "submit"
    if any(tool_name == p or tool_name.startswith(p) for p in _NETWORK_TOOLS_PREFIXES):
        return "network"
    return "other"


def _read_kill_state() -> str:
    """Return the kill switch value from Redis, or ``""`` on any error.

    Returning ``""`` (empty) is the fail-open signal — the hook treats
    it as "no halt active". Any noise in Redis (garbage values, stale
    keys without TTL) is treated the same way; the supervisor's
    separate health check is responsible for flagging it.
    """
    try:
        import redis  # type: ignore[import-not-found]
    except ImportError:
        return ""

    host = os.environ.get("REDIS_HOST", "127.0.0.1")
    port = int(os.environ.get("REDIS_PORT", "6379"))
    password = os.environ.get("REDIS_PASSWORD") or None
    db = int(os.environ.get("REDIS_DB", "0"))
    key = os.environ.get(
        "KILL_SWITCH_KEY", "bountystrike:killswitch:global"
    )
    try:
        client = redis.Redis(
            host=host,
            port=port,
            password=password,
            db=db,
            socket_timeout=0.5,        # fail-open quickly if Redis is slow
            socket_connect_timeout=0.5,
        )
        raw = client.get(key)
    except Exception:
        return ""
    if raw is None:
        return ""
    if isinstance(raw, (bytes, bytearray)):
        return raw.decode(errors="replace")
    return str(raw)


def _decide(state: str, category: str) -> tuple[bool, str]:
    """Return ``(allow, reason)`` for the given state + tool category."""
    if state == "halt_all":
        return False, "Kill switch: halt_all — all tool calls blocked."
    if state == "halt_scans" and category in {"network", "submit"}:
        return False, f"Kill switch: halt_scans — {category} tools blocked."
    if state == "halt_submissions" and category == "submit":
        return False, "Kill switch: halt_submissions — submission tools blocked."
    return True, ""


def main() -> int:
    try:
        event = json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError:
        # Malformed input — fail open so we never wedge sessions on a
        # protocol drift. The build-plan §6.6 supervisor layer is the
        # net for this.
        sys.stdout.write(json.dumps({"decision": "allow"}))
        return 0

    tool_name = str(event.get("tool_name") or "")
    category = _classify(tool_name)
    state = _read_kill_state()

    allow, reason = _decide(state, category)
    decision = {"decision": "allow"} if allow else {"decision": "deny", "reason": reason}
    sys.stdout.write(json.dumps(decision))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
