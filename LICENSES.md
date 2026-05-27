# LICENSES — Directory → Tier → License Mapping

Authoritative, machine-checkable binding of every code directory to its tier and
license. Because the monorepo is a HYBRID (the uv Python workspace stays in place;
pnpm/Turborepo is layered on top), existing code lives outside `packages/` — so the
license↔code binding is recorded here explicitly, not inferred from directory path.

## Mapping

| Directory | Tier | License | SPDX |
|-----------|------|---------|------|
| `packages/core/*` | core | Apache-2.0 | `Apache-2.0` |
| `packages/community/*` | community | AGPL-3.0 | `AGPL-3.0-or-later` |
| `packages/enterprise/*` | enterprise | Proprietary | `LicenseRef-BountyStrike-Proprietary` |
| `control-plane/` | community | AGPL-3.0 | `AGPL-3.0-or-later` |
| `mcp/bugcrowd-mcp/` | community | AGPL-3.0 | `AGPL-3.0-or-later` |
| `mcp/dedup-mcp/` | community | AGPL-3.0 | `AGPL-3.0-or-later` |
| `mcp/evidence-mcp/` | community | AGPL-3.0 | `AGPL-3.0-or-later` |
| `mcp/ev-mcp/` | community | AGPL-3.0 | `AGPL-3.0-or-later` |
| `mcp/h1-mcp/` | community | AGPL-3.0 | `AGPL-3.0-or-later` |
| `mcp/immunefi-mcp/` | community | AGPL-3.0 | `AGPL-3.0-or-later` |
| `mcp/intigriti-mcp/` | community | AGPL-3.0 | `AGPL-3.0-or-later` |
| `mcp/kev-mcp/` | community | AGPL-3.0 | `AGPL-3.0-or-later` |
| `mcp/normalize-mcp/` | community | AGPL-3.0 | `AGPL-3.0-or-later` |
| `mcp/oracle-mcp/` | community | AGPL-3.0 | `AGPL-3.0-or-later` |
| `mcp/politeness-mcp/` | community | AGPL-3.0 | `AGPL-3.0-or-later` |
| `mcp/sandbox-mcp/` | community | AGPL-3.0 | `AGPL-3.0-or-later` |
| `mcp/scope-mcp/` | community | AGPL-3.0 | `AGPL-3.0-or-later` |
| `mcp/state-mcp/` | community | AGPL-3.0 | `AGPL-3.0-or-later` |
| `mcp/yeswehack-mcp/` | community | AGPL-3.0 | `AGPL-3.0-or-later` |
| `scripts/` | community | AGPL-3.0 | `AGPL-3.0-or-later` |

## Notes

- Full license texts: `packages/core/LICENSE` (Apache-2.0), `packages/community/LICENSE` (AGPL-3.0, incl §13), `packages/enterprise/LICENSE` (proprietary).
- AGPL-3.0 §13 (Remote Network Interaction) applies to all community-tier directories above.
- Deferred: per-file SPDX headers + physical relocation of `control-plane/` and `mcp/*` under `packages/community/` (a later Phase 0/1 plan). Until then, THIS table is the authoritative binding.
