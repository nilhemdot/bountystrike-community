"""FastMCP server for h1-mcp.

Exposes one MCP tool:
  - submit_report(...)  — POST /v1/hackers/reports

The reporter-agent calls this AFTER T3 approval (enforced upstream by
``pretool_approval_gate.py``). The MCP itself does not re-check approval.

Transport: stdio (default FastMCP transport).
Entry point: ``h1-mcp`` CLI script.

Required env:
  - ``H1_API_USERNAME`` — your HackerOne username (HTTP Basic user)
  - ``H1_API_TOKEN``    — your HackerOne personal API token
Optional:
  - ``H1_BASE_URL``     — default https://api.hackerone.com
"""

from __future__ import annotations

import asyncio

from mcp.server.fastmcp import FastMCP

from h1_mcp.client import HackerOneClient, HackerOneError

mcp = FastMCP("h1-mcp")

_client: HackerOneClient | None = None
_init_lock = asyncio.Lock()


async def _get_client() -> HackerOneClient:
    global _client
    if _client is not None:
        return _client
    async with _init_lock:
        if _client is None:
            _client = HackerOneClient()
    return _client


async def _submit_report_impl(
    client: HackerOneClient,
    *,
    team_handle: str,
    title: str,
    vulnerability_information: str,
    impact: str,
    severity_rating: str,
    weakness_id: int | None = None,
) -> dict:
    try:
        return {
            "ok": True,
            **await client.submit_report(
                team_handle=team_handle,
                title=title,
                vulnerability_information=vulnerability_information,
                impact=impact,
                severity_rating=severity_rating,
                weakness_id=weakness_id,
            ),
        }
    except HackerOneError as exc:
        return {
            "ok": False,
            "error": str(exc),
            "status_code": exc.status_code,
            "body": exc.body,
        }


@mcp.tool()
async def submit_report(
    team_handle: str,
    title: str,
    vulnerability_information: str,
    impact: str,
    severity_rating: str,
    weakness_id: int | None = None,
) -> dict:
    """Submit a finding to HackerOne.

    Call only AFTER T3 approval — the approval-gate hook blocks
    unapproved invocations.

    Args:
        team_handle: HackerOne program slug (e.g. ``acme-corp``).
        title: Report title (1..200 chars).
        vulnerability_information: Full markdown report body. Anti-slop
            hook will have rejected non-compliant content upstream.
        impact: Impact section (markdown).
        severity_rating: ``none|low|medium|high|critical`` — H1 does not
            recognise ``informational``.
        weakness_id: Optional MITRE CWE numeric ID (e.g. 79). Set to
            None to let H1 triage assign it. Negative or zero raises.

    Returns:
        On success::

            {ok: True, submission_id, title, state, created_at, raw}

        On platform rejection or transport failure::

            {ok: False, error, status_code, body}
    """
    client = await _get_client()
    return await _submit_report_impl(
        client,
        team_handle=team_handle,
        title=title,
        vulnerability_information=vulnerability_information,
        impact=impact,
        severity_rating=severity_rating,
        weakness_id=weakness_id,
    )


def main() -> None:
    """Run the h1-mcp FastMCP server (stdio transport)."""
    mcp.run()


if __name__ == "__main__":
    main()
