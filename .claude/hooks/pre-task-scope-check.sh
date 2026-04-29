#!/usr/bin/env bash
# Hook: pre-task-scope-check
# Validates SCOPE_JWT is present and not within 24h of expiry before any
# recon-agent task starts. Exits non-zero to abort the task on failure.

set -euo pipefail

if [[ -z "${SCOPE_JWT:-}" ]]; then
  echo "pre-task-scope-check: SCOPE_JWT not set — aborting" >&2
  exit 1
fi

# Decode the JWT payload (second segment, base64url-padded).
payload_b64=$(echo "$SCOPE_JWT" | cut -d. -f2)
# Add padding
pad=$(( (4 - ${#payload_b64} % 4) % 4 ))
payload_b64="${payload_b64}$(printf '=%.0s' $(seq 1 $pad))"
payload=$(echo "$payload_b64" | tr '_-' '/+' | base64 -d 2>/dev/null)

exp=$(echo "$payload" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('exp', 0))")
now=$(date +%s)
remaining=$(( exp - now ))
threshold=$(( 24 * 3600 ))

if (( remaining < threshold )); then
  echo "pre-task-scope-check: JWT expires in ${remaining}s (< ${threshold}s) — refresh before recon" >&2
  exit 1
fi

echo "pre-task-scope-check: JWT valid, ${remaining}s until expiry" >&2
exit 0
