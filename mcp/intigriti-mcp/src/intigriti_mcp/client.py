"""Intigriti submission client.

Endpoint base (build-plan §4.3): https://api.intigriti.com/core/researcher/v1.
The scope-fetch path is documented at::

  GET /core/researcher/v1/programs/{company}/{program}/scopes
      Authorization: Bearer <PAT>

The submission path follows the same versioned base. The exact body
shape is programme-driven; this client ships the documented common
fields and forwards an optional ``extra`` blob the caller can populate
per-programme without bumping the client.

  POST {base_url}/core/researcher/v1/submissions
    Authorization: Bearer <PAT>
    Content-Type: application/json
    Body:
      {
        "programId":         "<uuid>",
        "title":             "<= 200 chars",
        "endpointUrl":       "<asset URL>",
        "severity":          "low|medium|high|critical|exceptional",
        "type":              "CWE-NN" | "<intigriti category>",
        "description":       "<markdown>",
        "proofOfConcept":    "<markdown>",
        "impact":            "<markdown>",
        ...                  "<extra fields>"
      }

NOTE: Intigriti's researcher submission API has been less publicly
documented than HackerOne / Bugcrowd; verify the body shape against
your live programme before first prod use. Tests lock the contract,
so any drift surfaces as test failures, not silent prod errors.
``extra`` lets you bolt programme-specific fields onto the body
without forking the client.

Severity name pass-through:
  Intigriti accepts the lower-case string verbatim. ``exceptional``
  is the Intigriti-only highest tier (above ``critical``).
"""

from __future__ import annotations

import os
from typing import Any

import httpx

DEFAULT_BASE_URL = os.environ.get(
    "INTIGRITI_BASE_URL", "https://api.intigriti.com"
)
DEFAULT_TIMEOUT_S = 30.0

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
        self._base_url = base_url.rstrip("/")
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(timeout=timeout_s)

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def __aenter__(self) -> "IntigritiClient":
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.aclose()

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "bountystrike-intigriti-mcp/0.1",
        }

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

        url = f"{self._base_url}/core/researcher/v1/submissions"

        last_exc: Exception | None = None
        for attempt in range(MAX_RETRIES + 1):
            try:
                resp = await self._client.post(url, headers=self._headers(), json=body)
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
                payload = resp.json()
                if not isinstance(payload, dict):
                    raise IntigritiError(
                        "unexpected response shape (not an object)",
                        status_code=resp.status_code,
                        body=payload,
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

            if 400 <= resp.status_code < 500:
                try:
                    body_obj = resp.json()
                except Exception:
                    body_obj = resp.text
                raise IntigritiError(
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
            raise IntigritiError(
                f"server error {resp.status_code} after {MAX_RETRIES + 1} attempts",
                status_code=resp.status_code,
                body=body_obj,
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
