# Kill Switch
**Definition:** A 3-layer emergency stop so any one layer being down is not catastrophic.
**Why it matters:** An autonomous agent fleet making outbound HTTP/subprocess calls needs an instant, defense-in-depth halt the operator fully controls.

## How it works
- **L1 — Redis flag** (~10 ms): operator sets `bountystrike:killswitch:global` (TTL 86400s). Backend `redis` or `memory`.
- **L2 — PreToolUse hook** (`pretool_killswitch.py`, matcher `*`): reads the flag on every tool call, denies if set. **Fail-open** — if Redis is unreachable it allows the call, so a Redis outage doesn't halt all scans.
- **L3 — Process supervisor**: systemd / `docker stop` / `pkill`, SIGTERM→SIGKILL. The backstop if the runtime ignores the hook.

## Related
- [[approval-tiers]] — both gate agent tool calls
- [[SubAgents]] — every agent call traverses L2
- [[scope-jwt-trust-boundary]] — the other network-layer control

## Sources
- docs/system-architecture.md §5 — 2026-05-01
- .claude/hooks/pretool_killswitch.py — current
