# Validator-Agent Contract Audit — 2026-05-13

**Status:** Draft (operator review pending)
**Auditor:** Claude Code session `10525405` (resumed from `bs5-fp-defense`)
**Trigger:** Stage-2 boot run (~$8, real HackerOne traffic to `mariadb.org`) is the natural next step. This audit de-risks that spend by mapping contract gaps between `.claude/agents/validator.md` and the actual recon/scanner emission paths *before* the spend.

**Output discipline:** read-only. No source files modified. Single doc.

---

## 1. Exec Summary

| Gap # | Title                                            | Severity | Stage-2 Impact (with `MAX_EXPLOITS=0`)                                    | Operator Decision Needed                                              |
| ----- | ------------------------------------------------ | -------- | ------------------------------------------------------------------------- | --------------------------------------------------------------------- |
| Gap 1 | Scanner-agent emit path lacks reflection probe   | HIGH     | Recon path is clean post-`beb85cf`; scanner-agent Python missing → moot for first boot, regression risk once scanner-agent ships | Accept (manual `bs filter-unreflected` between scanner + validator), or block boot until scanner-agent emit path is implemented with embedded probe? |
| Gap 2 | IDOR `oracle_method` session credentials capture is undefined | HIGH     | Any `idor-candidate` recon emits will land at `validation_pending` 100%; mariadb's auth surface unknown → impact may be 0 or N | Skip IDOR for Stage-2 (set runbook gate), or pre-mint a manual session credential JSON for one known authenticated endpoint? |
| Gap 3 | `raw_finding` jsonb codec assumption in validator | MEDIUM   | Hypothesis-status rows have `raw_finding = '{}'::jsonb` default; validator's `chain_steps` lookup must `json.loads()` before `.get()` access | Document the parse step in `validator.md` (low-risk doc-only fix), or live with current behaviour (always-fallback path triggers — works but undocumented)? |
| Gap 4 | CWE normalization lives in agent runtime, not code | MEDIUM   | Validator agent strips `-candidate` suffix per LLM prompt-following; risk grows with model version drift | Add a normalization regression-fixture in `tests/` for `xss-candidate → verify_xss`, or accept drift until first failed-validation observation? |

**Recommended boot posture (informed by table):** Stage-2 is **conditionally Go** with `MAX_EXPLOITS=0` AND `--skip-idor` runbook flag (not yet implemented — Gap 2 below). Defer until Gap-1 / Gap-2 decisions are recorded in `docs/phase3_lessons.md`. Cost to record decisions: ~0 (operator typing). Cost to boot without recording: $8 + ambiguous post-run signal.

---

## 2. Scope & Method

**Read** (no edits): `.claude/agents/validator.md` (261 lines), `.claude/agents/scanner-agent.md` (226 lines), `.claude/agents/recon.md` (208 lines), `control-plane/src/control_plane/domains/recon/persistence.py:144-153`, `control-plane/src/control_plane/domains/recon/probers.py` (40 lines), `infra/sql/01_schema.sql:156-187`, `infra/sql/05_findings_raw_finding.sql` (21 lines), `mcp/oracle-mcp/src/oracle_mcp/server.py:216-253`, `docs/stage2_boot_runbook.md` (226 lines), `docs/phase3_lessons.md`.

**Not touched:** any file under `control-plane/`, `mcp/`, `infra/sql/`, `scripts/`, or `.claude/agents/`. Classifier-blocked surfaces (per session memory: agent-spec edits get auto-denied even with verbal user OK).

**External references via context7 MCP:**

- **asyncpg** (`/magicstack/asyncpg`) — default jsonb codec returns `str`, not `dict`. Caller must install `set_type_codec('jsonb', json.dumps, json.loads)` or call `json.loads()` explicitly on read.
- **httpx** (`/encode/httpx`) — `params=` dict semantics confirm `HttpxReflectionProber` in `probers.py:30-36` is using the correct primitive for reflection-probe substring match.
- **Playwright Python** (`/microsoft/playwright-python`) — `Page.evaluate()` / `Page.expose_function()` API; confirms `verify_xss` oracle has a sound DOM-mutation detection vector. The gap is purely emission-side, not oracle-side.
- **MCP Python SDK** (`/modelcontextprotocol/python-sdk`) — `arguments: dict[str, Any]` for tool calls. Confirms validator must pass parsed dicts (not JSON strings) to `verify_idor`.

**Method:** for each gap, gather evidence with file:line cites, articulate Stage-2 impact under the runbook's `MAX_EXPLOITS=0` posture, propose the smallest possible fix (not applied), define a cheaper-than-$8 verification, and frame a yes/no operator decision.

---

## 3. Gap 1 — Scanner-agent emit path lacks reflection probe

**Severity:** HIGH (latent — depends on scanner-agent implementation status)
**Evidence:**
- Reflection probe lives only in recon path: `control-plane/src/control_plane/domains/recon/service.py:222-225` (per session memory), implemented by `control-plane/src/control_plane/domains/recon/probers.py:17-36` (`HttpxReflectionProber`).
- Scanner-agent spec INSERT (`.claude/agents/scanner-agent.md:138-150`) populates `raw_finding` and emits `xss-candidate` from arjun and nuclei, with NO equivalent reflection check.
- No scanner-agent Python implementation was discovered in `control-plane/` or `mcp/` during Phase-1 explore. The spec is currently aspirational.
- Compensating control already shipped: `scripts/filter_unreflected_findings.py` (commit `73f5d60`) + `scripts/bs filter-unreflected` (commit `f8a75e1`) — operator-runnable, imports `HttpxReflectionProber` from the shared `probers.py` module.

**Stage-2 Impact:** With `MAX_EXPLOITS=0`, the validator-agent does not get exercised (per `docs/stage2_boot_runbook.md:188-201`, only `hypothesis`/`duplicate`/`rejected` are legitimate terminals). FP `xss-candidate` rows that leak from scanner-agent would simply land at `hypothesis` and never be validated. Result: a recon-clean run that *looks* good in the status distribution but actually leaks scanner-side FPs. The 2026-05-13 FP memories (mariadb `/download/`, WP `?ver=`, WP REST routes) would not re-appear from recon, but could re-appear if scanner-agent fires arjun/nuclei `xss` templates against the same surface.

**Fix Proposal (NOT applied):** Until scanner-agent Python lands, wire `scripts/bs filter-unreflected --job-id <id>` as a mandatory pre-validator step in `docs/stage2_boot_runbook.md` between Step "scan" and "expected status distribution". Two-line addition to the runbook, zero code change. When scanner-agent Python lands, embed `HttpxReflectionProber` into its emit path (mirroring `service.py:222-225`).

**Cheaper Verification:**
```bash
grep -rn "HttpxReflectionProber\|filter_unreflected" .claude/agents/scanner-agent.md
# expect: 0 lines — confirms scanner-agent has no reflection-probe wiring
ls control-plane/src/control_plane/domains/scanner/ 2>&1
# expect: "No such file or directory" — confirms scanner-agent Python not yet built
```

**Operator Decision:** Add the `bs filter-unreflected` step to `stage2_boot_runbook.md` as a mandatory post-scanner pre-validator gate? (yes/no)

---

## 4. Gap 2 — IDOR `oracle_method` session credentials capture is undefined

**Severity:** HIGH
**Evidence:**
- Validator spec requires session credentials in `findings.oracle_method` as JSON string (`.claude/agents/validator.md:129-133`): `owner_headers`, `owner_cookies`, `accessor_headers`, `accessor_cookies`.
- Oracle MCP signature confirms dicts, not strings (`mcp/oracle-mcp/src/oracle_mcp/server.py:217-225`): `owner_headers: dict, owner_cookies: dict, accessor_headers: dict, accessor_cookies: dict`. MCP Python SDK (context7: `/modelcontextprotocol/python-sdk`) confirms tool `arguments: dict[str, Any]`, so the validator agent must `json.loads()` the stored string before calling the tool.
- Recon INSERT signature does NOT populate `oracle_method` (`control-plane/src/control_plane/domains/recon/persistence.py:144-153`): only `id, job_id, program_handle, platform, cwe, url, parameter, status` are written. `findings.oracle_method` is `TEXT` with no `DEFAULT` (`infra/sql/01_schema.sql:166`), so it lands as `NULL`.
- Recon spec emits `idor-candidate` (`.claude/agents/recon.md:143`) under "Resource access without ownership check" — but there is no documented mechanism for recon to obtain or store session credentials.
- Validator spec itself acknowledges this with a safe fallback: "If the JSON is absent, update status to `validation_pending` and exit 0 (needs manual session capture)" (`validator.md:131-133`).

**Stage-2 Impact:** Every `idor-candidate` recon emits during the `mariadb.org` run will land at `validation_pending` with no oracle call attempted. If mariadb's recon surface yields 0 IDOR candidates, impact is 0; if it yields N, the post-run status distribution will show N rows at `validation_pending` that need manual triage. Under `MAX_EXPLOITS=0` posture, these would be a *new* terminal state outside the legitimate set in `docs/stage2_boot_runbook.md:193-197`, which would be misread as a regression.

**Fix Proposal (NOT applied):**
1. Short-term, runbook-only: amend `stage2_boot_runbook.md` "Expected status distribution" to include `validation_pending` as a legitimate terminal for `idor-candidate` rows specifically. Single table row addition.
2. Mid-term: define a manual operator workflow in a new section "IDOR session credential capture" in the runbook — `psql` UPDATE template to populate `oracle_method` for a chosen finding after manual login. Not blocking Stage-2 first boot.
3. Long-term: recon-agent could detect "auth wall" responses (302→login, 401, etc.) and surface candidates differently from anonymous `idor-candidate`. Out of scope for this audit.

**Cheaper Verification:**
```sql
-- Run after Stage-2 scan; expect 0 rows OR rows annotated with operator decision
SELECT cwe, status, COUNT(*) FROM findings
 WHERE job_id = (SELECT id FROM scan_jobs WHERE program_handle='mariadb' ORDER BY created_at DESC LIMIT 1)
   AND cwe LIKE 'idor%'
 GROUP BY cwe, status;
```
```bash
# Confirm runbook does not currently account for idor-validation_pending
grep -n "validation_pending\|idor" docs/stage2_boot_runbook.md
# expect: only commit-reference matches, NOT a status-table row
```

**Operator Decision:** For Stage-2 first boot, treat any `idor-candidate` + `validation_pending` rows as legitimate (not a regression) and record the count in the post-run lessons entry? (yes/no)

---

## 5. Gap 3 — `raw_finding` jsonb codec assumption in validator

**Severity:** MEDIUM (subtle; surfaced by context7 asyncpg docs)
**Evidence:**
- Migration `infra/sql/05_findings_raw_finding.sql:11-12` adds `raw_finding JSONB DEFAULT '{}'::jsonb`. Idempotent.
- Validator spec reads `raw_finding.chain_steps` in dict-access form (`.claude/agents/validator.md:85-91`) for `exploit_pending_validation` rows; spec line 90-91 explicitly handles absence: "When `chain_steps` is absent, fall back to plain-finding oracle dispatch as if the row were `hypothesis`."
- asyncpg context7 (`/magicstack/asyncpg`): default codec maps `json`/`jsonb` → Python `str`. To get a `dict` automatically, caller must install `conn.set_type_codec('jsonb', encoder=json.dumps, decoder=json.loads, schema='pg_catalog')`. No such codec install is documented in `validator.md`.
- Recon never populates `raw_finding` (`persistence.py:144-153` omits the column), so the migration default `'{}'::jsonb` always applies for recon-origin rows. The spec's fallback line 90-91 covers this safely.
- The real risk surface is `exploit_pending_validation` rows where exploit-agent populates `chain_steps`. The validator agent must parse the string into a dict before `.get('chain_steps')`. If the agent's LLM-generated Python does this correctly (almost always — Claude is good at this), no failure. If it tries `raw_finding['chain_steps']` on a string, an error surfaces at runtime, the validator falls back per its own error-handling rule (`validator.md:228-236`) and sets status to `validation_pending`.

**Stage-2 Impact:** Under `MAX_EXPLOITS=0`, exploit-agent never runs, so `exploit_pending_validation` rows do not exist for this boot. **Gap 3 has zero Stage-2-first-run impact** but will surface the next time `MAX_EXPLOITS>0` is set, which gates on Path C decision.

**Fix Proposal (NOT applied):** Add a 3-line note to `.claude/agents/validator.md` under §Step 1: "After the `RETURNING` clause, `raw_finding` arrives as a JSON string (asyncpg default jsonb codec). Use `json.loads()` before accessing `chain_steps`." Doc-only change to a classifier-blocked file — would require Plan-mode-style explicit user OK in a future session, OR alternative: install the codec at the asyncpg connection setup site to make the conversion automatic for all readers.

**Cheaper Verification:**
```bash
grep -n "set_type_codec\|json.loads\|raw_finding" .claude/agents/validator.md
# expect: 'raw_finding' mentions (>=2), 'json.loads' likely absent → confirms gap
grep -rn "set_type_codec" control-plane/src/control_plane/
# expect: confirms whether project-wide jsonb codec is installed anywhere
```

**Operator Decision:** Document the `json.loads` parse step in validator.md (later session, classifier-blocked), or install a project-wide jsonb codec at the asyncpg connection-init site (separate code change)? Either or neither acceptable for Stage-2 first boot.

---

## 6. Gap 4 — CWE normalization lives in agent runtime, not code

**Severity:** MEDIUM
**Evidence:**
- Recon emits `xss-candidate`, `ssrf-candidate`, etc. (`.claude/agents/recon.md:134-144`).
- Validator strips `-candidate` per spec line 65-66: "For legacy `*-candidate` strings from the recon agent, strip `-candidate` and match the prefix (e.g. `ssrf-imds-candidate` → `verify_ssrf_imds`)."
- The strip-and-prefix-match is performed by the validator-agent's LLM at invocation time. There is no Python regression test fixture asserting `xss-candidate → verify_xss`, `ssrf-imds-candidate → verify_ssrf_imds`, etc.
- Risk: future model-version drift (Opus → Sonnet, Sonnet → Haiku, prompt-following regression) silently maps `ssrf-imds-candidate` to `verify_ssrf` (wrong oracle, wrong evidence) without an explicit test failure.

**Stage-2 Impact:** Under `MAX_EXPLOITS=0`, validator does not run. Gap 4 has zero impact on Stage-2 first boot. Becomes a real risk once Path C decision turns dynamic and validator starts firing.

**Fix Proposal (NOT applied):** Add a `tests/test_validator_cwe_normalization.py` that ships an 8-row fixture mapping each `*-candidate` value to the expected oracle tool name, and runs it as a guardrail check via the operator CLI (e.g. `scripts/bs check-cwe-mapping`). The test does not invoke the validator-agent itself — it exercises a small Python helper that mirrors the spec's strip-and-prefix-match logic, and the operator runs it pre-boot. Out-of-scope refactor: move the helper from LLM runtime into a shared Python module that the validator-agent also references — that's a larger architectural change.

**Cheaper Verification:**
```bash
grep -rn "candidate\b" tests/ control-plane/tests/ 2>/dev/null | grep -E "(xss|ssrf|sqli|ssti|idor|rce|open.redirect)-candidate" | head -20
# expect: matches in test_filter_unreflected_findings.py and test_recon.py, but NONE asserting validator-side CWE→oracle mapping
```

**Operator Decision:** Add the cheap CWE normalization fixture before Stage-2 first boot (~30 lines of test code, no agent changes), or defer until first observed misroute? (yes/no)

---

## 7. Stage-2 Go/No-Go Matrix

Each row maps a gap to a boot-time decision under the existing `docs/stage2_boot_runbook.md:188-209` posture.

| Gap | Verdict | Reason | Pre-boot Action |
| --- | --- | --- | --- |
| Gap 1 | **Go (with mitigation)** | scanner-agent Python not built; recon emit path is reflection-clean post-`beb85cf`. Manual `bs filter-unreflected` between scan + validator covers regression risk | Add one-line gate to runbook: "After scanner-agent step, run `scripts/bs filter-unreflected --job-id $JOB_ID`" |
| Gap 2 | **Defer one decision** | `idor-candidate` + `validation_pending` rows will look like regressions in current expected-status table | Amend runbook §"Expected status distribution" to whitelist `validation_pending` for `idor-candidate` rows |
| Gap 3 | **Go (no action needed for this boot)** | `MAX_EXPLOITS=0` means no `exploit_pending_validation` rows → codec gap doesn't surface | Log gap in `phase3_lessons.md` for next session when `MAX_EXPLOITS>0` |
| Gap 4 | **Go (no action needed for this boot)** | Validator does not run with `MAX_EXPLOITS=0`; CWE normalization never exercised | Optional: add CWE fixture before next Path-C dynamic boot |

**Net verdict:** **Go for Stage-2 with `MAX_EXPLOITS=0`** provided the operator records yes/no on the four decisions above and applies the two runbook amendments (Gap 1 and Gap 2 mitigations). Cost of the runbook amendments: ~10 minutes operator-side, $0 spend. Without them, post-run signal is ambiguous and the $8 produces less learning per dollar than it should.

**Hand-off:** the next session should treat this doc as the input to a `docs/phase3_lessons.md` decision entry titled "Stage-2 first run (date) — N findings, decision Path X chosen", per the runbook's existing convention at `docs/stage2_boot_runbook.md:208-209`.

---

## Appendix — References cited

- `.claude/agents/validator.md` (full read, 261 lines)
- `.claude/agents/scanner-agent.md` (full read, 226 lines)
- `.claude/agents/recon.md` (full read, 208 lines)
- `control-plane/src/control_plane/domains/recon/persistence.py:144-153`
- `control-plane/src/control_plane/domains/recon/probers.py:1-39`
- `infra/sql/01_schema.sql:156-187` (findings table + indexes)
- `infra/sql/05_findings_raw_finding.sql:11-21` (raw_finding migration)
- `mcp/oracle-mcp/src/oracle_mcp/server.py:216-253` (verify_idor signature)
- `docs/stage2_boot_runbook.md:188-209` (expected status + decision branch)
- `docs/phase3_lessons.md` (Path C decision context)
- `scripts/filter_unreflected_findings.py` (commit `73f5d60`)
- `scripts/bs filter-unreflected` (commit `f8a75e1`)
- Commits: `beb85cf` (recon reflection probe), `73f5d60` (probers extraction + post-filter), `f8a75e1` (bs CLI wiring)
- context7: `/magicstack/asyncpg`, `/encode/httpx`, `/microsoft/playwright-python`, `/modelcontextprotocol/python-sdk`
