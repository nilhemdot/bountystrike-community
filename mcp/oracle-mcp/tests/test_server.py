"""Tests for the oracle-mcp FastMCP server registration."""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_server_tools_registered():
    """The FastMCP app must expose exactly the three oracle tools."""
    from oracle_mcp.server import mcp

    tools = await mcp.list_tools()
    tool_names = {t.name for t in tools}

    assert "verify_xss" in tool_names, f"verify_xss missing; got {tool_names}"
    assert "verify_ssrf" in tool_names, f"verify_ssrf missing; got {tool_names}"
    assert "verify_sqli" in tool_names, f"verify_sqli missing; got {tool_names}"
