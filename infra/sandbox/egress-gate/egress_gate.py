# SPDX-License-Identifier: AGPL-3.0-or-later

"""bs5-egress-gate — network-layer egress allowlist for sandbox containers.

The gate is the platform's core safety control: a sandboxed PoC must never
reach a host outside the authorised scope. Enforcement is at the network
layer (iptables), NOT the prompt layer — the PoC container is ``--cap-drop=ALL``
and cannot tamper with these rules; only this sidecar holds ``NET_ADMIN``.

Trust model
-----------
* This sidecar runs with ``NET_ADMIN`` on the host network namespace and has
  the docker socket mounted (read-only inspect). It installs per-container
  deny-by-default rules in docker's ``DOCKER-USER`` chain — the documented,
  docker-sanctioned hook that is traversed before docker's own ACCEPT rules.
  It never edits the host ``INPUT``/``OUTPUT`` policy or any non-docker chain.
* The PoC container holds NO network capabilities. It cannot add/remove rules.

Per container we create a chain ``BS5_<cid12>``:
    ESTABLISHED,RELATED  -> ACCEPT   (return traffic for allowed flows)
    udp/tcp dport 53     -> ACCEPT   (DNS resolution)
    -d <allowed_ip> 80/443 -> ACCEPT (each allowlisted host's resolved IPs)
    LOG (prefix BS5B_<cid12>)        (record blocked attempts)
    -j DROP                          (deny-by-default catch-all)
and jump into it from ``DOCKER-USER`` for the container's source IP.

Endpoints
---------
    POST /register    {container_id, egress_allowlist: [host,...]}
    POST /deregister  {container_id}
    GET  /report/{container_id}  -> {blocked: [...], attempts: [...]}
    GET  /healthz                -> {"status": "ok"}
"""

from __future__ import annotations

import asyncio
import ipaddress
import re
import socket

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

app = FastAPI(title="bs5-egress-gate")

# container_id -> {chain, ip, allowlist, allowed_ips}
_REGISTRY: dict[str, dict] = {}
_LOCK = asyncio.Lock()

_CID_RE = re.compile(r"^[a-zA-Z0-9_.-]+$")


class RegisterBody(BaseModel):
    container_id: str = Field(min_length=1, max_length=128)
    egress_allowlist: list[str] = Field(default_factory=list)


class DeregisterBody(BaseModel):
    container_id: str = Field(min_length=1, max_length=128)


def _chain_for(container_id: str) -> str:
    return f"BS5_{container_id[:12]}"


def _log_prefix(container_id: str) -> str:
    return f"BS5B_{container_id[:12]}"


async def _run(*args: str) -> tuple[int, str, str]:
    proc = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    out, err = await proc.communicate()
    return (
        proc.returncode or 0,
        out.decode("utf-8", "replace"),
        err.decode("utf-8", "replace"),
    )


async def _ipt(*args: str) -> tuple[int, str, str]:
    return await _run("iptables", *args)


async def _container_ip(container_id: str) -> str:
    rc, out, err = await _run(
        "docker",
        "inspect",
        "-f",
        # IPAMConfig.IPv4Address holds the static --ip pinned at CREATE and is
        # readable BEFORE `docker start`; .IPAddress is only populated AFTER the
        # container starts. Emit both (reserved first) so register-before-start
        # resolves to the pinned IP without waiting for the container to run.
        "{{range .NetworkSettings.Networks}}"
        "{{if .IPAMConfig}}{{.IPAMConfig.IPv4Address}}{{end}} {{.IPAddress}} "
        "{{end}}",
        container_id,
    )
    if rc != 0:
        raise HTTPException(status_code=404, detail=f"docker inspect failed: {err.strip()}")
    # Templating empty IP fields can yield junk tokens ("<nil>", "invalid IP");
    # accept only the first token that parses as a real IPv4 address.
    for tok in out.split():
        try:
            ipaddress.IPv4Address(tok)
        except ValueError:
            continue
        return tok
    raise HTTPException(status_code=409, detail="container has no network IP yet")


def _resolve(host: str) -> set[str]:
    """Resolve a hostname to its IPv4 addresses (best-effort)."""
    out: set[str] = set()
    try:
        for info in socket.getaddrinfo(host, None, family=socket.AF_INET):
            out.add(info[4][0])
    except OSError:
        pass
    return out


async def _install(container_id: str, ip: str, allowed_ips: set[str]) -> str:
    chain = _chain_for(container_id)
    # Fresh chain (flush if a stale one exists).
    await _ipt("-N", chain)
    await _ipt("-F", chain)
    await _ipt("-A", chain, "-m", "conntrack", "--ctstate", "ESTABLISHED,RELATED", "-j", "ACCEPT")
    await _ipt("-A", chain, "-p", "udp", "--dport", "53", "-j", "ACCEPT")
    await _ipt("-A", chain, "-p", "tcp", "--dport", "53", "-j", "ACCEPT")
    for aip in sorted(allowed_ips):
        await _ipt(
            "-A",
            chain,
            "-d",
            aip,
            "-p",
            "tcp",
            "-m",
            "multiport",
            "--dports",
            "80,443",
            "-j",
            "ACCEPT",
        )
    await _ipt(
        "-A",
        chain,
        "-j",
        "LOG",
        "--log-prefix",
        f"{_log_prefix(container_id)} ",
        "--log-level",
        "4",
    )
    await _ipt("-A", chain, "-j", "DROP")
    # Jump from DOCKER-USER for this container's source IP (insert at top).
    await _ipt("-I", "DOCKER-USER", "-s", ip, "-j", chain)
    return chain


async def _teardown(container_id: str, ip: str) -> None:
    chain = _chain_for(container_id)
    # Order matters: remove the jump before flushing/deleting the chain.
    await _ipt("-D", "DOCKER-USER", "-s", ip, "-j", chain)
    await _ipt("-F", chain)
    await _ipt("-X", chain)


async def _drop_count(chain: str) -> int:
    rc, out, _err = await _ipt("-vnxL", chain)
    if rc != 0:
        return 0
    for line in out.splitlines():
        parts = line.split()
        # `-vnx` columns: pkts bytes target prot ...
        if len(parts) >= 3 and parts[2] == "DROP":
            try:
                return int(parts[0])
            except ValueError:
                return 0
    return 0


async def _blocked_dsts(container_id: str) -> list[str]:
    """Best-effort: parse kernel log for destinations this chain dropped.

    Reads from ``dmesg`` (gate has access to the host kernel ring buffer).
    Returns the unique blocked destination IPs. Falls back to empty when the
    log is unavailable — the DROP counter still drives the egress_blocked
    verdict in that case.
    """
    rc, out, _err = await _run("dmesg")
    if rc != 0:
        return []
    prefix = _log_prefix(container_id)
    dsts: list[str] = []
    for line in out.splitlines():
        if prefix not in line:
            continue
        m = re.search(r"DST=(\d+\.\d+\.\d+\.\d+)", line)
        if m and m.group(1) not in dsts:
            dsts.append(m.group(1))
    return dsts


@app.get("/healthz")
async def healthz() -> dict:
    return {"status": "ok", "registered": len(_REGISTRY)}


@app.post("/register")
async def register(body: RegisterBody) -> dict:
    cid = body.container_id
    if not _CID_RE.match(cid):
        raise HTTPException(status_code=400, detail="invalid container_id")
    allowed_ips: set[str] = set()
    for host in body.egress_allowlist:
        allowed_ips |= _resolve(host)
    async with _LOCK:
        ip = await _container_ip(cid)
        chain = await _install(cid, ip, allowed_ips)
        _REGISTRY[cid] = {
            "chain": chain,
            "ip": ip,
            "allowlist": list(body.egress_allowlist),
            "allowed_ips": sorted(allowed_ips),
        }
    return {"registered": cid, "ip": ip, "allowed_ips": sorted(allowed_ips)}


@app.post("/deregister")
async def deregister(body: DeregisterBody) -> dict:
    cid = body.container_id
    async with _LOCK:
        entry = _REGISTRY.pop(cid, None)
        if entry is None:
            return {"deregistered": cid, "noop": True}
        await _teardown(cid, entry["ip"])
    return {"deregistered": cid}


@app.get("/report/{container_id}")
async def report(container_id: str) -> dict:
    entry = _REGISTRY.get(container_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="unknown container_id")
    chain = entry["chain"]
    drops = await _drop_count(chain)
    blocked = await _blocked_dsts(container_id)
    # If the kernel log was unavailable but packets were dropped, still flag
    # that egress was blocked (without a resolved host name).
    if drops > 0 and not blocked:
        blocked = ["<blocked-destination>"]
    attempts = [{"dst": dst, "blocked": True} for dst in blocked]
    return {
        "container_id": container_id,
        "blocked": blocked,
        "attempts": attempts,
        "drop_count": drops,
        "allowed_ips": entry["allowed_ips"],
    }
