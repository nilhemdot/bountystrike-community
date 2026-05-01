#!/usr/bin/env python3
"""PreToolUse model routing hook (build-plan §10.4 Phase 2).

Enforces the platform's payload-generation routing policy:

  - Anthropic models are forbidden for payload-generation prompts —
    they refuse > 70% of such prompts (build-plan §6.6 measurement),
    burning latency and tokens before the agent eventually retries.
  - Default-rerouted to Venice Dolphin (privacy mode `data_collection:
    deny`); Hermes-3-70B is accepted as an explicit override.

Wire via `.claude/settings.json`::

    {
      "hooks": {
        "PreToolUse": [
          {"command": ".claude/hooks/pretool_venice_route.py"}
        ]
      }
    }

Input shape (Claude Code PreToolUse event)::

    {
      "tool_name": "mcp__openrouter__openrouter_complete",
      "arguments": {
        "model":    "...",
        "messages": [..., {"content": "..."}]
      }
    }

Decision contract:
  - non-OpenRouter calls           → ``allow`` (hook is a no-op)
  - non-payload prompts            → ``allow``
  - payload + Anthropic model      → ``deny`` with reason
  - payload + non-allowed model    → ``allow`` with rewritten args
                                     pinning Venice Dolphin
  - payload + already-Venice/Hermes → ``allow``

Fail-open on malformed input (sets ``allow``) — better to let the
session continue than wedge it on a hook protocol drift; the kill
switch hook is the safety net for true emergencies.
"""

from __future__ import annotations

import json
import sys
from typing import Any

OPENROUTER_TOOL_NAME = "mcp__openrouter__openrouter_complete"

# Substring matches in the latest user message → "this is a payload
# generation prompt". Lower-cased before matching so e.g. "Inject" hits.
PAYLOAD_KEYWORDS: tuple[str, ...] = (
    "payload",
    "inject",
    "bypass",
    "polyglot",
    "xss",
    "sqli",
    "ssti",
    "rce",
    "shellcode",
)

# Models that may receive payload prompts directly. Venice Dolphin is the
# default reroute target; Hermes-3-70B is an explicit operator override.
ALLOWED_PAYLOAD_MODELS: frozenset[str] = frozenset({
    "cognitivecomputations/dolphin-mistral-24b-venice-edition",
    "cognitivecomputations/hermes-3-llama-3-1-70b",
})

DEFAULT_REROUTE_MODEL = "cognitivecomputations/dolphin-mistral-24b-venice-edition"

ANTHROPIC_DENY_REASON = (
    "Anthropic models have a measured >70% refusal rate for payload "
    "generation prompts. Reroute to "
    "cognitivecomputations/dolphin-mistral-24b-venice-edition or "
    "cognitivecomputations/hermes-3-llama-3-1-70b via OpenRouter."
)


def is_payload_prompt(text: str) -> bool:
    """Return True iff *text* looks like a payload-generation request.

    Keyword search is intentionally crude — false positives just nudge a
    benign prompt to a non-Anthropic model, while false negatives leak a
    payload prompt to a refusing model. The asymmetry favours
    over-flagging.
    """
    if not text:
        return False
    lowered = text.lower()
    return any(kw in lowered for kw in PAYLOAD_KEYWORDS)


def _last_user_message_content(messages: list[dict[str, Any]] | None) -> str:
    """Pull the last message's ``content`` string, tolerating shape drift."""
    if not isinstance(messages, list) or not messages:
        return ""
    last = messages[-1]
    if not isinstance(last, dict):
        return ""
    content = last.get("content", "")
    if isinstance(content, str):
        return content
    # OpenRouter accepts list-of-blocks too — concatenate text blocks.
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, dict) and isinstance(block.get("text"), str):
                parts.append(block["text"])
        return "\n".join(parts)
    return ""


def route(event: dict[str, Any]) -> dict[str, Any]:
    """Classify the call and return the Claude Code hook decision dict.

    Pure function — easy to unit-test, no stdin/stdout.
    """
    tool_name = str(event.get("tool_name") or "")
    if tool_name != OPENROUTER_TOOL_NAME:
        return {"decision": "allow"}

    args = event.get("arguments")
    if not isinstance(args, dict):
        return {"decision": "allow"}

    model = str(args.get("model") or "")
    prompt = _last_user_message_content(args.get("messages"))

    if not is_payload_prompt(prompt):
        return {"decision": "allow"}

    # Payload prompt — Anthropic models are forbidden outright.
    if model.startswith("anthropic/"):
        return {"decision": "deny", "reason": ANTHROPIC_DENY_REASON}

    # Already on an allowed payload model — let it through unchanged.
    if model in ALLOWED_PAYLOAD_MODELS:
        return {"decision": "allow"}

    # Otherwise rewrite the args to pin Venice Dolphin in privacy mode.
    new_args = {**args}
    new_args["model"] = DEFAULT_REROUTE_MODEL
    new_args["provider"] = {"data_collection": "deny"}
    return {"decision": "allow", "updatedInput": new_args}


def _to_wire(decision: dict) -> dict:
    """Translate legacy ``{decision: allow|deny, ...}`` to Claude Code wire schema.

    Claude Code's PreToolUse hook validator rejects ``decision: "allow"``
    (legacy enum is ``approve|block``). Emit modern ``hookSpecificOutput``
    on deny; empty object on plain allow; preserve ``updatedInput`` field
    on rewrite-and-allow paths.
    """
    if decision.get("decision") == "deny":
        return {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": decision.get("reason", ""),
            }
        }
    if "updatedInput" in decision:
        return {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "allow",
            },
            "updatedInput": decision["updatedInput"],
        }
    return {}


def main() -> int:
    """Entry point — read event JSON from stdin, write decision to stdout."""
    raw = sys.stdin.read() or "{}"
    try:
        event = json.loads(raw)
    except json.JSONDecodeError:
        # Fail-open per the docstring contract.
        sys.stdout.write(json.dumps({}))
        return 0
    if not isinstance(event, dict):
        sys.stdout.write(json.dumps({}))
        return 0
    sys.stdout.write(json.dumps(_to_wire(route(event))))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
