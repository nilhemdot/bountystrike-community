# Decision: Validate findings with deterministic oracles (TPR=1.0 / FPR=0.0)
**Date:** 2026-05-01  **Status:** decided

## Context
LLM agents hallucinate vulnerabilities ("AnyPoC" reward-hacking) and produce false positives that waste triager goodwill and burn program reputation. A finding must be machine-proven before it can be submitted.

## Options
| Option | Pro | Con |
|--------|-----|-----|
| LLM self-judges its own PoC | cheap | reward-hackable; no ground truth |
| Heuristic scanners (nuclei et al.) as truth | fast | noisy; designed for triage, not proof |
| Deterministic oracle per vuln class, field-validated | provable verdict | one oracle to build/validate per class |

## Decision
Each vuln class gets a deterministic oracle in `oracle-mcp` (Playwright for DOM/JS execution, Interactsh for blind/OOB callbacks), and may not wire to agents until its field-validation suite hits **TPR=1.0 / FPR=0.0**. Chosen because a verifiable verdict is the only defensible basis for auto-submission.

## Consequences
- Enables trustworthy `validation_pending → validated|rejected` transitions and a credible quality bar.
- Constrains new vuln classes: no oracle + passing suite = not shippable (SQLi still pending W9-10).
- Heuristic scanners are demoted to candidate-generation only, never proof.

Implemented by [[OracleMcp]]; drives [[finding-lifecycle]].
