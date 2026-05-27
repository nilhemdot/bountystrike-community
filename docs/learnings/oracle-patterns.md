# oracle-patterns.md — Oracle / Vulnerability Detection Patterns

## Field-Validation Requirement

Every oracle must pass TPR=1.0 / FPR=0.0 on its field-validation suite before wiring to agents.

```bash
uv run pytest scripts/run_<oracle>_field_validation.py -v
```

## Oracle Interface

```python
class OracleInput(BaseModel):
    target_url: str
    payload: str
    context: dict[str, str] = {}

class OracleResult(BaseModel):
    confirmed: bool
    confidence: float  # 0.0 - 1.0
    evidence: str
    technique: str
```

## Existing Oracles (oracle-mcp)

| Oracle | Status | Technique |
|--------|--------|-----------|
| XSS | field-validated | Playwright DOM reflection |
| SQLi | field-validated | error pattern + time-based |
| SSRF | field-validated | Interactsh OAST callback |
| SSRF->IMDS | field-validated | metadata endpoint response |
| IDOR | field-validated | response diff + ownership check |
| RCE | field-validated | Interactsh OAST + output capture |
| SSTI | field-validated | template math eval |
| Open Redirect | field-validated | Location header follow |

## Adding a New Oracle

1. Create verifier in `mcp/oracle-mcp/src/oracle_mcp/verifiers/<name>.py`
2. Wire into `mcp/oracle-mcp/src/oracle_mcp/server.py`
3. Create `scripts/run_<name>_field_validation.py` with >=10 TP + >=10 FP test cases
4. Run validation — must hit TPR=1.0 / FPR=0.0
5. Add to oracle tool list in relevant agent specs

## OAST / Interactsh

Used for out-of-band confirmation (SSRF, RCE). Interactsh client is in oracle-mcp. Requires `INTERACTSH_SERVER` and `INTERACTSH_TOKEN` env vars.
