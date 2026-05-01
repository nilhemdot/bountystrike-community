"""Sandbox request/result schemas.

Pure data — no I/O. Driver implementations consume ``RunRequest`` and
return ``RunResult``. Keeping the schemas in their own module makes
swapping drivers trivial.
"""

from __future__ import annotations

import dataclasses
import enum
from typing import Any


class Verdict(str, enum.Enum):
    SUCCESS = "success"
    EGRESS_BLOCKED = "egress_blocked"
    TIMEOUT = "timeout"
    CRASH = "crash"
    ERROR = "error"


# Default and ceiling for ``timeout_sec``. The 120s default matches
# build-plan §2.3.6; the 600s ceiling prevents an exploit-agent from
# allocating an unbounded sandbox window (denial-of-wallet defence).
DEFAULT_TIMEOUT_SEC = 120
MAX_TIMEOUT_SEC = 600

# Maximum stdout/stderr captured per run — payload should ALWAYS fit, but
# a runaway loop would otherwise OOM the orchestrator. 4 MB is well above
# the 64 KB any sane PoC produces.
MAX_OUTPUT_BYTES = 4 * 1024 * 1024


@dataclasses.dataclass(frozen=True)
class RunRequest:
    """Inputs to a single sandbox execution.

    Mandatory:
      finding_id        — UUID of the parent finding row. Used as the
                          audit-trail key and as the container/VM tag.
      scope_token       — Raw RS256 scope JWT. The driver MUST verify
                          before allocating any resources.
      egress_allowlist  — Hostnames the sandbox may reach. Derived from
                          the scope JWT's wildcards/exact_hosts by the
                          orchestrator; this field is the binding list
                          the driver enforces.
      command           — Shell command to execute inside the sandbox.

    Optional:
      template_id       — Identifies a structured chain template (curl
                          chain, Python script, Burp replay) when
                          provided; the driver may apply per-template
                          hardening.
      stdin_bytes       — Optional bytes to feed on stdin.
      env               — Extra environment vars to set inside the
                          sandbox. The driver always strips host env
                          to a minimal allowlist before applying these.
      timeout_sec       — Wall-clock budget; clamped to MAX_TIMEOUT_SEC.
      cleanup           — When True (default) the driver tears down the
                          container/VM after the run. False keeps it for
                          post-mortem snapshotting.
    """

    finding_id: str
    scope_token: str
    egress_allowlist: tuple[str, ...]
    command: str
    template_id: str | None = None
    stdin_bytes: bytes | None = None
    env: dict[str, str] = dataclasses.field(default_factory=dict)
    timeout_sec: int = DEFAULT_TIMEOUT_SEC
    cleanup: bool = True


@dataclasses.dataclass(frozen=True)
class RunResult:
    """Output of a single sandbox execution.

    The driver hashes ``stdout_bytes + stderr_bytes`` to produce
    ``content_hash_hex`` (SHA-256). Use this in the evidence chain.
    """

    verdict: Verdict
    finding_id: str
    run_id: str
    duration_ms: int
    stdout: str
    stderr: str
    exit_code: int | None
    content_hash_hex: str
    egress_attempts: tuple[dict[str, Any], ...]
    blocked_egress: tuple[str, ...]
    error: str | None = None


__all__ = [
    "DEFAULT_TIMEOUT_SEC",
    "MAX_OUTPUT_BYTES",
    "MAX_TIMEOUT_SEC",
    "RunRequest",
    "RunResult",
    "Verdict",
]
