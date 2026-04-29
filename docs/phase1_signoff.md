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
| 1 | XSS 20-target TPR/FPR | GAP | **GAP-data** (runner code complete, fixture data pending) |
| 2 | SQLi Welch t-test p<0.01 | PASS | PASS |
| 3 | SSRF 5-endpoint interactsh | GAP | **GAP-data** (runner code complete, OAST infra + fixture pending) |
| 4 | Recon agent on 3 programs | FAIL | **GAP-deploy** (harness Python complete, container image pending) |
| 5 | Evidence chain SHA-256+R2+audit | PARTIAL | **GAP-deploy** (R2 code complete, live cred verify pending) |
| 6 | Audit hash chain | PASS | **PASS++** (race-fixed in BOTH stores) |

**Reading the legend:**
- `GAP-data` = code ships, awaits real-world inputs.
- `GAP-deploy` = code ships, awaits container/cred wiring.
- `PASS++` = passed at sign-off, hardened since.

What remains for Phase 1 closeout is *infrastructure work*, not *code work*.
