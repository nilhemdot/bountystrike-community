# 01-07 SUMMARY — Recon rate-limiting token bucket

**Plan:** `.paul/phases/01-community-edition-mvp/01-07-PLAN.md`
**Applied:** 2026-05-31
**Status:** APPLY complete — 3/3 tasks qualified PASS. Ready for UNIFY.

---

## What shipped

Wired the already-built, audit-hardened `TokenBucketLimiter`
(`mcp/politeness-mcp`) into the recon pipeline's one unbounded in-process
egress path — the reflection prober's per-candidate HTTP GET. WIRE-not-build,
same posture as 01-06 oracles. `bucket.py` was not touched.

| File | Change |
|------|--------|
| `pyproject.toml` | `[tool.uv.sources] += politeness-mcp = { workspace = true }` |
| `control-plane/pyproject.toml` | `dependencies += "politeness-mcp"` (workspace, `uv sync --all-packages`) |
| `control-plane/src/control_plane/domains/recon/probers.py` | `HttpxReflectionProber` gains keyword-only `limiter` / `rps_for_host` (both default `None`); gated path does acquire-before / report-after, fail-open |
| `control-plane/src/control_plane/domains/recon/__main__.py` | builds one limiter per run, injects `scope_filter.rps_for_host` (relaxed_hosts goes live) |
| `control-plane/tests/test_recon_politeness.py` | NEW — 8 deterministic offline tests |

## Acceptance criteria

| AC | Result |
|----|--------|
| AC-1 dep resolves in control-plane | PASS — `uv sync --all-packages` (195 pkgs), import smoke ok, ruff clean |
| AC-2 each GET gated (acquire before / report after, host from URL) | PASS — order assertion `acquire→get→report` |
| AC-3 per-host override (relaxed_hosts) honoured | PASS — fast=20 / slow=5 via `status()` |
| AC-4 429/503 → adaptive backoff | PASS — `backoff_active` True, `consecutive_429`==1 |
| AC-5 wait-cap exhaustion FAILS OPEN | PASS — `probe→True`, GET not called, `probe_skipped` WARNING |
| AC-7 per-host rps clamped to ceiling | PASS — rps passed to acquire == 50, no crash |
| AC-6 ungated path unchanged | PASS — single GET, substring result; 41 existing recon tests green |

## Audit fixes carried into the build

- **M1 fail-open:** `granted=False` → keep candidate (`probe` returns `True`) +
  `recon.politeness.probe_skipped` WARNING. The deterministic oracle remains the
  sole gate that may reject a finding.
- **M2 bucket key:** `(urlparse(url).hostname or "_nohost").lower()` — never the
  full URL.
- **S1/AC-7 clamp:** `rps = min(rps_for_host(host), MAX_RPS_CEILING)` before acquire.
- **S2 limiter fail-open:** `acquire`/`report` wrapped — a limiter error warns and
  falls through to the ungated GET; never crashes recon.

## Deviations

1. `probers.py` had **no** structlog logger (plan said "use the existing
   logger") — added `log = structlog.get_logger(__name__)`. Additive; import
   landed in the same edit as its use.
2. AC-5 test pre-creates the host bucket via a direct `limiter.acquire` then
   forces `tokens` negative (mirrors `test_bucket.py`'s excessive-wait test) —
   the prober's own acquire cannot easily provoke a >30 s projected wait on a
   fresh bucket.
3. **No** live worker/orchestrator trigger. Recon is launched by orchestrator
   `_phase_recon` as a subprocess, not a Hatchet task — so unlike 01-03/04/05/06
   this plan touches no `tasks.py` / `worker.py` / `orchestrator.py`. Verified by
   import smoke + deterministic offline tests instead.

## Deferred (per plan boundaries)

- `dnsx` / `naabu` pipeline stages → Phase 2.
- Token-bucket / relaxed_hosts batching of the out-of-process ProjectDiscovery
  binaries (they keep their `-rate-limit` flag self-limit; an in-process bucket
  can't throttle a binary's internal request loop).
- Redis / multi-process bucket backend (single-process recon container).
- Skip-rate metrics → Langfuse (Phase 2/3).

## Verification commands

```bash
uv sync --all-packages
cd control-plane && uv run pytest tests/test_recon_politeness.py tests/test_recon.py tests/test_recon_main.py -q   # 49 passed
uv run ruff check control-plane/src/control_plane/domains/recon/probers.py \
  control-plane/src/control_plane/domains/recon/__main__.py \
  control-plane/tests/test_recon_politeness.py   # All checks passed!
```

## Open / deploy gate (01-08)

Live recon→scan pipeline smoke (real binaries + chromium + scope JWT) remains a
deploy-time check, same posture as 01-04/05/06.
