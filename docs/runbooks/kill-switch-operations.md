# Kill-Switch Operations Runbook — BountyStrike v5

Operational reference for the three-layer kill switch that halts agent activity within 5 seconds. Use this when an agent goes rogue, a scope violation is detected, or oracle FP rate breaches the 2% threshold.

**Quick action:** `redis-cli -a $REDIS_PASSWORD SET bountystrike:killswitch:global halt_all EX 86400`

## Quick Reference — Three Tiers

| Tier | State | What Gets Blocked | When To Use | SLA |
|---|---|---|---|---|
| **T1** | `halt_submissions` | All `submit_*` tools (H1, Bugcrowd, etc.) | Oracle FP > 2%, bad report submitted | <5s |
| **T2** | `halt_scans` | All network tools + submissions | Scope violation, out-of-scope activity detected | <5s |
| **T3** | `halt_all` | **Every tool call** + process termination | Critical incident, compromised agent | <5s |

Tiers are hierarchical: T2 blocks everything T1 does + network tools; T3 blocks everything + terminates processes.

## Layer Architecture

Three independent enforcement paths (build-plan §6.6):

| Layer | Mechanism | Latency | Fail Mode |
|---|---|---|---|
| **L1** | Redis flag `bountystrike:killswitch:global` | ~10 ms | Manual set/unset |
| **L2** | `.claude/hooks/pretool_killswitch.py` (PreToolUse) | Per tool call | Fail-open if Redis unreachable |
| **L3** | Process supervisor (systemd / docker / pkill) | SIGTERM → SIGKILL | Manual intervention |

**Critical property:** L2 fails open if Redis is down — L3 supervisor is the backstop.

## Activation Procedures

### T1 — Halt Submissions

Blocks all bug bounty submission tools. Oracle FP breach triggers this automatically.

```bash
# Manual activation
redis-cli -a $REDIS_PASSWORD SET bountystrike:killswitch:global halt_submissions EX 86400

# Verify
redis-cli -a $REDIS_PASSWORD GET bountystrike:killswitch:global
# Expected: "halt_submissions"
```

**Effect:** Agents can still scan/exploit but cannot submit reports. Reporter-agents block at `mcp__h1-mcp__submit_report`, etc.

### T2 — Halt Scans

Blocks network-touching tools + submissions.

```bash
# Manual activation
redis-cli -a $REDIS_PASSWORD SET bountystrike:killswitch:global halt_scans EX 86400

# Verify
redis-cli -a $REDIS_PASSWORD GET bountystrike:killswitch:global
# Expected: "halt_scans"
```

**Effect:** Agents cannot run scanners, exploit attempts, OAST callbacks, or submit reports. Blocks: `Bash`, `WebFetch`, `mcp__pd-tools__*`, `mcp__burp__*`, `mcp__caido__*`, `mcp__shodan__*`, `mcp__hexstrike__*`, `mcp__oracle-mcp__*`, `mcp__recon-mcp__*`.

### T3 — Halt All (Emergency)

Blocks every tool call + terminates agent processes.

```bash
# Step 1: Set Redis flag
redis-cli -a $REDIS_PASSWORD SET bountystrike:killswitch:global halt_all EX 86400

# Step 2: Stop orchestrator process
# Docker:
docker compose -f infra/docker/docker-compose.yml exec orchestrator pkill -TERM -f orchestrator.py

# Systemd:
sudo systemctl stop bountystrike-orchestrator.service

# Manual:
pkill -TERM -f "python.*orchestrator.py"

# Step 3: Verify no agent processes remain
ps aux | grep -E 'claude|orchestrator|validator|exploit|reporter' | grep -v grep
# Expected: empty (no running agents)
```

**Effect:** All agents halt immediately. Layer 2 blocks all tool calls; Layer 3 terminates processes.

## Deactivation

Remove the Redis key to lift the kill switch.

```bash
# Clear the flag
redis-cli -a $REDIS_PASSWORD DEL bountystrike:killswitch:global

# Verify inactive
redis-cli -a $REDIS_PASSWORD GET bountystrike:killswitch:global
# Expected: (nil)

# Check monitoring confirms inactive state
tail -f logs/orchestrator.log | grep kill_switch
# Expected: "kill_switch.state_transition state=inactive"
```

**Critical:** After deactivation, review the incident that triggered activation. Fix root cause before resuming operations.

## Monitoring & Alerting

### Automated FP Guard

`scripts/kill_switch_watch.py` polls `v_oracle_fp_rate` every 60s. When any oracle breaches 2% FP rate, it auto-activates T1 (`halt_submissions`) and fires webhook alert.

```bash
# Start as systemd service
sudo systemctl start bountystrike-kill-switch-watch.service
sudo systemctl status bountystrike-kill-switch-watch.service

# Manual one-shot check
python scripts/kill_switch_watch.py --once

# Dry-run (no activation, no webhook)
python scripts/kill_switch_watch.py --once --dry-run
```

**Webhook:** Set `KILL_SWITCH_WEBHOOK_URL` to a Slack/Discord/generic endpoint. Payload:

```json
{
  "alert": "oracle_fp_breach",
  "threshold": 0.02,
  "produced_at": "2026-05-24T14:30:00Z",
  "actor": "kill_switch_watch",
  "breaches": [
    {
      "cwe": "CWE-79",
      "fp_rate": 0.0312,
      "rejected": 5,
      "confirmed": 155,
      "total_submitted": 160
    }
  ]
}
```

### State-Transition Alerts

`KillSwitchMonitor` polls state every 100ms and emits structured logs on INACTIVE → ACTIVE transition. Alert latency <1s (build-plan §10.4).

```bash
# Watch for alerts in real-time
tail -f logs/orchestrator.log | grep 'kill_switch.alert'

# Example alert:
# {"event": "kill_switch.alert", "state": "halt_all", "timestamp": "2026-05-24T14:30:00.123Z", "severity": "critical"}
```

Wire these logs to PagerDuty, Slack, or your monitoring stack.

### Check Current State

```bash
# Redis direct
redis-cli -a $REDIS_PASSWORD GET bountystrike:killswitch:global

# Via control-plane (requires DATABASE_URL + REDIS_URL)
python -m control_plane.domains.safety.services.kill_switch_service status
```

## Expected SLA Metrics

| Metric | Target | Measured (Phase 2 W9-10) | Test |
|---|---|---|---|
| **Activation latency** | <5s | ~0.27s (50-worker test) | `tests/integration/test_kill_switch_*.py` |
| **Alert latency** | <1s | ~0.1s (100ms poll) | `KillSwitchMonitor` default |
| **Redis flag propagation** | <10ms | ~5ms (localhost Redis) | Layer 1 benchmark |

SLA is consistently met across all tiers. The <5s requirement has ~18x headroom.

## Troubleshooting

### 1. Redis Down — Kill Switch Ignored

**Symptom:** Agents continue tool calls despite `bountystrike:killswitch:global` set.

**Diagnosis:**

```bash
# Test Redis connectivity
redis-cli -a $REDIS_PASSWORD ping
# Expected: PONG

# Check pretool_killswitch.py can reach Redis
echo '{"tool_name":"Bash"}' | REDIS_PASSWORD=$REDIS_PASSWORD .claude/hooks/pretool_killswitch.py
# Expected: {} (empty JSON = allow, because fail-open when Redis unreachable)
```

**Root cause:** L2 hook fails open when Redis is unreachable (build-plan §6.6).

**Fix:**

1. **Immediate:** Activate L3 — stop orchestrator process (see T3 activation above).
2. **Restore Redis:** Fix Redis service, verify with `redis-cli ping`.
3. **Re-verify:** Trigger kill switch, confirm hook blocks tool calls.

### 2. Hook Not Firing — Tools Execute Despite Flag

**Symptom:** `bountystrike:killswitch:global=halt_all` set, but tools execute.

**Diagnosis:**

```bash
# Verify hook is wired in settings.json
cat .claude/settings.json | jq '.hooks.PreToolUse'
# Expected: [{"command": ".claude/hooks/pretool_killswitch.py"}]

# Test hook manually
echo '{"tool_name":"Bash"}' | \
  REDIS_PASSWORD=$REDIS_PASSWORD \
  KILL_SWITCH_KEY=bountystrike:killswitch:global \
  .claude/hooks/pretool_killswitch.py
# Expected: {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny", ...}}
```

**Root cause:** Hook not wired in `.claude/settings.json`, or env vars missing.

**Fix:**

1. Wire hook if missing (see [`.claude/hooks/pretool_killswitch.py`](../../.claude/hooks/pretool_killswitch.py) header comment).
2. Export `REDIS_PASSWORD`, `REDIS_HOST`, `REDIS_PORT` in orchestrator env.
3. Restart orchestrator to pick up new settings.

### 3. Supervisor Not Cancelling — Processes Persist After T3

**Symptom:** Agent processes still running after T3 kill switch + SIGTERM.

**Diagnosis:**

```bash
# List all agent processes
ps aux | grep -E 'orchestrator|validator|exploit|reporter' | grep -v grep

# Check process tree
pstree -p $(pgrep -f orchestrator.py)
```

**Root cause:** Processes ignoring SIGTERM, or orphaned subprocesses.

**Fix:**

1. **Send SIGKILL:** `pkill -KILL -f orchestrator.py`
2. **Clean up docker:** `docker compose -f infra/docker/docker-compose.yml down`
3. **Verify:** `ps aux | grep -E 'orchestrator|claude' | grep -v grep` should be empty.
4. **Investigate:** Check logs for stuck asyncio loops, hung network calls, or deadlocked threads.

### 4. Auto-Expiry Confusion — Kill Switch Resets Unexpectedly

**Symptom:** Kill switch clears after 24h without operator action.

**Root cause:** Redis key has `EX 86400` TTL (intentional design — prevents abandoned kill switch from permanently bricking platform).

**Fix:**

- **By design.** If you need persistent halt, re-set the key every 12h, or use a longer TTL:
  ```bash
  redis-cli -a $REDIS_PASSWORD SET bountystrike:killswitch:global halt_all EX 604800  # 7 days
  ```
- For production incidents, document the incident in the audit log before the key expires.

### 5. False FP Breach — Watcher Trips on Transient Spike

**Symptom:** `kill_switch_watch.py` activates T1 due to a single bad oracle verdict, but manual review shows no FP pattern.

**Root cause:** The 7-day rolling window in `v_oracle_fp_rate` includes transient spikes. Threshold is fixed at 2% (Phase 3 §10.5).

**Fix:**

1. **Immediate:** Manually deactivate kill switch (see Deactivation section).
2. **Review:** `SELECT * FROM v_oracle_fp_rate WHERE cwe = 'CWE-XXX';` — confirm transient vs. systemic.
3. **Tune watcher:** If false positives are frequent, increase `FP_RATE_THRESHOLD` in `scripts/kill_switch_watch.py` (default 0.02).
4. **Long-term:** Phase 3+ adds EV-gated submission queue — the watcher becomes a backstop, not the primary gate.

## Post-Incident Checklist

After any kill switch activation:

- [ ] Document incident in audit log: `INSERT INTO audit_log (action, actor, reason, metadata) VALUES (...)`
- [ ] Review Langfuse traces for agent activity leading to activation
- [ ] If FP breach: inspect rejected findings, tune oracle or payloads
- [ ] If scope violation: verify scope-JWT claims match program terms
- [ ] If compromised agent: rotate `ANTHROPIC_API_KEY`, scope-JWT signing key
- [ ] Update this runbook if new failure modes discovered

## Environment Variables

| Variable | Default | Required? | Purpose |
|---|---|---|---|
| `REDIS_HOST` | `127.0.0.1` | Yes | Redis host for L1 flag |
| `REDIS_PORT` | `6379` | Yes | Redis port |
| `REDIS_PASSWORD` | — | **REQUIRED** | AUTH password |
| `REDIS_DB` | `0` | No | Logical DB number |
| `KILL_SWITCH_KEY` | `bountystrike:killswitch:global` | No | Redis key name |
| `KILL_SWITCH_BACKEND` | `redis` | No | `redis` (prod) or `memory` (tests only) |
| `KILL_SWITCH_WEBHOOK_URL` | — | No | Slack/Discord endpoint for FP alerts |
| `DATABASE_URL` | — | Yes (for watcher) | Postgres connection for `v_oracle_fp_rate` |

Full reference: [`configuration-guide.md`](configuration-guide.md).

## See Also

- [`.claude/hooks/pretool_killswitch.py`](../../.claude/hooks/pretool_killswitch.py) — Layer 2 hook source
- [`system-architecture.md`](../system-architecture.md) §Kill-Switch Layers — Mermaid diagram
- [`deployment-guide.md`](deployment-guide.md) §Kill Switch — bring-up instructions
- Build-plan §6.6 — three-layer design rationale
- Build-plan §10.4 — <5s SLA requirement
- Phase 3 §10.5 — oracle FP guard watcher
