# SPDX-License-Identifier: AGPL-3.0-or-later

"""ProjectDiscovery toolchain wrappers (subfinder, httpx, katana).

Each wrapper shells out via :func:`asyncio.create_subprocess_exec`,
streams JSONL on stdout, and yields parsed dataclasses. The toolchain
binaries are NOT invoked directly by callers — :class:`ReconService`
goes through the :class:`BinaryRunner` Protocol so tests can replace
the runner with a fake that yields canned JSONL.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Iterable
from dataclasses import dataclass
from typing import Any, Protocol


class SubprocessError(RuntimeError):
    """Raised when an external binary exits non-zero or emits invalid JSON."""


# ---------------------------------------------------------------------------
# Result dataclasses (light — full schema kept inside JSONL strings)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class HttpxProbe:
    """One row from `httpx -json`."""

    url: str
    host: str
    status_code: int
    title: str
    tech: tuple[str, ...]
    raw: dict[str, Any]


@dataclass(frozen=True, slots=True)
class KatanaEndpoint:
    """One row from `katana -jsonl`."""

    url: str
    method: str
    parameters: tuple[str, ...]
    raw: dict[str, Any]


# ---------------------------------------------------------------------------
# Runner protocol
# ---------------------------------------------------------------------------


class BinaryRunner(Protocol):
    """Adapter the service depends on — production = subprocess, tests = fake."""

    async def subfinder(self, domain: str, rps: int) -> list[str]: ...

    async def httpx(self, hosts: Iterable[str], rps: int) -> list[HttpxProbe]: ...

    async def katana(
        self,
        urls: Iterable[str],
        rps: int,
        scope_regex: str,
    ) -> list[KatanaEndpoint]: ...


# ---------------------------------------------------------------------------
# Real implementation (asyncio.create_subprocess_exec)
# ---------------------------------------------------------------------------


async def _run_jsonl(args: list[str], stdin: bytes | None = None) -> AsyncIterator[dict]:
    """Run *args*, yield each parsed JSON line on stdout. Raises on non-zero exit."""
    proc = await asyncio.create_subprocess_exec(
        *args,
        stdin=asyncio.subprocess.PIPE if stdin is not None else asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate(input=stdin)
    if proc.returncode != 0:
        raise SubprocessError(
            f"{args[0]} exited {proc.returncode}: {stderr.decode(errors='replace')!r}"
        )
    out: list[dict] = []
    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise SubprocessError(f"{args[0]} non-JSON line: {line!r}") from exc

    async def _gen() -> AsyncIterator[dict]:
        for row in out:
            yield row

    return _gen()  # type: ignore[return-value]


class RealBinaryRunner:
    """Production runner — shells out to PATH-installed PD binaries."""

    def __init__(
        self,
        subfinder_bin: str = "subfinder",
        httpx_bin: str = "httpx",
        katana_bin: str = "katana",
    ) -> None:
        self.subfinder_bin = subfinder_bin
        self.httpx_bin = httpx_bin
        self.katana_bin = katana_bin

    async def subfinder(self, domain: str, rps: int) -> list[str]:
        del rps  # subfinder has no RPS knob — passive sources cap themselves.
        gen = await _run_jsonl(
            [self.subfinder_bin, "-d", domain, "-silent", "-all", "-json"]
        )
        rows = [row async for row in gen]
        return [r["host"] for r in rows if "host" in r]

    async def httpx(self, hosts: Iterable[str], rps: int) -> list[HttpxProbe]:
        host_list = list(hosts)
        if not host_list:
            return []
        stdin_bytes = ("\n".join(host_list) + "\n").encode()
        gen = await _run_jsonl(
            [
                self.httpx_bin,
                "-silent", "-json", "-title", "-tech-detect",
                "-status-code", "-content-length",
                "-ports", "80,443",
                "-threads", "25",
                "-rate-limit", str(rps),
            ],
            stdin=stdin_bytes,
        )
        out: list[HttpxProbe] = []
        async for row in gen:
            out.append(_to_httpx_probe(row))
        return out

    async def katana(
        self,
        urls: Iterable[str],
        rps: int,
        scope_regex: str,
    ) -> list[KatanaEndpoint]:
        url_list = list(urls)
        if not url_list:
            return []
        stdin_bytes = ("\n".join(url_list) + "\n").encode()
        args = [
            self.katana_bin,
            "-silent", "-jsonl",
            "-depth", "3",
            "-strategy", "breadth-first",
            "-rate-limit", str(rps),
            "-known-files", "robotstxt,sitemapxml",
            "-form-extraction",
        ]
        if scope_regex:
            args.extend(["-scope", scope_regex])
        gen = await _run_jsonl(args, stdin=stdin_bytes)
        out: list[KatanaEndpoint] = []
        async for row in gen:
            out.append(_to_katana_endpoint(row))
        return out


# ---------------------------------------------------------------------------
# Row → dataclass coercion (tolerant of schema drift across PD versions)
# ---------------------------------------------------------------------------


def _to_httpx_probe(row: dict) -> HttpxProbe:
    url = str(row.get("url") or row.get("input") or "")
    host = str(row.get("host") or row.get("input") or "")
    status_raw = row.get("status_code") or row.get("status-code") or 0
    tech = row.get("tech") or row.get("technologies") or ()
    return HttpxProbe(
        url=url,
        host=host,
        status_code=int(status_raw or 0),
        title=str(row.get("title") or ""),
        tech=tuple(str(t) for t in tech),
        raw=row,
    )


def _to_katana_endpoint(row: dict) -> KatanaEndpoint:
    request = row.get("request") or {}
    url = str(request.get("endpoint") or row.get("url") or "")
    method = str(request.get("method") or "GET").upper()
    params: list[str] = []
    body = request.get("body") or {}
    if isinstance(body, dict):
        params.extend(str(k) for k in body)
    # katana also exposes form fields under `form_data` and query params via
    # the URL itself; the URL parsing is the validator-agent's job.
    form_data = request.get("form_data") or request.get("form-data") or []
    if isinstance(form_data, list):
        for entry in form_data:
            if isinstance(entry, dict) and "name" in entry:
                params.append(str(entry["name"]))
    return KatanaEndpoint(
        url=url,
        method=method,
        parameters=tuple(dict.fromkeys(params)),  # de-dup, preserve order
        raw=row,
    )


__all__ = [
    "BinaryRunner",
    "HttpxProbe",
    "KatanaEndpoint",
    "RealBinaryRunner",
    "SubprocessError",
]
