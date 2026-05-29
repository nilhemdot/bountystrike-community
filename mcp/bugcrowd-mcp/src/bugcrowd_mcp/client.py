# SPDX-License-Identifier: AGPL-3.0-or-later

"""Bugcrowd submission client.

API surface (verified against https://docs.bugcrowd.com/api/latest):

  POST {base_url}/submissions
    Authorization: Token <api_token>          (Bugcrowd's documented Basic-Auth-like
                                              "Token" scheme; some accounts use
                                              ``Bearer`` — override via the
                                              ``auth_scheme`` arg if your token
                                              works only with one)
    Content-Type: application/json
    Body (JSON:API):
      {
        "data": {
          "type": "submission",
          "attributes": {
            "title":       "<= ~200 chars>",
            "description": "<full markdown report (POC inline)>",
            "severity":    1..5,                       (P1=1 critical … P5=5 informational)
            "vrt_id":      "<dot.path.id>"             (optional; e.g. cross_site_scripting_xss)
          },
          "relationships": {
            "program": {
              "data": {
                "type": "program",
                "id":   "<program_uuid>"               (REQUIRED — UUID, not slug)
              }
            },
            "target": {                                (OPTIONAL)
              "data": {
                "type": "target",
                "id":   "<target_uuid>"
              }
            }
          }
        }
      }

Returns 201 with the new submission as a JSON:API resource::

  {
    "data": {
      "type": "submission",
      "id":   "<submission_uuid>",
      "attributes": {
        "title":      "...",
        "state":      "new",
        "severity":   2,
        "created_at": "2026-05-01T..."
      },
      "relationships": {...}
    },
    "included": []                                     (may carry a ClaimTicket)
  }

Severity mapping (Bugcrowd P1..P5):
  critical / P1 → 1
  high / P2     → 2
  medium / P3   → 3
  low / P4      → 4
  informational / P5 → 5

The previous version of this module shipped against a build-plan-derived
``{"submission": {...}}`` body shape and a ``target`` URL field; both
were wrong per the live JSON:API spec. The fix is intentionally
breaking: the function signature now takes ``program_id`` (UUID) and an
optional ``target_id`` (UUID), and the body is the JSON:API resource.
"""

from __future__ import annotations

import json as _json
import os
from datetime import UTC
from typing import Any

import httpx

from bugcrowd_mcp._url_guard import validate_target_url

DEFAULT_BASE_URL = os.environ.get("BUGCROWD_BASE_URL", "https://api.bugcrowd.com")
DEFAULT_TIMEOUT_S = 30.0
DEFAULT_AUTH_SCHEME = os.environ.get("BUGCROWD_AUTH_SCHEME", "Token")
MAX_ERROR_BODY_BYTES = 4096
_ALLOW_HTTP_BASE_URL = os.environ.get("BS_PLATFORM_ALLOW_HTTP") == "1"


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

# Severity name → Bugcrowd integer (P1..P5).
SEVERITY_TO_INT: dict[str, int] = {
    "critical": 1,
    "high": 2,
    "medium": 3,
    "low": 4,
    "informational": 5,
}

MAX_RETRIES = 2
RETRY_BACKOFF_S = (0.5, 2.0)


class BugcrowdError(RuntimeError):
    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        body: Any = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.body = body


class BugcrowdClient:
    def __init__(
        self,
        api_token: str | None = None,
        base_url: str = DEFAULT_BASE_URL,
        auth_scheme: str = DEFAULT_AUTH_SCHEME,
        timeout_s: float = DEFAULT_TIMEOUT_S,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._token = api_token or os.environ.get("BUGCROWD_API_TOKEN", "")
        if not self._token:
            raise RuntimeError("BUGCROWD_API_TOKEN is not set")
        validate_target_url(base_url, allow_http=_ALLOW_HTTP_BASE_URL)
        self._base_url = base_url.rstrip("/")
        self._auth_scheme = auth_scheme
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(timeout=timeout_s)

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def __aenter__(self) -> BugcrowdClient:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.aclose()

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"{self._auth_scheme} {self._token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "bountystrike-bugcrowd-mcp/0.1",
        }

    @staticmethod
    def _build_body(
        program_id: str,
        title: str,
        description: str,
        severity_int: int,
        vrt_id: str | None,
        target_id: str | None,
    ) -> dict[str, Any]:
        attributes: dict[str, Any] = {
            "title": title,
            "description": description,
            "severity": severity_int,
        }
        if vrt_id:
            attributes["vrt_id"] = vrt_id
        relationships: dict[str, Any] = {
            "program": {"data": {"type": "program", "id": program_id}}
        }
        if target_id:
            relationships["target"] = {
                "data": {"type": "target", "id": target_id}
            }
        return {
            "data": {
                "type": "submission",
                "attributes": attributes,
                "relationships": relationships,
            }
        }

    async def submit_report(
        self,
        program_id: str,
        title: str,
        description: str,
        severity: str,
        vrt_id: str | None = None,
        target_id: str | None = None,
    ) -> dict[str, Any]:
        if not program_id:
            raise ValueError("program_id is required (Bugcrowd program UUID)")
        if not title or len(title) > 200:
            raise ValueError("title must be 1..200 chars")
        sev = severity.lower()
        if sev not in SEVERITY_TO_INT:
            raise ValueError(
                f"severity {severity!r} not in {sorted(SEVERITY_TO_INT)}"
            )

        body = self._build_body(
            program_id, title, description, SEVERITY_TO_INT[sev], vrt_id, target_id,
        )
        url = f"{self._base_url}/submissions"

        last_exc: Exception | None = None
        for attempt in range(MAX_RETRIES + 1):
            try:
                resp = await self._client.post(url, headers=self._headers(), json=body)
            except httpx.RequestError as exc:
                last_exc = exc
                if attempt < MAX_RETRIES:
                    await self._sleep_for_retry(attempt)
                    continue
                raise BugcrowdError(
                    f"network error after {MAX_RETRIES + 1} attempts: {exc}",
                    status_code=None,
                ) from exc

            if 200 <= resp.status_code < 300:
                try:
                    payload = resp.json()
                except Exception as exc:
                    raise BugcrowdError(
                        f"non-JSON 2xx body ({type(exc).__name__})",
                        status_code=resp.status_code,
                        body=_truncate_body(resp.text),
                    ) from exc
                if not isinstance(payload, dict) or "data" not in payload:
                    raise BugcrowdError(
                        "unexpected response shape (missing 'data')",
                        status_code=resp.status_code,
                        body=_truncate_body(payload),
                    )
                data = payload["data"]
                attrs = data.get("attributes", {}) if isinstance(data, dict) else {}
                return {
                    "submission_id": data.get("id"),
                    "status": attrs.get("state"),
                    "title": attrs.get("title"),
                    "severity": attrs.get("severity"),
                    "created_at": attrs.get("created_at"),
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
                raise BugcrowdError(
                    f"rate-limited (429) after {MAX_RETRIES + 1} attempts",
                    status_code=429,
                    body=_truncate_body(body_obj),
                )

            if 400 <= resp.status_code < 500:
                try:
                    body_obj = resp.json()
                except Exception:
                    body_obj = resp.text
                raise BugcrowdError(
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
            raise BugcrowdError(
                f"server error {resp.status_code} after {MAX_RETRIES + 1} attempts",
                status_code=resp.status_code,
                body=_truncate_body(body_obj),
            )

        raise BugcrowdError("retry loop exhausted unexpectedly") from last_exc

    @staticmethod
    async def _sleep_for_retry(attempt: int) -> None:
        import asyncio

        delay = RETRY_BACKOFF_S[min(attempt, len(RETRY_BACKOFF_S) - 1)]
        await asyncio.sleep(delay)


__all__ = [
    "DEFAULT_AUTH_SCHEME",
    "DEFAULT_BASE_URL",
    "MAX_RETRIES",
    "RETRY_BACKOFF_S",
    "SEVERITY_TO_INT",
    "BugcrowdClient",
    "BugcrowdError",
]
