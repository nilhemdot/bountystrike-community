# SPDX-License-Identifier: AGPL-3.0-or-later

"""Reflection-probe concrete implementations.

The ``ReflectionProber`` Protocol lives in :mod:`.service` next to the
service that consumes it. Concrete implementations live here so callers
outside the recon runtime (e.g. ``scripts/filter_unreflected_findings.py``)
can import them without dragging the recon CLI's ``__main__`` import
graph (asyncpg, scope JWT validator, etc.).
"""

from __future__ import annotations

import httpx

DEFAULT_TIMEOUT_SEC = 8.0


class HttpxReflectionProber:
    """Production reflection prober — single GET, substring match.

    Uses a short timeout so slow targets default to "no reflection" (drop).
    The exploit-agent's WebFetch probe is the catch-net for borderline cases
    flagged by validator; this prober's job is to drop the obvious FPs.
    """

    name = "httpx"

    def __init__(self, timeout_sec: float = DEFAULT_TIMEOUT_SEC) -> None:
        self._timeout_sec = timeout_sec

    async def probe(self, url: str, parameter: str, sentinel: str) -> bool:
        del parameter  # only the URL + sentinel matter for substring check
        async with httpx.AsyncClient(
            timeout=self._timeout_sec, follow_redirects=True
        ) as client:
            response = await client.get(url)
            return sentinel in response.text


__all__ = ["DEFAULT_TIMEOUT_SEC", "HttpxReflectionProber"]
