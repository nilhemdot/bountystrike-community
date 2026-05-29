# SPDX-License-Identifier: AGPL-3.0-or-later

"""Simplified Interactsh client (HTTP-only, no RSA/AES).

The upstream Interactsh protocol (https://github.com/projectdiscovery/interactsh)
encrypts polled interactions with a per-client RSA keypair. Implementing
the full protocol pulls in ASN.1 parsing, AES-CFB, secret pinning, and
OOB DNS server registration — overkill for Phase 1 verification probes.

This stub instead assumes a *trusted* Interactsh server (or a
BountyStrike-controlled callback collector) reachable over HTTPS that
exposes:

- ``GET  /register?token=<random>``      → 200 if accepted
- ``GET  /poll?token=<random>``          → JSON ``{"data": [Interaction…]}``
- ``GET  /deregister?token=<random>``   → 200

For the real production deployment, swap this implementation for the
full Interactsh client (or run our own collector with a self-signed cert
pinned via ``INTERACTSH_PUBLIC_KEY``). All oracles depend only on this
narrow async interface, so the swap is local.

Env:
    INTERACTSH_SERVER_URL — default ``https://oast.fun``
    INTERACTSH_TOKEN_PREFIX — default ``bs``
"""

from __future__ import annotations

import asyncio
import os
import secrets
import time
from dataclasses import dataclass, field
from typing import Any

import httpx
import structlog

log = structlog.get_logger("oracle_mcp.oast")

DEFAULT_SERVER = os.environ.get("INTERACTSH_SERVER_URL", "https://oast.fun")
DEFAULT_PREFIX = os.environ.get("INTERACTSH_TOKEN_PREFIX", "bs")


def _server_supports_subdomain_callbacks(server_url: str) -> bool:
    """Heuristic: only real DNS hostnames can host wildcard subdomain callbacks.

    Local OAST collectors running on ``127.0.0.1`` / ``localhost`` cannot
    receive a request to ``<token>.127.0.0.1`` (DNS won't resolve), so we
    fall back to a path-based callback that the collector handles at
    ``/cb/<token>``.
    """
    host = server_url.removeprefix("https://").removeprefix("http://")
    host_only = host.split("/", 1)[0].split(":", 1)[0]
    if not host_only:
        return False
    if host_only in {"localhost", "127.0.0.1", "::1"}:
        return False
    # Bare IP literal (no letters) ⇒ no DNS ⇒ path callback.
    return not all(ch.isdigit() or ch == "." for ch in host_only)


@dataclass(frozen=True, slots=True)
class InteractshToken:
    """Opaque handle returned by ``register_token``."""

    token: str
    server: str
    registered_at: float

    @property
    def _supports_subdomain(self) -> bool:
        return _server_supports_subdomain_callbacks(self.server)

    @property
    def callback_url(self) -> str:
        """HTTP callback URL embedded in payloads (e.g. for SSRF/RCE OOB).

        Subdomain form for real OAST hosts (``http://<tok>.oast.fun``);
        path form for localhost / IP-only collectors
        (``http://127.0.0.1:5097/cb/<tok>``) where wildcard DNS is
        unavailable.
        """
        host = self.server.removeprefix("https://").removeprefix("http://")
        host_with_port = host.split("/", 1)[0]
        if self._supports_subdomain:
            return f"http://{self.token}.{host_with_port}"
        scheme = "https" if self.server.startswith("https://") else "http"
        return f"{scheme}://{host_with_port}/cb/{self.token}"

    @property
    def callback_host(self) -> str:
        host = self.server.removeprefix("https://").removeprefix("http://")
        host_with_port = host.split("/", 1)[0]
        if self._supports_subdomain:
            return f"{self.token}.{host_with_port}"
        return host_with_port


@dataclass(frozen=True, slots=True)
class Interaction:
    """Single OOB interaction (HTTP request, DNS query, …) seen by Interactsh."""

    interaction_type: str  # "http" | "dns" | "smtp"
    source_ip: str
    timestamp: str
    raw_request: str = ""
    path: str = ""
    extra: dict[str, Any] = field(default_factory=dict)


class InteractshClient:
    """Minimal async Interactsh client.

    Parameters:
        server_url: e.g. ``https://oast.fun`` (Project Discovery's public
            shared instance). Override via ``INTERACTSH_SERVER_URL``.
        http_client: optional pre-built ``httpx.AsyncClient`` (for tests).
    """

    def __init__(
        self,
        server_url: str = DEFAULT_SERVER,
        http_client: httpx.AsyncClient | None = None,
        token_prefix: str = DEFAULT_PREFIX,
    ) -> None:
        self.server_url = server_url.rstrip("/")
        self._client = http_client
        self._owns_client = http_client is None
        self._token_prefix = token_prefix

    async def __aenter__(self) -> InteractshClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=10.0)
            self._owns_client = True
        return self

    async def __aexit__(self, *exc: Any) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()
            self._client = None

    def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=10.0)
            self._owns_client = True
        return self._client

    async def register_token(self) -> InteractshToken:
        """Register a fresh token on the server.

        Tokens are 24 hex chars prefixed with ``bs`` so they're easy to
        spot in target-side logs during incident debriefs.
        """
        token_value = f"{self._token_prefix}{secrets.token_hex(12)}"
        client = self._ensure_client()
        try:
            r = await client.get(
                f"{self.server_url}/register",
                params={"token": token_value},
            )
            # Many simplified collectors return 200/204; we tolerate both.
            if r.status_code >= 500:
                r.raise_for_status()
        except httpx.HTTPError as exc:
            # Soft-fail: registration is informational on simple stubs.
            log.warning(
                "interactsh.register.soft_fail",
                error=str(exc),
                server=self.server_url,
            )
        return InteractshToken(
            token=token_value,
            server=self.server_url,
            registered_at=time.time(),
        )

    async def poll_interactions(
        self,
        token: InteractshToken,
        timeout: float = 20.0,  # noqa: ASYNC109 - timeout is part of the public oracle contract
        interaction_types: tuple[str, ...] = ("http", "dns"),
        poll_interval: float = 1.5,
    ) -> list[Interaction]:
        """Poll for interactions until ``timeout`` elapses.

        Returns the accumulated list (possibly empty). Stops early once
        any matching interaction is observed — enough evidence for the
        oracle.
        """
        client = self._ensure_client()
        deadline = time.monotonic() + timeout
        seen: list[Interaction] = []

        while time.monotonic() < deadline:
            try:
                r = await client.get(
                    f"{self.server_url}/poll",
                    params={"token": token.token},
                )
            except httpx.HTTPError as exc:
                log.debug("interactsh.poll.error", error=str(exc))
                await asyncio.sleep(poll_interval)
                continue

            if r.status_code == 200:
                try:
                    payload = r.json()
                except ValueError:
                    payload = {}
                for raw in payload.get("data", []) or []:
                    interaction = _parse_interaction(raw)
                    if interaction is None:
                        continue
                    if interaction.interaction_type in interaction_types:
                        seen.append(interaction)
                if seen:
                    return seen

            await asyncio.sleep(poll_interval)

        return seen

    async def deregister(self, token: InteractshToken) -> None:
        """Best-effort deregister; failures are logged, not raised."""
        client = self._ensure_client()
        try:
            await client.get(
                f"{self.server_url}/deregister",
                params={"token": token.token},
            )
        except httpx.HTTPError as exc:
            log.debug("interactsh.deregister.soft_fail", error=str(exc))


def _parse_interaction(raw: dict[str, Any]) -> Interaction | None:
    """Normalize a single poll-server entry into ``Interaction``."""
    if not isinstance(raw, dict):
        return None
    itype = (
        raw.get("protocol")
        or raw.get("interaction_type")
        or raw.get("type")
        or "http"
    ).lower()
    return Interaction(
        interaction_type=itype,
        source_ip=str(raw.get("remote-address") or raw.get("source_ip") or ""),
        timestamp=str(raw.get("timestamp") or raw.get("ts") or ""),
        raw_request=str(raw.get("raw-request") or raw.get("raw_request") or ""),
        path=str(raw.get("path") or ""),
        extra={
            k: v
            for k, v in raw.items()
            if k
            not in {
                "protocol",
                "type",
                "interaction_type",
                "remote-address",
                "source_ip",
                "timestamp",
                "ts",
                "raw-request",
                "raw_request",
                "path",
            }
        },
    )


_DEFAULT_CLIENT: InteractshClient | None = None


def get_default_client() -> InteractshClient:
    """Lazy-built shared client (per-process)."""
    global _DEFAULT_CLIENT
    if _DEFAULT_CLIENT is None:
        _DEFAULT_CLIENT = InteractshClient()
    return _DEFAULT_CLIENT
