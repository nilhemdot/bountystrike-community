"""Intigriti submission client.

**IMPORTANT — Intigriti has no public researcher submission API.**

Verified against the official Intigriti OpenAPI specs (researcher API at
``https://api.intigriti.com/external/researcher`` and company API at
``https://api.intigriti.com/external/company``):

  - The researcher API exposes GET endpoints only — programme listing,
    programme detail, scope, rules of engagement. There is no
    documented POST /submissions endpoint for researchers to create new
    submissions.
  - The company API exposes write endpoints for tasks the researcher
    cannot perform (POSTing internal/external comments to existing
    submissions, adding payouts, etc.).

Researchers create new submissions via the Intigriti **web UI**, not
the API. This is the platform's documented model.

This module therefore ships ``submit_report`` as a **best-effort
placeholder** that POSTs to a configurable URL with a sensible body
shape. The default URL is ``{base_url}/v1/submissions`` (which Intigriti
will 404), explicitly so a caller cannot accidentally fire it against
the real platform thinking it works. To make ``submit_report``
functional, the caller MUST either:

  - point it at a custom relay endpoint they operate (set
    ``INTIGRITI_SUBMIT_URL`` env), or
  - know the body shape Intigriti accepts on a private/closed-beta
    submission API and pass that via the ``extra`` parameter.

The reporter-agent should treat Intigriti submissions as a manual
gate and route via the web UI for now. Calling this MCP without
override yields ``{ok: False, status_code: 404}``.

Verified base URL (Intigriti researcher API):
  https://api.intigriti.com/external/researcher

Auth: Bearer ``INTIGRITI_API_TOKEN`` (researcher PAT).

Severity vocabulary used by ``submit_report`` for compatibility with
the cross-platform reporter contract:
  informational | low | medium | high | critical | exceptional
"""

from __future__ import annotations

import json as _json
import os
from datetime import UTC
from typing import Any

import httpx

from intigriti_mcp._url_guard import (
    UrlGuardError,
    hosts_match,
    validate_target_url,
)

DEFAULT_BASE_URL = os.environ.get(
    "INTIGRITI_BASE_URL", "https://api.intigriti.com/external/researcher"
)
DEFAULT_TIMEOUT_S = 30.0
MAX_ERROR_BODY_BYTES = 4096
_ALLOW_HTTP_BASE_URL = os.environ.get("BS_PLATFORM_ALLOW_HTTP") == "1"

# Re-read at call time so a deploy that exports the var post-import
# picks it up; the previous module-load capture made the env-var path
# inert in production. Tests can either set the env or override the
# attribute directly via monkeypatch.
SUBMIT_URL_OVERRIDE_ENV = "INTIGRITI_SUBMIT_URL"


def _current_submit_url_override() -> str:
    """Read INTIGRITI_SUBMIT_URL on every call; backwards-compat with
    tests that monkeypatch the legacy module attribute."""
    legacy = globals().get("SUBMIT_URL_OVERRIDE", "")
    if legacy:
        return legacy
    return os.environ.get(SUBMIT_URL_OVERRIDE_ENV, "")


# Legacy module attribute kept for backwards compatibility with tests
# that monkeypatch ``intigriti_mcp.client.SUBMIT_URL_OVERRIDE``. The env
# path supersedes it via ``_current_submit_url_override``.
SUBMIT_URL_OVERRIDE = ""


def _truncate_body(body: Any) -> Any:
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
    {"informational", "low", "medium", "high", "critical", "exceptional"}
)

MAX_RETRIES = 2
RETRY_BACKOFF_S = (0.5, 2.0)


class IntigritiError(RuntimeError):
    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        body: Any = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.body = body


class IntigritiClient:
    def __init__(
        self,
        api_token: str | None = None,
        base_url: str = DEFAULT_BASE_URL,
        timeout_s: float = DEFAULT_TIMEOUT_S,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._token = api_token or os.environ.get("INTIGRITI_API_TOKEN", "")
        if not self._token:
            raise RuntimeError("INTIGRITI_API_TOKEN is not set")
        # base_url is a Bearer destination — must not silently become an
        # exfil channel on env misconfiguration.
        validate_target_url(base_url, allow_http=_ALLOW_HTTP_BASE_URL)
        self._base_url = base_url.rstrip("/")
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(timeout=timeout_s)

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def __aenter__(self) -> IntigritiClient:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.aclose()

    def _headers(self, *, attach_auth: bool = True) -> dict[str, str]:
        h: dict[str, str] = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "bountystrike-intigriti-mcp/0.1",
        }
        if attach_auth:
            h["Authorization"] = f"Bearer {self._token}"
        return h

    async def submit_report(
        self,
        program_id: str,
        title: str,
        endpoint_url: str,
        severity: str,
        vuln_type: str,
        description: str,
        proof_of_concept: str,
        impact: str,
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not program_id:
            raise ValueError("program_id is required")
        if not title or len(title) > 200:
            raise ValueError("title must be 1..200 chars")
        sev = severity.lower()
        if sev not in VALID_SEVERITIES:
            raise ValueError(
                f"severity {severity!r} not in {sorted(VALID_SEVERITIES)}"
            )

        body: dict[str, Any] = {
            "programId": program_id,
            "title": title,
            "endpointUrl": endpoint_url,
            "severity": sev,
            "type": vuln_type,
            "description": description,
            "proofOfConcept": proof_of_concept,
            "impact": impact,
        }
        if extra:
            for k, v in extra.items():
                if k not in body:  # never let extra silently overwrite contract fields
                    body[k] = v

        # Intigriti has no documented researcher POST /submissions
        # endpoint — see the module docstring. The default below WILL
        # 404 on the live platform; a real submission requires
        # INTIGRITI_SUBMIT_URL to point at a relay you control.
        override = _current_submit_url_override()
        if override:
            try:
                validate_target_url(override, allow_http=_ALLOW_HTTP_BASE_URL)
            except UrlGuardError as exc:
                raise ValueError(
                    f"INTIGRITI_SUBMIT_URL rejected by URL guard: {exc}"
                ) from exc
            url = override
            attach_auth = hosts_match(override, self._base_url)
        else:
            url = f"{self._base_url}/v1/submissions"
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
                raise IntigritiError(
                    f"network error after {MAX_RETRIES + 1} attempts: {exc}",
                    status_code=None,
                ) from exc

            if 200 <= resp.status_code < 300:
                try:
                    payload = resp.json()
                except Exception as exc:
                    raise IntigritiError(
                        f"non-JSON 2xx body ({type(exc).__name__})",
                        status_code=resp.status_code,
                        body=_truncate_body(resp.text),
                    ) from exc
                if not isinstance(payload, dict):
                    raise IntigritiError(
                        "unexpected response shape (not an object)",
                        status_code=resp.status_code,
                        body=_truncate_body(payload),
                    )
                return {
                    "submission_id": (
                        payload.get("id")
                        or payload.get("submissionId")
                        or payload.get("reference")
                    ),
                    "status": payload.get("state") or payload.get("status"),
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
                raise IntigritiError(
                    f"rate-limited (429) after {MAX_RETRIES + 1} attempts",
                    status_code=429,
                    body=_truncate_body(body_obj),
                )

            if 400 <= resp.status_code < 500:
                try:
                    body_obj = resp.json()
                except Exception:
                    body_obj = resp.text
                raise IntigritiError(
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
            raise IntigritiError(
                f"server error {resp.status_code} after {MAX_RETRIES + 1} attempts",
                status_code=resp.status_code,
                body=_truncate_body(body_obj),
            )

        raise IntigritiError("retry loop exhausted unexpectedly") from last_exc

    @staticmethod
    async def _sleep_for_retry(attempt: int) -> None:
        import asyncio

        delay = RETRY_BACKOFF_S[min(attempt, len(RETRY_BACKOFF_S) - 1)]
        await asyncio.sleep(delay)


__all__ = [
    "DEFAULT_BASE_URL",
    "MAX_RETRIES",
    "RETRY_BACKOFF_S",
    "VALID_SEVERITIES",
    "IntigritiClient",
    "IntigritiError",
]
