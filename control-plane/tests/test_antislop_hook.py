"""Tests for the .claude/hooks/pretool_antislop.py PreToolUse hook.

The hook is a standalone script (no control-plane PYTHONPATH dependency
in production). Loaded via importlib for pure-function tests; subprocess
boundary covered with one round-trip case.
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
    / ".claude" / "hooks" / "pretool_antislop.py"
)


def _load_hook_module():
    spec = importlib.util.spec_from_file_location("pretool_antislop", _HOOK_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def hook():
    return _load_hook_module()


# ---------------------------------------------------------------------------
# Path classifier
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "path",
    [
        "reports/abc-123.md",
        "/abs/path/reports/finding.md",
        "subdir/reports/x.md",
    ],
)
def test_is_report_path_true(hook, path: str) -> None:
    assert hook._is_report_path(path) is True


@pytest.mark.parametrize(
    "path",
    [
        "src/foo.py",
        "reports/sub/nested.md",  # nested ⇒ outside reports root
        "reports/foo.txt",
        "",
    ],
)
def test_is_report_path_false(hook, path: str) -> None:
    assert hook._is_report_path(path) is False


# ---------------------------------------------------------------------------
# Banned filler tokens
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "snippet,banned",
    [
        ("This leverages the SSRF gadget.", "leverages"),
        ("Furthermore, the request triggers RCE.", "furthermore"),
        ("We delve into the auth flow.", "delve"),
        ("It is important to note the timing.", "it is important to note"),
        ("This holistic approach beats lone tools.", "holistic approach"),
    ],
)
def test_find_banned_hits(hook, snippet: str, banned: str) -> None:
    assert banned in hook._find_banned(snippet)


def test_find_banned_clean(hook) -> None:
    text = "The XSS payload triggers DOM mutation. artifact_abc123 confirms."
    assert hook._find_banned(text) == []


# ---------------------------------------------------------------------------
# Word count cap
# ---------------------------------------------------------------------------


def _padding(words: int) -> str:
    return " ".join(["word"] * words)


def test_word_cap_ok_under_standard(hook) -> None:
    text = _padding(500) + " artifact_abc123"
    decision = hook.evaluate("reports/x.md", text)
    assert decision["decision"] == "allow"


def test_word_cap_rejects_over_standard(hook) -> None:
    text = _padding(700) + " artifact_abc123"
    decision = hook.evaluate("reports/x.md", text)
    assert decision["decision"] == "deny"
    assert "word count" in decision["reason"]


def test_critical_lifts_word_cap(hook) -> None:
    # Critical hint extends the cap to 1000.
    text = "Severity: critical\n\n" + _padding(800) + " artifact_abc"
    decision = hook.evaluate("reports/x.md", text)
    assert decision["decision"] == "allow"


def test_critical_still_capped_at_1000(hook) -> None:
    text = "Severity: critical\n\n" + _padding(1100) + " artifact_abc"
    decision = hook.evaluate("reports/x.md", text)
    assert decision["decision"] == "deny"
    assert "1000" in decision["reason"]


# ---------------------------------------------------------------------------
# Provenance requirement
# ---------------------------------------------------------------------------


def test_no_provenance_rejects(hook) -> None:
    text = "Reflected XSS at /search?q=. Trigger via the q parameter."
    decision = hook.evaluate("reports/x.md", text)
    assert decision["decision"] == "deny"
    assert "artifact" in decision["reason"]


@pytest.mark.parametrize(
    "anchor",
    [
        "artifact_abcdef0123",
        "audit_2026050112_scope_guard_a1b2c3d4",
        "evidence_hash",
        "chain_hash",
        "sha256:8a3f9b2c1d",
    ],
)
def test_each_anchor_satisfies_provenance(hook, anchor: str) -> None:
    text = f"Reflected XSS confirmed via oracle. See {anchor}."
    decision = hook.evaluate("reports/x.md", text)
    assert decision["decision"] == "allow"


# ---------------------------------------------------------------------------
# Redaction discipline
# ---------------------------------------------------------------------------


def test_unredacted_aws_key_rejected(hook) -> None:
    text = "Captured key AKIAIOSFODNN7EXAMPLE in IMDS response. artifact_abc"
    decision = hook.evaluate("reports/x.md", text)
    assert decision["decision"] == "deny"
    assert "AWS access key" in decision["reason"]


def test_unredacted_email_rejected(hook) -> None:
    text = "Victim user victim@example.com hit. artifact_abc"
    decision = hook.evaluate("reports/x.md", text)
    assert decision["decision"] == "deny"
    assert "email PII" in decision["reason"]


def test_redacted_email_passes(hook) -> None:
    text = "Victim <PII:redacted> hit. artifact_abc"
    decision = hook.evaluate("reports/x.md", text)
    assert decision["decision"] == "allow"


def test_redacted_token_passes(hook) -> None:
    text = "Bearer <REDACTED:sha256:8> exfiltrated. artifact_abc"
    decision = hook.evaluate("reports/x.md", text)
    assert decision["decision"] == "allow"


def test_unredacted_jwt_rejected(hook) -> None:
    text = (
        "Captured eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkw.dummysig"
        "valuelongerthan10chars artifact_abc"
    )
    decision = hook.evaluate("reports/x.md", text)
    assert decision["decision"] == "deny"
    assert "JWT" in decision["reason"]


# ---------------------------------------------------------------------------
# decide() — wires it all together
# ---------------------------------------------------------------------------


def test_decide_non_write_tool_allow(hook) -> None:
    event = {"tool_name": "Bash", "arguments": {"command": "ls"}}
    assert hook.decide(event) == {"decision": "allow"}


def test_decide_write_outside_reports_allow(hook) -> None:
    event = {
        "tool_name": "Write",
        "arguments": {"file_path": "src/foo.py", "content": "leverages furthermore"},
    }
    assert hook.decide(event) == {"decision": "allow"}


def test_decide_clean_report_allow(hook) -> None:
    event = {
        "tool_name": "Write",
        "arguments": {
            "file_path": "reports/abc.md",
            "content": (
                "## Summary\n\nReflected XSS at /search?q=. "
                "Confirmed via oracle. See artifact_abc123."
            ),
        },
    }
    assert hook.decide(event)["decision"] == "allow"


def test_decide_dirty_report_deny(hook) -> None:
    event = {
        "tool_name": "Write",
        "arguments": {
            "file_path": "reports/abc.md",
            "content": (
                "## Summary\n\nThe SSRF leverages IMDS. "
                "Furthermore the operator victim@example.com is at risk."
            ),
        },
    }
    decision = hook.decide(event)
    assert decision["decision"] == "deny"
    # Should mention multiple violations
    reason = decision["reason"]
    assert "leverages" in reason.lower() or "leverage" in reason.lower()
    assert "furthermore" in reason.lower()


def test_decide_edit_tool_inspected(hook) -> None:
    event = {
        "tool_name": "Edit",
        "arguments": {
            "file_path": "reports/abc.md",
            "old_string": "old",
            "new_string": "Furthermore, the bug leverages CSRF.",
        },
    }
    assert hook.decide(event)["decision"] == "deny"


# ---------------------------------------------------------------------------
# Subprocess round-trip — confirms the JSON-on-stdin / stdout contract.
# ---------------------------------------------------------------------------


def test_subprocess_roundtrip_clean_report() -> None:
    event = {
        "tool_name": "Write",
        "arguments": {
            "file_path": "reports/sub.md",
            "content": "## Summary\n\nXSS confirmed. See artifact_abc123.",
        },
    }
    proc = subprocess.run(
        [sys.executable, str(_HOOK_PATH)],
        input=json.dumps(event),
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout) == {"decision": "allow"}


def test_subprocess_roundtrip_malformed_input_fails_open() -> None:
    proc = subprocess.run(
        [sys.executable, str(_HOOK_PATH)],
        input="{not json",
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert proc.returncode == 0
    assert json.loads(proc.stdout) == {"decision": "allow"}
