"""Defence-in-depth checks for caller-supplied URLs.

The submission MCP attaches a Bearer token to every outbound request when
``IMMUNEFI_API_TOKEN`` is set. The reporter-agent path can also accept a
caller-supplied ``submit_url`` (per-programme relays — Cantina,
Code4rena-style). Without a guard:

  - An LLM-driven caller can be social-engineered into POSTing the full
    PoC + asset details + Bearer token to an attacker-controlled URL.
  - A misconfigured ``IMMUNEFI_BASE_URL`` env (HTTP proxy, redirect-
    swallowing CDN) can do the same passively.

This module is the seam where the URL is checked. Its policy:

  - https only in production (allow_http only for tests).
  - Reject ``file://``, ``gopher://``, ``ftp://``, ``ldap://``, etc.
  - Reject cloud-metadata hostnames (AWS / GCP / Azure / Alibaba).
  - Reject loopback / link-local / private / multicast IP literals.

Plus a host-match helper the request layer uses to decide whether the
``Authorization`` header is safe to attach.
"""

from __future__ import annotations

import ipaddress
from urllib.parse import urlparse

# Cloud-metadata service hostnames + IPs.
DENIED_HOSTS: frozenset[str] = frozenset({
    "169.254.169.254",          # AWS / OpenStack IMDS
    "metadata.google.internal",  # GCP
    "metadata.azure.com",        # Azure
    "100.100.100.200",           # Alibaba
    "169.254.170.2",             # AWS ECS task metadata
    "fd00:ec2::254",             # AWS IPv6 IMDS
})

ALLOWED_SCHEMES_PROD: frozenset[str] = frozenset({"https"})
ALLOWED_SCHEMES_DEV: frozenset[str] = frozenset({"https", "http"})


class UrlGuardError(ValueError):
    """Raised when a caller-supplied URL fails the guard."""


def _host_of(url: str) -> str:
    return (urlparse(url).hostname or "").lower()


def host_of(url: str) -> str:
    """Public alias — used by the request layer for header decisions."""
    return _host_of(url)


def hosts_match(url_a: str, url_b: str) -> bool:
    """True iff both URLs target the same host (case-insensitive)."""
    return _host_of(url_a) == _host_of(url_b) and bool(_host_of(url_a))


def validate_target_url(url: str, *, allow_http: bool = False) -> None:
    """Raise :class:`UrlGuardError` if *url* fails the policy.

    Returns None on pass. The function is silent on success so callers
    can chain it before the actual request.

    Args:
        url: The URL to check.
        allow_http: When True, ``http://`` is accepted (for tests
            against local httpbin / respx mocks). Production callers
            never set this — the default is https-only.
    """
    if not url:
        raise UrlGuardError("empty url")

    parsed = urlparse(url)

    allowed = ALLOWED_SCHEMES_DEV if allow_http else ALLOWED_SCHEMES_PROD
    if parsed.scheme.lower() not in allowed:
        raise UrlGuardError(
            f"scheme {parsed.scheme!r} not allowed; need one of {sorted(allowed)}"
        )

    host = (parsed.hostname or "").lower()
    if not host:
        raise UrlGuardError("url has no host")

    if host in DENIED_HOSTS:
        raise UrlGuardError(f"host {host!r} is a cloud-metadata endpoint")

    # IP-literal hosts: reject loopback / link-local / private / multicast
    # / unspecified. Reserved (240.0.0.0/4) is also rejected because a
    # caller is much more likely to be testing a typo than legitimately
    # POSTing to a CGN address.
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        ip = None
    if ip is not None:
        # Loopback is allowed when allow_http=True (test harness path),
        # but never in production.
        if ip.is_loopback and not allow_http:
            raise UrlGuardError(
                f"host {host!r} is loopback; production submission must use a public host"
            )
        if not ip.is_loopback and (
            ip.is_link_local
            or ip.is_private
            or ip.is_multicast
            or ip.is_unspecified
            or ip.is_reserved
        ):
            raise UrlGuardError(
                f"host {host!r} is private / link-local / reserved"
            )


__all__ = [
    "ALLOWED_SCHEMES_DEV",
    "ALLOWED_SCHEMES_PROD",
    "DENIED_HOSTS",
    "UrlGuardError",
    "host_of",
    "hosts_match",
    "validate_target_url",
]
