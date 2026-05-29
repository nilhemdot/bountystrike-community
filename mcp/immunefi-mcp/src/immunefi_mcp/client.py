# SPDX-License-Identifier: AGPL-3.0-or-later

"""Immunefi submission client.

Status: **programme-driven body shape.**

Immunefi (smart-contract bug bounty platform) does not publish a
universal submission JSON contract — many programmes have custom Vaults
flows, off-chain processes, or require Discord / email handoff. The
build-plan §reporter-agent reflects this::

    Use the Immunefi Vaults API. Submission format is programme-specific —
    fetch programme rules via `scope-mcp check_target` first.

This client therefore takes a fairly minimal canonical shape and lets
the caller pass an ``extra`` dict for programme-specific fields. The
endpoint and auth scheme are also overridable via ``submit_url`` /
``api_token`` so a programme that fronts its own collection endpoint
(e.g. via Cantina, Code4rena-style relay) can be reached through the
same MCP.

Default endpoint::

  POST {base_url}/v1/reports
    Authorization: Bearer <token>             (optional — many programmes
                                                accept anonymous + email)
    Content-Type: application/json
    Body:
      {
        "programme":          "<slug>",
        "title":              "<= 200 chars",
        "severity":           "informational|low|medium|high|critical",
        "asset_type":         "smart_contract|website_and_application|blockchain|other",
        "asset":              "<contract addr | URL>",
        "impact":             "<markdown>",
        "vulnerability_details": "<markdown>",
        "proof_of_concept":   "<markdown>",
        ...                   "<extra fields>"
      }

The submission is best-effort against this default shape; for a real
deployment, set ``IMMUNEFI_BASE_URL`` and verify the programme's
documented surface first. Tests lock the default contract.
"""

from __future__ import annotations

import json as _json
import os
from datetime import UTC
from typing import Any

import httpx

from immunefi_mcp._url_guard import (
    UrlGuardError,
    hosts_match,
    validate_target_url,
)

DEFAULT_BASE_URL = os.environ.get(
    "IMMUNEFI_BASE_URL", "https://api.immunefi.com"
)
DEFAULT_TIMEOUT_S = 30.0
# Cap on response body kept inside ImmunefiError.body. A misbehaving
# upstream (or hostile proxy) could echo multi-MB responses; without
# a cap, the body propagates into MCP stdio + agent transcripts.
MAX_ERROR_BODY_BYTES = 4096
# When True, the URL guard accepts http:// in addition to https:// and
# allows loopback IPs. Tests opt in by setting BS_PLATFORM_ALLOW_HTTP=1
# (e.g. for respx mocks against https URLs the flag has no effect, but
# integration suites against a local httpbin do).
_ALLOW_HTTP_BASE_URL = os.environ.get("BS_PLATFORM_ALLOW_HTTP") == "1"


def _truncate_body(body: Any) -> Any:
    """Cap body size to ``MAX_ERROR_BODY_BYTES``. JSON / dict bodies are
    serialised, truncated, and the truncation is signalled by a sentinel.
    Non-serialisable objects fall back to ``str(body)``."""
    if body is None:
        return None
    try:
        s = body if isinstance(body, str) else _json.dumps(body)
    except Exception:
        s = str(body)
    if len(s) <= MAX_ERROR_BODY_BYTES:
        return body if isinstance(body, (dict, list, str)) else s
    head = s[: MAX_ERROR_BODY_BYTES - 64]
    return f"{head}…<TRUNCATED:{len(s) - len(head)} bytes>"


RETRY_AFTER_CAP_SEC = 60


def _parse_retry_after(value: str) -> float | None:
    if not value:
        return None
    value = value.strip()
    try:
        secs = float(value)
        if secs < 0:
            return None
        return min(secs, RETRY_AFTER_CAP_SEC)
    except ValueError:
        try:
            from datetime import datetime
            from email.utils import parsedate_to_datetime

            target = parsedate_to_datetime(value)
            if target.tzinfo is None:
                target = target.replace(tzinfo=UTC)
            delta = (target - datetime.now(tz=UTC)).total_seconds()
            if delta < 0:
                return 0.0
            return min(delta, RETRY_AFTER_CAP_SEC)
        except Exception:
            return None

VALID_SEVERITIES: frozenset[str] = frozenset(
    {"informational", "low", "medium", "high", "critical"}
)
VALID_ASSET_TYPES: frozenset[str] = frozenset(
    {"smart_contract", "website_and_application", "blockchain", "other"}
)

MAX_RETRIES = 2
RETRY_BACKOFF_S = (0.5, 2.0)


class ImmunefiError(RuntimeError):
    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        body: Any = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.body = body


class ImmunefiClient:
    def __init__(
        self,
        api_token: str | None = None,
        base_url: str = DEFAULT_BASE_URL,
        timeout_s: float = DEFAULT_TIMEOUT_S,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        # Auth is OPTIONAL for Immunefi — many programmes accept
        # anonymous submissions. Read but don't require.
        self._token = api_token if api_token is not None else os.environ.get(
            "IMMUNEFI_API_TOKEN", ""
        )
        # base_url validation: a misconfigured IMMUNEFI_BASE_URL must not
        # silently become a credential exfil channel.
        validate_target_url(base_url, allow_http=_ALLOW_HTTP_BASE_URL)
        self._base_url = base_url.rstrip("/")
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(timeout=timeout_s)

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def __aenter__(self) -> ImmunefiClient:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.aclose()

    def _headers(self, *, attach_auth: bool = True) -> dict[str, str]:
        h = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "bountystrike-immunefi-mcp/0.1",
        }
        if attach_auth and self._token:
            h["Authorization"] = f"Bearer {self._token}"
        return h

    async def submit_report(
        self,
        programme: str,
        title: str,
        severity: str,
        asset_type: str,
        asset: str,
        impact: str,
        vulnerability_details: str,
        proof_of_concept: str,
        submit_url: str | None = None,
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not programme:
            raise ValueError("programme is required")
        if not title or len(title) > 200:
            raise ValueError("title must be 1..200 chars")
        sev = severity.lower()
        if sev not in VALID_SEVERITIES:
            raise ValueError(
                f"severity {severity!r} not in {sorted(VALID_SEVERITIES)}"
            )
        atype = asset_type.lower()
        if atype not in VALID_ASSET_TYPES:
            raise ValueError(
                f"asset_type {asset_type!r} not in {sorted(VALID_ASSET_TYPES)}"
            )

        body: dict[str, Any] = {
            "programme": programme,
            "title": title,
            "severity": sev,
            "asset_type": atype,
            "asset": asset,
            "impact": impact,
            "vulnerability_details": vulnerability_details,
            "proof_of_concept": proof_of_concept,
        }
        if extra:
            for k, v in extra.items():
                if k not in body:
                    body[k] = v

        # Resolve URL + decide auth attachment. If the caller passed an
        # override, validate it and only attach the platform Bearer when
        # the override host matches the configured base URL. Otherwise
        # the override could silently exfiltrate the token.
        if submit_url:
            try:
                validate_target_url(submit_url, allow_http=_ALLOW_HTTP_BASE_URL)
            except UrlGuardError as exc:
                raise ValueError(f"submit_url rejected by URL guard: {exc}") from exc
            url = submit_url
            attach_auth = hosts_match(submit_url, self._base_url)
        else:
            url = f"{self._base_url}/v1/reports"
            attach_auth = True

        headers = self._headers(attach_auth=attach_auth)

        last_exc: Exception | None = None
        for attempt in range(MAX_RETRIES + 1):
            try:
                resp = await self._client.post(url, headers=headers, json=body)
            except httpx.RequestError as exc:
                last_exc = exc
                if attempt < MAX_RETRIES:
                    await self._sleep_for_retry(attempt)
                    continue
                raise ImmunefiError(
                    f"network error after {MAX_RETRIES + 1} attempts: {exc}",
                    status_code=None,
                ) from exc

            if 200 <= resp.status_code < 300:
                try:
                    payload = resp.json()
                except Exception as exc:
                    raise ImmunefiError(
                        f"non-JSON 2xx body ({type(exc).__name__})",
                        status_code=resp.status_code,
                        body=_truncate_body(resp.text),
                    ) from exc
                if not isinstance(payload, dict):
                    raise ImmunefiError(
                        "unexpected response shape (not an object)",
                        status_code=resp.status_code,
                        body=_truncate_body(payload),
                    )
                return {
                    "submission_id": (
                        payload.get("id")
                        or payload.get("report_id")
                        or payload.get("reference")
                    ),
                    "status": payload.get("status") or payload.get("state"),
                    "title": payload.get("title"),
                    "raw": payload,
                }

            if resp.status_code == 429:
                if attempt < MAX_RETRIES:
                    server_wait = _parse_retry_after(
                        resp.headers.get("retry-after", "")
                    )
                    backoff_wait = RETRY_BACKOFF_S[
                        min(attempt, len(RETRY_BACKOFF_S) - 1)
                    ]
                    import asyncio as _asyncio

                    await _asyncio.sleep(
                        max(server_wait or 0.0, backoff_wait)
                    )
                    continue
                try:
                    body_obj = resp.json()
                except Exception:
                    body_obj = resp.text
                raise ImmunefiError(
                    f"rate-limited (429) after {MAX_RETRIES + 1} attempts",
                    status_code=429,
                    body=_truncate_body(body_obj),
                )

            if 400 <= resp.status_code < 500:
                try:
                    body_obj = resp.json()
                except Exception:
                    body_obj = resp.text
                raise ImmunefiError(
                    f"client error {resp.status_code}: rejected — fix report and retry",
                    status_code=resp.status_code,
                    body=_truncate_body(body_obj),
                )

            if attempt < MAX_RETRIES:
                await self._sleep_for_retry(attempt)
                continue
            try:
                body_obj = resp.json()
            except Exception:
                body_obj = resp.text
            raise ImmunefiError(
                f"server error {resp.status_code} after {MAX_RETRIES + 1} attempts",
                status_code=resp.status_code,
                body=_truncate_body(body_obj),
            )

        raise ImmunefiError("retry loop exhausted unexpectedly") from last_exc

    @staticmethod
    async def _sleep_for_retry(attempt: int) -> None:
        import asyncio

        delay = RETRY_BACKOFF_S[min(attempt, len(RETRY_BACKOFF_S) - 1)]
        await asyncio.sleep(delay)


__all__ = [
    "DEFAULT_BASE_URL",
    "MAX_RETRIES",
    "RETRY_BACKOFF_S",
    "VALID_ASSET_TYPES",
    "VALID_SEVERITIES",
    "ImmunefiClient",
    "ImmunefiError",
]
