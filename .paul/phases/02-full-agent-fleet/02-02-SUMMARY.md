# 02-02 SUMMARY — Sandbox docker-driver substrate (egress-enforced PoC runner)

**Status:** UNIFY complete (loop closed). All 3 auto tasks qualified PASS; human-verify checkpoint approved (live egress proof on real docker daemon). AC-1..AC-6 met.

## Acceptance Criteria Results

| Criterion | Status | Evidence |
|-----------|--------|----------|
| AC-1: Faithful RunResult (exec, content_hash, verdict map) | Pass | `DockerDriver.run()` impl; success/crash tests; sha256(stdout+stderr) |
| AC-2: Egress deny-by-default vs allowlist | Pass | egress-gate per-cid iptables; LIVE allowed-succeeds + denied→egress_blocked at human-verify |
| AC-3: Isolation + hygiene (env strip, cleanup) | Pass | `--cap-drop=ALL` + no-new-privileges; PATH-only env; try/finally deregister+rm; cleanup-on-exception test |
| AC-4: Resource bounds (output cap, timeout) | Pass | `_bounded_read` MAX_OUTPUT_BYTES; timeout→kill→verdict=timeout tests |
| AC-5: Fail-closed on missing/unreachable gate | Pass | RuntimeError preflight BEFORE networked container; 2 fail-closed tests + LIVE gate-stopped refusal |
| AC-6: Hardened image + infra wiring | Pass | `bs5/sandbox-runtime:0.1.0` build ✓ (56MiB, non-root); compose gate svc + `config -q` ✓ |

Re-verified at UNIFY vs disk: `pytest mcp/sandbox-mcp/tests/` → **40 passed**; `ruff check mcp/sandbox-mcp/ infra/sandbox/` → clean.

## Shipped
- **`mcp/sandbox-mcp/src/sandbox_mcp/drivers/docker.py`** — real `DockerDriver.run()` (was scaffold returning `Verdict.ERROR`). Race-free sequence: `docker create` → gate `/register` (iptables installed) → `docker start -a` (payload runs with rules live) → `/report` → `/deregister` + `rm -f` in `try/finally`. Fail-closed preflight (RuntimeError on unset/unreachable gate BEFORE any networked container). `--cap-drop=ALL --security-opt no-new-privileges --pids-limit 256 --memory 512m --read-only --tmpfs /tmp`, PATH-only env strip, bounded streaming (`_bounded_read` duplicated from local.py w/ attribution — local.py boundary-locked). Verdict map incl `egress_blocked` (blocked∧nonzero). `content_hash=sha256(stdout+stderr)`. FORCE escape (`BS_SANDBOX_DOCKER_FORCE=1`) → `--network none`. `snapshot()` = `docker commit` or `{supported:False}`.
- **`mcp/sandbox-mcp/pyproject.toml`** — +`httpx>=0.27` (gate calls; no docker SDK).
- **`infra/sandbox/egress-gate/{egress_gate.py,Dockerfile,pyproject.toml}`** — FastAPI gate: `/register /deregister /report/{cid} /healthz`. Per-cid chain `BS5_<cid12>` (established+DNS+allowlisted IPs:80/443 → LOG → DROP), jumped from `DOCKER-USER` by container src IP. Deny-by-default. NET_ADMIN + docker.sock(ro), host-net.
- **`infra/sandbox/Dockerfile.runtime`** — `bs5/sandbox-runtime:0.1.0` (alpine 3.20, curl/jq/python3, non-root uid 1000, no caches). DockerDriver default image.
- **`infra/sandbox/README.md`** — trust model, fail-closed contract, build/run, DOOD notes.
- **`infra/docker/docker-compose.yml`** — +`bs5-egress-gate` (host-net, NET_ADMIN, docker.sock, healthcheck) + `sandbox` network; mcp-sandbox gains `SANDBOX_DRIVER=docker`, `BS_EGRESS_GATE_URL` (host.docker.internal:9090), `BS_SANDBOX_NETWORK`, docker.sock, depends_on gate-healthy.
- **Tests:** `tests/test_docker_driver.py` (12 hermetic — mock `_docker_exec` seam + GateStub; success/crash/timeout-kill/output-cap/env-strip+cap-drop/cleanup-on-exception/no-rm/fail-closed×2/egress_blocked/allowed-success/force-none/snapshot×2). Rewrote `test_sandbox_mcp::test_docker_driver_refuses_without_egress_gate` NotImplementedError→fail-closed RuntimeError+no-launch. **40 passed**, ruff clean.

## Verified
pytest 40p · ruff clean (mcp/sandbox-mcp + infra/sandbox) · `docker build Dockerfile.runtime` ✓ (56MiB, tools+non-root confirmed) · `compose config -q` ✓ · live checkpoint approved (allowed-succeeds, denied→egress_blocked, fail-closed, no orphans).

## Deviations / known gaps (no scope change)
1. Base images pinned to minor tags, not `@sha256:` digests — digest-pin = documented operator hardening (fabricating a digest would be dishonest). README-noted.
2. `Dockerfile.mcp-python` does NOT bake a `docker` CLI → in-container DOOD production path needs that follow-up; driver proven host-run. Out of files_modified scope. README-noted.
3. Env read live inside `run()` (not module const) so tests monkeypatch without reload; `EGRESS_GATE_URL` module const kept vestigial for `__all__`/import compat. Added `EGRESS_GATE_ENV` const.
4. Gate `/report` blocked-host names best-effort via `dmesg` parse; DROP-counter fallback flags egress_blocked even without resolved name.
5. WSL host hit `error getting credentials` (docker cred-helper) during verify — env issue, not code.

## Boundaries honored
types.py / local.py / protocol.py / server `_select_driver` / validation domain / infra/sql untouched. No Firecracker, no finding_status migration, no exploit-agent rewrite (→02-03). httpx only, no docker SDK.

## Next
`/paul:unify 02-02` to reconcile + close loop. Then 02-03 (exploit-agent wiring + `exploit_failed_*` enum).
