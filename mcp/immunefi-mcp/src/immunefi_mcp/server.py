# SPDX-License-Identifier: AGPL-3.0-or-later

"""FastMCP server for immunefi-mcp.

Exposes one MCP tool: submit_report — POST {base_url}/v1/reports (or
``submit_url`` override per programme).

Auth is OPTIONAL — many Immunefi programmes accept anonymous submissions.
``IMMUNEFI_API_TOKEN`` is read if set and forwarded as a Bearer token.
"""

from __future__ import annotations

import asyncio
from typing import Any

from mcp.server.fastmcp import FastMCP

from immunefi_mcp.client import ImmunefiClient, ImmunefiError

mcp = FastMCP("immunefi-mcp")

_client: ImmunefiClient | None = None
_init_lock = asyncio.Lock()


async def _get_client() -> ImmunefiClient:
    global _client
    if _client is not None:
        return _client
    async with _init_lock:
        if _client is None:
            _client = ImmunefiClient()
    return _client


async def _submit_report_impl(
    client: ImmunefiClient,
    *,
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
) -> dict:
    try:
        return {
            "ok": True,
            **await client.submit_report(
                programme=programme,
                title=title,
                severity=severity,
                asset_type=asset_type,
                asset=asset,
                impact=impact,
                vulnerability_details=vulnerability_details,
                proof_of_concept=proof_of_concept,
                submit_url=submit_url,
                extra=extra,
            ),
        }
    except ImmunefiError as exc:
        return {
            "ok": False,
            "error": str(exc),
            "status_code": exc.status_code,
            "body": exc.body,
        }


@mcp.tool()
async def submit_report(
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
) -> dict:
    """Submit a finding to Immunefi.

    Call only AFTER T3 approval — the approval-gate hook blocks
    unapproved invocations.

    Args:
        programme: Immunefi programme slug.
        title: Report title (1..200 chars).
        severity: ``informational|low|medium|high|critical``.
        asset_type: ``smart_contract|website_and_application|blockchain|other``.
        asset: Contract address or asset URL.
        impact: Markdown impact section.
        vulnerability_details: Markdown technical details.
        proof_of_concept: Markdown reproduction.
        submit_url: Override the submission endpoint per programme — many
            Immunefi programmes front custom Vaults / relay endpoints.
        extra: Programme-specific fields appended to the body. Will not
            overwrite the contract fields above.

    Returns:
        ``{ok, submission_id, status, title, raw}`` on success;
        ``{ok: False, error, status_code, body}`` on failure.
    """
    client = await _get_client()
    return await _submit_report_impl(
        client,
        programme=programme,
        title=title,
        severity=severity,
        asset_type=asset_type,
        asset=asset,
        impact=impact,
        vulnerability_details=vulnerability_details,
        proof_of_concept=proof_of_concept,
        submit_url=submit_url,
        extra=extra,
    )


def main() -> None:
    """Run the immunefi-mcp FastMCP server (stdio transport)."""
    mcp.run()


if __name__ == "__main__":
    main()
