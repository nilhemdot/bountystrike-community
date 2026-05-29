# Stage-2 Boot Runbook — Phase 3 Path B

**Purpose.** Operator-ready checklist for the LLM-augmented orchestrator run
against `mariadb.org` referenced as Path B of the [Path C decision](../signoffs/phase3_lessons.md#decision-path-c--hybrid-recorded-2026-05-13).

**Why this exists.** First Phase-3 run (2026-05-07) hit a WAF wall on three
H1 programs using naive nuclei probing. The Stage-2 orchestrator path —
LLM-driven recon + exploit-agent + validator — is the actual differentiator
and has never been exercised live. This run is the cheap-evidence test that
unblocks the Phase 3 exit gate or proves we need Path A.

**Cost.** ~$8 in non-Anthropic provider spend. ~30–90 min wall clock.
**Blast radius.** Real outbound traffic to `mariadb.org` scope (visible to
HackerOne). Scope-JWT-gated egress prevents out-of-scope hits at the network
layer (build-plan §6.6).

---

## Pre-flight checklist

Each box must be ✓ before firing. Anything ✗ → stop, fix, re-check.

### Stack

- [ ] `docker ps` lists `bs_postgres`, `bs_redis` healthy
- [ ] `docker exec bs_postgres pg_isready -U bs -d bountystrike` returns "accepting connections"
- [ ] `docker exec bs_redis redis-cli PING` returns `PONG`

### Env

From the repo root:

```bash
set -a && source .env && set +a
```

- [ ] `echo $DATABASE_URL` resolves to `bountystrike`
- [ ] `echo $REDIS_URL` set
- [ ] `echo $ANTHROPIC_API_KEY` non-empty (external-LLM routing layer archived 2026-05-18; see `docs/audits/ollama-route-rewire.md`)
- [ ] `ls keys/scope_jwt_private.pem keys/scope_jwt_public.pem` both exist
- [ ] `echo $R2_ACCESS_KEY_ID` non-empty (evidence backend)

### Scanner binaries

- [ ] `which subfinder httpx nuclei` → 3 paths, no "not found"

### MCP servers import-clean

```bash
for d in mcp/oracle-mcp mcp/dedup-mcp mcp/state-mcp mcp/evidence-mcp \
         mcp/sandbox-mcp mcp/politeness-mcp mcp/kev-mcp mcp/normalize-mcp \
         mcp/ev-mcp mcp/scope-mcp; do
  (cd "$d" && uv run --no-sync python -c "import sys; sys.exit(0)") \
    || echo "FAIL: $d"
done
```

- [ ] No `FAIL:` lines printed

### Scope JWT (must be unexpired)

Phase 3 lessons (2026-05-07) recorded the mariadb JWT as `jti=jwt_1778173815_7a4efe1489eae078`, 7-day TTL → expires **2026-05-14**. If today > 2026-05-14, re-mint:

```bash
uv run python scripts/gen_scope_jwt.py \
  --program mariadb \
  --platform hackerone \
  --operator nilhem \
  --hours 24 \
  --out /tmp/mariadb.jwt
export SCOPE_JWT=$(cat /tmp/mariadb.jwt)
```

If the prior JWT is still on disk somewhere (operator habit), re-export it instead.

- [ ] `echo $SCOPE_JWT | cut -d. -f2 | base64 -d 2>/dev/null | python3 -m json.tool`
      shows `exp` in the future and `program == "mariadb"`

### Kill switch armed

```bash
scripts/bs kill-switch-watch --once --dry-run
```

`scripts/bs` is a bash dispatcher (not a Python module); invoke directly, not via `uv run python`.

- [ ] Exits 0 with "no breaches" — confirms `v_oracle_fp_rate` reachable
- [ ] (Optional) Start the systemd unit if running multi-hour:
      `sudo systemctl start bountystrike-kill-switch-watch.service`

### Cost ceiling configured

Build-plan §3.4 Level-2: orchestrator early-stops at 80% of `cost_budget_usd`.

- [ ] Set `COST_BUDGET_USD=10` (default $8 + 25% headroom) or override per shell

### Sandbox driver selection (GAP-aware)

**State as of 2026-05-13**: every production-grade sandbox driver in
`mcp/sandbox-mcp` is GAP-deploy. Picking the wrong driver wastes the
recon + scanner LLM spend on stages that cannot complete.

| Driver | State | When to use |
|--------|-------|-------------|
| `local` | dev-only; refuses unless `BS_SANDBOX_DEV_MODE=1` AND scope JWT carries `dev_mode_sandbox=true`. Production JWTs never do | unit-test loops only — NEVER Stage-2 |
| `docker` | scaffold (`drivers/docker.py`). Returns `Verdict.ERROR` unless `BS_SANDBOX_DOCKER_FORCE=1`. Egress allowlist unenforced even when forced (needs `bs5-egress-gate` sidecar, not implemented) | only if you accept unfiltered egress on real targets — usually no |
| `firecracker` | not implemented (`server.py:53` raises). `infra/sandbox/firecracker/` dir absent. Tracking: build-plan §6.5 | once driver lands |

- [ ] Decide whether this run **needs sandbox execution at all**:
   - **NO sandbox needed** (most likely for this run — goal is "≥1 hypothesis
     finding"): `export SKIP_EXPLOIT=1`. Saves Venice/Hermes spend. Exploit-
     agent fan-out skipped; validator-agent still claims `hypothesis` rows.
     Recon + scanner-agent still run.
   - **YES, must exec PoCs**: pick a driver and set `SANDBOX_DRIVER`, leave
     `SKIP_EXPLOIT` unset. Without `SANDBOX_DRIVER`, sandbox-mcp refuses any
     call and exploit-agent crashes at step 6.
- [ ] If `SKIP_EXPLOIT` is unset (exploit phase will fan out), also:
  `echo $SANDBOX_DRIVER` non-empty

> **Why `SKIP_EXPLOIT=1` and not `MAX_EXPLOITS=0`?**
> Pre-PR-#3 orchestrators built `asyncio.Semaphore(max_exploits)` and
> `gather`'d over the hypothesis findings; with `max_exploits=0` every
> task blocked on `.acquire()` forever (Stage-2 run on 2026-05-17 hung
> 128 tasks this way; see `docs/signoffs/phase3_lessons.md` §Stage-2 first run).
> PR #3 treats `MAX_EXPLOITS<=0` as equivalent to `SKIP_EXPLOIT=1`, so
> both now work — `SKIP_EXPLOIT=1` is preferred for semantic clarity and
> for portability against any operator running a pre-patch checkout.

---

## Fire

From the repo root:

```bash
export PROGRAM_HANDLE=mariadb
export PLATFORM=hackerone
export SCOPE_JWT="<the unexpired JWT from above>"
export SKIP_REPORT=1               # do not actually submit anything
# SKIP_EXPLOIT=1 short-circuits the exploit-agent fan-out — recommended
# until a production sandbox driver lands (see preflight §"Sandbox driver
# selection"). Drop this and export SANDBOX_DRIVER=<driver>, MAX_EXPLOITS=3
# only if you've accepted the GAP-deploy risk.
export SKIP_EXPLOIT=1
export MAX_VALIDATORS=5
export COST_BUDGET_USD=10

uv run python scripts/orchestrator.py 2>&1 | tee /tmp/stage2_$(date +%Y%m%d_%H%M).log
```

The orchestrator will:
1. Create a `scan_jobs` row (status=queued → recon_started → ...)
2. Launch recon-agent (subfinder + httpx + LLM enrichment)
3. Launch scanner-agent (LLM-driven probing — the differentiator)
4. Fan out exploit-agent per hypothesis finding (≤3 concurrent)
5. Fan out validator-agent per exploit_pending_validation finding (≤5 concurrent)
6. Skip reporter (SKIP_REPORT=1)
7. Print summary

---

## Monitoring

Open two extra panes:

**Pane 2 — DB watch:**
```bash
watch -n 5 'docker exec bs_postgres psql -U bs -d bountystrike -c \
  "SELECT status, COUNT(*) FROM findings WHERE job_id = (SELECT id FROM scan_jobs ORDER BY created_at DESC LIMIT 1) GROUP BY status;"'
```

**Pane 3 — Grafana:** open `http://127.0.0.1:3010` → BountyStrike folder → Phase 3 Exit. Watch the FP-rate panel; it should stay flat (no submissions yet because `SKIP_REPORT=1`).

**Pane 4 — Cost:**
```bash
watch -n 30 'uv run python scripts/cost_audit.py --json | python3 -c "import json,sys; d=json.load(sys.stdin); print(f\"\${d.get(\"total_usd\",0):.2f} / \${d.get(\"budget_usd\",0):.2f}\")"'
```

---

## Abort criteria (stop the run)

- Cost watcher shows > $10 spent → `Ctrl+C` + investigate
- Kill switch trips (FP rate > 2%) → orchestrator auto-pauses
- `findings` rows generated against out-of-scope hosts → check scope-JWT egress proxy logs, scope-MCP failed
- Any out-of-scope HTTP egress visible in `audit_log` → escalate, stop

---

## Post-run verification — the actual goal

This run answers a single yes/no question:

> Did Stage 2 produce ≥1 hypothesis finding on a WAF-shielded target?

### Pre-status post-scanner reflection filter (Gap 1 mitigation)

The recon-stage reflection probe (`beb85cf`) drops unreflected `xss-candidate` rows at the recon emission path. Scanner-agent emit path has no equivalent probe (see `docs/audits/validator_agent_contract_audit_2026-05-13.md` §Gap 1). Run the post-scanner filter to drop any unreflected `xss-candidate` rows scanner-agent emitted before the status table is interpreted:

```bash
JOB_ID=$(docker exec bs_postgres psql -U bs -d bountystrike -At -c \
  "SELECT id FROM scan_jobs WHERE program_handle='mariadb' ORDER BY created_at DESC LIMIT 1")
scripts/bs filter-unreflected --job-id "$JOB_ID"
```

```bash
docker exec bs_postgres psql -U bs -d bountystrike -c "
SELECT status, COUNT(*)
FROM findings
WHERE job_id = (SELECT id FROM scan_jobs WHERE program_handle='mariadb' ORDER BY created_at DESC LIMIT 1)
GROUP BY status;
"
```

### Expected status distribution (SKIP_EXPLOIT=1)

With sandbox-stack GAP-deploy and `SKIP_EXPLOIT=1`, the only legitimate
terminal statuses for this run are:

| Status | Meaning |
|--------|---------|
| `hypothesis` | Scanner-agent landed a candidate. Validator's deterministic oracles + reflection-probe class (recon `feat(recon): reflection probe`, commit `beb85cf`) already filtered the bulk of FPs |
| `duplicate` | dedup-mcp caught a prior submission shape |
| `rejected` | scope-guard or FP-class memory pre-empt fired |
| `validation_pending` (`idor-candidate` rows only) | Validator hit Gap 2: recon emitted an `idor-candidate` without session credentials in `oracle_method`. Audit doc `docs/audits/validator_agent_contract_audit_2026-05-13.md` §Gap 2 explicitly whitelists this terminal for IDOR rows |

Any `exploit_attempt`, `approval_pending_t2`, `exploit_failed_*`, or
`exploit_pending_validation` row in this run is a regression — either
`SKIP_EXPLOIT` was unset (or `MAX_EXPLOITS` non-zero on a pre-PR-#3
orchestrator), or the orchestrator ignored the env. A `validation_pending`
row on a non-IDOR CWE is also a regression (it indicates an oracle failure
path the audit did not anticipate).

### Decision branch

- **≥1 hypothesis finding** → continue dynamic. Defer `static-agent`. Next session: pick second target, repeat, build toward 5+ submissions for ρ measurement.
- **0 findings** → Path C decision rule fires. Open `docs/spikes/static_agent_scaffold.md` and commit to Path A next sprint.

Record the outcome in a new section of `docs/signoffs/phase3_lessons.md`:
"## Stage-2 first run (date) — N findings, decision Path X chosen."

---

## Cleanup

- [ ] If pre-flight set up a temporary kill-switch-watch process, stop it
- [ ] Archive `/tmp/stage2_*.log` to `reports/stage2/`
- [ ] Note final cost vs budget in changelog

---

## References

- `scripts/orchestrator.py` — pipeline entry
- `docs/architecture/bountystrike_v5_build_plan.md` §3.4 cost guardrails, §6.6 kill switch
- `docs/signoffs/phase3_lessons.md` — Path C decision context
- `docs/spikes/static_agent_scaffold.md` — Path A fallback design
