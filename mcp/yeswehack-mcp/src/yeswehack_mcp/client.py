"""YesWeHack submission client.

API surface used:

  POST {base_url}/api/v1/programs/{slug}/reports
    Authorization: Bearer <token>
    Content-Type: application/json
    Body:
      {
        "title":               "<= 200 chars",
        "scope":               "<asset URL or label>",
        "vulnerability_type":  "<CWE-NN or YWH category slug>",
        "severity":            "low|medium|high|critical",
        "cvss":                "<vector string>",
        "description":         "<full markdown report body>",
        "report_attachments":  [],          # not used for first-pass submit
        "exploit_information": "<repro steps section>"
      }

Returns (201): ``{"id": <int>, "title": "...", "state": "ASKED", ...}``.

Reference: YesWeHack platform docs (researcher API). The schema has
been stable since 2024 — bump the API_VERSION constant if YWH publishes
a v2.

The client is async (httpx.AsyncClient) so it composes with asyncio MCP
servers without a thread pool. ``aclose()`` MUST be called on shutdown
to drain the connection pool.
"""

from __future__ import annotations

import json as _json
import os
from typing import Any

import httpx

from yeswehack_mcp._url_guard import validate_target_url

API_VERSION = "v1"
DEFAULT_BASE_URL = os.environ.get(
    "YESWEHACK_BASE_URL", "https://api.yeswehack.com"
)
DEFAULT_TIMEOUT_S = 30.0
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

# Retry policy: only retry idempotent failures (5xx, network), never 4xx.
MAX_RETRIES = 2
RETRY_BACKOFF_S = (0.5, 2.0)  # exponential — first retry 0.5s, second 2.0s


class YesWeHackError(RuntimeError):
    """Submission failure, including HTTP status if any."""

    def __init__(self, message: str, status_code: int | None = None, body: Any = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.body = body


class YesWeHackClient:
    def __init__(
        self,
        api_token: str | None = None,
        base_url: str = DEFAULT_BASE_URL,
        timeout_s: float = DEFAULT_TIMEOUT_S,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._token = api_token or os.environ.get("YESWEHACK_API_TOKEN", "")
        if not self._token:
            raise RuntimeError("YESWEHACK_API_TOKEN is not set")
        validate_target_url(base_url, allow_http=_ALLOW_HTTP_BASE_URL)
        self._base_url = base_url.rstrip("/")
        # Allow injecting a client for tests (respx).
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(timeout=timeout_s)

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def __aenter__(self) -> "YesWeHackClient":
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.aclose()

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "bountystrike-yeswehack-mcp/0.1",
        }

    async def submit_report(
        self,
        program_slug: str,
        title: str,
        scope: str,
        vulnerability_type: str,
        severity: str,
        cvss_vector: str,
        description: str,
        exploit_information: str,
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not program_slug:
            raise ValueError("program_slug is required")
        if not title or len(title) > 200:
            raise ValueError("title must be 1..200 chars")
        if severity.lower() not in {"informational", "low", "medium", "high", "critical"}:
            raise ValueError(f"severity {severity!r} not recognised")
        url = f"{self._base_url}/api/{API_VERSION}/programs/{program_slug}/reports"
        body: dict[str, Any] = {
            "title": title,
            "scope": scope,
            "vulnerability_type": vulnerability_type,
            "severity": severity.lower(),
            "cvss": cvss_vector,
            "description": description,
            "exploit_information": exploit_information,
        }
        # Programme-specific fields not part of the canonical contract.
        # YesWeHack body shape is unverified against context7 (the
        # library is not indexed); the ``extra`` escape hatch lets
        # callers add fields a programme requires without forking the
        # client. Contract fields above are NEVER overwritten —
        # silent shadowing of e.g. ``severity`` would defeat the
        # validator above. This mirrors the immunefi / intigriti
        # pattern documented in 00c-context7-verifications.md.
        if extra:
            for k, v in extra.items():
                if k not in body:
                    body[k] = v

        last_exc: Exception | None = None
        for attempt in range(MAX_RETRIES + 1):
            try:
                resp = await self._client.post(url, headers=self._headers(), json=body)
            except httpx.RequestError as exc:
                last_exc = exc
                if attempt < MAX_RETRIES:
                    await self._sleep_for_retry(attempt)
                    continue
                raise YesWeHackError(
                    f"network error after {MAX_RETRIES + 1} attempts: {exc}",
                    status_code=None,
                ) from exc

            if 200 <= resp.status_code < 300:
                try:
                    payload = resp.json()
                except Exception as exc:
                    raise YesWeHackError(
                        f"non-JSON 2xx body ({type(exc).__name__})",
                        status_code=resp.status_code,
                        body=_truncate_body(resp.text),
                    ) from exc
                if not isinstance(payload, dict):
                    raise YesWeHackError(
                        "unexpected response shape (not an object)",
                        status_code=resp.status_code,
                        body=_truncate_body(payload),
                    )
                return {
                    "submission_id": payload.get("id"),
                    "title": payload.get("title"),
                    "state": payload.get("state"),
                    "raw": payload,
                }

            if 400 <= resp.status_code < 500:
                # 4xx errors are NEVER retried — caller must fix the report.
                try:
                    body_obj = resp.json()
                except Exception:
                    body_obj = resp.text
                raise YesWeHackError(
                    f"client error {resp.status_code}: rejected — fix report and retry",
                    status_code=resp.status_code,
                    body=_truncate_body(body_obj),
                )

            # 5xx — retryable
            if attempt < MAX_RETRIES:
                await self._sleep_for_retry(attempt)
                continue
            try:
                body_obj = resp.json()
            except Exception:
                body_obj = resp.text
            raise YesWeHackError(
                f"server error {resp.status_code} after {MAX_RETRIES + 1} attempts",
                status_code=resp.status_code,
                body=_truncate_body(body_obj),
            )

        # Unreachable; exhausted retries always raise.
        raise YesWeHackError("retry loop exhausted unexpectedly") from last_exc

    @staticmethod
    async def _sleep_for_retry(attempt: int) -> None:
        import asyncio

        delay = RETRY_BACKOFF_S[min(attempt, len(RETRY_BACKOFF_S) - 1)]
        await asyncio.sleep(delay)


__all__ = [
    "API_VERSION",
    "DEFAULT_BASE_URL",
    "MAX_RETRIES",
    "RETRY_BACKOFF_S",
    "YesWeHackClient",
    "YesWeHackError",
]
