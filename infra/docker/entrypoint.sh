#!/usr/bin/env bash
# BountyStrike v5 — Docker entrypoint with pre-flight checks
#
# Purpose:
#   Unified entrypoint for control-plane, MCP servers, and workers.
#   Verifies dependencies, waits for services, generates JWT keys,
#   runs migrations (control-plane only), then execs main command.
#
# Usage (in Dockerfile):
#   ENTRYPOINT ["/app/infra/docker/entrypoint.sh"]
#   CMD ["uvicorn", "control_plane.app:app", "--host", "0.0.0.0", "--port", "8000"]
#
# Environment variables:
#   SERVICE_NAME        — identifies service for logging (e.g., "control-plane")
#   DATABASE_URL        — Postgres connection string (required for DB-dependent services)
#   REDIS_URL           — Redis connection string (required for cache/kill-switch)
#   REDIS_PASSWORD      — Redis password (legacy, prefer REDIS_URL)
#   SKIP_DB_WAIT        — set to "1" to skip Postgres wait (for Redis-only services)
#   SKIP_REDIS_WAIT     — set to "1" to skip Redis wait (for DB-only services)
#   SKIP_MIGRATIONS     — set to "1" to skip migration check (for non-control-plane)
#   SKIP_KEY_GEN        — set to "1" to skip JWT keypair generation
#   SCOPE_JWT_PRIVATE_KEY_PATH — path to private key (default: keys/scope_jwt_private.pem)
#   SCOPE_JWT_PUBLIC_KEY_PATH  — path to public key (default: keys/scope_jwt_public.pem)
#
# Reference: docs/research/05-deployment.md §First Launch Sequence

set -euo pipefail

# ----------------------------------------------------------------------------
# Configuration & defaults
# ----------------------------------------------------------------------------
SERVICE_NAME="${SERVICE_NAME:-unknown}"
SKIP_DB_WAIT="${SKIP_DB_WAIT:-0}"
SKIP_REDIS_WAIT="${SKIP_REDIS_WAIT:-0}"
SKIP_MIGRATIONS="${SKIP_MIGRATIONS:-0}"
SKIP_KEY_GEN="${SKIP_KEY_GEN:-0}"

SCOPE_JWT_PRIVATE_KEY_PATH="${SCOPE_JWT_PRIVATE_KEY_PATH:-keys/scope_jwt_private.pem}"
SCOPE_JWT_PUBLIC_KEY_PATH="${SCOPE_JWT_PUBLIC_KEY_PATH:-keys/scope_jwt_public.pem}"

MAX_RETRIES=30
RETRY_INTERVAL=2

# ----------------------------------------------------------------------------
# Logging helpers
# ----------------------------------------------------------------------------
log_info() {
    echo "[$SERVICE_NAME] [INFO] $*" >&2
}

log_error() {
    echo "[$SERVICE_NAME] [ERROR] $*" >&2
}

log_fatal() {
    log_error "$@"
    exit 1
}

# ----------------------------------------------------------------------------
# Pre-flight check: verify openssl is available (for key generation)
# ----------------------------------------------------------------------------
check_openssl() {
    if ! command -v openssl &> /dev/null; then
        log_fatal "openssl not found in PATH — required for JWT keypair generation"
    fi
}

# ----------------------------------------------------------------------------
# Pre-flight check: verify psql is available (for Postgres wait/migrations)
# ----------------------------------------------------------------------------
check_psql() {
    if [[ "$SKIP_DB_WAIT" == "1" ]]; then
        return 0
    fi

    if ! command -v psql &> /dev/null; then
        log_error "psql not found in PATH — cannot verify Postgres readiness"
        log_error "Install postgresql-client or set SKIP_DB_WAIT=1"
        exit 1
    fi
}

# ----------------------------------------------------------------------------
# Pre-flight check: verify redis-cli is available (for Redis wait)
# ----------------------------------------------------------------------------
check_redis_cli() {
    if [[ "$SKIP_REDIS_WAIT" == "1" ]]; then
        return 0
    fi

    if ! command -v redis-cli &> /dev/null; then
        log_error "redis-cli not found in PATH — cannot verify Redis readiness"
        log_error "Install redis-tools or set SKIP_REDIS_WAIT=1"
        exit 1
    fi
}

# ----------------------------------------------------------------------------
# Wait for Postgres to accept connections
# ----------------------------------------------------------------------------
wait_for_postgres() {
    if [[ "$SKIP_DB_WAIT" == "1" ]]; then
        log_info "Skipping Postgres wait (SKIP_DB_WAIT=1)"
        return 0
    fi

    if [[ -z "${DATABASE_URL:-}" ]]; then
        log_fatal "DATABASE_URL not set — cannot wait for Postgres"
    fi

    log_info "Waiting for Postgres at $DATABASE_URL (max ${MAX_RETRIES}x${RETRY_INTERVAL}s retries)..."

    local attempt=0
    while [[ $attempt -lt $MAX_RETRIES ]]; do
        if psql "$DATABASE_URL" -c "SELECT 1" &> /dev/null; then
            log_info "Postgres ready after $attempt retries"
            return 0
        fi
        attempt=$((attempt + 1))
        log_info "Postgres not ready (attempt $attempt/$MAX_RETRIES), retrying in ${RETRY_INTERVAL}s..."
        sleep "$RETRY_INTERVAL"
    done

    log_fatal "Postgres did not become ready after $MAX_RETRIES retries"
}

# ----------------------------------------------------------------------------
# Wait for Redis to accept connections
# ----------------------------------------------------------------------------
wait_for_redis() {
    if [[ "$SKIP_REDIS_WAIT" == "1" ]]; then
        log_info "Skipping Redis wait (SKIP_REDIS_WAIT=1)"
        return 0
    fi

    # Parse REDIS_URL or fallback to legacy REDIS_PASSWORD format
    local redis_host="redis"
    local redis_port="6379"
    local redis_password="${REDIS_PASSWORD:-}"

    if [[ -n "${REDIS_URL:-}" ]]; then
        # Parse redis://:password@host:port/db format
        if [[ "$REDIS_URL" =~ redis://(:([^@]+)@)?([^:]+):([0-9]+) ]]; then
            redis_password="${BASH_REMATCH[2]:-}"
            redis_host="${BASH_REMATCH[3]}"
            redis_port="${BASH_REMATCH[4]}"
        fi
    fi

    if [[ -z "$redis_password" ]]; then
        log_error "REDIS_PASSWORD or REDIS_URL with password not set"
        log_fatal "Cannot authenticate to Redis"
    fi

    log_info "Waiting for Redis at $redis_host:$redis_port (max ${MAX_RETRIES}x${RETRY_INTERVAL}s retries)..."

    local attempt=0
    while [[ $attempt -lt $MAX_RETRIES ]]; do
        if redis-cli -h "$redis_host" -p "$redis_port" -a "$redis_password" ping 2>/dev/null | grep -q PONG; then
            log_info "Redis ready after $attempt retries"
            return 0
        fi
        attempt=$((attempt + 1))
        log_info "Redis not ready (attempt $attempt/$MAX_RETRIES), retrying in ${RETRY_INTERVAL}s..."
        sleep "$RETRY_INTERVAL"
    done

    log_fatal "Redis did not become ready after $MAX_RETRIES retries"
}

# ----------------------------------------------------------------------------
# Generate JWT keypair if missing (RS256 4096-bit)
# Reference: docs/research/05-deployment.md §JWT Keypair Setup
# ----------------------------------------------------------------------------
generate_jwt_keypair() {
    if [[ "$SKIP_KEY_GEN" == "1" ]]; then
        log_info "Skipping JWT keypair generation (SKIP_KEY_GEN=1)"
        return 0
    fi

    # Keys already exist — no-op
    if [[ -f "$SCOPE_JWT_PRIVATE_KEY_PATH" && -f "$SCOPE_JWT_PUBLIC_KEY_PATH" ]]; then
        log_info "JWT keypair already exists:"
        log_info "  private → $SCOPE_JWT_PRIVATE_KEY_PATH"
        log_info "  public  → $SCOPE_JWT_PUBLIC_KEY_PATH"
        return 0
    fi

    log_info "Generating RS256 4096-bit JWT keypair..."

    # Create keys directory if missing
    local keys_dir
    keys_dir="$(dirname "$SCOPE_JWT_PRIVATE_KEY_PATH")"
    mkdir -p "$keys_dir"

    # Generate private key (RSA-4096, no passphrase)
    if ! openssl genrsa -out "$SCOPE_JWT_PRIVATE_KEY_PATH" 4096 2>&1 | grep -v "^.*\."; then
        log_fatal "Failed to generate private key at $SCOPE_JWT_PRIVATE_KEY_PATH"
    fi

    # Extract public key from private key
    if ! openssl rsa -in "$SCOPE_JWT_PRIVATE_KEY_PATH" -pubout -out "$SCOPE_JWT_PUBLIC_KEY_PATH" 2>&1 | grep -v "^.*\."; then
        log_fatal "Failed to extract public key to $SCOPE_JWT_PUBLIC_KEY_PATH"
    fi

    # Set secure permissions on private key (owner read/write only)
    chmod 600 "$SCOPE_JWT_PRIVATE_KEY_PATH"

    log_info "  private → $SCOPE_JWT_PRIVATE_KEY_PATH"
    log_info "  public  → $SCOPE_JWT_PUBLIC_KEY_PATH"
    log_info "JWT keypair generated successfully"
}

# ----------------------------------------------------------------------------
# Run database migrations (control-plane only)
# Reference: docs/research/05-deployment.md §Initial Scope Ingest Flow
# ----------------------------------------------------------------------------
run_migrations() {
    if [[ "$SKIP_MIGRATIONS" == "1" ]]; then
        log_info "Skipping migrations (SKIP_MIGRATIONS=1)"
        return 0
    fi

    if [[ -z "${DATABASE_URL:-}" ]]; then
        log_error "DATABASE_URL not set — cannot run migrations"
        return 0
    fi

    log_info "Checking migration status..."

    # Check if pgvector extension exists (proxy for "migrations already ran")
    if psql "$DATABASE_URL" -tAc "SELECT 1 FROM pg_extension WHERE extname='vector'" 2>/dev/null | grep -q 1; then
        log_info "Migrations already applied (pgvector extension detected)"
        return 0
    fi

    # Locate SQL migration files (relative to repo root or mounted volume)
    local sql_dir="/app/infra/sql"
    if [[ ! -d "$sql_dir" ]]; then
        sql_dir="./infra/sql"
    fi

    if [[ ! -d "$sql_dir" ]]; then
        log_error "Migration directory not found: $sql_dir"
        log_error "Skipping migrations (files not mounted or missing)"
        return 0
    fi

    log_info "Running migrations from $sql_dir..."

    # Apply migrations in numeric order (00_*, 01_*, ...)
    local migration_count=0
    for sql_file in "$sql_dir"/*.sql; do
        if [[ ! -f "$sql_file" ]]; then
            continue
        fi

        log_info "  Applying $(basename "$sql_file")..."
        if ! psql "$DATABASE_URL" -f "$sql_file" > /dev/null 2>&1; then
            log_error "Migration failed: $(basename "$sql_file")"
            log_error "Review logs and fix schema before restarting"
            exit 1
        fi
        migration_count=$((migration_count + 1))
    done

    if [[ $migration_count -eq 0 ]]; then
        log_info "No migration files found in $sql_dir"
    else
        log_info "Applied $migration_count migration(s) successfully"
    fi
}

# ----------------------------------------------------------------------------
# Main entrypoint flow
# ----------------------------------------------------------------------------
main() {
    log_info "Starting BountyStrike v5 entrypoint (service: $SERVICE_NAME)"
    log_info "Pre-flight checks starting..."

    # 1. Verify required CLI tools are available
    check_openssl
    check_psql
    check_redis_cli

    # 2. Wait for dependent services
    wait_for_postgres
    wait_for_redis

    # 3. Generate JWT keypair if missing (idempotent)
    generate_jwt_keypair

    # 4. Run database migrations (control-plane only, idempotent)
    run_migrations

    log_info "Pre-flight checks complete — starting service"
    log_info "Executing command: $*"

    # 5. Replace shell with main service process (preserves signals)
    exec "$@"
}

# ----------------------------------------------------------------------------
# Entry point
# ----------------------------------------------------------------------------
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi
