---
phase: "00-truth-in-claims-foundation"
task: "00-04"
title: "SPDX Header Sweep + Import-Linter CI"
status: "COMPLETE"
completed_at: "2026-05-29"
tasks_passed: 6
tasks_total: 6
---

# 00-04 SUMMARY — SPDX Header Sweep + Import-Linter CI

## Task Status

| # | Name | Status | Notes |
|---|------|--------|-------|
| 1 | Write `scripts/add_spdx_headers.py` | PASS | ruff clean; all ACs encoded |
| 2 | Apply sweep to ~243 source files | PASS | 250 files stamped, 1 skipped (script itself), 52 skip-list |
| 3 | Add import-linter to `pyproject.toml` | PASS | PEP 735 `[dependency-groups] dev`, `import-linter~=2.3`; contracts added |
| 4 | Write CI workflow | PASS | YAML valid; both jobs blocking; PR + push triggers |
| 5 | Verify import-linter (clean + canary) | PASS | Clean exit 0; canary exit 1; no residue |
| 6 | Write `docs/learnings/licensing-ci.md` | PASS | All 11 required topics present |

## AC Coverage Map

| AC | Description | Status |
|----|-------------|--------|
| AC-1 | Correct SPDX identifier per root | PASS — AGPL-3.0-or-later for control-plane/mcp/scripts; Apache-2.0 for packages/core (no files); LicenseRef-BountyStrike-Proprietary for packages/enterprise (no files) |
| AC-1a | No foreign/generated code stamped | PASS — foreign-path gate empty for .venv/, /infra/, /dist/ |
| AC-2 | Idempotency | PASS — second apply: "0 files updated"; --check exits 0 after apply |
| AC-2a | Shebang/cookie preservation | PASS — orchestrator.py shebang on line 1; SPDX on line 2 |
| AC-3 | Skip-list correctness | PASS — 52 files skipped (skip-list); no .json/.toml/.md/.lock touched |
| AC-3a | scope-mcp dist excluded, src included | PASS — dist/ in skip-list; mcp/scope-mcp/src/*.ts stamped |
| AC-4 | CI check mode passes on clean tree | PASS — --check exits 0 after apply |
| AC-5 | Import-ban catches forbidden import | PASS — canary in control_plane exits 1 with "not allowed to import" |
| AC-5a | Contract is non-vacuous | PASS — control_plane resolves at /home/nilhem/bountystrike-ai7/control-plane/src/control_plane/__init__.py |
| AC-5b | Canary in scanned source module | PASS — canary placed in control-plane/src/control_plane/; not packages/community/ |
| AC-6 | Import-ban passes on clean tree | PASS — "Contracts: 2 kept, 0 broken." exit 0 |

## Files Created

| File | Type |
|------|------|
| `scripts/add_spdx_headers.py` | New — idempotent SPDX sweep script |
| `.github/workflows/license-and-imports.yml` | New — CI workflow (2 blocking jobs) |
| `docs/learnings/licensing-ci.md` | New — pattern notes |
| `pyproject.toml` | Modified — `import-linter~=2.3` in `[dependency-groups] dev` + `[tool.importlinter]` contracts |

## Files Stamped per Root

| Root | Files stamped | SPDX identifier |
|------|--------------|-----------------|
| `control-plane/**` | 120 | `AGPL-3.0-or-later` |
| `mcp/**` | 103 (py) + 8 (ts) = 111 (minus already-had: see note) | `AGPL-3.0-or-later` |
| `scripts/**` | 27 | `AGPL-3.0-or-later` |
| `packages/core/**` | 0 (no .py/.ts files exist yet) | `Apache-2.0` (configured) |
| `packages/community/**` | 0 (no .py/.ts files exist yet) | `AGPL-3.0-or-later` (configured) |
| `packages/enterprise/**` | 0 (no .py/.ts files exist yet) | `LicenseRef-BountyStrike-Proprietary` (configured) |
| **Total** | **250 files updated** (script self: 1 already-had-header) | |

Note: script itself (`scripts/add_spdx_headers.py`) was written with SPDX already present;
counted in "already have header" (251 total after apply).

## Deviations from Plan

1. **`lint-imports` must be run from repo root, not `control-plane/`** — the plan's verify
   command says `cd control-plane && uv run lint-imports`. This fails because
   `[tool.importlinter]` lives in the root `pyproject.toml`. Correct invocation:
   `cd /repo-root && uv run lint-imports`. CI workflow uses repo root correctly.
   This is a verify-command wording issue in the plan, not a contract defect.

2. **`packages/core`, `packages/community`, `packages/enterprise` have 0 source files** —
   only `LICENSE`, `README.md`, `.gitkeep` exist. No files stamped; allow-list and SPDX
   mapping are configured correctly for when files are added.

3. **CRLF warnings on `git diff`** — many pre-existing files in the repo have Windows CRLF
   line endings. Git emits `CRLF will be replaced by LF` warnings on status/diff but this
   is a pre-existing condition, not introduced by the sweep. The sweep writes UTF-8 with
   the file's original line endings preserved via `splitlines(keepends=True)`.

## Exact Verify Outputs

### ruff check + format (script)

```
All checks passed!
exit=0
1 file already formatted
format-exit=0
```

### --check before apply

```
250 files missing header, 1 files already have header, 52 files skipped
exit=1
```

### Apply (first run)

```
250 files updated, 1 files skipped (already have header), 0 files skipped (not eligible), 52 files skipped (skip-list)
exit=0
```

### Idempotency proof (second apply)

```
0 files updated, 251 files skipped (already have header), 0 files skipped (not eligible), 52 files skipped (skip-list)
exit=0
```

### --check after apply

```
0 files missing header, 251 files already have header, 52 files skipped
exit=0
```

### Foreign-path gate (venv/infra/dist)

```
GATE PASSED: no foreign paths
```

(The grep `git diff --name-only | grep -E '\.venv/|/infra/|/dist/'` returned empty.
`.claude/agents/*.md` appeared in `git diff` but are pre-existing unrelated working-tree
changes from before this session; the sweep never touches `.claude/` per allow-list +
skip-list. `.md` files are in the skip-list regardless.)

### Shebang survival

```
head -1 scripts/orchestrator.py → #!/usr/bin/env python3  (OK shebang preserved)
head -2 scripts/orchestrator.py → # SPDX-License-Identifier: AGPL-3.0-or-later
```

### lint-imports clean tree

```
community must not import enterprise KEPT
core must not import enterprise KEPT
Contracts: 2 kept, 0 broken.
exit=0
```

### control_plane resolves (non-vacuous)

```
control_plane resolves OK: /home/nilhem/bountystrike-ai7/control-plane/src/control_plane/__init__.py
```

### Canary negative test

```
Canary created: control-plane/src/control_plane/_import_ban_canary_DELETE_ME.py
lint-imports → "control_plane is not allowed to import bountystrike_enterprise"
lint-imports-exit=1
Canary removed
git status --porcelain | grep '_import_ban_canary' → (empty)
CLEAN: no canary residue
```

### YAML validation

```
YAML valid OK
triggers: ['pull_request', 'push']
jobs: ['license-check', 'import-ban']
PR trigger: OK runs on PR
continue-on-error: only in comment on line 6 (not a directive) — gates are blocking
```

### Doc content check

```
OK all topics present
```
(Required: SPDX-License-Identifier, Apache-2.0, AGPL-3.0-or-later,
LicenseRef-BountyStrike-Proprietary, idempotent, import-linter, negative test, Phase 0,
shebang, allow-list, control_plane — all present)

## Boundary Compliance

- Did NOT modify `00-02` license files or `LICENSES.md`
- Did NOT touch `00-03` feature-flag package logic
- Only created: SPDX sweep script, CI workflow, learnings doc; modified: `pyproject.toml` (import-linter config only)
- No logic changes, no physical reorg, no STATE.md update (UNIFY's responsibility)
