# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Licensed under [AGPL-3.0-or-later](LICENSE-AGPL) (see [LICENSES.md](LICENSES.md) for
the full third-party license posture). Self-host with the one-line installer:

```bash
bash scripts/install.sh
```

## [0.1.0] - 2026-05-31

First public **Community Edition** release — the Phase 0 foundation plus the Phase 1
"moat": a deterministic, scope-gated bug-bounty pipeline that produces verifiable
evidence instead of noisy AI submissions.

### Added

- **Database foundation** — Postgres 17 with `pgvector` + `vectorscale` + `pg_search`;
  6 migrations (extensions, schema, dedup, audit realign, approval queue, raw_finding).
- **Hatchet v1 workflow runtime** — function-based `@hatchet.task()` workers with
  Pydantic inputs and async (`aio_`) execution.
- **Hash-chained evidence store** — Cloudflare R2 write path with per-artifact hashing
  for tamper-evident evidence chains.
- **Federated scope ingestion** — bbscope v2 (`poll`/`db`) + projectdiscovery list,
  merged into a unified scope DB with HackerOne `scope_exclusions` handling.
- **RS256 scope JWT** — 4096-bit keypair; recon is gated so every probe target derives
  from the signed JWT only (`algorithms=["RS256"]`, none-alg attack closed).
- **Deterministic verifier** — CWE→oracle dispatch with a `verify-finding` task wiring
  5 oracles; findings promote from hypothesis only on real oracle evidence.
- **Scope-diff notification delivery** — webhook POST on scope changes (secret URL
  redacted to scheme+host in logs).
- **Recon politeness** — per-program token-bucket rate limiting on the recon path.
- **One-line installer** — idempotent `scripts/install.sh`; never overwrites an existing
  `.env`, never pipes `curl | sh` to root unless explicitly requested.
- **Baked, integrity-verified images** — bbscope pinned by commit (verified via the Go
  module-checksum DB) and chromium pinned by the Playwright lockfile, baked into the
  worker/recon images; never `latest`.
- **AGPLv3 Community Edition licensing** — `LICENSE`, `LICENSE-AGPL`, `LICENSE-APACHE`,
  and a `LICENSES.md` third-party manifest, with SPDX header sweep + import-linter CI.

### Fixed

- Repo-wide **CRLF→LF** normalization with a `.gitattributes` guard (`* text=auto eol=lf`,
  `-text` for crypto/binary material) to prevent recurrence.
- `uv sync` exit-2 in the runtime images — the full `mcp/` workspace tree is now copied
  before the control-plane source so workspace members resolve.

[0.1.0]: https://keepachangelog.com/en/1.1.0/
