# OracleMcp
**Type:** component
**Summary:** `mcp/oracle-mcp/` — stateless deterministic vulnerability verifiers backed by Playwright (DOM/JS execution) and Interactsh (OAST callbacks). Turns a raw exploit candidate into a deterministic verdict, the gate that lets the platform claim TPR=1.0 / FPR=0.0.

## Key Facts
- 8 verifiers on disk: `verify_xss`, `verify_ssrf`, `verify_sqli`, `verify_ssti`, `verify_open_redirect`, `verify_ssrf_imds`, `verify_idor`, `verify_rce`.
- 7 of 8 field-validated at **TPR=1.0 / FPR=0.0** (XSS, SSRF, SSRF→IMDS, IDOR, RCE, SSTI, Open Redirect). **SQLi suite pending** (W9-10).
- Field-validation harnesses live in `scripts/run_*_field_validation.py` (one per vuln class).
- Extra deps vs baseline MCP: `playwright>=1.48`, `scipy>=1.13`, `cryptography>=43`.
- Playwright footgun: register the dialog handler BEFORE the trigger and always accept/dismiss, or the page freezes.

## Connections
- [[deterministic-oracles]] — the decision behind this design
- [[finding-lifecycle]] — oracle verdict drives `validation_pending → validated | rejected`
- [[SubAgents]] — `validator-agent` calls the verifiers
- [[McpServers]] — part of the MCP fleet

## Sources
- docs/codebase-summary.md §MCP Inventory — 2026-05-01
- docs/system-architecture.md §6 — 2026-05-01
