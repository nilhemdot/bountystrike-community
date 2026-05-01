"""FastMCP server for yeswehack-mcp.

Exposes one MCP tool:
  - submit_report(...)  — POST a structured report to YesWeHack

The reporter-agent calls this AFTER T3 approval (enforced upstream by
``pretool_approval_gate.py``). The MCP itself does NOT re-check
approval — that's the hook's job, and duplicating the check inside the
MCP would diverge over time.

Transport: stdio (default FastMCP transport).
Entry point: ``yeswehack-mcp`` CLI script.

Requires ``YESWEHACK_API_TOKEN`` env var. Optional
``YESWEHACK_BASE_URL`` overrides the default platform endpoint (used by
the staging environment).
"""

from __future__ import annotations

import asyncio

from mcp.server.fastmcp import FastMCP

from yeswehack_mcp.client import YesWeHackClient, YesWeHackError

mcp = FastMCP("yeswehack-mcp")

_client: YesWeHackClient | None = None
_init_lock = asyncio.Lock()


async def _get_client() -> YesWeHackClient:
    global _client
    if _client is not None:
        return _client
    async with _init_lock:
        if _client is None:
            _client = YesWeHackClient()
    return _client


async def _submit_report_impl(
    client: YesWeHackClient,
    *,
    program_slug: str,
    title: str,
    scope: str,
    vulnerability_type: str,
    severity: str,
    cvss_vector: str,
    description: str,
    exploit_information: str,
) -> dict:
    try:
        return {
            "ok": True,
            **await client.submit_report(
                program_slug=program_slug,
                title=title,
                scope=scope,
                vulnerability_type=vulnerability_type,
                severity=severity,
                cvss_vector=cvss_vector,
                description=description,
                exploit_information=exploit_information,
            ),
        }
    except YesWeHackError as exc:
        return {
            "ok": False,
            "error": str(exc),
            "status_code": exc.status_code,
            "body": exc.body,
        }


@mcp.tool()
async def submit_report(
    program_slug: str,
    title: str,
    scope: str,
    vulnerability_type: str,
    severity: str,
    cvss_vector: str,
    description: str,
    exploit_information: str,
) -> dict:
    """Submit a finding to YesWeHack.

    Call only AFTER T3 approval has been granted; the approval-gate
    PreToolUse hook blocks unapproved invocations.

    Args:
        program_slug: YWH program slug (e.g. ``acme-corp``).
        title: Report title (1..200 chars).
        scope: Asset URL / scope label this report concerns.
        vulnerability_type: ``CWE-NN`` (preferred) or YWH category slug.
        severity: ``low|medium|high|critical|informational``.
        cvss_vector: CVSS v3.1 or v4 vector string (verbatim).
        description: Full markdown report body. Anti-slop hook will have
            already rejected non-compliant content upstream.
        exploit_information: Reproduction-steps section.

    Returns:
        ``{ok: True, submission_id, title, state, raw}`` on success.
        ``{ok: False, error, status_code, body}`` on platform rejection
        or transport failure.
    """
    client = await _get_client()
    return await _submit_report_impl(
        client,
        program_slug=program_slug,
        title=title,
        scope=scope,
        vulnerability_type=vulnerability_type,
        severity=severity,
        cvss_vector=cvss_vector,
        description=description,
        exploit_information=exploit_information,
    )


def main() -> None:
    """Run the yeswehack-mcp FastMCP server (stdio transport)."""
    mcp.run()


if __name__ == "__main__":
    main()
