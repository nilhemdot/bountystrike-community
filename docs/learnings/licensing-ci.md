# Licensing CI Patterns — BountyStrike v5

> Phase 0 task 00-04. Covers the SPDX header sweep, import-linter contract, and CI enforcement.

---

## 1. 3-Root SPDX Map (authoritative per `LICENSES.md`)

| Directory root | Tier | SPDX-License-Identifier |
|---|---|---|
| `packages/core/` | Community (Apache) | `Apache-2.0` |
| `packages/community/` | Community (AGPL) | `AGPL-3.0-or-later` |
| `packages/enterprise/` | Enterprise | `LicenseRef-BountyStrike-Proprietary` |
| `control-plane/` | Community (AGPL) | `AGPL-3.0-or-later` |
| `mcp/` (all 15 servers) | Community (AGPL) | `AGPL-3.0-or-later` |
| `scripts/` | Community (AGPL) | `AGPL-3.0-or-later` |

Use `AGPL-3.0-or-later` — NOT `AGPL-3.0-only`. Never AGPL-stamp an Apache `core` file.

---

## 2. Allow-List vs Deny-List (why both gates exist)

**Primary gate — allow-list:** The sweep walks ONLY the six licensed roots above. Any path
outside all six (e.g. `infra/`, `docs/`, `.claude/`, `.gemini/`, repo-root dotfiles) has NO
authoritative SPDX mapping and must NOT be stamped. Mis-licensing `.venv/` site-packages as
`AGPL-3.0-or-later` is a release-blocking legal defect, not a style choice.

**Secondary gate — deny skip-list (belt-and-suspenders):** Even within a root, the following
are never stamped:

- `__pycache__/`, `*.pyc`, `.turbo/` — Python bytecode / build caches
- `node_modules/`, `*.lock`, `pnpm-lock.yaml`, `uv.lock` — vendored/lockfiles
- `migrations/` — Alembic SQL migrations (schema, not product code)
- `fixtures/`, `testdata/` — test data, not source
- `.github/` YAML — CI config, not license-bearing Python/TS source
- `.venv/`, `site-packages/` — third-party installed packages
- `dist/`, `build/`, `*.d.ts`, `*.min.*` — compiled/generated output
- `.claude/`, `.gemini/` — tooling hook scripts, not product source
- Non-source extensions: `.json`, `.toml`, `.md`, `.txt`, `.env*`

A file is stamped **ONLY IF** it is under one of the six roots AND not in the skip-list.

---

## 3. Idempotency Design

The sweep checks the first 10 lines of every file for any `SPDX-License-Identifier:` string
before writing. If found, the file is skipped — zero bytes changed. Re-running the script
on an already-stamped tree produces:

```
0 files updated, N files skipped (already have header), ...
```

**Byte-equality proof:** Apply once → `git diff --stat` shows N changed files.
Apply twice → `git diff --stat` shows zero additional changes. This is enforced in CI
(`--check` mode exits 0 on a clean tree).

---

## 4. Comment Syntax by Extension + Shebang/Cookie Ordering

| Extension | Comment prefix | Example |
|---|---|---|
| `.py`, `.sh` | `#` | `# SPDX-License-Identifier: AGPL-3.0-or-later` |
| `.ts`, `.tsx`, `.js` | `//` | `// SPDX-License-Identifier: AGPL-3.0-or-later` |
| `.sql` | `--` | `-- SPDX-License-Identifier: AGPL-3.0-or-later` |

**Shebang/cookie ordering rule (AC-2a):**

- If line 1 is a shebang (`#!`), the SPDX comment goes on line 2. Never displace a shebang.
- If a PEP-263 coding cookie (`# -*- coding: ... -*-` or `# coding:`) is present in the
  first two lines, the SPDX comment goes immediately after it.
- Otherwise the SPDX comment is line 1.
- A blank-line separator is added after the SPDX comment when the next existing line is
  non-blank (keeps readability).

**Correct ordering for a shebang script:**

```python
#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Module docstring."""
```

---

## 5. Running the Sweep

```bash
# Check mode (dry-run, exits 1 if any file missing header):
uv run python scripts/add_spdx_headers.py --check

# Apply mode (stamps files, idempotent):
uv run python scripts/add_spdx_headers.py

# Prove idempotency (byte-equality):
uv run python scripts/add_spdx_headers.py
git diff --stat HEAD   # note changed files
uv run python scripts/add_spdx_headers.py
# "0 files updated" + git diff --stat shows no new changes
```

Foreign-path gate (must return empty after sweep):

```bash
git diff --name-only | grep -E '\.venv/|/infra/|/dist/|\.claude/|\.gemini/'
# Any output here is a release-blocking mis-licensing defect
```

---

## 6. Import-Linter Contract Schema

Configured in root `pyproject.toml` under `[tool.importlinter]`.

```toml
[tool.importlinter]
root_packages = ["control_plane"]
include_external_packages = true

[[tool.importlinter.contracts]]
name = "community must not import enterprise"
type = "forbidden"
source_modules = ["control_plane"]
forbidden_modules = ["bountystrike_enterprise"]

[[tool.importlinter.contracts]]
name = "core must not import enterprise"
type = "forbidden"
source_modules = ["control_plane.core"]
forbidden_modules = ["bountystrike_enterprise"]
```

**Key design decisions:**

- `root_packages = ["control_plane"]` — import-linter resolves this via import machinery;
  `control_plane` must be importable (`uv sync` installs the workspace member).
- `forbidden_modules = ["bountystrike_enterprise"]` — matched by name against the import
  graph. The package does not need to exist for the contract to load and fire.
- `include_external_packages = true` — required so `bountystrike_enterprise` (not installed)
  is treated as a valid forbidden target rather than ignored.

---

## 7. Negative Test Instructions — negative test (canary)

The canary MUST be placed inside a scanned `source_module` — NOT in `packages/community/`
which is outside every `source_modules` entry and would silently pass.

```bash
# Create canary inside control_plane (source_modules covers it):
echo 'import bountystrike_enterprise' > \
  control-plane/src/control_plane/_import_ban_canary_DELETE_ME.py

# Assert lint-imports exits NON-zero:
uv run lint-imports
# → "control_plane is not allowed to import bountystrike_enterprise"
# → exit=1

# Remove canary (trap-cleanup — NEVER commit it):
rm control-plane/src/control_plane/_import_ban_canary_DELETE_ME.py

# Assert no residue:
git status --porcelain | grep '_import_ban_canary'
# → empty (clean)
```

Then assert the clean tree passes again:

```bash
uv run lint-imports
# → "Contracts: 2 kept, 0 broken."
# → exit=0
```

---

## 8. CI Workflow

`.github/workflows/license-and-imports.yml` runs on every PR and push to master/main.

- **`license-check` job** — runs `add_spdx_headers.py --check`; exits 1 if any file is
  missing a header.
- **`import-ban` job** — runs `uv run lint-imports`; exits 1 if any forbidden import found.
  Also asserts `control_plane` resolves (non-vacuous guard).
- Both jobs use `setup-uv@v5`; `import-linter~=2.3` is pinned in `[dependency-groups] dev`.
- Neither job uses `continue-on-error` — both gates are blocking.

---

## Phase 0 Exit Criterion

This task (00-04) satisfies the Phase 0 SPDX + import-ban exit criterion.
After UNIFY closes the loop, Phase 0 transitions to Phase 1.
