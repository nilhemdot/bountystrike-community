"""Bugcrowd submission client.

API surface used (per build-plan §reporter-agent + Bugcrowd Researcher API):

  POST {base_url}/submissions
    Authorization: Token <api_token>          (Bugcrowd uses ``Token``, not ``Bearer``)
    X-BUGCROWD-API-VERSION: <pinned date>
    Content-Type: application/json
    Body:
      {
        "submission": {
          "target":      "<asset URL>",
          "title":       "<= 200 chars",
          "description": "<full markdown report>",
          "severity":    1..5,                  (P1=1 critical … P5=5 informational)
          "vrt_id":      "<vrt taxonomy id>"     (optional)
        }
      }

Returns 201 with::

  {
    "submission_id":  "<uuid>",
    "status":         "needs_review" | "in_progress" | ...,
    "title":          "...",
    ...
  }

Severity mapping (build-plan §reporter):
  critical / P1 → 1
  high / P2     → 2
  medium / P3   → 3
  low / P4      → 4
  informational / P5 → 5

NOTE: Bugcrowd's Researcher API has had multiple shape revisions; pin
``X-BUGCROWD-API-VERSION`` to a date you've verified against. The default
``2024-01-11`` matches build-plan §reporter; bump via ``BUGCROWD_API_VERSION``
env when Bugcrowd publishes a newer stable version. Tests lock the
contract — any drift surfaces as test failures, not silent prod errors.
"""

from __future__ import annotations

import os
from typing import Any

import httpx

DEFAULT_BASE_URL = os.environ.get("BUGCROWD_BASE_URL", "https://api.bugcrowd.com")
DEFAULT_API_VERSION = os.environ.get("BUGCROWD_API_VERSION", "2024-01-11")
DEFAULT_TIMEOUT_S = 30.0

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
        api_version: str = DEFAULT_API_VERSION,
        timeout_s: float = DEFAULT_TIMEOUT_S,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._token = api_token or os.environ.get("BUGCROWD_API_TOKEN", "")
        if not self._token:
            raise RuntimeError("BUGCROWD_API_TOKEN is not set")
        self._base_url = base_url.rstrip("/")
        self._api_version = api_version
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(timeout=timeout_s)

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def __aenter__(self) -> "BugcrowdClient":
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.aclose()

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Token {self._token}",
            "X-BUGCROWD-API-VERSION": self._api_version,
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "bountystrike-bugcrowd-mcp/0.1",
        }

    async def submit_report(
        self,
        target: str,
        title: str,
        description: str,
        severity: str,
        vrt_id: str | None = None,
    ) -> dict[str, Any]:
        if not target:
            raise ValueError("target is required")
        if not title or len(title) > 200:
            raise ValueError("title must be 1..200 chars")
        sev = severity.lower()
        if sev not in SEVERITY_TO_INT:
            raise ValueError(
                f"severity {severity!r} not in {sorted(SEVERITY_TO_INT)}"
            )
        body: dict[str, Any] = {
            "submission": {
                "target": target,
                "title": title,
                "description": description,
                "severity": SEVERITY_TO_INT[sev],
            }
        }
        if vrt_id:
            body["submission"]["vrt_id"] = vrt_id

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
                payload = resp.json()
                if not isinstance(payload, dict):
                    raise BugcrowdError(
                        "unexpected response shape (not an object)",
                        status_code=resp.status_code,
                        body=payload,
                    )
                # Bugcrowd has used both top-level ``submission_id`` and
                # nested ``submission.id``; tolerate both.
                sid = (
                    payload.get("submission_id")
                    or (payload.get("submission") or {}).get("id")
                )
                state = (
                    payload.get("status")
                    or (payload.get("submission") or {}).get("status")
                )
                title_out = (
                    payload.get("title")
                    or (payload.get("submission") or {}).get("title")
                )
                return {
                    "submission_id": sid,
                    "status": state,
                    "title": title_out,
                    "raw": payload,
                }

            if 400 <= resp.status_code < 500:
                try:
                    body_obj = resp.json()
                except Exception:
                    body_obj = resp.text
                raise BugcrowdError(
                    f"client error {resp.status_code}: rejected — fix report and retry",
                    status_code=resp.status_code,
                    body=body_obj,
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
                body=body_obj,
            )

        raise BugcrowdError("retry loop exhausted unexpectedly") from last_exc

    @staticmethod
    async def _sleep_for_retry(attempt: int) -> None:
        import asyncio

        delay = RETRY_BACKOFF_S[min(attempt, len(RETRY_BACKOFF_S) - 1)]
        await asyncio.sleep(delay)


__all__ = [
    "DEFAULT_API_VERSION",
    "DEFAULT_BASE_URL",
    "MAX_RETRIES",
    "RETRY_BACKOFF_S",
    "SEVERITY_TO_INT",
    "BugcrowdClient",
    "BugcrowdError",
]
