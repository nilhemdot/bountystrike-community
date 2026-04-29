"""oracle-mcp — deterministic verification oracles for BountyStrike v5.

Per build plan §5: 8 bug-class oracles (XSS, SSRF, SQLi, SSTI, IDOR,
open-redirect, RCE, SSRF→IMDS) exposed over MCP stdio for the
validator-agent. Stateless verification probes — no persistence here;
evidence storage is Phase 1.2's evidence-mcp's responsibility.
"""

from .result import OracleResult, Verdict

__all__ = ["OracleResult", "Verdict"]
__version__ = "0.1.0"
