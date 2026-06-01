# SPDX-License-Identifier: AGPL-3.0-or-later

"""DockerDriver — container-based sandbox driver (community edition).

Executes one PoC per ``docker`` container, driving the ``docker`` CLI via
``asyncio.create_subprocess_exec`` (no docker SDK dependency — async-native,
mirrors ``local.py``).

Egress is enforced at the network layer, not the prompt layer, by the
``bs5-egress-gate`` sidecar (see ``infra/sandbox/``). The gate holds
``NET_ADMIN`` and installs deny-by-default iptables for each registered
container, allowing only the run's ``egress_allowlist`` hosts. The PoC
container itself stays ``--cap-drop=ALL`` and can NEVER touch iptables.

Fail-closed contract (the core safety invariant): if the egress gate is
unset or unreachable, ``run()`` refuses LOUDLY (``RuntimeError``) BEFORE any
networked container is started. It NEVER silently runs a container whose
egress is unenforced. The only bypass is ``BS_SANDBOX_DOCKER_FORCE=1`` for
CI image-smoke, and that path forces ``--network none`` (no egress at all).

Race-free sequence:
    1. ``docker create``  — container exists but is NOT running (zero traffic).
    2. gate ``/register``  — iptables installed for the container's IP.
    3. ``docker start -a`` — payload runs with rules already live.
    4. gate ``/report``    — populate blocked_egress / egress_attempts.
    5. ``/deregister`` + ``rm -f`` in ``finally`` — no orphans, no stale rules.
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import ipaddress
import os
import time
import uuid

import httpx

from sandbox_mcp.types import (
    DEFAULT_TIMEOUT_SEC,
    MAX_OUTPUT_BYTES,
    MAX_TIMEOUT_SEC,
    RunRequest,
    RunResult,
    Verdict,
)

# Env keys.
EGRESS_GATE_ENV = "BS_EGRESS_GATE_URL"
DOCKER_FORCE_ENV = "BS_SANDBOX_DOCKER_FORCE"
DEFAULT_IMAGE_ENV = "SANDBOX_DOCKER_IMAGE"
SANDBOX_NETWORK_ENV = "BS_SANDBOX_NETWORK"

# Import-time snapshots (live reads happen inside run() so tests can
# monkeypatch the env without reloading the module).
EGRESS_GATE_URL = os.environ.get(EGRESS_GATE_ENV, "")
DEFAULT_IMAGE = os.environ.get(DEFAULT_IMAGE_ENV, "bs5/sandbox-runtime:0.1.0")

_DOCKER_BIN = "docker"
_PIDS_LIMIT = 256
_MEMORY = "512m"
_GATE_TIMEOUT = 5.0
_DRAIN_TIMEOUT = 2.0

# Streaming chunk size — bounded peak memory, prompt cap checks.
# (Pattern duplicated from drivers/local.py — boundaries forbid editing
# local.py to extract a shared util, so it is re-stated here verbatim.)
_READ_CHUNK_BYTES = 8192


async def _bounded_read(reader, max_bytes: int) -> bytes:
    """Read up to ``max_bytes`` from ``reader``; drain the rest so the OS
    pipe never blocks the subprocess.

    Duplicated from ``drivers/local.py`` (``_bounded_read``) — the two driver
    modules deliberately do not import each other's private names, and
    ``local.py`` is boundary-locked. A runaway PoC emitting many GB is capped
    at ``max_bytes`` per stream regardless of output volume.
    """
    buf = bytearray()
    overflow = 0
    while True:
        chunk = await reader.read(_READ_CHUNK_BYTES)
        if not chunk:
            break
        remaining = max_bytes - len(buf)
        if remaining > 0:
            buf.extend(chunk[:remaining])
        if remaining < len(chunk):
            overflow += len(chunk) - max(0, remaining)
    if overflow:
        marker = f"\n<TRUNCATED:{overflow} bytes>".encode()
        if len(buf) + len(marker) <= max_bytes:
            buf.extend(marker)
    return bytes(buf)


class DockerDriver:
    """Container-per-run sandbox driver with network-layer egress enforcement."""

    name = "docker"

    # -- docker CLI seam (monkeypatched in hermetic tests) -----------------

    async def _docker_exec(
        self,
        args: list[str],
        *,
        input_bytes: bytes | None = None,
        timeout_s: float | None = None,
        max_bytes: int | None = None,
    ) -> tuple[int | None, bytes, bytes, bool]:
        """Run ``docker <args>``. Returns ``(returncode, stdout, stderr,
        timed_out)``.

        With ``max_bytes`` the output is streamed + capped (used for the
        attached ``docker start -a``); ``timeout`` kills the container on
        expiry. Without ``max_bytes`` it is a simple ``communicate()`` (used
        for create / kill / rm / commit / inspect).
        """
        proc = await asyncio.create_subprocess_exec(
            _DOCKER_BIN,
            *args,
            stdin=asyncio.subprocess.PIPE if input_bytes else None,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        if max_bytes is None:
            out, err = await proc.communicate(input=input_bytes)
            return proc.returncode, out or b"", err or b"", False

        stdout_task = asyncio.create_task(_bounded_read(proc.stdout, max_bytes))
        stderr_task = asyncio.create_task(_bounded_read(proc.stderr, max_bytes))

        if input_bytes and proc.stdin is not None:
            with contextlib.suppress(Exception):
                proc.stdin.write(input_bytes)
                await proc.stdin.drain()
                proc.stdin.close()

        timed_out = False
        try:
            await asyncio.wait_for(proc.wait(), timeout=timeout_s)
        except TimeoutError:
            proc.kill()
            with contextlib.suppress(Exception):
                await proc.wait()
            timed_out = True

        try:
            out = await asyncio.wait_for(stdout_task, timeout=_DRAIN_TIMEOUT)
        except Exception:
            stdout_task.cancel()
            out = b""
        try:
            err = await asyncio.wait_for(stderr_task, timeout=_DRAIN_TIMEOUT)
        except Exception:
            stderr_task.cancel()
            err = b""

        return proc.returncode, out, err, timed_out

    # -- egress-gate client (monkeypatched in hermetic tests) --------------

    async def _gate_healthz(self, gate_url: str) -> bool:
        try:
            async with httpx.AsyncClient(timeout=_GATE_TIMEOUT) as client:
                resp = await client.get(f"{gate_url.rstrip('/')}/healthz")
                return resp.status_code == 200
        except Exception:
            return False

    async def _gate_register(self, gate_url: str, container_id: str, allowlist: list[str]) -> None:
        async with httpx.AsyncClient(timeout=_GATE_TIMEOUT) as client:
            resp = await client.post(
                f"{gate_url.rstrip('/')}/register",
                json={"container_id": container_id, "egress_allowlist": allowlist},
            )
            resp.raise_for_status()

    async def _gate_deregister(self, gate_url: str, container_id: str) -> None:
        async with httpx.AsyncClient(timeout=_GATE_TIMEOUT) as client:
            resp = await client.post(
                f"{gate_url.rstrip('/')}/deregister",
                json={"container_id": container_id},
            )
            resp.raise_for_status()

    async def _gate_report(self, gate_url: str, container_id: str) -> dict:
        async with httpx.AsyncClient(timeout=_GATE_TIMEOUT) as client:
            resp = await client.get(f"{gate_url.rstrip('/')}/report/{container_id}")
            resp.raise_for_status()
            data = resp.json()
            return data if isinstance(data, dict) else {}

    # -- helpers -----------------------------------------------------------

    def _error_result(
        self, request: RunRequest, run_id: str, started: float, message: str
    ) -> RunResult:
        return RunResult(
            verdict=Verdict.ERROR,
            finding_id=request.finding_id,
            run_id=run_id,
            duration_ms=int((time.monotonic() - started) * 1000),
            stdout="",
            stderr="",
            exit_code=None,
            content_hash_hex=hashlib.sha256(b"").hexdigest(),
            egress_attempts=(),
            blocked_egress=(),
            error=message,
        )

    async def _reserve_ip(self, network: str, run_id: str, attempt: int) -> str | None:
        """Deterministic in-subnet IP to pin via ``--ip`` at container create.

        Bridge IPs are only assigned at ``docker start``; the egress gate must
        install iptables at ``/register`` (BEFORE start) and resolves the
        container's IP from ``IPAMConfig.IPv4Address``, which is populated at
        create only when ``--ip`` is supplied. Derive a stable host address
        from ``run_id`` so the value is collision-resistant across concurrent
        runs; ``attempt`` shifts the host octet to retry on an IP clash.
        Returns ``None`` when the subnet cannot be read or is too small, in
        which case the caller creates without ``--ip`` (legacy behaviour).
        """
        rc, out, _err, _ = await self._docker_exec(
            ["network", "inspect", "-f", "{{range .IPAM.Config}}{{.Subnet}}{{end}}", network]
        )
        sub = out.decode("utf-8", "replace").strip()
        if rc != 0 or not sub:
            return None
        try:
            net = ipaddress.ip_network(sub, strict=False)
        except ValueError:
            return None
        span = net.num_addresses
        if span <= 64:
            return None
        h = int(hashlib.sha256(run_id.encode()).hexdigest(), 16)
        # Host offset in [32, span-2]: skip the gateway / low reserved and the
        # broadcast address. +attempt walks forward on collision.
        offset = 32 + ((h + attempt) % (span - 64))
        return str(net.network_address + offset)

    # -- driver protocol ---------------------------------------------------

    async def run(self, request: RunRequest) -> RunResult:
        started = time.monotonic()
        run_id = f"docker-{uuid.uuid4().hex[:12]}"
        force = os.environ.get(DOCKER_FORCE_ENV) == "1"
        gate_url = (os.environ.get(EGRESS_GATE_ENV) or "").strip()

        # --- Fail-closed preflight (BEFORE any networked container) -------
        if not force:
            if not gate_url:
                raise RuntimeError(
                    f"DockerDriver fail-closed: {EGRESS_GATE_ENV} is unset. The "
                    "egress allowlist cannot be enforced without the "
                    "bs5-egress-gate sidecar, and this driver NEVER runs a "
                    "networked container with unenforced egress. Set "
                    f"{EGRESS_GATE_ENV}, or {DOCKER_FORCE_ENV}=1 for "
                    "network-isolated CI image-smoke only."
                )
            if not await self._gate_healthz(gate_url):
                raise RuntimeError(
                    f"DockerDriver fail-closed: egress gate at {gate_url} is "
                    "unreachable. Refusing to start a networked container "
                    "without a confirmed egress gate."
                )

        timeout = max(1, min(MAX_TIMEOUT_SEC, request.timeout_sec or DEFAULT_TIMEOUT_SEC))
        image = os.environ.get(DEFAULT_IMAGE_ENV) or DEFAULT_IMAGE
        network = "none" if force else (os.environ.get(SANDBOX_NETWORK_ENV) or "sandbox")
        name = f"bs5-sbx-{run_id}"

        container_id = ""
        registered = False
        try:
            # Restricted env: PATH only + request.env (str values only).
            env_args: list[str] = [
                "-e",
                f"PATH={os.environ.get('PATH', '/usr/local/bin:/usr/bin:/bin')}",
            ]
            for key, val in (request.env or {}).items():
                if isinstance(val, str):
                    env_args += ["-e", f"{key}={val}"]

            base_create = [
                "create",
                "--name",
                name,
                "--label",
                f"bs5.finding_id={request.finding_id}",
                "--label",
                f"bs5.run_id={run_id}",
                "--cap-drop=ALL",
                "--security-opt",
                "no-new-privileges",
                "--pids-limit",
                str(_PIDS_LIMIT),
                "--memory",
                _MEMORY,
                "--memory-swap",
                _MEMORY,
                "--read-only",
                "--tmpfs",
                "/tmp:rw,size=64m",
                "--network",
                network,
            ]
            tail_create = [*env_args, image, "sh", "-c", request.command]

            # Pin a static in-subnet --ip so the gate can install iptables at
            # /register, BEFORE `docker start`. Bridge IPs bind at start, but
            # --ip surfaces IPAMConfig.IPv4Address at create — which the gate
            # reads — keeping the register-before-start sequence race-free.
            # `--network none` (force / CI smoke) has no egress, so skip.
            out = b""
            err = b""
            rc = -1
            container_id = ""
            for attempt in range(4):
                ip_args: list[str] = []
                if network != "none":
                    cand = await self._reserve_ip(network, run_id, attempt)
                    if cand:
                        ip_args = ["--ip", cand]
                rc, out, err, _ = await self._docker_exec([*base_create, *ip_args, *tail_create])
                if rc == 0 and out.strip():
                    container_id = out.decode("utf-8", "replace").strip().splitlines()[-1]
                    break
                # IP collision → drop the half-created name, bump octet, retry.
                if ip_args and b"address already in use" in err.lower():
                    with contextlib.suppress(Exception):
                        await self._docker_exec(["rm", "-f", name])
                    continue
                return self._error_result(
                    request,
                    run_id,
                    started,
                    f"docker create failed (rc={rc}): {err.decode('utf-8', 'replace')[:500]}",
                )
            if not container_id:
                return self._error_result(
                    request,
                    run_id,
                    started,
                    "docker create failed: no free sandbox IP after 4 attempts",
                )

            # Install deny-by-default iptables BEFORE the payload runs. If the
            # gate is now unreachable the register raises → we never start the
            # container (still fail-closed: created != running, zero traffic).
            if not force:
                await self._gate_register(gate_url, container_id, list(request.egress_allowlist))
                registered = True

            rc, stdout_b, stderr_b, timed_out = await self._docker_exec(
                ["start", "-a", container_id],
                input_bytes=request.stdin_bytes,
                timeout_s=timeout,
                max_bytes=MAX_OUTPUT_BYTES,
            )

            if timed_out:
                with contextlib.suppress(Exception):
                    await self._docker_exec(["kill", container_id])
                verdict = Verdict.TIMEOUT
                exit_code = None
            else:
                exit_code = rc
                verdict = Verdict.SUCCESS if rc == 0 else Verdict.CRASH

            blocked: tuple[str, ...] = ()
            attempts: tuple[dict, ...] = ()
            if registered:
                with contextlib.suppress(Exception):
                    report = await self._gate_report(gate_url, container_id)
                    blocked = tuple(report.get("blocked") or ())
                    attempts = tuple(report.get("attempts") or ())
                # A run that failed AND hit only blocked hosts is an egress
                # block, not a generic crash (AC-2).
                if blocked and verdict == Verdict.CRASH:
                    verdict = Verdict.EGRESS_BLOCKED

            stdout_b = stdout_b[:MAX_OUTPUT_BYTES]
            stderr_b = stderr_b[:MAX_OUTPUT_BYTES]
            content_hash_hex = hashlib.sha256(stdout_b + stderr_b).hexdigest()

            return RunResult(
                verdict=verdict,
                finding_id=request.finding_id,
                run_id=run_id,
                duration_ms=int((time.monotonic() - started) * 1000),
                stdout=stdout_b.decode("utf-8", "replace"),
                stderr=stderr_b.decode("utf-8", "replace"),
                exit_code=exit_code,
                content_hash_hex=content_hash_hex,
                egress_attempts=attempts,
                blocked_egress=blocked,
                error=None,
            )
        except Exception as exc:
            return self._error_result(request, run_id, started, f"{type(exc).__name__}: {exc}")
        finally:
            # Always release iptables + remove the container — no orphans, no
            # stale rules — even on exception (AC-3).
            if registered and gate_url and container_id:
                with contextlib.suppress(Exception):
                    await self._gate_deregister(gate_url, container_id)
            if container_id and request.cleanup:
                with contextlib.suppress(Exception):
                    await self._docker_exec(["rm", "-f", container_id])

    async def snapshot(self, run_id: str) -> dict:
        """Commit the (stopped) container's filesystem to a content image.

        Minimal by design — full snapshot tooling (R2 upload, content
        addressing) is out of scope. If ``cleanup`` already removed the
        container, the commit fails and we report ``{supported: False}``.
        """
        name = f"bs5-sbx-{run_id}"
        with contextlib.suppress(Exception):
            rc, out, _err, _ = await self._docker_exec(["commit", name])
            if rc == 0 and out.strip():
                return {
                    "supported": True,
                    "run_id": run_id,
                    "driver": self.name,
                    "image_id": out.decode("utf-8", "replace").strip(),
                }
        return {"supported": False, "run_id": run_id, "driver": self.name}


__all__ = [
    "DEFAULT_IMAGE",
    "DOCKER_FORCE_ENV",
    "DockerDriver",
    "EGRESS_GATE_ENV",
    "EGRESS_GATE_URL",
]
