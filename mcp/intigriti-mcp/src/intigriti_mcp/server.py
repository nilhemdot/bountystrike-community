"""FastMCP server for intigriti-mcp.

Exposes one MCP tool: submit_report — POST /core/researcher/v1/submissions.

Required env:
  - INTIGRITI_API_TOKEN — Intigriti researcher PAT (Bearer token)
Optional:
  - INTIGRITI_BASE_URL  — default https://api.intigriti.com
"""

from __future__ import annotations

import asyncio
from typing import Any

from mcp.server.fastmcp import FastMCP

from intigriti_mcp.client import IntigritiClient, IntigritiError

mcp = FastMCP("intigriti-mcp")

_client: IntigritiClient | None = None
_init_lock = asyncio.Lock()


async def _get_client() -> IntigritiClient:
    global _client
    if _client is not None:
        return _client
    async with _init_lock:
        if _client is None:
            _client = IntigritiClient()
    return _client


async def _submit_report_impl(
    client: IntigritiClient,
    *,
    program_id: str,
    title: str,
    endpoint_url: str,
    severity: str,
    vuln_type: str,
    description: str,
    proof_of_concept: str,
    impact: str,
    extra: dict[str, Any] | None = None,
) -> dict:
    try:
        return {
            "ok": True,
            **await client.submit_report(
                program_id=program_id,
                title=title,
                endpoint_url=endpoint_url,
                severity=severity,
                vuln_type=vuln_type,
                description=description,
                proof_of_concept=proof_of_concept,
                impact=impact,
                extra=extra,
            ),
        }
    except IntigritiError as exc:
        return {
            "ok": False,
            "error": str(exc),
            "status_code": exc.status_code,
            "body": exc.body,
        }


@mcp.tool()
async def submit_report(
    program_id: str,
    title: str,
    endpoint_url: str,
    severity: str,
    vuln_type: str,
    description: str,
    proof_of_concept: str,
    impact: str,
    extra: dict[str, Any] | None = None,
) -> dict:
    """Submit a finding to Intigriti.

    Call only AFTER T3 approval — the approval-gate hook blocks
    unapproved invocations.

    Args:
        program_id: Intigriti programme UUID.
        title: Report title (1..200 chars).
        endpoint_url: Asset URL the finding concerns.
        severity: ``informational|low|medium|high|critical|exceptional``.
        vuln_type: ``CWE-NN`` (preferred) or Intigriti category slug.
        description: Markdown body.
        proof_of_concept: Markdown reproduction.
        impact: Markdown impact section.
        extra: Programme-specific fields appended to the body. Will not
            overwrite the contract fields above.

    Returns:
        ``{ok, submission_id, status, title, raw}`` on success;
        ``{ok: False, error, status_code, body}`` on failure.
    """
    client = await _get_client()
    return await _submit_report_impl(
        client,
        program_id=program_id,
        title=title,
        endpoint_url=endpoint_url,
        severity=severity,
        vuln_type=vuln_type,
        description=description,
        proof_of_concept=proof_of_concept,
        impact=impact,
        extra=extra,
    )


def main() -> None:
    """Run the intigriti-mcp FastMCP server (stdio transport)."""
    mcp.run()


if __name__ == "__main__":
    main()
