"""FastMCP server for normalize-mcp.

Exposes three MCP tools:
  - cvss_score(vector)         — compute base score + severity for a v3.1 / v4.0 vector
  - severity_from_cvss(score)  — score → {informational, low, medium, high, critical}
  - cwe_normalize(value)       — canonical ``CWE-<int>`` from slug / numeric / mixed

Transport: stdio (default FastMCP transport).
Entry point: ``normalize-mcp`` CLI script (see pyproject.toml).
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from normalize_mcp import cvss_calc, cwe

mcp = FastMCP("normalize-mcp")


@mcp.tool()
async def cvss_score(vector: str) -> dict:
    """Compute the CVSS base score for a v3.1 or v4.0 vector string.

    Auto-detects version from the ``CVSS:3.1/`` or ``CVSS:4.0/`` prefix.
    Used by the reporter-agent before submission to populate the
    severity field.

    Args:
        vector: Full vector string. Example::

            CVSS:3.1/AV:N/AC:L/PR:L/UI:N/S:U/C:H/I:H/A:H

    Returns:
        ``{vector, version, base_score, severity}``.

    Raises:
        ValueError: malformed vector or unsupported version.
    """
    return cvss_calc.compute(vector)


@mcp.tool()
async def severity_from_cvss(score: float) -> dict:
    """Map a numeric CVSS base score to its severity label.

    Returns:
        ``{score, severity}`` where severity is one of
        ``informational | low | medium | high | critical``.
    """
    return {"score": float(score), "severity": cvss_calc.severity_from_score(float(score))}


@mcp.tool()
async def cwe_normalize(value: str) -> dict:
    """Normalise a CWE identifier or recon slug to ``CWE-<int>``.

    Used wherever code reads cwe values that originate from heterogeneous
    sources (recon emissions, oracle outputs, manual operator entry).

    Args:
        value: Slug (``xss``, ``ssrf-imds-candidate``), numeric (``79``),
            full ID (``CWE-79``), or cloud cluster (``cloud-iam-privesc``).

    Returns:
        ``{input, cwe, mitre_id}``.

    Raises:
        ValueError: input cannot be mapped.
    """
    canonical = cwe.normalize(value)
    mitre_id = int(canonical.split("-", 1)[1])
    return {"input": value, "cwe": canonical, "mitre_id": mitre_id}


def main() -> None:
    """Run the normalize-mcp FastMCP server (stdio transport)."""
    mcp.run()


if __name__ == "__main__":
    main()
