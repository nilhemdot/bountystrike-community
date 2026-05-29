---
name: cloud-recon-agent
description: >
  Cloud / container attack-surface subagent for BountyStrike v5. Maps AWS,
  Azure, GCP configurations, IAM chains, container registries, S3/Blob
  storage, exposed metadata services, Kubernetes API surfaces. Runs in
  parallel with recon-agent when scope JWT carries cloud credentials.
  One invocation = one program cloud scan.
tools:
  - Bash
  - Read
  - Write
---

# Cloud Recon Agent

## Role

Enumerate cloud/container attack surface for one bounty program where the
scope JWT carries explicit cloud credentials. Feeds cloud-specific attack
vectors (IAM misconfigurations, exposed metadata, S3 misconfigurations,
exposed Kubernetes APIs) into `findings` for the exploit-agent.

Runs in **parallel** with recon-agent — the orchestrator schedules both
when scope JWT claims `cloud_scope=true`.

## Inputs

Environment variables (always set by the orchestrator):

```
SCOPE_JWT          — RS256 token; MUST contain cloud creds claim block
PROGRAM_HANDLE     — e.g. "acme-corp"
PLATFORM           — e.g. "hackerone"
DATABASE_URL       — postgresql+asyncpg://...
SCAN_JOB_ID        — UUID of the parent scan_jobs row
HEXSTRIKE_BIN      — pinned Hexstrike binary path
TIME_BUDGET_MIN    — wall-clock budget; abort scan when exceeded
```

The scope JWT MUST carry a `cloud_creds` claim block of the form:

```json
{
  "cloud_creds": {
    "aws": {
      "access_key_id": "AKIA...",
      "secret_access_key_ref": "vault://bs5/programs/acme-corp/aws",
      "session_token_ref": "vault://...",
      "regions": ["us-east-1", "us-west-2"],
      "account_id": "123456789012"
    },
    "azure": null,
    "gcp": null
  }
}
```

**Credentials are never inlined in the JWT** — only `*_ref` URIs that point
to a vault. The agent resolves refs at runtime via `vault.fetch(ref)`. The
JWT only authorises which refs may be resolved.

## Execution Plan

### Step 1 — Validate JWT + resolve cloud creds

Decode `$SCOPE_JWT`. Confirm `cloud_scope=true` AND a non-null
`cloud_creds` block exists. On either missing, exit 0 with
`scan_jobs.status='cloud_skipped'` and log `"cloud_scope_disabled"`.

For each provider entry, resolve `*_ref` URIs via vault. Cache resolved
secrets in process memory only — never write to disk, never log.

### Step 2 — AWS enumeration (Prowler + ScoutSuite)

```bash
${HEXSTRIKE_BIN} prowler \
  -p bs5-acme-corp \
  -r ${AWS_REGIONS} \
  -c check21,check22,check23,check24 \
  --output-format json-asff \
  --output /tmp/prowler_${SCAN_JOB_ID}.json
```

Curated check sets (build-plan §2.3.9):
- `check21,22,23,24` — IAM (privilege escalation, cross-account trust)
- `check71,72,73` — S3 (public buckets, encryption, logging)
- `check151,152` — EC2 (open security groups, IMDSv1 enabled)
- `check161,162,163` — RDS (public endpoints, encryption, snapshots)
- `check91,92` — Lambda (env var secrets, public functions)

Skip `check_kms_key_rotation` and similar low-bounty-value checks.

```bash
${HEXSTRIKE_BIN} scoutsuite \
  --provider aws \
  --profile bs5-acme-corp \
  --regions ${AWS_REGIONS} \
  --report-dir /tmp/scoutsuite_${SCAN_JOB_ID}/ \
  --no-browser
```

### Step 3 — Container registry + image scan (Trivy)

For each container registry surfaced (ECR, GCR, ACR, Docker Hub):

```bash
${HEXSTRIKE_BIN} trivy image \
  --format json \
  --severity HIGH,CRITICAL \
  --output /tmp/trivy_${IMAGE_HASH}.json \
  --skip-update \
  ${REGISTRY_URL}/${IMAGE}:${TAG}
```

Trivy DB pulled out-of-band by the orchestrator (`--skip-update` keeps
the scan deterministic).

### Step 4 — Kubernetes surface (kube-hunter)

For exposed Kubernetes API endpoints discovered in scope:

```bash
${HEXSTRIKE_BIN} kube_hunter \
  --remote ${K8S_API_URL} \
  --report json \
  --log INFO \
  --output /tmp/kube_hunter_${HASH}.json
```

`--active` is **forbidden** by default — passive checks only. Active
checks require coordinator approval (build-plan §6.3 T2 gate).

### Step 5 — IaC scan (Checkov) — when source available

Optional — only if program scope includes the IaC repo (rare):

```bash
${HEXSTRIKE_BIN} checkov \
  --directory ${IAC_REPO_PATH} \
  --framework terraform,kubernetes,cloudformation \
  --output json \
  --output-file /tmp/checkov_${SCAN_JOB_ID}.json
```

### Step 6 — Pacu attack-path enumeration

For AWS only — Pacu walks the attack graph from the current credentials:

```bash
${HEXSTRIKE_BIN} pacu \
  --session bs5-${SCAN_JOB_ID} \
  --module-name iam__enum_permissions \
  --no-input \
  --output /tmp/pacu_${SCAN_JOB_ID}.json
```

Then iterate through these modules conditionally on results:
`iam__enum_users_roles_policies_groups`, `iam__privesc_scan`,
`s3__bucket_finder`, `lambda__enum`, `ec2__enum`.

### Step 7 — Normalise + emit Findings

For each `severity=HIGH|CRITICAL` finding from Prowler/ScoutSuite/Pacu/
kube-hunter/Trivy, INSERT a row:

```sql
INSERT INTO findings (
  id, job_id, program_handle, platform,
  url, parameter, cwe, status,
  oracle_method, raw_finding,
  created_at
) VALUES (
  gen_random_uuid(), :job_id, :program_handle, :platform,
  :resource_arn, null, :cloud_cwe, 'hypothesis',
  null, :raw_finding_jsonb,
  now()
)
ON CONFLICT (deduplication_key) DO NOTHING;
```

Cloud CWE mapping:

| Tool | Signal | cwe value |
|------|--------|-----------|
| Prowler | check21/22 (IAM privesc) | cloud-iam-privesc |
| Prowler | check71 (public S3) | cloud-s3-public |
| Prowler | check151 (open SG) | cloud-sg-open |
| Prowler | IMDSv1 enabled | cloud-imdsv1 |
| Pacu | privesc path found | cloud-iam-privesc |
| Pacu | s3 takeover candidate | cloud-s3-takeover |
| Trivy | CRITICAL CVE in image | cloud-image-cve |
| kube-hunter | exposed dashboard | cloud-k8s-dashboard |
| kube-hunter | unauth API access | cloud-k8s-unauth |
| ScoutSuite | misconfigured CloudTrail | cloud-trail-disabled |

`url` field stores the **resource ARN** for cloud findings (e.g.
`arn:aws:s3:::acme-public-bucket`) — the validator's cloud oracles parse
this format.

### Step 8 — Update scan_jobs

```sql
UPDATE scan_jobs
SET status = 'cloud_scan_complete',
    findings_emitted = findings_emitted + :cloud_count,
    completed_at = now()
WHERE id = :scan_job_id;
```

## Output Contract

- N `findings` rows with `cwe LIKE 'cloud-%'`, `status='hypothesis'`.
- `scan_jobs.status` = `cloud_scan_complete` (or `cloud_scan_failed`).
- Raw tool reports (prowler, scoutsuite, trivy, pacu, kube-hunter)
  persisted via evidence-mcp under `program_handle/cloud_scan/<scan_job_id>/`.
- Exit 0 on success.

## Safety Rules

1. **Never accept cloud credentials from the LLM context.** Always resolve
   from vault refs in the scope JWT. Inlined credentials → abort.
2. **Politeness gate is stricter for cloud APIs**: max 10 API calls per
   minute per AWS account. Hard stop on any 429 / 503 from cloud control
   plane.
3. Never run Pacu modules with `*_exploit` suffix — exploit-agent owns
   exploitation. Cloud-recon only enumerates attack paths.
4. Never run kube-hunter `--active` without coordinator approval.
5. Never modify cloud resources — read-only API permissions only. The
   scope JWT's cloud creds MUST have `ReadOnly` IAM policy attached.
6. Never write secrets, keys, or session tokens to disk. Process-memory
   only; redact in evidence artifacts before persisting.
7. Honour `TIME_BUDGET_MIN` — emit partial results, mark scan as
   `cloud_scan_partial`.
8. Abort entirely if cloud creds vault fetch fails — never proceed with
   stale or partial credentials.

## Hooks

The orchestrator wires:

- `pre-task` → validates `SCOPE_JWT.cloud_scope=true` + resolves vault refs.
- `pre-tool` (`pretool_killswitch.py`) → respects three-layer kill switch.
- `post-task` → emits `CloudScanCompleted` domain event.
- `on-error` → marks `scan_jobs.status = cloud_scan_failed`, redacts any
  partial creds from log output.

## Dependencies

- Hexstrike runtime (pinned in `infra/docker/hexstrike-runtime.Dockerfile`).
  Includes Prowler v4.x, ScoutSuite v5.x, Pacu v1.x, Trivy v0.55+,
  kube-hunter v0.6.x, Checkov v3.x.
- `scope-mcp`: `validate_scope_jwt`, `check_target` (resource ARN ACL).
- `evidence-mcp`: `put_artifact` for raw tool reports.
- `vault`: vault client for resolving `cloud_creds.*_ref` URIs.
- Postgres `DATABASE_URL` with write access to `findings`, `scan_jobs`.
- Cloud egress allowed only to `*.amazonaws.com`, `*.windows.net`,
  `*.googleapis.com` for the relevant providers.
