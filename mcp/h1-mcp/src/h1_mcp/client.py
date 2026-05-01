"""HackerOne hacker-side submission client.

API surface used:

  POST https://api.hackerone.com/v1/hackers/reports
    Authorization: Basic <base64(username:api_token)>
    Content-Type: application/json
    Body (JSON:API):
      {
        "data": {
          "type": "report",
          "attributes": {
            "team_handle":              "<program slug>",
            "title":                    "<= 200 chars>",
            "vulnerability_information": "<full markdown>",
            "impact":                   "<impact section>",
            "severity_rating":          "none|low|medium|high|critical",     (optional)
            "weakness_id":              <int weakness id; H1's catalogue,    (optional)
                                          NOT MITRE CWE>,
            "structured_scope_id":      <int scope-asset id from H1's        (optional)
                                          structured_scopes endpoint>
          }
        }
      }

Returns 201 with::

  {
    "data": {
      "id":   "<report id>",
      "type": "report",
      "attributes": {
        "title":      "...",
        "state":      "new",
        "created_at": "..."
      }
    }
  }

Reference: https://api.hackerone.com/hacker-resources/#reports-create-report
The endpoint has been stable since at least 2023; H1's April 2026 deprecation
affected the /v1/organizations/{id}/assets endpoint (scope ingest), not
/v1/hackers/reports.

Auth notes
----------
HackerOne's hacker API uses HTTP Basic where the username is your H1
username (lowercase, e.g. ``alice``) and the password is your personal
API token. ``H1_API_USERNAME`` is therefore distinct from ``H1_API_TOKEN``
and both are required. The reporter-agent injects them via env at
spawn time; the MCP itself never logs either value.
"""

from __future__ import annotations

import json as _json
import os
from typing import Any

import httpx

from h1_mcp._url_guard import validate_target_url

DEFAULT_BASE_URL = os.environ.get("H1_BASE_URL", "https://api.hackerone.com")
DEFAULT_TIMEOUT_S = 30.0
MAX_ERROR_BODY_BYTES = 4096
_ALLOW_HTTP_BASE_URL = os.environ.get("BS_PLATFORM_ALLOW_HTTP") == "1"


def _truncate_body(body: Any) -> Any:
    """Cap response body size kept in :class:`HackerOneError.body`.

    Without truncation, a hostile / misbehaving upstream that echoes
    the request (or the Authorization header) in a 4xx/5xx body
    propagates that into MCP stdio + agent transcripts.
    """
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


H1_SEVERITIES: frozenset[str] = frozenset(
    {"none", "low", "medium", "high", "critical"}
)

# Retry policy: only retry idempotent failures (5xx, network).
MAX_RETRIES = 2
RETRY_BACKOFF_S = (0.5, 2.0)


class HackerOneError(RuntimeError):
    """Submission failure, including HTTP status if any."""

    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        body: Any = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.body = body


class HackerOneClient:
    def __init__(
        self,
        username: str | None = None,
        api_token: str | None = None,
        base_url: str = DEFAULT_BASE_URL,
        timeout_s: float = DEFAULT_TIMEOUT_S,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._username = username or os.environ.get("H1_API_USERNAME", "")
        self._token = api_token or os.environ.get("H1_API_TOKEN", "")
        if not self._username:
            raise RuntimeError("H1_API_USERNAME is not set")
        if not self._token:
            raise RuntimeError("H1_API_TOKEN is not set")
        # base_url is the Bearer destination — must not silently become
        # an exfil channel on env misconfiguration.
        validate_target_url(base_url, allow_http=_ALLOW_HTTP_BASE_URL)
        self._base_url = base_url.rstrip("/")
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(timeout=timeout_s)

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def __aenter__(self) -> "HackerOneClient":
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.aclose()

    @staticmethod
    def _basic_auth(username: str, token: str) -> str:
        import base64

        raw = f"{username}:{token}".encode()
        return "Basic " + base64.b64encode(raw).decode()

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": self._basic_auth(self._username, self._token),
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "bountystrike-h1-mcp/0.1",
        }

    @staticmethod
    def _build_body(
        team_handle: str,
        title: str,
        vulnerability_information: str,
        impact: str,
        severity_rating: str,
        weakness_id: int | None,
        structured_scope_id: int | None,
    ) -> dict[str, Any]:
        attributes: dict[str, Any] = {
            "team_handle": team_handle,
            "title": title,
            "vulnerability_information": vulnerability_information,
            "impact": impact,
            "severity_rating": severity_rating,
        }
        if weakness_id is not None:
            attributes["weakness_id"] = int(weakness_id)
        if structured_scope_id is not None:
            attributes["structured_scope_id"] = int(structured_scope_id)
        return {"data": {"type": "report", "attributes": attributes}}

    async def submit_report(
        self,
        team_handle: str,
        title: str,
        vulnerability_information: str,
        impact: str,
        severity_rating: str,
        weakness_id: int | None = None,
        structured_scope_id: int | None = None,
    ) -> dict[str, Any]:
        if not team_handle:
            raise ValueError("team_handle is required")
        if not title or len(title) > 200:
            raise ValueError("title must be 1..200 chars")
        sev = severity_rating.lower()
        if sev not in H1_SEVERITIES:
            raise ValueError(
                f"severity_rating {severity_rating!r} not in {sorted(H1_SEVERITIES)}"
            )
        # H1 docs use ``"weakness_id": 0`` as the unspecified-weakness
        # sentinel in their published examples. Accept any non-negative
        # integer; reject negatives only.
        if weakness_id is not None and weakness_id < 0:
            raise ValueError("weakness_id must be >= 0 or None")
        if structured_scope_id is not None and structured_scope_id < 0:
            raise ValueError("structured_scope_id must be >= 0 or None")

        url = f"{self._base_url}/v1/hackers/reports"
        body = self._build_body(
            team_handle, title, vulnerability_information, impact, sev,
            weakness_id, structured_scope_id,
        )

        last_exc: Exception | None = None
        for attempt in range(MAX_RETRIES + 1):
            try:
                resp = await self._client.post(url, headers=self._headers(), json=body)
            except httpx.RequestError as exc:
                last_exc = exc
                if attempt < MAX_RETRIES:
                    await self._sleep_for_retry(attempt)
                    continue
                raise HackerOneError(
                    f"network error after {MAX_RETRIES + 1} attempts: {exc}",
                    status_code=None,
                ) from exc

            if 200 <= resp.status_code < 300:
                try:
                    payload = resp.json()
                except Exception as exc:
                    raise HackerOneError(
                        f"non-JSON 2xx body ({type(exc).__name__})",
                        status_code=resp.status_code,
                        body=_truncate_body(resp.text),
                    ) from exc
                if not isinstance(payload, dict) or "data" not in payload:
                    raise HackerOneError(
                        "unexpected response shape (missing 'data')",
                        status_code=resp.status_code,
                        body=_truncate_body(payload),
                    )
                data = payload["data"]
                attrs = data.get("attributes", {}) if isinstance(data, dict) else {}
                return {
                    "submission_id": data.get("id"),
                    "title": attrs.get("title"),
                    "state": attrs.get("state"),
                    "created_at": attrs.get("created_at"),
                    "raw": payload,
                }

            if 400 <= resp.status_code < 500:
                # 4xx — never retried.
                try:
                    body_obj = resp.json()
                except Exception:
                    body_obj = resp.text
                raise HackerOneError(
                    f"client error {resp.status_code}: rejected — fix report and retry",
                    status_code=resp.status_code,
                    body=_truncate_body(body_obj),
                )

            # 5xx — retryable.
            if attempt < MAX_RETRIES:
                await self._sleep_for_retry(attempt)
                continue
            try:
                body_obj = resp.json()
            except Exception:
                body_obj = resp.text
            raise HackerOneError(
                f"server error {resp.status_code} after {MAX_RETRIES + 1} attempts",
                status_code=resp.status_code,
                body=_truncate_body(body_obj),
            )

        raise HackerOneError("retry loop exhausted unexpectedly") from last_exc

    @staticmethod
    async def _sleep_for_retry(attempt: int) -> None:
        import asyncio

        delay = RETRY_BACKOFF_S[min(attempt, len(RETRY_BACKOFF_S) - 1)]
        await asyncio.sleep(delay)


__all__ = [
    "DEFAULT_BASE_URL",
    "H1_SEVERITIES",
    "MAX_RETRIES",
    "RETRY_BACKOFF_S",
    "HackerOneClient",
    "HackerOneError",
]
