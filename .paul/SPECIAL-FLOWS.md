# Special Flows: BountyStrike-AIv7

Specialized skill integrations for this project. Verified during UNIFY.

## Project-Level Skills

| Skill | Work Type | Priority | Trigger |
|-------|-----------|----------|---------|
| /llm-recon | AI endpoint fingerprinting (OWASP LLM Top 10) | Required | Before attacking any LLM/MCP/RAG endpoint — fingerprint model, extract system prompt, map injection surfaces |
| /llm-audit | AI red-team findings compilation | Required | Wrapping up ai-vuln-hunter engagement — compile multi-technique results into structured report |
| /ai-jailbreak | Structural/architectural jailbreak probes | Required | Testing LLM guardrails — promptinject, DAN, encoding, CoT exploit against target AI endpoints |
| /obfuscation-bypass | Content-filter evasion encoding | Required | When string-match/tokenizer safety filters block payloads — Base64/Hex/Unicode/homoglyph transforms |
| /openrouter | Multi-model attack orchestration | Required | Sending prompts to target LLMs, multi-model parallel comparison, multi-turn attack history |
| /e2e | End-to-end critical flow testing | Required | Testing recon→scan→validate→report pipeline end-to-end |

## Skill Routing Map

All AI red-team skills route to the **ai-vuln-hunter** subagent for OWASP LLM Top 10 work:
- Recon: /llm-recon (always first)
- Attack: /ai-jailbreak + /obfuscation-bypass
- Delivery: /openrouter
- Report: /llm-audit

/e2e routes to pipeline testing (recon → scan → validate → report).

## Phase Overrides

None configured.

## Templates / Assets

None configured.

---
*SPECIAL-FLOWS.md — Updated 2026-05-27*
