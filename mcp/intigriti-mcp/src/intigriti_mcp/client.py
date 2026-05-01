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

import os
from typing import Any

import httpx

DEFAULT_BASE_URL = os.environ.get(
    "INTIGRITI_BASE_URL", "https://api.intigriti.com/external/researcher"
)
# Optional override: if set, ``submit_report`` POSTs here instead of the
# (non-existent) Intigriti submission endpoint. Intended for callers
# who run their own relay or have closed-beta submission API access.
SUBMIT_URL_OVERRIDE = os.environ.get("INTIGRITI_SUBMIT_URL", "")
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

        # Intigriti has no documented researcher POST /submissions
        # endpoint — see the module docstring. The default below WILL
        # 404 on the live platform; a real submission requires
        # INTIGRITI_SUBMIT_URL to point at a relay you control.
        url = SUBMIT_URL_OVERRIDE or f"{self._base_url}/v1/submissions"

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
