#!/usr/bin/env bash
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# seed_env.sh — non-interactive .env secret seeder for BountyStrike v5.
#
# Idempotent: copies .env.example -> .env if absent, then fills ONLY the empty
# infra secrets with fresh random values. Never overwrites an already-set value;
# never touches BYOK / platform-credential keys. Writes .env as mode 0600.
#
# Usage: bash scripts/seed_env.sh
#
# Exit codes: 0 ok | non-zero on a missing prerequisite (detected BEFORE any
#             write, so a partial/blank .env is never left behind).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ENV_FILE="$REPO_ROOT/.env"
ENV_EXAMPLE="$REPO_ROOT/.env.example"

# --- Preflight (M4/AC-9): fail loud BEFORE mutating .env ---
if ! command -v openssl >/dev/null 2>&1; then
    echo "ERROR: openssl not found on PATH — required to generate secrets." >&2
    echo "Install openssl and re-run; .env was not created or modified." >&2
    exit 1
fi
if [[ ! -f "$ENV_EXAMPLE" ]]; then
    echo "ERROR: $ENV_EXAMPLE not found — cannot seed .env." >&2
    exit 1
fi

# --- Create .env from the template if absent ---
if [[ ! -f "$ENV_FILE" ]]; then
    cp "$ENV_EXAMPLE" "$ENV_FILE"
    echo "Created .env from .env.example"
fi

# Tighten perms early (M1/AC-7): host umask is typically 022, so a fresh copy is
# 0644 (world-readable secrets) unless explicitly locked down.
chmod 600 "$ENV_FILE"

# Fill the value of $key only when its line is exactly `KEY=` (empty). Matches by
# key name only — base64 output contains / + = which breaks naive `sed -i`, so we
# substitute via awk into a temp file then atomically mv (never a truncated .env).
fill_if_empty() {
    local key="$1" gen="$2" val tmp
    if grep -qE "^${key}=$" "$ENV_FILE"; then
        val="$(eval "$gen")"
        tmp="$(mktemp "${ENV_FILE}.XXXXXX")"   # mktemp creates with mode 0600
        awk -v key="$key" -v val="$val" '
            $0 == key "=" { print key "=" val; next }
            { print }
        ' "$ENV_FILE" > "$tmp"
        chmod 600 "$tmp"
        mv "$tmp" "$ENV_FILE"
        echo "  seeded $key"
    fi
}

# Infra / compose-consumed secrets. This set INCLUDES the secrets that
# docker-compose.yml only `:-`-defaults (e.g. HATCHET_POSTGRES_PASSWORD:-hatchet),
# so the running stack uses the random .env value, never the source-visible
# default (M2/AC-5). BYOK keys and platform creds are deliberately NOT here.
fill_if_empty POSTGRES_PASSWORD         "openssl rand -base64 32"
fill_if_empty REDIS_PASSWORD            "openssl rand -base64 32"
fill_if_empty HATCHET_COOKIE_SECRET     "openssl rand -base64 32"
fill_if_empty HATCHET_POSTGRES_PASSWORD "openssl rand -base64 32"
fill_if_empty LANGFUSE_SECRET           "openssl rand -base64 32"
fill_if_empty LANGFUSE_SALT             "openssl rand -hex 16"

chmod 600 "$ENV_FILE"
mode="$(stat -c %a "$ENV_FILE" 2>/dev/null || stat -f %A "$ENV_FILE" 2>/dev/null || echo '?')"
echo "seed_env: infra secrets ready (.env mode ${mode})"
