# Scope-JWT Trust Boundary
**Definition:** Scope is enforced at the network layer via a signed RS256 JWT, not by trusting the agent's prompt. The control-plane signs claims (allowed hosts, wildcards, IPs, exclusions, rate limits); every MCP that touches a target validates the signature before acting.
**Why it matters:** A prompt-injected or buggy agent cannot expand its own scope — the firewall and the JWT verifier, not the LLM, decide what is reachable.

## How it works
`jwt_issuer.py` (trusted plane) signs with a gitignored 4096-bit RSA private key (`keys/scope_jwt_private.pem`), 168h max expiry, JTI revocation. `scope-mcp` (TypeScript) verifies the signature against the public key and extracts claims. In Phase 2+, a Firecracker microVM runs an iptables egress allowlist derived from the JWT claims. Ambiguous cases the regex hook can't resolve escalate to the `scope-guard` sub-agent. PyJWT must hardcode `algorithms=["RS256"]` to block the none-alg attack (RFC 8725 §2.1).

## Related
- [[scope-enforced-at-network-not-prompt]] — the decision record
- [[ControlPlane]] — `jwt_issuer.py` is the signer
- [[SubAgents]] — scope-guard adjudicates ambiguous cases
- [[kill-switch]] — the other network-layer safety control

## Sources
- docs/system-architecture.md §4 — 2026-05-01
- control-plane/.../scope_management/services/jwt_issuer.py — current
