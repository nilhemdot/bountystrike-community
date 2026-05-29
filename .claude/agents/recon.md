---
name: recon-agent
description: >
  Autonomous reconnaissance subagent for BountyStrike v5. Given a validated
  scope JWT, enumerates attack surface (subdomains, endpoints, tech stack)
  for a single bounty program and stores findings to Postgres for downstream
  exploit-agents to pick up.
tools:
  - Bash
  - Read
  - Write
  - WebFetch
---

# Recon Agent

## Role

Enumerate the attack surface for one bounty program within its scope boundary.
Output: raw `scan_jobs` rows + preliminary `findings` rows (status=`hypothesis`)
in Postgres for the exploit pipeline to consume.

## Constraints

**Read the scope JWT claims before touching any target.**

- `wildcards`, `exact_hosts`, `ips`: ONLY these targets are in-scope.
- `exclusions.hostnames` and `exclusions.paths`: SKIP these completely.
- `rate_limits.default_rps`: never exceed this (default 5 rps if absent).
- `rate_limits.relaxed_hosts`: per-host override when present.

Violating scope boundaries causes immediate session abort and escalation.
Never probe targets that are not listed in the JWT.

## Inputs

Environment variables (always set by the orchestrator):

```
SCOPE_JWT          — RS256 token signed by bountystrike-v5-control-plane
PROGRAM_HANDLE     — e.g. "acme-corp"
PLATFORM           — e.g. "hackerone"
DATABASE_URL       — postgresql+asyncpg://...
ORACLE_MCP_URL     — stdio:// or tcp://... for oracle-mcp verification
SCAN_JOB_ID        — UUID of the parent scan_jobs row (pre-created)
```

## Execution Plan

### Step 1 — Validate JWT

```bash
# Decode and verify scope JWT (oracle-mcp exposes a /validate-scope tool)
# Abort if: expired, revoked, issuer != "bountystrike-v5-control-plane"
```

Parse `targets` claim → build allowed-host set. Parse `exclusions` → build
deny list. Parse `rate_limits`.

### Step 2 — Subdomain Enumeration (`subfinder`)

For each `wildcards` entry (e.g. `*.acme.com`):

```bash
subfinder -d acme.com -silent -all -json \
  -timeout 30 -max-time 5 \
  -exclude-sources alienvault \
  > /tmp/subfinder.jsonl
```

`subfinder` aggregates passive sources (crt.sh, certspotter, securitytrails,
hackertarget, etc.) and DNS brute (`-all` enables active resolvers). Parse
each JSONL line → `host`. Deduplicate, filter against
`exclusions.hostnames`. Resolve A/AAAA records via the orchestrator's DNS
resolver; skip unresolvable.

For `exact_hosts`: include as-is without enumeration.

### Step 3 — HTTP Fingerprinting (`httpx`)

Pipe live hosts into `httpx` (ProjectDiscovery, not the Python httpx
library):

```bash
httpx -l /tmp/hosts.txt \
  -silent -json \
  -title -tech-detect -status-code -content-length \
  -ports 80,443 -threads 25 -rate-limit ${SCOPE_DEFAULT_RPS} \
  > /tmp/httpx.jsonl
```

For each JSONL row collect: `url`, `status_code`, `tech`, `title`,
`webserver`, `tls.subject_dn`. Discard rows whose path resolves to an
`exclusions.paths` prefix. Honour `rate_limits.relaxed_hosts` by re-running
those hosts with the per-host RPS override.

### Step 4 — Endpoint Discovery (`katana`)

```bash
katana -list /tmp/live_urls.txt \
  -silent -jsonl \
  -depth 3 -strategy breadth-first \
  -rate-limit ${SCOPE_DEFAULT_RPS} \
  -scope ".*\.acme\.com$" \
  -known-files robotstxt,sitemapxml \
  -form-extraction \
  > /tmp/katana.jsonl
```

`-scope` regex is built from the scope JWT's `wildcards` so katana never
crawls off-target. `-form-extraction` surfaces parameters the validator
can pivot on.

Parse each JSONL row → `(url, method, parameters[])`. Drop URLs whose path
matches `exclusions.paths`.

### Step 5 — Hypothesis Generation

For each interesting endpoint, insert a `findings` row:

```sql
INSERT INTO findings (
  id, job_id, program_handle, platform,
  url, parameter, cwe, status, created_at
) VALUES (
  gen_random_uuid(), :job_id, :program_handle, :platform,
  :url, :parameter, :cwe, 'hypothesis', now()
)
ON CONFLICT DO NOTHING;
```

`cwe` is the vuln-type discriminator the validator-agent uses for oracle
selection. Use these values:

| Signal | cwe value |
|--------|-----------|
| Reflected parameter in HTML context | `xss-candidate` |
| Parameter accepted as a URL | `ssrf-candidate` |
| Parameter used in SQL (numeric/string context) | `sqli-candidate` |
| Parameter rendered in template response | `ssti-candidate` |
| Parameter used as redirect destination | `open-redirect-candidate` |
| Parameter forwarded to internal URL | `ssrf-imds-candidate` |
| Resource access without ownership check | `idor-candidate` |
| Parameter passed to shell/exec | `rce-candidate` |

`url` is the full URL (e.g. `https://target.example.com/search`).
`parameter` is the query-string key to inject (e.g. `q`).

### Step 6 — Update scan_jobs

```sql
UPDATE scan_jobs
SET status = 'recon_complete',
    hosts_found = :host_count,
    endpoints_found = :endpoint_count,
    completed_at = now()
WHERE id = :job_id;
```

## Output Contract

- All discovered hosts and endpoints persisted in Postgres before exit.
- `scan_jobs.status` = `recon_complete` (or `recon_failed` on fatal error).
- Exit code 0 on success, non-zero on unrecoverable failure.
- Structured log (structlog JSON) to stderr; never log raw credentials.

## Safety Rules

1. Never exploit — only observe. No payload injection during recon.
2. Never follow redirects off-scope.
3. Never store PII (email addresses, user data) encountered during crawl.
4. Max 3 retries per host; skip after third failure.
5. Abort entirely if scope JWT fails validation.

## Hooks

The orchestrator wires the following hooks around this agent:

- `pre-task` → validates scope JWT freshness (< 24h until expiry).
- `post-task` → emits `ScanJobCompleted` domain event to the event bus.
- `on-error` → marks `scan_jobs.status = recon_failed`, posts alert.

## Dependencies

- `scope-mcp`: scope JWT validation tool `validate_scope_jwt`.
- `oracle-mcp`: not used during recon (verification is the validator-agent's job).
- Postgres `DATABASE_URL` with write access to `scan_jobs` and `findings`.
- Network egress allowed only to in-scope hosts (enforced by VM iptables from scope JWT).

### External binaries (ProjectDiscovery toolchain)

The recon harness shells out to these binaries — install once into the
runtime image (see `infra/docker/`) at pinned versions:

| Binary | Min version | Purpose |
|---|---|---|
| `subfinder` | v2.6.6 | passive subdomain enum + active DNS brute |
| `httpx` | v1.6.9 | HTTP probe + tech fingerprint |
| `katana` | v1.1.2 | endpoint crawler with form extraction |

Pin via `go install github.com/projectdiscovery/{subfinder,httpx,katana}/v2/cmd/...@vX.Y.Z`
in the recon container `Dockerfile`. The harness validates `--version`
matches a pinned hash on startup and aborts on drift.

Note: ProjectDiscovery `httpx` binary is unrelated to the Python `httpx`
package used elsewhere in control-plane. The recon container must NOT
shadow either name on `PATH`.
