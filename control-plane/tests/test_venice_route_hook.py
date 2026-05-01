"""Tests for the .claude/hooks/pretool_venice_route.py PreToolUse hook.

The hook is a standalone script (deliberately, so it has no PYTHONPATH
dependency on control-plane in production). We load it via importlib
to exercise the pure functions, and round-trip a few cases through the
process boundary to confirm the JSON-on-stdin / JSON-on-stdout
contract.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

_HOOK_PATH = (
    Path(__file__).resolve().parents[2]
    / ".claude" / "hooks" / "pretool_venice_route.py"
)


def _load_hook_module():
    spec = importlib.util.spec_from_file_location(
        "pretool_venice_route", _HOOK_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def hook():
    return _load_hook_module()


# ---------------------------------------------------------------------------
# 1. is_payload_prompt — keyword classifier
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "Generate an XSS payload",
        "Build a SSTI bypass for jinja2",
        "I need a polyglot here",
        "How do I inject this parameter",
        "Write shellcode for x86_64",
        "draft a SQLi probe",
        "Make an RCE PoC",
        "PAYLOAD please",  # case-insensitive
    ],
)
def test_is_payload_prompt_true(hook, text: str):
    assert hook.is_payload_prompt(text) is True


@pytest.mark.parametrize(
    "text",
    [
        "Summarize this report",
        "What is CVSS v4?",
        "Explain bug bounty triage",
        "",
        "   ",
    ],
)
def test_is_payload_prompt_false(hook, text: str):
    assert hook.is_payload_prompt(text) is False


# ---------------------------------------------------------------------------
# 2. _last_user_message_content — tolerates content shape drift
# ---------------------------------------------------------------------------


def test_last_user_message_string_content(hook):
    msgs = [
        {"role": "user", "content": "first"},
        {"role": "user", "content": "last"},
    ]
    assert hook._last_user_message_content(msgs) == "last"


def test_last_user_message_block_list_content(hook):
    msgs = [
        {"role": "user", "content": [
            {"type": "text", "text": "block A"},
            {"type": "text", "text": "block B"},
        ]},
    ]
    out = hook._last_user_message_content(msgs)
    assert "block A" in out and "block B" in out


def test_last_user_message_handles_none_and_empty(hook):
    assert hook._last_user_message_content(None) == ""
    assert hook._last_user_message_content([]) == ""
    assert hook._last_user_message_content("not a list") == ""  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# 3. route() — decision matrix
# ---------------------------------------------------------------------------


def _event(model: str, content: str = "Generate an XSS payload"):
    return {
        "tool_name": "mcp__openrouter__openrouter_complete",
        "arguments": {
            "model": model,
            "messages": [{"role": "user", "content": content}],
        },
    }


def test_route_non_openrouter_tool_is_noop(hook):
    out = hook.route({
        "tool_name": "Bash",
        "arguments": {"command": "ls"},
    })
    assert out == {"decision": "allow"}


def test_route_openrouter_with_no_args_is_noop(hook):
    out = hook.route({
        "tool_name": "mcp__openrouter__openrouter_complete",
        "arguments": "not a dict",
    })
    assert out == {"decision": "allow"}


def test_route_non_payload_prompt_is_noop(hook):
    out = hook.route(_event("anthropic/claude-sonnet-4-6", "summarize this"))
    assert out == {"decision": "allow"}


def test_route_payload_prompt_to_anthropic_is_denied(hook):
    out = hook.route(_event("anthropic/claude-sonnet-4-6"))
    assert out["decision"] == "deny"
    assert "Anthropic" in out["reason"]


def test_route_payload_prompt_to_venice_passthrough(hook):
    out = hook.route(_event(
        "cognitivecomputations/dolphin-mistral-24b-venice-edition"
    ))
    assert out == {"decision": "allow"}


def test_route_payload_prompt_to_hermes_passthrough(hook):
    out = hook.route(_event(
        "cognitivecomputations/hermes-3-llama-3-1-70b"
    ))
    assert out == {"decision": "allow"}


def test_route_payload_prompt_unknown_model_is_rerouted(hook):
    out = hook.route(_event("openai/gpt-4-turbo"))
    assert out["decision"] == "allow"
    assert (
        out["updatedInput"]["model"]
        == "cognitivecomputations/dolphin-mistral-24b-venice-edition"
    )
    # Privacy-mode flag must be set per build-plan §10.4.
    assert out["updatedInput"]["provider"] == {"data_collection": "deny"}


def test_route_reroute_preserves_other_args(hook):
    event = _event("openai/gpt-4-turbo")
    event["arguments"]["temperature"] = 0.7
    event["arguments"]["max_tokens"] = 2048
    out = hook.route(event)
    assert out["updatedInput"]["temperature"] == 0.7
    assert out["updatedInput"]["max_tokens"] == 2048


def test_route_block_list_content_classified_as_payload(hook):
    out = hook.route({
        "tool_name": "mcp__openrouter__openrouter_complete",
        "arguments": {
            "model": "openai/gpt-4-turbo",
            "messages": [{"role": "user", "content": [
                {"type": "text", "text": "We need a polyglot for"},
                {"type": "text", "text": " the search field"},
            ]}],
        },
    })
    assert out["decision"] == "allow"
    assert (
        out["updatedInput"]["model"]
        == "cognitivecomputations/dolphin-mistral-24b-venice-edition"
    )


# ---------------------------------------------------------------------------
# 4. main() — stdin/stdout JSON contract
# ---------------------------------------------------------------------------


def _run_hook(stdin_payload: str) -> dict:
    """Subprocess the hook script and return the parsed stdout JSON."""
    completed = subprocess.run(
        [sys.executable, str(_HOOK_PATH)],
        input=stdin_payload,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert completed.returncode == 0, completed.stderr
    return json.loads(completed.stdout)


def test_main_invalid_json_fails_open():
    out = _run_hook("not valid json")
    assert out == {}


def test_main_non_object_input_fails_open():
    out = _run_hook("[]")
    assert out == {}


def test_main_full_pipeline_anthropic_denial():
    payload = json.dumps({
        "tool_name": "mcp__openrouter__openrouter_complete",
        "arguments": {
            "model": "anthropic/claude-opus-4-7",
            "messages": [{"role": "user", "content": "Generate an XSS payload"}],
        },
    })
    out = _run_hook(payload)
    assert out["hookSpecificOutput"]["permissionDecision"] == "deny"
