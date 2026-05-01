"""FastMCP server for bugcrowd-mcp.

Exposes one MCP tool: submit_report — POST /submissions.

Required env:
  - BUGCROWD_API_TOKEN — Bugcrowd Researcher API token
Optional:
  - BUGCROWD_BASE_URL    — default https://api.bugcrowd.com
  - BUGCROWD_API_VERSION — default 2024-01-11; pin to a verified date
"""

from __future__ import annotations

import asyncio

from mcp.server.fastmcp import FastMCP

from bugcrowd_mcp.client import BugcrowdClient, BugcrowdError

mcp = FastMCP("bugcrowd-mcp")

_client: BugcrowdClient | None = None
_init_lock = asyncio.Lock()


async def _get_client() -> BugcrowdClient:
    global _client
    if _client is not None:
        return _client
    async with _init_lock:
        if _client is None:
            _client = BugcrowdClient()
    return _client


async def _submit_report_impl(
    client: BugcrowdClient,
    *,
    target: str,
    title: str,
    description: str,
    severity: str,
    vrt_id: str | None = None,
) -> dict:
    try:
        return {
            "ok": True,
            **await client.submit_report(
                target=target,
                title=title,
                description=description,
                severity=severity,
                vrt_id=vrt_id,
            ),
        }
    except BugcrowdError as exc:
        return {
            "ok": False,
            "error": str(exc),
            "status_code": exc.status_code,
            "body": exc.body,
        }


@mcp.tool()
async def submit_report(
    target: str,
    title: str,
    description: str,
    severity: str,
    vrt_id: str | None = None,
) -> dict:
    """Submit a finding to Bugcrowd.

    Call only AFTER T3 approval — the approval-gate hook blocks
    unapproved invocations.

    Args:
        target: Asset URL the finding concerns.
        title: Report title (1..200 chars).
        description: Full markdown report body. Anti-slop hook will
            have rejected non-compliant content upstream.
        severity: ``critical|high|medium|low|informational``. The
            client maps this to Bugcrowd's P1..P5 integer.
        vrt_id: Optional Bugcrowd VRT taxonomy id (Vulnerability
            Rating Taxonomy). Not all programs require it.

    Returns:
        ``{ok, submission_id, status, title, raw}`` on success;
        ``{ok: False, error, status_code, body}`` on failure.
    """
    client = await _get_client()
    return await _submit_report_impl(
        client,
        target=target,
        title=title,
        description=description,
        severity=severity,
        vrt_id=vrt_id,
    )


def main() -> None:
    """Run the bugcrowd-mcp FastMCP server (stdio transport)."""
    mcp.run()


if __name__ == "__main__":
    main()
