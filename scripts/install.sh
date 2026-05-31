#!/usr/bin/env bash
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# install.sh — one-line unattended bootstrap for BountyStrike v5 Community Edition.
#
# Takes a fresh checkout from clone -> running stack:
#   preflight -> (ensure docker) -> seed .env secrets -> generate scope keypair
#   -> docker compose up -d --build -> wait for health -> print next steps.
# Idempotent: re-running never clobbers an existing .env or keypair.
#
# Usage:
#   bash scripts/install.sh                              # full run (interactive-safe)
#   bash scripts/install.sh --no-up                      # provision .env + keys, skip compose
#   bash scripts/install.sh --unattended                 # no prompts (-y alias)
#   bash scripts/install.sh --install-docker --unattended  # opt-in: auto-install Docker
#   bash scripts/install.sh --help
#
# Env knobs (used by the offline test harness to force a fast health timeout):
#   INSTALL_HEALTH_RETRIES  (default 30)  — health poll attempts
#   INSTALL_HEALTH_INTERVAL (default 10)  — seconds between attempts

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
COMPOSE_FILE="$REPO_ROOT/infra/docker/docker-compose.yml"
ENV_FILE="$REPO_ROOT/.env"

NO_UP=0
UNATTENDED=0
INSTALL_DOCKER=0

HEALTH_RETRIES="${INSTALL_HEALTH_RETRIES:-30}"
HEALTH_INTERVAL="${INSTALL_HEALTH_INTERVAL:-10}"

log() { echo "[install] $*"; }
err() { echo "[install] ERROR: $*" >&2; }

usage() {
    cat <<'EOF'
BountyStrike v5 — one-line installer

Usage: bash scripts/install.sh [OPTIONS]

Options:
  --no-up            Provision .env + scope keypair only; do not start the stack.
  --unattended, -y   Run with no interactive prompts.
  --install-docker   Explicit opt-in to auto-install Docker via get.docker.com.
                     Only honoured together with --unattended. Never implied.
  --help, -h         Show this help and exit.

Environment:
  INSTALL_HEALTH_RETRIES   Health poll attempts (default 30).
  INSTALL_HEALTH_INTERVAL  Seconds between attempts (default 10).
EOF
}

for arg in "$@"; do
    case "$arg" in
        --no-up) NO_UP=1 ;;
        --unattended|-y) UNATTENDED=1 ;;
        --install-docker) INSTALL_DOCKER=1 ;;
        -h|--help) usage; exit 0 ;;
        *) err "unknown argument: $arg"; usage >&2; exit 1 ;;
    esac
done

# 0. Preflight (M4/AC-9): assert host prerequisites BEFORE writing any file,
#    so we never leave a half-written .env behind.
preflight() {
    local missing=()
    local tool
    for tool in openssl bash awk grep mktemp; do
        command -v "$tool" >/dev/null 2>&1 || missing+=("$tool")
    done
    if (( ${#missing[@]} > 0 )); then
        err "missing required host tools: ${missing[*]}"
        err "install them and re-run; no files were written."
        exit 1
    fi
}

# 1. ensure_docker (AC-4/S1): never pipe curl|sh implicitly. Auto-install only
#    when BOTH --install-docker AND --unattended are set; otherwise fail loud
#    with the exact command the operator can run themselves.
ensure_docker() {
    if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
        log "docker + compose plugin present"
        return 0
    fi
    if [[ $INSTALL_DOCKER -eq 1 && $UNATTENDED -eq 1 ]]; then
        log "installing Docker via get.docker.com (--install-docker opt-in)"
        curl -fsSL https://get.docker.com | sh
        if ! { command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; }; then
            err "Docker still unavailable after the install attempt."
            exit 1
        fi
        log "docker installed"
        return 0
    fi
    err "Docker (with the compose plugin) is required but was not found."
    err "Install it yourself, then re-run this script:"
    err "    curl -fsSL https://get.docker.com | sh"
    err "Or re-run with the explicit opt-in:"
    err "    bash scripts/install.sh --install-docker --unattended"
    exit 1
}

# 2. seed_secrets: delegate to seed_env.sh (owns chmod 600 on .env, AC-7).
seed_secrets() {
    log "seeding .env secrets"
    bash "$REPO_ROOT/scripts/seed_env.sh"
}

# 3. ensure_keys: reuse generate_keys.sh as-is (idempotent, chmod 600 private key).
ensure_keys() {
    log "ensuring scope-JWT keypair"
    bash "$REPO_ROOT/scripts/generate_keys.sh"
}

# 4. bring_up: validate compose, start the stack, wait for health (fail loud).
bring_up() {
    log "validating compose config"
    if ! docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" config -q; then
        err "compose config invalid (a required secret may be missing/blank) — aborting before start."
        exit 1
    fi
    log "starting stack: docker compose up -d --build"
    docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" up -d --build
    health_wait
}

# health_wait (M3/AC-8): poll health_check.sh in a bounded loop. health_check
# exits 0 healthy / 1 unhealthy / 2 not-running; capture its rc so `set -e`
# does not abort the retry loop. On timeout, exit NON-ZERO naming the still-down
# services. Never print success while a service is down.
health_wait() {
    log "waiting for services to become healthy (${HEALTH_RETRIES} x ${HEALTH_INTERVAL}s)"
    local i rc out=""
    for (( i=1; i<=HEALTH_RETRIES; i++ )); do
        rc=0
        out="$(bash "$REPO_ROOT/scripts/health_check.sh" 2>&1)" || rc=$?
        if [[ $rc -eq 0 ]]; then
            log "all services healthy"
            return 0
        fi
        log "health attempt $i/$HEALTH_RETRIES not ready (rc=$rc); retrying in ${HEALTH_INTERVAL}s"
        sleep "$HEALTH_INTERVAL"
    done
    err "stack did NOT become healthy within $(( HEALTH_RETRIES * HEALTH_INTERVAL ))s"
    err "still-unhealthy services from the last check:"
    echo "$out" | grep -E '✗|unhealthy|not running' >&2 || echo "$out" >&2
    exit 1
}

# 5. print_next_steps: list still-blank BYOK keys + the scope-JWT command + URLs.
print_next_steps() {
    echo ""
    log "============================================================"
    log "BountyStrike Community Edition — provisioning complete"
    log "============================================================"

    local blanks
    blanks="$(grep -E '^[A-Z0-9_]+=$' "$ENV_FILE" 2>/dev/null | sed 's/=$//' || true)"
    if [[ -n "$blanks" ]]; then
        echo ""
        log "Fill in your BYOK / platform credentials in .env (still blank):"
        while IFS= read -r k; do
            [[ -n "$k" ]] && echo "    - $k"
        done <<< "$blanks"
    fi

    echo ""
    log "Issue a scope JWT for one program before scanning:"
    echo "    python scripts/gen_scope_jwt.py issue \\"
    echo "      --operator-id <you> --program-handle <handle> \\"
    echo "      --platform hackerone --targets 'wildcard=*.example.com' --out scope.jwt"

    if [[ $NO_UP -eq 0 ]]; then
        echo ""
        log "Local dashboards (once healthy):"
        echo "    control-plane : http://localhost:8001"
        echo "    langfuse      : http://localhost:3000"
        echo "    hatchet       : http://localhost:8080"
    else
        echo ""
        log "Stack not started (--no-up). Start it with:"
        echo "    docker compose -f infra/docker/docker-compose.yml --env-file .env up -d --build"
    fi
}

main() {
    preflight
    if [[ $NO_UP -eq 0 ]]; then
        ensure_docker
    fi
    seed_secrets
    ensure_keys
    if [[ $NO_UP -eq 0 ]]; then
        bring_up
    fi
    print_next_steps
}

main
