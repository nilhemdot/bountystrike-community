# Contributing to BountyStrike

## Dev setup

```bash
uv sync                 # Python workspace (control-plane + 15 MCPs)
pnpm install            # JS task layer (Turborepo) — optional unless touching apps/
uv run ruff check .     # lint
uv run pytest tests/    # unit tests
```

The Python `uv` workspace (`pyproject.toml [tool.uv.workspace]`) is authoritative
for all Python packages. `pnpm`/`turbo` only orchestrate cross-language tasks.

## License tiers — READ BEFORE CONTRIBUTING

This repo is multi-licensed (see `LICENSE` + `LICENSES.md`):

- **core** (`packages/core/*`) — Apache-2.0
- **community** (`packages/community/*`, plus current `control-plane/`, `mcp/*`, `scripts/`) — AGPL-3.0
- **enterprise** (`packages/enterprise/*`) — proprietary

### Hard rules

1. **No imports from `community/` → `core/`.** `core` must stay Apache-clean. A copyleft (AGPL) import into core would relicense core. CI/pre-commit will enforce this (a later plan); until then it is a review gate.
2. **AGPL-3.0 §13 (Remote Network Interaction):** community-tier code carries the network-use obligation — if you deploy modified community code as a network service, you must offer its source to users. Do not contribute community-tier code expecting it to be relicensed away from AGPL.
3. **Relicensing boundary:** core(Apache) → community(AGPL) → enterprise(proprietary). Enterprise-only behavior goes behind a `tier=enterprise` flag, never a forked code path.
4. **License headers:** each new source file should carry its tier's SPDX header (`SPDX-License-Identifier: Apache-2.0` / `AGPL-3.0-or-later` / `LicenseRef-BountyStrike-Proprietary`). Header automation is a later plan; add manually for now.

## PR process

1. Branch from `master`.
2. Keep changes within one tier where possible; flag any cross-tier change explicitly.
3. `uv run ruff check . && uv run ruff format . && uv run pytest tests/` must pass.
4. Sign off per `CLA.md`.
