# Decision: Enforce scope at the network layer, not the prompt
**Date:** 2026-05-01  **Status:** decided

## Context
An autonomous agent fleet hits live third-party targets. Relying on the LLM to "stay in scope" is unsafe — prompt injection or a reasoning error could send traffic out of bounds, which is a legal/ToS violation in bug bounty.

## Options
| Option | Pro | Con |
|--------|-----|-----|
| Prompt-only scope ("only test X") | trivial | unenforceable; injection bypasses it |
| Signed scope JWT + MCP-side validation | tamper-proof; verifiable per-call | extra signing/verify infra |
| + iptables egress allowlist in microVM | enforced even if MCP is buggy | Firecracker complexity (deferred to Phase 2+) |

## Decision
Sign an RS256 4096-bit scope JWT in the trusted control-plane; every target-touching MCP validates it before acting; a Firecracker egress allowlist derived from the claims is the network backstop. Chosen because scope must hold even against a fully compromised agent.

## Consequences
- Enables hard, auditable scope boundaries independent of LLM behavior (JTI revocation, 168h max expiry).
- Constrains every MCP to carry JWT verification; PyJWT must pin `algorithms=["RS256"]` (none-alg attack).
- Firecracker VM + iptables layer is deferred — full enforcement is Phase 2+.

See [[scope-jwt-trust-boundary]].
