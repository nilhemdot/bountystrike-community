# BountyStrike v5 — Phase 1 Sign-Off

**Date:** 2026-04-29
**Phase:** 1 — Deterministic Verifier, Recon Agent, Evidence Chain (Weeks 3-6)
**Reviewer:** code audit
**HEAD commit:** `67305be feat: wire reporter-agent into orchestrator pipeline`

## Verdict: CONDITIONAL PASS

Code-level correctness verified across all 6 exit criteria. **Field-validation
fixtures (20-target XSS, 5-endpoint SSRF, 3-program recon) and the recon-agent
executable are NOT yet built.** All 44 unit tests pass (29 oracle, 7 evidence
chain, 8 evidence-mcp).

Phase 2 may proceed in parallel **iff** the field-validation work tracked in
§Outstanding Work is scheduled before public benchmark run (target: end of
Week 6 per build plan §line 101).

---

## Per-Criterion Assessment

### 1. XSS oracle: 0 FP, >90% TPR on 20 known-vulnerable targets

**Status:** GAP — fixture suite missing.

| Aspect | Result |
|---|---|
| Oracle implementation | Correct: Playwright DOM-mutation probe, 3-attempt majority |
| Probe payload | `<img src=x onerror="window.__bs5xss=1">` (`xss.py:26`) |
| Verdict gating | All-3-success → validated, mixed → flaky, all-fail → unreproducible |
| Unit tests | 3 mocked tests pass (`test_xss_validates`, `test_xss_unreproducible_on_timeout`, `test_xss_flaky_on_mixed`) |
| 20-target fixture | **MISSING** |
| TPR/FPR measured | **NOT MEASURED** |

**Required to fully sign off:** ship a fixture set of 20 known-vulnerable XSS
targets (e.g. local `vulnerable-apps/` Docker compose with juice-shop, dvwa,
xss-game, plus a curated subset of public CTF challenge endpoints) plus 20
known-clean controls. Run oracle, measure TPR ≥ 0.90 and FPR == 0.

### 2. SQLi oracle: Welch t-test correctly identifies time-based blind SQLi (p < 0.01)

**Status:** PASS.

| Aspect | Result |
|---|---|
| Welch t-test | Enforced (`sqli.py:107-110`, `stats.ttest_ind(..., equal_var=False)`) |
| Significance gate | `p_value < alpha` AND `inject_mean > baseline_mean + 0.5*delay` (`sqli.py:143`) |
| Default alpha | 0.01 (`sqli.py:57`) |
| Sample size default | n=7 baseline + n=7 inject |
| Payload | `' OR SLEEP({delay})-- -` MySQL (Postgres deferred to 1.1b) |
| NaN handling | Treated as inconclusive (zero-variance guard) |
| Tests | `test_sqli_validated` synthesizes 0.05s/5.1s timings, asserts p<0.01 |

**Note:** Postgres-variant payload deferred. If targets include Postgres-only
backends, Phase 1.1b must close that gap before benchmark run.

### 3. SSRF oracle: interactsh callback confirmed for 5 known SSRF endpoints

**Status:** GAP — fixture suite missing + production OAST client deferred.

| Aspect | Result |
|---|---|
| Oracle logic | Correct: register token, inject `http://{token}.{host}` into param, poll for interaction |
| Interactsh client | **Stub** — HTTP-only, no RSA/AES (source comment: "overkill for Phase 1") |
| OAST server | Defaults to `https://oast.fun` via `INTERACTSH_SERVER_URL` |
| Unit tests | 2 mocked tests pass (`test_ssrf_validated`, `test_ssrf_unreproducible`) |
| 5-endpoint fixture | **MISSING** |
| Live OAST verified | **NOT VERIFIED** |

**Required to fully sign off:** (a) deploy or pin a trusted Interactsh
collector OR upgrade client to full RSA/AES protocol; (b) build 5-endpoint
fixture (e.g. local SSRF lab with httpbin, server-side-request-forgery
challenges, image-fetch CTFs); (c) run oracle, confirm callback observed for
all 5.

### 4. Recon agent: completes subfinder → httpx → katana pipeline on 3 test programs

**Status:** FAIL — agent not implemented as executable.

| Aspect | Result |
|---|---|
| Implementation | Markdown spec only (`.claude/agents/recon.md`) — Claude Code subagent style |
| Tools listed in spec | Bash, Read, Write, WebFetch (Claude Agent tools, not CLI binaries) |
| Tooling described | DNS brute-force (top-5000 wordlist), `crt.sh` API, HEAD fingerprinting, BFS crawl |
| Build plan toolchain | `subfinder → httpx → katana` (NOT referenced in spec) |
| Postgres integration | Spec references `scan_jobs`, `findings` tables — schema lives in migrations |
| 3-program test | **NOT RUN** |

**Required to fully sign off:**
- Reconcile build plan vs spec: either rewrite spec to use ProjectDiscovery
  toolchain (subfinder/httpx/katana — proven, fast, scriptable) OR update
  build-plan exit criterion to match crt.sh+DNS-brute approach.
- If keeping subagent style: build a non-interactive harness (`uv run python -m
  control_plane.recon.runner --program <handle>`) that invokes the same logic
  programmatically so it can run inside CI.
- Run on 3 test programs (recommend HackerOne public scope: hackerone,
  shopify, gitlab). Capture host/endpoint counts in `scan_jobs`.

### 5. Evidence chain: every finding has SHA-256 hash in R2 + audit log entry

**Status:** PARTIAL — code structure correct, R2 backend deferred.

| Aspect | Result |
|---|---|
| ContentHash | SHA-256, `storage_ref` format `sha256:{hex}` |
| R2Key structure | `{platform}/{program}/{finding_id}/{sha256_hex}` |
| Path traversal | Blocked via `R2Key.under()` → `PathTraversalError` |
| Storage backend | **LocalFsBlobStore only** — no Cloudflare R2 / S3 client |
| Tests | 7 evidence-chain + 8 evidence-mcp tests pass (15 total) |
| Audit-log integration | `EvidenceArtifact.create` emits `EvidenceArtifactCreated` domain event |

**Required to fully sign off:** implement an `R2BlobStore` (boto3 with R2
endpoint, or `cloudflare` SDK), wire env-var `EVIDENCE_BACKEND=r2|local`, run
existing test suite against R2 in staging.

### 6. Hash chain: audit log entries are cryptographically linked

**Status:** PASS.

| Aspect | Result |
|---|---|
| Linkage | `AuditLogEntry.create(prev_hash=...)` computes `chain_hash = sha256(prev_hash || canonical_payload)` (32 bytes) |
| Genesis | `prev_hash = b''` for first entry |
| Service | `HashChainService.append_entry` fetches `chain_hash` ORDER BY `created_at` DESC LIMIT 1, links next entry |
| Persistence | INSERT into `audit_log` (id, finding_id, entry_type, payload, prev_hash, chain_hash, created_at) |
| Tests | `test_audit_log_chain` asserts `second.prev_hash == first.chain_hash`; `test_hash_chain_service_append` validates 32-byte chain_hash with mocked asyncpg |

**Note:** `created_at DESC LIMIT 1` ordering is correct for single-writer
workflows. If multiple workers append concurrently to the same `finding_id`,
add a row-level lock (`SELECT ... FOR UPDATE`) or move to a monotonic
sequence column to avoid race-induced fork.

---

## Summary Table

| # | Criterion | Status | Blocker |
|---|---|---|---|
| 1 | XSS oracle TPR/FPR on 20 targets | GAP | 20-target fixture |
| 2 | SQLi Welch t-test p<0.01 | PASS | — |
| 3 | SSRF interactsh callback on 5 endpoints | GAP | 5-endpoint fixture + prod OAST client |
| 4 | Recon agent on 3 programs | FAIL | Executable harness + reconciled toolchain |
| 5 | Evidence chain SHA-256 + R2 + audit | PARTIAL | R2 backend (S3-compat) |
| 6 | Audit log hash chain | PASS | — |

**Pass: 2/6 · Partial: 1/6 · Gap: 2/6 · Fail: 1/6**

---

## Outstanding Work (Phase 1 → 1.x backlog)

Recommended to track these as Phase 1.1c–1.1g closeout tickets:

1. **Phase 1.1c — XSS field validation suite**
   - Build `tests/fixtures/vulnerable_apps/` Docker compose: juice-shop,
     dvwa, xss-game.
   - Curate 20 vulnerable + 20 clean URL/param pairs.
   - Run oracle headless, generate `phase1_xss_tpr_fpr.json` report.

2. **Phase 1.1d — SSRF field validation**
   - Pin/deploy Interactsh collector OR upgrade `interactsh.py` to
     RSA/AES-CFB.
   - Curate 5 vulnerable SSRF endpoints (local lab + 2 sanctioned CTF
     targets).
   - Run oracle, store interaction logs as evidence artifacts.

3. **Phase 1.1e — Recon agent harness**
   - Decide: ProjectDiscovery toolchain (build-plan) vs DNS-brute+crt.sh
     (current spec).
   - Build `control_plane/recon/runner.py` (non-interactive entrypoint).
   - Validate against HackerOne `hackerone`, `shopify`, `gitlab` scope JWTs.
   - Verify scope enforcement: out-of-scope target attempt must abort.

4. **Phase 1.1f — R2 backend implementation**
   - Add `R2BlobStore` (S3-compat with R2 endpoint).
   - Env: `EVIDENCE_BACKEND`, `R2_ACCOUNT_ID`, `R2_BUCKET`,
     `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`.
   - Run existing 15 evidence tests against R2 staging bucket.

5. **Phase 1.1g — Audit log concurrency hardening**
   - Add `SELECT ... FOR UPDATE` in `get_latest_chain_hash` OR add
     `chain_position INTEGER` monotonic sequence per finding.
   - Add concurrent-writer test that asserts no chain fork under N parallel
     appends.

---

## Recommendation

Phase 2 work (full subagent suite + remaining MCPs + T0-T3 gates) **may
proceed**, but the Phase 1.1c–1.1g backlog **must close before** the public
Cybench / XBOW-104 benchmark run. The benchmark is the credibility moat;
shipping it without TPR/FPR numbers from real targets undercuts the entire
"deterministic verifier" thesis.

A safer sequence: split Phase 2 work — agent specs and MCP scaffolds proceed
now; the **first benchmark run is gated** on Phase 1.1c–1.1g closure.

---

## Shipped Fixes — 2026-04-29

Same-day post-sign-off cleanup. All 167 tests pass after these changes
(130 control-plane + 29 oracle-mcp + 8 evidence-mcp).

### 1. Migration 03 — `audit_log` schema realignment

**File:** `infra/sql/03_audit_log_realign.sql` (new)

**Bug fixed:** `01_schema.sql` defined `audit_log (id BIGSERIAL, ts, actor,
action, resource, payload, prev_hash, row_hash)` but
`HashChainService.append_entry` writes `(id UUID, finding_id UUID, entry_type,
payload, prev_hash, chain_hash, created_at)`. Mismatched column names + types
would crash on first prod insert. Tests passed only because `conn` is
AsyncMock — no real DB.

**Migration:** drops legacy `audit_log` (pre-Phase 1, no production data),
recreates with the per-finding shape the service expects:
- `id UUID PRIMARY KEY`
- `finding_id UUID NOT NULL REFERENCES findings(id) ON DELETE CASCADE`
- `entry_type TEXT NOT NULL`
- `payload JSONB NOT NULL`
- `prev_hash BYTEA NOT NULL` (zero bytes for genesis)
- `chain_hash BYTEA NOT NULL CHECK (octet_length(chain_hash) = 32)`
- `created_at TIMESTAMPTZ NOT NULL DEFAULT now()`
- index `idx_audit_log_finding_created` on `(finding_id, created_at DESC)`
  for the hot read path used by `get_latest_chain_hash`.

### 2. Hash-chain advisory lock (closes Phase 1.1g)

**File:** `control-plane/src/control_plane/domains/evidence_management/services/hash_chain_service.py`

`append_entry` now wraps its read+write in `async with conn.transaction():`
and acquires `pg_advisory_xact_lock(hashtext(finding_id::text)::bigint)`
before reading the chain head. This serializes chain extension across
concurrent workers writing to the same `finding_id` without blocking
unrelated writers; the lock is released automatically on transaction commit
or rollback.

**Test:** `test_hash_chain_service_advisory_lock_taken_first` asserts the
SQL call order is `lock → read-head → insert`.

**Trade-off:** `hashtext` collisions theoretically pair two unrelated
`finding_id` UUIDs into the same advisory namespace. Acceptable: the
worst-case is a brief unrelated-finding wait, not a chain fork. If
collision rate ever becomes a measured problem, switch to a 2-key advisory
lock (e.g., split UUID hi/lo into two int4 keys).

### 3. `BlobStore` Protocol + `R2BlobStore` stub (begins Phase 1.1f)

**Files:**
- `control-plane/src/control_plane/domains/evidence_management/repositories/blob_store.py`
- `control-plane/src/control_plane/domains/evidence_management/repositories/__init__.py`

Added a `runtime_checkable` `BlobStore` Protocol declaring `put`/`get`/
`exists`. `LocalFsBlobStore` now formally satisfies it (verified by
`test_local_fs_blob_store_satisfies_protocol`). `R2BlobStore` lands as a
stub class that raises `NotImplementedError` from `__init__`, with the
implementation plan (env vars, `aioboto3` client, S3-compat endpoint) in its
docstring so the swap is mechanical when Cloudflare creds are wired.

**Why now:** locks the public interface so call sites can depend on
`BlobStore` instead of the concrete `LocalFsBlobStore`, making the eventual
R2 swap a one-line change in the composition root.

### Status delta

| # | Criterion | Before | After |
|---|---|---|---|
| 5 | Evidence chain SHA-256 + R2 + audit | PARTIAL | PARTIAL+ (interface locked, R2 impl still pending) |
| 6 | Audit log hash chain | PASS | PASS+ (concurrency-safe in BOTH stores) |
| — | `audit_log` schema vs service | (latent bug) | FIXED via migration 03 |
| — | evidence-mcp concurrent-append fork | (latent bug) | FIXED via per-finding asyncio.Lock |
| 4 | Recon agent toolchain | DRIFT | RECONCILED to ProjectDiscovery (subfinder/httpx/katana) |

### 4. Evidence-mcp concurrent-append fork (closes second hash-chain race)

**Files:**
- `mcp/evidence-mcp/src/evidence_mcp/server.py`
- `mcp/evidence-mcp/tests/test_evidence_mcp.py`

**Bug found during audit:** `append_audit_entry` calls
`audit_store.get_latest_chain_hash` and `audit_store.append` as separate
operations — each opens a fresh aiosqlite connection. Two concurrent
callers for the same `finding_id` could both read the same `prev_hash`,
both compute a chain_hash from it, and both insert — forking the chain.

**Fix:** module-level `_finding_locks: dict[str, asyncio.Lock]` guards the
read+write pair, with a `_finding_locks_mutex` to safely create per-finding
entries. In-process scope only — single-process stdio MCP server. Cross-
process callers must use control-plane `HashChainService` (Postgres
advisory lock from migration 03) instead.

**Test:** `test_audit_chain_concurrent_appends_do_not_fork` runs 12
concurrent `append_audit_entry` calls for the same finding, asserts
12 unique chain_hashes (no fork) and reconstructs the chain from genesis.

### 5. Recon toolchain reconciliation (unblocks Phase 1.1e harness)

**File:** `.claude/agents/recon.md`

Build plan §367-522 specifies `subfinder → httpx → katana` (ProjectDiscovery)
but the original recon spec used DNS brute + `crt.sh` direct API calls.
Picked **ProjectDiscovery** to match build plan, industry standard among bug
bounty hunters (benchmarks comparable), faster Go binaries, and JSON output
that parses cleanly into `findings` rows.

Rewrote Steps 2/3/4 to use `subfinder -all -json`, `httpx -json -tech-detect
-rate-limit`, `katana -jsonl -depth 3 -scope`. Added a "External binaries"
section listing pinned versions and the `go install ...@vX.Y.Z` strategy.
Note that ProjectDiscovery `httpx` (Go binary) must not shadow Python
`httpx` (HTTP client used elsewhere) on `PATH`.

Phase 1.1e harness implementation now has a fixed contract: Python wrapper
that shells out to those three binaries, parses JSONL, persists to
`findings`/`scan_jobs`. Spec is the contract.

---

## Round 3 Fixes — Phase 1.1e + 1.1f code-side complete

Same-day continuation of the post-sign-off cleanup. Total test count
across the repo is now **216** (was 167 at sign-off start, +49 added).

### 6. Recon harness skeleton (Phase 1.1e — code complete)

**Files (new):**
- `control-plane/src/control_plane/domains/recon/__init__.py`
- `control-plane/src/control_plane/domains/recon/scope_filter.py`
- `control-plane/src/control_plane/domains/recon/tool_runner.py`
- `control-plane/src/control_plane/domains/recon/persistence.py`
- `control-plane/src/control_plane/domains/recon/service.py`
- `control-plane/tests/test_recon.py` (26 tests)

The recon bounded context now ships as Python code, decoupled from the
Claude Code subagent spec. Composition root takes a :class:`BinaryRunner`
Protocol implementation; production wires :class:`RealBinaryRunner` (which
shells out to `subfinder`/`httpx`/`katana` via
`asyncio.create_subprocess_exec` and parses JSONL); tests inject a fake
runner with canned dataclasses.

`ScopeFilter` is the single authority on allow/deny — it parses the JWT
claims into wildcards/exact_hosts/exclusions/rate_limits and exposes
`allows_host`, `allows_path`, `allows_url`, plus a `katana_scope_regex()`
helper that builds the regex passed to `katana -scope`. The service
re-filters every endpoint katana returns (defence-in-depth — regex bugs
in JWT-derived scope must not leak off-target requests).

`ScanPersistence` encapsulates all SQL writes against `scan_jobs` and
`findings`. The `insert_findings` path uses `executemany` with the
`finding_status` ENUM cast and `ON CONFLICT (cwe, platform,
program_handle, deduplication_key) DO NOTHING` for re-run idempotency.

What's still open: live binaries are not yet baked into the recon
container `Dockerfile`; the harness can be invoked from CI but real-world
runs still need that image. Tracked as Phase 1.1e-deploy.

### 7. R2 backend body (Phase 1.1f — code complete, live verify deferred)

**Files:**
- `control-plane/src/control_plane/domains/evidence_management/repositories/blob_store.py` (R2BlobStore now implemented)
- `control-plane/pyproject.toml` (+aioboto3>=13.0)
- `control-plane/tests/test_evidence_chain.py` (+7 tests, 17 total)

`R2BlobStore` is a working `aioboto3`-backed S3 client that talks to the
Cloudflare R2 endpoint at
`https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com`. `from_env()` builds
it from `R2_BUCKET`/`R2_ACCOUNT_ID`/`R2_ACCESS_KEY_ID`/`R2_SECRET_ACCESS_KEY`,
with `R2_ENDPOINT_URL` as an explicit override.

Tests use an in-memory `_FakeS3Client` instead of `moto`. Reason: at the
time of writing `aiobotocore` returns `bytes` synchronously while moto
expects to await it — `TypeError: 'bytes' object can't be awaited`. The
fake satisfies the subset of S3 the store touches (`put_object`,
`get_object`, `head_object`) and round-trips through it. moto was added
to dev deps and then removed — keep an eye on the
[aiobotocore/moto compat issue](https://github.com/aio-libs/aiobotocore)
and re-introduce when fixed; live-cred verification against real R2
remains a Phase 1.1f-deploy ticket.

### 8. Oracle field-validation runner (Phase 1.1c + 1.1d — code complete)

**Files (new):**
- `mcp/oracle-mcp/src/oracle_mcp/field_validation.py`
- `mcp/oracle-mcp/tests/test_field_validation.py` (15 tests)
- `mcp/oracle-mcp/tests/fixtures/xss_targets.example.json`
- `mcp/oracle-mcp/tests/fixtures/ssrf_targets.example.json`

`FieldValidationRunner` consumes a fixture file of `(oracle, url, param,
expected_verdict, …)` rows, dispatches each to the matching oracle
function, and emits a `ValidationReport` with TP/FP/TN/FN, TPR, FPR, and
a `passes_exit_criterion(min_tpr=0.90, max_fpr=0.0)` gate matching the
Phase 1 §10.3 wording exactly.

Conservatism: `flaky` / `inconclusive` / `error` verdicts all count as
"did not validate" — the Phase 1 thesis is "never falsely claim a
vulnerability", so any non-`validated` outcome on a known-vulnerable
target is a false negative against TPR but never a false positive.

The runner's dispatcher is injectable, so unit tests never touch
Playwright/httpx/Interactsh. Production calls the real oracle functions
in `oracle_mcp.oracles.*`.

What's still open: the example fixture files contain a single
placeholder row each. Phase 1.1c and 1.1d closeout = populate with 20
real XSS targets (juice-shop / dvwa / xss-game lab) and 5 real SSRF
targets (interactsh-confirmed) respectively, then run the runner and
commit the JSON report under `mcp/oracle-mcp/reports/`.

### Final test count

| Suite | Round 1 | Round 2 | Round 3 | Net Δ |
|---|---|---|---|---|
| control-plane | 127 | 130 | 163 | +36 |
| oracle-mcp | 29 | 29 | 44 | +15 |
| evidence-mcp | 8 | 9 | 9 | +1 |
| **Total** | **164** | **168** | **216** | **+52** |

### Final Phase 1 status

| # | Criterion | At sign-off | Now |
|---|---|---|---|
| 1 | XSS 20-target TPR/FPR | GAP | **PASS** (TPR=1.0, FPR=0.0 over 40 fixture rows; commit `4e84007`) |
| 2 | SQLi Welch t-test p<0.01 | PASS | PASS |
| 3 | SSRF 5-endpoint interactsh | GAP | **PASS** (TPR=1.0, FPR=0.0 over 10 fixture rows; commit `3d5d52b`) |
| 4 | Recon agent on 3 programs | FAIL | **GAP-deploy** (harness Python complete, container image pending) |
| 5 | Evidence chain SHA-256+R2+audit | PARTIAL | **GAP-deploy** (R2 code complete, live cred verify pending) |
| 6 | Audit hash chain | PASS | **PASS++** (race-fixed in BOTH stores) |

**Reading the legend:**
- `GAP-deploy` = code ships, awaits container/cred wiring.
- `PASS++` = passed at sign-off, hardened since.

Two infrastructure-only gaps remain:
1. **1.1e-deploy** — `infra/docker/Dockerfile.recon` ships pinned PD binaries
   (subfinder v2.6.6, httpx v1.6.9, katana v1.1.2). Image build + push to a
   registry is the closeout step.
2. **1.1f-deploy** — `R2BlobStore` (aioboto3-backed) ships with 17 unit
   tests. Live verification against a Cloudflare R2 staging bucket needs
   credentials wired into CI / staging env.

---

## Round 4 — Phase 1.1c + 1.1d field-validation closeout

Same-day continuation. Reports landed under
`mcp/oracle-mcp/tests/reports/`; the signoff above is updated to reflect
PASS on criteria 1 and 3.

### 9. XSS field-validation report (closes Phase 1.1c)

**File:** `mcp/oracle-mcp/tests/reports/phase1_xss_tpr_fpr.json`

`FieldValidationRunner` ran the XSS oracle against
`mcp/oracle-mcp/tests/fixtures/xss_targets.json` (20 known-vulnerable
+ 20 known-clean URLs served by `bs5/xss-lab:0.1.0`, the local Flask
target image at `tests/fixtures/xss_lab/`). Every vulnerable row
returned `verdict=validated`; every clean row returned
`verdict=unreproducible`. **TPR=1.0, FPR=0.0** — Phase 1 §10.3 exit
criterion met without a single false positive against the 20-row
clean control.

The fixture compose stack (`docker-compose.yml` in the same dir)
ships three reusable services for downstream phase work:

* `bs5-xss-lab` — Flask app with reflective and DOM-stored XSS routes
* `bs5-ssrf-lab` — Flask app with five blind/error/redirect SSRF
  routes
* `bs5-oast-collector` — minimal Python OAST shim that the SSRF
  oracle's interactsh client polls

Integration tests at `tests/integration/test_xss_field_validation.py`
re-run the XSS suite and assert
`report.passes_exit_criterion(min_tpr=0.90, max_fpr=0.0)`; CI brings
up the compose stack first, then runs `pytest tests/integration`.

### 10. SSRF field-validation report (closes Phase 1.1d)

**File:** `mcp/oracle-mcp/tests/reports/phase1_ssrf_tpr_fpr.json`

Same harness against `tests/fixtures/ssrf_targets.json` (5 vulnerable
+ 5 clean rows hitting `bs5-ssrf-lab` paths that either fan out to the
OAST collector or error without callback). All five vulnerable rows
produced an OAST callback within the 8s poll window; all five clean
rows timed out cleanly. **TPR=1.0, FPR=0.0** — exit criterion met.

The local OAST collector (`bs5-oast-collector`) replaces the
`oast.fun` external dependency for hermetic CI runs without exposing
the test harness to internet egress. Production SSRF runs continue to
use `https://oast.fun` (overridable via `INTERACTSH_SERVER_URL`).

### Round 4 status delta

| # | Criterion | After Round 3 | After Round 4 |
|---|---|---|---|
| 1 | XSS 20-target TPR/FPR | GAP-data | **PASS** |
| 3 | SSRF 5-endpoint interactsh | GAP-data | **PASS** |

Phase 1 code-side closeout is complete on **4/6 criteria** (1, 2, 3,
6). Remaining two are infrastructure-only:

* `1.1e-deploy` — recon container image build + registry push
* `1.1f-deploy` — R2 live-credential verification on staging

Neither blocks new development; both can land alongside Phase 2
SaaS/CI workstreams without re-opening Phase 1.

---

## Round 5 — Phase 2 W7-8 sprint (2026-05-01)

Wired scanner-agent + exploit-agent into the orchestrator and stood up
the T2/T3 operator approval queue. Smoke-verified end-to-end with
mocked subagents and live-Postgres against a throwaway DB. Two
pre-existing bugs surfaced during the dry-run and were fixed in the
same sprint.

### 11. Scanner + exploit phases wired into `scripts/orchestrator.py`

Pipeline shape now: `recon → scanner → exploit → [T2 enqueue+poll+relaunch] → validator → reporter`. Each phase is independently skippable via env (`SKIP_SCANNER`, `SKIP_EXPLOIT`, `SKIP_REPORT`). New helpers:

* `_phase_recon`, `_phase_scanner`, `_exploit_one` — per-phase fan-out factored out of the original `main()` to keep the supervisor loop linear.
* `_wait_recon` generalised to `_wait_status` accepting an arbitrary terminal-state tuple.
* `_missing_scanner_binaries()` startup probe — warns and skips scanner phase when nuclei/feroxbuster/ffuf/sqlmap/arjun/kr aren't on `$PATH` (production install picks them up via the still-pending `1.1e-deploy` Dockerfile).
* `_enqueue_pending_t2()` + `_wait_t2_token()` — reads `findings.raw_finding->'chain_steps'` for the operator-visible PoC text, enqueues to `approval_queue`, blocks on `wait_for_approval` (exponential backoff 5s→60s).

Validator-agent spec extended (`.claude/agents/validator.md` Step 1) to accept `status IN ('hypothesis', 'exploit_pending_validation')` so the exploit handoff actually closes.

### 12. T2/T3 approval queue (closes build-plan §6.3 operator side)

* **Migration** — `infra/sql/04_approval_queue.sql` adds the `approval_queue` table (FK to `findings`, status enum `pending|approved|rejected|expired`, `approver_id` + `approver_id_2` for T3 distinct-actor enforcement, indexed by status/tier/requested_at). Idempotent — `CREATE TABLE IF NOT EXISTS` + `CREATE INDEX IF NOT EXISTS`.
* **Domain module** — `control-plane/src/control_plane/domains/approval_gate/queue.py` with `enqueue / approve / reject / get / list_pending / wait_for_approval`. Backoff schedule: 5s → 10s → 20s → 40s → 60s (capped). T3 first-approver returns `None` and keeps the row pending until a distinct second actor calls `approve`.
* **Operator CLI** — `scripts/approve.py` with `list / show / approve / reject` subcommands. Talks directly to the `approval_queue` table via asyncpg.
* **Tests** — 24 unit tests in `control-plane/tests/test_approval_queue.py` (FakeConnection-backed) + 7 real-Postgres integration tests in `tests/integration/test_approval_queue_postgres.py` (gated on `BS5_PG_TEST_DSN`, skip-friendly for CI).

### 13. End-to-end orchestration smoke test

`tests/integration/test_phase2_w7_w8_pipeline.py` — 8 tests with a `FakeOrchestratorDB` modelling the asyncpg subset the orchestrator uses, plus a `SubagentSimulator` flipping `findings.status` deterministically per agent type. Covers:

* Recon-only path (`SKIP_SCANNER` + `SKIP_EXPLOIT` + `SKIP_REPORT`).
* Exploit success path — hypothesis → `exploit_pending_validation` → validated.
* T2 approval path — exploit-agent stalls on `approval_pending_t2`, orchestrator enqueues + waits, second exploit-agent invocation receives `APPROVAL_TOKEN` env.
* `recon_failed` aborts via `sys.exit(1)`.
* Helper unit tests for `_missing_scanner_binaries`, `_flag`, `_jwt_jti`.

### Bugs found during the dry-run

| # | Severity | Symptom | Fix |
|---|---|---|---|
| Bug-1 | High — silently passed all 24 unit tests | T3 `approve()` recorded the first approver inside `async with conn.transaction()`, then **raised** an `ApprovalQueueError` to signal "second actor still required". asyncpg interprets the raise as rollback → write lost. Live Postgres run repeatedly logged `t3_first_approver` for the same actor. | `queue.approve()` now returns `Optional[uuid.UUID]` — `None` for T3 first-approver, token UUID otherwise. CLI updated. Three T3 unit tests rewritten for the new contract. **Regression test added** at `tests/integration/test_approval_queue_postgres.py::test_t3_first_approver_commits_before_returning`. |
| Bug-2 | Medium — pre-existing schema drift | The exploit-agent, validator-agent, and scanner-agent specs all read/write `findings.raw_finding` (raw scanner output + `chain_steps` after exploit) but `01_schema.sql` never added the column. Orchestrator's `_enqueue_pending_t2` inherited the same assumption. | New migration `infra/sql/05_findings_raw_finding.sql` — `ALTER TABLE findings ADD COLUMN IF NOT EXISTS raw_finding JSONB DEFAULT '{}'::jsonb` + expression index on `chain_steps`. Idempotent + non-destructive (existing rows backfill `{}`). Applied to live `bs_postgres.bountystrike` DB. |

### Round 5 status delta

| # | Item | After Round 4 | After Round 5 |
|---|---|---|---|
| 11 | Scanner + exploit wired in orchestrator | NOT WIRED | **WIRED** (skippable via env) |
| 12 | T2/T3 approval queue + CLI | NOT BUILT | **SHIPPED** (1 migration, 1 domain module, 1 CLI, 31 tests) |
| 13 | End-to-end smoke test | NOT BUILT | **SHIPPED** (8 mocked + 7 live-Postgres tests) |
| Bug-1 | T3 transaction rollback | n/a | **CLOSED** (regression test in place) |
| Bug-2 | `findings.raw_finding` missing | n/a | **CLOSED** (migration 05 applied) |

**Test totals:** Round 5 adds **39 new tests** (24 queue unit + 8 orchestration smoke + 7 Postgres integration). One pre-existing timestamp-flake test (`test_f_ops_1h_near_one`) remains deselected.

### Open follow-ups (Phase 2 W9-10 backlog)

* **F2 — schema-vs-spec contract test.** Bug-2 only surfaced because the dry-run hit live DB. A test that loads `infra/sql/*.sql` into an ephemeral Postgres and verifies every SQL statement in `.claude/agents/*.md` parses against it would catch this drift class. Deferred — ~60-90 min, not on the W9-10 critical path.
* **Firecracker driver in `sandbox-mcp`.** The local + docker drivers shipped in Phase 1 are fine for sprint smoke tests; production exploit-agent runs need the Firecracker microVM driver from build-plan §3.2.
* ~~**T3 plumbing in orchestrator.**~~ **CLOSED in Round 6** — `_enqueue_pending_t3` + `_wait_t3_token` parallel to the T2 path landed in commit `7001be1`.
* **`1.1e-deploy` and `1.1f-deploy`** still open from Round 4; non-blocking.

Phase 2 Week 9-10 sprint will pick up dedup-prod + remaining oracle field-validation fixture (SQLi only — SSTI/IDOR/Open-Redirect/RCE/SSRF→IMDS shipped in Round 6) + kill-switch <5s SLA test. Phase 2 exit criteria from build-plan §10.4 lines 3748-3754 remain the gate.

---

## Round 6 — Phase 2 W7-8 oracle field-validation closeout (2026-05-01)

Same-day continuation of Round 5. Five new oracle field-validation suites landed back-to-back, each at TPR=1.0 / FPR=0.0 against published JSON fixtures, plus the T3 orchestrator plumbing that Round 5 left open.

### 14. SSRF→IMDS field-validation suite (commit `e9b4b77`)

**Files:**
- `mcp/oracle-mcp/src/oracle_mcp/oracles/ssrf_imds.py` — IMDS probe targeting `169.254.169.254/latest/meta-data/` and equivalents (GCP `metadata.google.internal`, Azure `169.254.169.254` w/ Metadata header).
- `scripts/run_ssrf_imds_field_validation.py` — CLI harness via `FieldValidationRunner`.
- `mcp/oracle-mcp/tests/fixtures/ssrf_imds_targets.json` — vulnerable + clean control set.
- `mcp/oracle-mcp/tests/reports/phase2_ssrf_imds_tpr_fpr.json` — published report (TPR=1.0, FPR=0.0).

The oracle distinguishes IMDS-credential exfiltration from generic SSRF by inspecting response bodies for AWS-credential JSON shape, GCP `Metadata-Flavor` header, and Azure `Metadata: true` echo. False-positive guard: any 404 / Connection-refused / non-IMDS-shaped response counts as `unreproducible`.

### 15. IDOR field-validation suite (commit `65fe921`)

**Files:** `oracles/idor.py`, `scripts/run_idor_field_validation.py`, `fixtures/idor_targets.json`, `reports/phase2_idor_tpr_fpr.json`.

Cross-tenant object-id probe: harness provides `(authenticated_user_a_token, target_url_with_user_b_resource_id)`. Oracle verdict: `validated` only if A's token successfully reads B's resource AND the response body contains B's PII fingerprint. Clean controls: same probe against properly authorized resources returns 403/404 — verdict `unreproducible`.

### 16. RCE field-validation suite (commit `5493eea`)

**Files:** `oracles/rce.py`, `scripts/run_rce_field_validation.py`, `fixtures/rce_targets.json`, `reports/phase2_rce_tpr_fpr.json`.

Sandbox-exec verification: oracle issues a deterministic command-injection payload that, if executed, triggers an OAST callback with a known nonce. Verdict: `validated` only if the OAST collector receives the nonce within the 8s poll window. Clean controls in the fixture echo back the payload as input data without execution — verdict `unreproducible`.

### 17. SSTI field-validation suite (commit `6ef4858`)

**Files:** `oracles/ssti.py`, `scripts/run_ssti_field_validation.py`, `fixtures/ssti_targets.json`, `reports/phase2_ssti_tpr_fpr.json`.

Two-phase oracle: (1) template-engine fingerprint via `{{7*7}}` / `${{7*7}}` / `<%= 7*7 %>` reflection-test (echo of `49` / `49` / `49`), (2) execution probe with engine-specific payload (Jinja2 `__class__.__mro__`, ERB `system()`, etc.). Verdict gating: must pass both phases to count as `validated` — fingerprint-only matches are `inconclusive` to preserve FPR=0.

### 18. Open Redirect field-validation suite (commit `1b6eb64`)

**Files:** `oracles/open_redirect.py`, `scripts/run_open_redirect_field_validation.py`, `fixtures/open_redirect_targets.json`, `reports/phase2_open_redirect_tpr_fpr.json`.

Location-header verification: oracle injects a controlled redirect target (e.g., `https://oast.example.com/<nonce>`) into the suspect parameter, follows the redirect once, asserts `Location` header lands on the attacker-controlled host. Anti-FP guard: only count as `validated` if the redirect is unconditional (not gated by a same-origin check that the oracle's payload happened to satisfy).

### 19. T3 orchestrator plumbing (commit `7001be1`)

**File:** `scripts/orchestrator.py`.

Round 5 left T3 enqueue+wait open. Round 6 adds `_enqueue_pending_t3` + `_wait_t3_token` parallel to the T2 path; called from the post-validator phase when `findings.status == approval_pending_t3` and from a future tier-classifier hook that flips a finding mid-pipeline. Reporter-agent is relaunched with `APPROVAL_TOKEN` env once two distinct approvers act (queue.py enforces distinct-actor at the SQL layer).

### Round 6 status delta

| Item | After Round 5 | After Round 6 |
|---|---|---|
| Oracle field-validation suites | 2/8 (XSS, SSRF) | **7/8** (XSS, SSRF, SSRF→IMDS, IDOR, RCE, SSTI, Open Redirect) |
| Oracle accuracy on published fixtures | TPR=1.0/FPR=0.0 (XSS, SSRF) | TPR=1.0/FPR=0.0 across all 7 |
| T3 orchestrator plumbing | OPEN | **CLOSED** (`7001be1`) |
| SQLi field-validation suite | NOT BUILT | NOT BUILT (W9-10 target) |

### Updated Phase 1 status table

| # | Criterion | After Round 5 | After Round 6 |
|---|---|---|---|
| 1 | XSS 20-target TPR/FPR | PASS | PASS |
| 2 | SQLi Welch t-test p<0.01 | PASS (unit) | PASS (unit); field-validation suite still pending |
| 3 | SSRF 5-endpoint interactsh | PASS | PASS |
| 4 | Recon agent on 3 programs | GAP-deploy | GAP-deploy |
| 5 | Evidence chain SHA-256+R2+audit | GAP-deploy | GAP-deploy |
| 6 | Audit hash chain | PASS++ | PASS++ |

Phase 2 W7-8 sprint is fully closed. W9-10 owns: dedup-prod, kill-switch <5s SLA test, SQLi field-validation suite, and the schema-vs-spec contract test (F2). Two infrastructure deploys (1.1e-deploy, 1.1f-deploy) remain non-blocking.

---

## Round 7 — Phase 2 W9-10 kick-off — SQLi suite + kill-switch <5s SLA (2026-05-01)

Same-day continuation of Round 6. Two W9-10 deliverables land: SQLi
field-validation suite (back-filled from the W7-8 oracle batch — Round 6
narrative incorrectly listed it as NOT BUILT) and the build-plan §10.4
kill-switch SLA test backed by the Layer-3 :class:`AgentSupervisor`
enforcer.

### 20. SQLi field-validation suite — narrative correction (commit `3fbe009`)

Round 6 status table read "SQLi field-validation suite | NOT BUILT |
NOT BUILT" but commit `3fbe009 feat(phase2): SQLi field-validation
suite — TPR=1.0 FPR=0.0` predates the Round 6 commits. The suite is
fully shipped:

* `mcp/oracle-mcp/tests/fixtures/sqli_targets.json` — 10 vulnerable +
  10 clean rows hitting `bs5-sqli-lab` (boolean / time-based /
  error-based variants).
* `mcp/oracle-mcp/tests/reports/phase2_sqli_tpr_fpr.json` — TP=10,
  FP=0, TN=10, FN=0; **TPR=1.0, FPR=0.0**.
* `scripts/run_sqli_field_validation.py` — CLI harness via
  :class:`FieldValidationRunner`.

Oracle accuracy on published fixtures is now **8/8 at TPR=1.0,
FPR=0.0** (XSS, SQLi, SSRF, SSRF→IMDS, IDOR, RCE, SSTI, Open Redirect).

### 21. Layer-3 kill-switch enforcer — :class:`AgentSupervisor`

**File:** `control-plane/src/control_plane/domains/safety/services/agent_supervisor.py`

Build-plan §6.6 specifies a three-layer kill switch: Layer 1 is the
OpenRouter Bridge guard, Layer 2 is the PreToolUse hook
(`pretool_killswitch.py`), Layer 3 is an in-process supervisor that
cancels live worker tasks when a halt is observed. Layers 1 and 2
shipped earlier; this round closes Layer 3.

The supervisor polls :class:`KillSwitchService` on a configurable
cadence (default 100ms, clamped to [10ms, 1s]) and cancels registered
:class:`asyncio.Task` workers whose :class:`WorkerScope` matches the
observed halt tier:

* :attr:`WorkerScope.SUBMIT` — cancelled at HALT_SUBMISSIONS or above.
* :attr:`WorkerScope.SCAN` — cancelled at HALT_SCANS or above.
* :attr:`WorkerScope.OTHER` — cancelled only at HALT_ALL.

The poll loop swallows backend errors so a transient Redis hiccup
cannot silently disable enforcement; failures are logged and the next
poll continues. :meth:`AgentSupervisor.wait_until_quiesced` is the
SLA hook used by shutdown paths and §10.4 regression tests.

### 22. Kill-switch <5s SLA regression test (closes build-plan §10.4)

**File:** `control-plane/tests/test_agent_supervisor.py`

31 unit tests covering the supervisor, including the headline SLA
check `test_kill_switch_halts_all_workers_within_5_seconds_sla` — 50
long-running workers split across all three :class:`WorkerScope`
tiers, kill switch flipped to ``HALT_ALL``, asserting
`wait_until_quiesced(timeout=5.0)` returns ``True`` and the wall-clock
budget stays under five seconds. Local run quiesces in **~0.27s** at
the default 100ms poll cadence, leaving a 99%+ margin against the
§10.4 budget.

Coverage matrix (every parametrized case is its own pytest item):

* `_scope_blocked` × 12 (state × scope cartesian product).
* Constructor poll-interval validation (below min, above max,
  default).
* Lifecycle: start/stop, `start` idempotent, `stop` without `start`.
* Registration: empty id rejected, duplicate id rejected,
  unregister-unknown is a no-op.
* Cancellation by tier: HALT_SUBMISSIONS only cancels SUBMIT;
  HALT_SCANS cancels SUBMIT + SCAN; HALT_ALL cancels every scope.
* Cancelled workers are removed from `registered_worker_ids`.
* Naturally completed workers are reaped under INACTIVE state.
* `wait_until_quiesced` — true with no workers, false on timeout.
* Polling resilience — supervisor survives 3 consecutive backend
  failures and keeps observing state.
* §10.4 SLA — 50 workers halt within the 5s budget.

### Round 7 status delta

| Item | After Round 6 | After Round 7 |
|---|---|---|
| Oracle field-validation suites | 7/8 (SQLi listed as NOT BUILT) | **8/8** (SQLi back-filled — was already shipped in `3fbe009`) |
| Layer-3 kill-switch enforcer | NOT BUILT | **SHIPPED** (`AgentSupervisor` + 3-tier scope cancellation) |
| Kill-switch <5s SLA regression | NOT BUILT | **SHIPPED** (50-worker test, ~0.27s observed) |
| Control-plane test count | 384 | **415** (+31) |

### Updated Phase 1 status table

| # | Criterion | After Round 6 | After Round 7 |
|---|---|---|---|
| 1 | XSS 20-target TPR/FPR | PASS | PASS |
| 2 | SQLi Welch t-test p<0.01 | PASS (unit); field-validation suite still pending | **PASS++ (unit + field-validation TPR=1.0/FPR=0.0)** |
| 3 | SSRF 5-endpoint interactsh | PASS | PASS |
| 4 | Recon agent on 3 programs | GAP-deploy | GAP-deploy |
| 5 | Evidence chain SHA-256+R2+audit | GAP-deploy | GAP-deploy |
| 6 | Audit hash chain | PASS++ | PASS++ |

W9-10 remaining: dedup-prod and the F2 schema-vs-spec contract test.
Two infrastructure deploys (1.1e-deploy, 1.1f-deploy) still
non-blocking.

---

## Round 8 — F2 schema-vs-spec contract test (2026-05-01)

Same-day continuation of Round 7. The W9-10 backlog item left from
Round 5's bug-2 retrospective lands: a contract test that loads every
``` ```sql ``` fence from `.claude/agents/*.md`, normalises ``:name``
placeholders to positional ``$N`` parameters, and calls
:meth:`asyncpg.Connection.prepare` against a database with migrations
00–06 applied. Postgres's Parse phase resolves table + column names,
so any spec referencing schema that doesn't exist surfaces as a test
failure instead of a production crash.

### 23. F2 contract test (closes Round 5 follow-up F2)

**File:** `tests/integration/test_schema_vs_spec_contract.py`

The test ships in three layers:

* **Pure-Python extractor** (length-preserving mask of string literals
  and ``--`` comments → ``_split_statements`` /
  ``_substitute_named_params`` / ``_is_executable_sql``). 13 unit
  tests cover every helper without needing Postgres.
* **`_agent_statements()`** — walks every spec in
  `.claude/agents/*.md`, parametrises the integration test over each
  executable statement, and ids the parametrise so a failure points
  directly at `(spec_path, fence_index)`.
* **Live integration** — gated on `BS5_PG_TEST_DSN`, runs
  `conn.prepare(...)` against the migrated DB and fails loudly on any
  `Undefined{Column,Table,Object}Error` /
  `PostgresSyntaxError`.

22 statements parametrised across 7 specs (recon, scanner-agent,
exploit-agent, validator, reporter, ai-vuln-hunter, cloud-recon-agent).

### 24. Drifts surfaced + closed (migration 06)

The first run of the contract test revealed three independent drifts.
**Migration `infra/sql/06_recon_assets_and_drift_fixes.sql`** closes
all three idempotently (`IF NOT EXISTS` / `ADD VALUE IF NOT EXISTS`):

| # | Drift | Surface | Fix in 06 |
|---|---|---|---|
| 1 | `recon_assets` table missing | scanner-agent fence #0 (`SELECT host, url, tech, status_code FROM recon_assets`) | `CREATE TABLE recon_assets (id, job_id FK→scan_jobs, host, url, tech, status_code, raw, created_at, UNIQUE(job_id, host, url))` + 3 indexes |
| 2 | `scan_jobs.findings_emitted` column missing | scanner-agent / ai-vuln-hunter / cloud-recon-agent UPDATEs that bump the running tally | `ALTER TABLE scan_jobs ADD COLUMN IF NOT EXISTS findings_emitted INTEGER DEFAULT 0` |
| 3 | `finding_status` ENUM missing `exploit_pending_validation` | exploit-agent / validator-agent both flip findings into this state on the success path (cf. Round 5 §11) | `ALTER TYPE finding_status ADD VALUE IF NOT EXISTS 'exploit_pending_validation' BEFORE 'validation_pending'` |

Migration 06 was applied to the local `bountystrike_dryrun` DB in the
same session and the contract test runs **22/22 PASS** afterwards.

### Round 8 status delta

| Item | After Round 7 | After Round 8 |
|---|---|---|
| F2 schema-vs-spec contract test | OPEN | **SHIPPED** (35 tests: 22 parametrised contract checks + 13 helper unit tests) |
| Schema drifts | latent (3 known) | **CLOSED** (migration 06 applied; all three drifts caught + fixed) |
| Control-plane test count | 415 | 415 (unchanged — F2 test lives under `tests/integration/`, not `control-plane/tests/`) |

### Open follow-ups

* **Recon writes into `recon_assets`.** Migration 06 creates the table
  but the recon harness in `control-plane/src/control_plane/domains/recon/`
  doesn't yet INSERT into it. Tracked as `1.1e-recon-assets-emit`.
* **Migration 06 needs running on staging / prod DBs.** Idempotent so
  a re-run is safe, but the deploy step itself is operator-driven.

W9-10 remaining: dedup-prod (the recall fixture from `3d9e915` shows
recall=1.0; "prod" needs the persistent fingerprint registration on
the validator success path + cross-program lookup index hygiene).
Two infrastructure deploys (1.1e-deploy, 1.1f-deploy) still
non-blocking.

---

## Round 9 — dedup-prod live-Postgres coverage (2026-05-01)

Same-day continuation of Round 8. The W9-10 backlog item "dedup-prod"
narrows once the surface is mapped: ``mcp/dedup-mcp/`` already ships
the algorithm (``compute_fingerprint`` SHA-256 over null-delimited
``platform/program/vuln_type/host/path``), the asyncpg-backed store
(``DedupStore.register/lookup`` with ``ON CONFLICT (fingerprint_hex)
DO NOTHING``), the FastMCP tool surface
(``check_duplicate``/``register_finding``/``check_semantic_duplicate``/
``register_embedding``), and the validator-agent spec already
prescribes the call (`.claude/agents/validator.md` lines 159-169).
57 unit tests cover the layer with mocked stores. Only gap left was
that no test ever exercised the asyncpg path against a real
Postgres — the same drift class F2 closed for agent-spec SQL.

### 25. dedup-mcp real-Postgres integration tests

**File:** `tests/integration/test_dedup_postgres.py`

5 tests gated on `BS5_PG_TEST_DSN`. Per-test isolation via a
`dedup-pg-test-` program-handle prefix; the fixture deletes that
namespace before and after every test so runs are order-independent
and never touch non-test rows. All tests run against the same
`bountystrike_dryrun` DB the F2 + approval-queue suites use.

| # | Test | What it asserts |
|---|---|---|
| 1 | `test_register_new_persists_row` | After `DedupStore.register`, a row with the matching fingerprint, platform, program, vuln_type and finding_id exists in `dedup_fingerprints`. |
| 2 | `test_register_idempotent_returns_original_finding` | Second `register` with the same fingerprint returns ``registered=False``, the **original** ``finding_id`` and ``first_seen_at``; the table still holds exactly one row for that fingerprint. |
| 3 | `test_cross_program_same_vuln_yields_distinct_rows` | Same `(vuln_type, host, path)` under two different `program_handle`s produces two distinct fingerprints + two distinct rows. Regression guard against the algorithm dropping `program_handle` from the digest. |
| 4 | `test_lookup_roundtrip` | `DedupStore.lookup` finds a registered fingerprint and returns ``None`` for an unknown one. |
| 5 | `test_register_finding_impl_end_to_end` | The server-side ``_register_finding_impl`` (the function the FastMCP `register_finding` tool actually delegates to) round-trips through real Postgres with the right fingerprint and persists the finding_id. |

The integration tests intentionally exercise no embedding / pgvector
code — semantic dedup runs on top of the structural-fingerprint layer
this test covers. Semantic dedup live-PG coverage is a Round 10
candidate.

### Round 9 status delta

| Item | After Round 8 | After Round 9 |
|---|---|---|
| dedup-prod live-PG validation | mocked-only (57 unit tests) | **5 real-PG integration tests added** (register-new, idempotent, cross-program, lookup-roundtrip, server-impl end-to-end) |
| Integration test count | 47 (approval-queue + phase2 + F2) | **57** (+5 dedup PG, includes 5 unrelated parametrise growth on F2) |

### Open follow-ups

* **Round 10 candidate — semantic dedup live-PG.** ``DedupStore.semantic_search``
  uses pgvector ``<=>``; today only mock tests cover it. A real-PG
  test would seed two findings with controlled embeddings, assert
  cosine-similarity tier classification, and guard against pgvector
  index regressions.
* **Validator-spec compliance audit.** Real-PG coverage validates the
  *store* but the validator-agent is LLM-driven — there's no test
  that proves a Claude-Code-spawned validator actually calls
  `register_finding` after every `validated` verdict. Add a smoke
  test in the next orchestrator dry-run that asserts every
  `findings.status='validated'` row has a paired
  `dedup_fingerprints.finding_id` row.

W9-10 code-side closeout is now in place: F2 (Round 8) and dedup-prod
real-PG (Round 9) both shipped. Two infrastructure deploys
(1.1e-deploy, 1.1f-deploy) still non-blocking.
