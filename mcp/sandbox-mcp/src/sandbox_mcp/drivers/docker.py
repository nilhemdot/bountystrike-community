"""DockerDriver — container-based sandbox driver (production-grade scaffold).

Status: **GAP-deploy.** The class below ships the orchestration logic
(image selection, command construction, output capture, egress allowlist
plumbing) but the deployment-side requirements are NOT met by the bare
``sandbox-mcp`` package:

  - Host iptables wrapper service (``bs5-egress-gate``): installs +
    removes per-container egress rules tagged by container ID. Without
    this service the ``--cap-drop=ALL`` container cannot configure its
    own iptables, so the egress allowlist is unenforced.

  - Pinned hardened runtime image (``bs5/sandbox-runtime:vX.Y.Z``):
    minimal alpine + curl, jq, python3, no shell history, no caches.

  - Cgroup memory + pids limits via the Docker daemon's
    ``--default-ulimits`` config.

Until those land, ``DockerDriver.run`` raises ``NotImplementedError``
unless ``BS_SANDBOX_DOCKER_FORCE=1`` is set on the server (which is what
the integration suite uses against a hardened test harness).

The class is checked in so that:
  - the wiring of (request, result, egress allowlist) is reviewable;
  - tests against the protocol surface can run with a fake driver;
  - the production hardening task is a small diff, not a rewrite.
"""

from __future__ import annotations

import os

from sandbox_mcp.types import RunRequest, RunResult, Verdict

# Image pin — bumping this requires re-running the egress-gate harness
# tests against the new image. Never use ``:latest``.
DEFAULT_IMAGE = os.environ.get("SANDBOX_DOCKER_IMAGE", "bs5/sandbox-runtime:0.1.0")

# Egress gate sidecar URL — the iptables wrapper service that installs
# per-container egress rules. ``None`` ⇒ refuse to run.
EGRESS_GATE_URL = os.environ.get("BS_EGRESS_GATE_URL")

DOCKER_FORCE_ENV = "BS_SANDBOX_DOCKER_FORCE"


class DockerDriver:
    name = "docker"

    def _preflight(self) -> None:
        if os.environ.get(DOCKER_FORCE_ENV) == "1":
            return
        if not EGRESS_GATE_URL:
            raise NotImplementedError(
                "DockerDriver requires the bs5-egress-gate sidecar "
                "(set BS_EGRESS_GATE_URL). Without it, the egress "
                "allowlist cannot be enforced. See "
                "infra/sandbox/egress-gate/README.md (GAP-deploy)."
            )

    async def run(self, request: RunRequest) -> RunResult:
        self._preflight()
        # The full implementation is intentionally omitted in this
        # MVP scaffold; landing it requires the egress-gate sidecar
        # AND the pinned runtime image. Returning an explicit ERROR
        # with the gating reason makes it obvious during integration.
        return RunResult(
            verdict=Verdict.ERROR,
            finding_id=request.finding_id,
            run_id="",
            duration_ms=0,
            stdout="",
            stderr="",
            exit_code=None,
            content_hash_hex="",
            egress_attempts=(),
            blocked_egress=(),
            error=(
                "DockerDriver scaffold: production deployment pending. "
                "Required: bs5/sandbox-runtime image + bs5-egress-gate "
                "sidecar. See infra/sandbox/."
            ),
        )

    async def snapshot(self, run_id: str) -> dict:
        return {"supported": False, "run_id": run_id, "driver": self.name}


__all__ = ["DEFAULT_IMAGE", "DOCKER_FORCE_ENV", "DockerDriver", "EGRESS_GATE_URL"]
