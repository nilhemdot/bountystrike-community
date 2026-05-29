# `static-agent` Scaffold — Phase 3 Path A (Contingent)

**Status.** Parked. Triggered only if Stage 2 (Path B per
[Path C decision](../signoffs/phase3_lessons.md#decision-path-c--hybrid-recorded-2026-05-13))
returns 0 hypothesis findings on a WAF-shielded H1 target.

**Purpose.** Add a source-code-scope path to the orchestrator so the system
can earn submissions on programs whose primary scope is a public GitHub
repository (rails, django, phabricator, concretecms, MariaDB server, etc.)
instead of an HTTP endpoint.

**Why this is parked, not built.** The build plan never carved a static-
analysis lane on the orchestrator's critical path. Building it speculatively
before Stage 2 produces zero-findings evidence would violate Karpathy §2
(simplicity first) and §1 (surface tradeoffs before deciding). The
prerequisites for this work (semgrep 1.161.0, trufflehog 3.94.3) are already
installed, but no orchestrator code knows how to invoke them.

---

## Trigger

This document becomes the active sprint plan if **both** are true:

1. `scripts/orchestrator.py` (Stage 2) completes against `mariadb.org` with
   `findings WHERE status IN ('hypothesis', 'exploit_pending_validation', 'validated')` = 0
2. A second WAF-shielded target run produces the same (to rule out target
   specificity)

If only the mariadb run fails, swap target before committing to Path A —
mariadb may simply be hardened beyond reach.

---

## Verifiable goal

Path A is complete when the orchestrator produces **≥1 submission-worthy
finding on a master-branch source-code-scope program** (rails or django
preferred — both have active H1 programs accepting code-level reports as
of 2026-05-13).

Loose definition of "submission-worthy" for the goal:
- Distinct `cwe` mapping
- `evidence_artifacts` row with deterministic PoC fixture compile output
- `findings.status='validated'` (validator-agent confirmed exploitability
  against a vulnerable revision tag)
- Adjudicated by oracle as `confirmed` or `pending` (FP rate ≤ 2%)

---

## Architecture

### New bounded context

`control_plane/domains/static_analysis/` — DDD-clean, mirrors existing
dynamic-scan layout. Surfaces:

- `value_objects/source_scope.py` — `SourceScope(repo_url, ref, commit_sha)`
- `repositories/static_finding_store.py` — persistence for SAST findings
- `services/static_analysis_service.py` — wraps `mcp/static-mcp`
- `services/sast_oracle_service.py` — adjudication for SAST-specific FP patterns
- `errors.py`

### New MCP server

`mcp/static-mcp/` — Python uv project. Tools exposed:

| Tool | Input | Output |
|---|---|---|
| `clone_scope` | `repo_url, ref` | local path + commit_sha (sandboxed, ephemeral fs) |
| `semgrep_scan` | path, ruleset (auto/p/owasp-top-ten/p/r2c) | list of `SastFinding` |
| `trufflehog_scan` | path | list of `SecretFinding` |
| `extract_source_sink` | path, finding | `SourceSinkPair` for validator |
| `cleanup_workspace` | path | confirm deleted |

Out-of-band: sandbox-MCP integration (Firecracker isolation per build-plan
§5.4) — the clone must happen in the existing scope-gated sandbox, not on
host filesystem.

### Orchestrator branch

`scripts/orchestrator.py` gains a scope-type detector at `_phase_recon`:

```python
scope_type = _detect_scope_type(scope_jwt)   # web | source | mixed
if scope_type == "source":
    await _phase_static_clone(...)
    await _phase_static_scan(...)
    await _phase_static_validate(...)
else:
    # existing path: recon → scan → exploit → validate
    ...
```

`_detect_scope_type` looks at `scope.host_or_pattern` shape: anything starting
with `github.com/` or `gitlab.com/` is source-scope; anything else stays
dynamic. Mixed scopes (rare) run both paths and dedup findings post-hoc.

### SAST oracle family

New oracle file `control_plane/domains/oracles/sast_oracles.py` covering:

- `SqlInjectionSastOracle` — taint-flow from request input through string formatting / concatenation into a query call
- `CommandInjectionSastOracle` — shell-execution sinks (system / subprocess-shell / exec-family) reached by request-tainted input
- `PathTraversalSastOracle` — file-open / path-construction sinks with unsanitized path joins
- `HardcodedSecretOracle` — wraps trufflehog output with KEV cross-reference
- `XssTemplateOracle` — template-escape-bypass markers (Jinja safe filter, Django mark-safe, raw-HTML React escape hatches)

Each oracle returns the same `OracleResult` shape the existing dynamic oracle
family emits, so reporter-agent + adjudication flow stays unchanged.

### Validator extension

The hardest part. SAST findings without PoC validation will sink ρ ≤ 0.60.
For each `validated` SAST finding, validator-agent must:

1. Check out the vulnerable commit (`source_sink.commit_sha`)
2. Compile/install the project in the existing sandbox-MCP (language-aware:
   bundler install / pip install / npm ci / etc.)
3. Run a minimal harness that exercises the source→sink path
4. Capture deterministic evidence (stdout + return code + sha256-pinned
   artifact) — same evidence-MCP path as dynamic findings use

Validator may have to maintain per-language compile recipes. Start with
Ruby (rails) and Python (django) since those have the largest H1 source-
scope program populations.

---

## Sprint sequencing

Two sprints, ~10 working days each.

### Sprint A (foundation)

| Day | Task | Acceptance |
|---|---|---|
| 1 | `mcp/static-mcp` scaffold — pyproject, src, tests | `uv run --no-sync python -c "import static_mcp"` clean |
| 2 | `clone_scope` tool — sandbox integration | Test clones django to ephemeral dir, returns commit_sha |
| 3 | `semgrep_scan` tool — JSON output normalization | Test against django/django@main returns ≥1 SastFinding |
| 4 | `trufflehog_scan` tool | Test against intentional-secret fixture returns ≥1 SecretFinding |
| 5 | `extract_source_sink` + value object plumbing | Unit tests green |
| 6 | `control_plane/domains/static_analysis/` skeleton | DDD layout, no business logic yet |
| 7 | Orchestrator branch + `_detect_scope_type` | Existing 542 tests still green; new tests for scope_type detector |
| 8 | Wire `_phase_static_clone` + `_phase_static_scan` | Integration test: orchestrator handles a source scope end-to-end (no validator yet) |
| 9 | SAST oracle family — first three oracles | Per-oracle unit tests + FP fixture |
| 10 | Sprint A review + Phase 3 lessons doc update | Decision: proceed to Sprint B yes/no |

### Sprint B (validator + first finding)

| Day | Task | Acceptance |
|---|---|---|
| 1 | Ruby compile recipe in sandbox-MCP | django+rails fixtures install clean inside sandbox |
| 2 | Python compile recipe | Same |
| 3 | Validator-agent SAST branch | Hits sandbox, runs harness, captures evidence |
| 4 | End-to-end Ruby (rails) target run | `findings.status='validated'` on at least one Ruby finding |
| 5 | End-to-end Python (django) target run | Same for Python |
| 6 | Oracle FP-rate tuning on first batch | Tighten patterns until FP-rate ≤ 2% in `v_oracle_fp_rate` |
| 7 | First real submission via `scripts/orchestrator.py` (drop SKIP_REPORT) | `report_submissions` row created |
| 8 | Wait + reconcile (depends on H1 triage SLA) | `hunt_outcomes` row appears |
| 9 | If accepted: Phase 3 exit criterion §10.5 #1 ticked toward 70% | At least 1 of 5 needed for ρ measurement |
| 10 | Sprint B review + Phase 3 sign-off (or Phase 4 spec) | Phase 3 lessons doc final update |

---

## Risks

| Risk | Impact | Mitigation |
|---|---|---|
| SAST FP rate exceeds 2% threshold | Kill switch trips, no submissions reach H1 | Oracle FP-tuning sprint built into Sprint B day 6 |
| Compile recipe explosion (per-language, per-framework) | Validator becomes infeasible to maintain | Start with Ruby + Python only; defer JS/Go/etc until those programs become priority |
| Vulnerable revision tag missing in `scope_jwt` | Validator cannot pin sandbox to specific commit | Add `commit_sha` field to source scopes during onboarding (`scripts/onboard_hunter.py` update) |
| Trufflehog secrets in commit history that are no longer live | High FP rate on `HardcodedSecretOracle` | Validate secret freshness via KEV-MCP + a probe to the named service before adjudicating |
| Sandbox escape from cloned malicious-input fixtures | Containment failure | Firecracker isolation already mandatory per build-plan §5.4 — reuse, do not weaken |

---

## Out of scope for this scaffold

- Multi-language support beyond Ruby + Python (defer to Phase 4)
- Custom SAST rule authoring (rely on semgrep registry rulesets)
- LLM-augmented triage of SAST findings (every static oracle starts rule-based;
  layer LLM later only if FP rate stays too high)
- Bug-bounty platform other than HackerOne (Bugcrowd / Intigriti source-scope
  programs come later)

---

## References

- `docs/signoffs/phase3_lessons.md` — Path C decision and trigger conditions
- `docs/runbooks/stage2_boot_runbook.md` — what produces the 0-findings signal that activates this scaffold
- `docs/architecture/bountystrike_v5_build_plan.md` line 322 — semgrep/trufflehog listed in toolbelt
- `docs/research/06-roadmap.md` — phase boundaries
