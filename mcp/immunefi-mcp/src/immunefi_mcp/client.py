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

import os
from typing import Any

import httpx

DEFAULT_BASE_URL = os.environ.get(
    "IMMUNEFI_BASE_URL", "https://api.immunefi.com"
)
DEFAULT_TIMEOUT_S = 30.0

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
        self._base_url = base_url.rstrip("/")
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(timeout=timeout_s)

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def __aenter__(self) -> "ImmunefiClient":
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.aclose()

    def _headers(self) -> dict[str, str]:
        h = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "bountystrike-immunefi-mcp/0.1",
        }
        if self._token:
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

        url = submit_url or f"{self._base_url}/v1/reports"

        last_exc: Exception | None = None
        for attempt in range(MAX_RETRIES + 1):
            try:
                resp = await self._client.post(url, headers=self._headers(), json=body)
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
                payload = resp.json()
                if not isinstance(payload, dict):
                    raise ImmunefiError(
                        "unexpected response shape (not an object)",
                        status_code=resp.status_code,
                        body=payload,
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

            if 400 <= resp.status_code < 500:
                try:
                    body_obj = resp.json()
                except Exception:
                    body_obj = resp.text
                raise ImmunefiError(
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
            raise ImmunefiError(
                f"server error {resp.status_code} after {MAX_RETRIES + 1} attempts",
                status_code=resp.status_code,
                body=body_obj,
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
