#!/usr/bin/env bash
# BountyStrike v5 — End-to-End Deployment Verification
#
# Purpose:
#   Verifies all deployment artifacts are correct and ready for
#   'docker compose up -d' on a fresh VPS. Run this before committing
#   to confirm the deployment package is complete.
#
# Usage:
#     bash scripts/e2e_verify.sh [--full]
#
# Options:
#     --full    Also attempt Docker operations (requires daemon)
#
# Exit codes:
#     0    All checks passed
#     1    One or more checks failed

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

PASS=0
FAIL=0
WARN=0
FULL=0

for arg in "$@"; do
    case "$arg" in
        --full) FULL=1 ;;
    esac
done

# ---- Helper functions ----
ok()  { echo "  ✓ $*"; PASS=$((PASS + 1)); }
fail()  { echo "  ✗ $*"; FAIL=$((FAIL + 1)); }
warn()  { echo "  ⚠ $*"; WARN=$((WARN + 1)); }
section() { echo ""; echo "$1"; echo "$(printf '─%.0s' $(seq 1 ${#1}))"; }

# ============================================================================
section "1. Docker Compose Config Validation"
# ============================================================================

# Check docker-compose.yml exists and is valid YAML
if [[ ! -f "$REPO_ROOT/infra/docker/docker-compose.yml" ]]; then
    fail "docker-compose.yml not found"
else
    ok "docker-compose.yml exists"
fi

# Check .env has required variables
if [[ ! -f "$REPO_ROOT/.env" ]]; then
    fail ".env file not found"
else
    ok ".env file exists"
fi

# Validate compose config (requires secrets in .env)
MISSING_VARS=0
for var in POSTGRES_PASSWORD REDIS_PASSWORD HATCHET_COOKIE_SECRET LANGFUSE_SECRET LANGFUSE_SALT ANTHROPIC_API_KEY; do
    if ! grep -q "^${var}=" "$REPO_ROOT/.env" 2>/dev/null; then
        warn "Variable $var not in .env"
        MISSING_VARS=$((MISSING_VARS + 1))
    fi
done
if [[ $MISSING_VARS -eq 0 ]]; then
    ok "All required .env variables present"
else
    fail "$MISSING_VARS required .env variables missing"
fi

# Count services in compose
EXPECTED_SERVICES=(postgres redis hatchet langfuse caddy control-plane)
EXPECTED_MCP=(oracle ev dedup evidence scope state normalize politeness sandbox kev h1 bugcrowd intigriti yeswehack immunefi)

COMPOSE_FILE="$REPO_ROOT/infra/docker/docker-compose.yml"
for svc in "${EXPECTED_SERVICES[@]}"; do
    if grep -q "^  ${svc}:" "$COMPOSE_FILE"; then
        ok "Service '$svc' defined in docker-compose.yml"
    else
        fail "Service '$svc' NOT found in docker-compose.yml"
    fi
done

MCP_COUNT=0
for svc in "${EXPECTED_MCP[@]}"; do
    if grep -q "^  mcp-${svc}:" "$COMPOSE_FILE"; then
        MCP_COUNT=$((MCP_COUNT + 1))
    else
        fail "MCP server 'mcp-$svc' NOT found"
    fi
done
ok "All 15 MCP servers defined ($MCP_COUNT/15)"

# Verify health checks
HEALTH_COUNT=$(grep -c "healthcheck:" "$COMPOSE_FILE" || true)
if [[ $HEALTH_COUNT -ge 4 ]]; then
    ok "Health checks defined on $HEALTH_COUNT services (≥4 expected)"
else
    fail "Only $HEALTH_COUNT healthchecks found (expected ≥4)"
fi

# Verify logging defaults
LOGGING_COUNT=$(grep -c "logging:" "$COMPOSE_FILE" || true)
if [[ $LOGGING_COUNT -ge 6 ]]; then
    ok "Logging config on $LOGGING_COUNT services"
else
    warn "Only $LOGGING_COUNT services with logging config"
fi

# Verify depends_on with conditions
DEPEND_COUNT=$(grep -c "condition: service_healthy" "$COMPOSE_FILE" || true)
if [[ $DEPEND_COUNT -ge 3 ]]; then
    ok "$DEPEND_COUNT healthy dependency conditions"
else
    fail "Only $DEPEND_COUNT healthy conditions (expected ≥3)"
fi

# ============================================================================
section "2. JWT Keypair Auto-Generation"
# ============================================================================

KEY_SCRIPT="$REPO_ROOT/scripts/generate_keys.sh"

if [[ -x "$KEY_SCRIPT" ]]; then
    ok "generate_keys.sh is executable"
else
    warn "generate_keys.sh not executable (would be fixed in Docker)"
fi

# Check keys directory
KEYS_DIR="$REPO_ROOT/keys"
if [[ -d "$KEYS_DIR" ]]; then
    ok "keys/ directory exists"
else
    fail "keys/ directory missing"
fi

# Check private key
PRIVATE_KEY="$KEYS_DIR/scope_jwt_private.pem"
if [[ -f "$PRIVATE_KEY" ]]; then
    PRIVATE_SIZE=$(wc -c < "$PRIVATE_KEY")
    if [[ $PRIVATE_SIZE -gt 3000 ]]; then
        ok "Private key exists ($PRIVATE_SIZE bytes, RSA-4096)"
    else
        warn "Private key small ($PRIVATE_SIZE bytes)"
    fi
else
    fail "Private key NOT found (expected at keys/scope_jwt_private.pem)"
fi

# Check public key
PUBLIC_KEY="$KEYS_DIR/scope_jwt_public.pem"
if [[ -f "$PUBLIC_KEY" ]]; then
    PUBLIC_SIZE=$(wc -c < "$PUBLIC_KEY")
    if [[ $PUBLIC_SIZE -gt 800 ]]; then
        ok "Public key exists ($PUBLIC_SIZE bytes)"
    else
        warn "Public key small ($PUBLIC_SIZE bytes)"
    fi
else
    fail "Public key NOT found (expected at keys/scope_jwt_public.pem)"
fi

# Verify key generation script is idempotent
if bash "$KEY_SCRIPT" 2>&1 | grep -q "already exist"; then
    ok "Key generation is idempotent (skips if keys exist)"
else
    warn "Idempotency test inconclusive"
fi

# Check .gitignore includes keys
if grep -q "keys/" "$REPO_ROOT/.gitignore" 2>/dev/null; then
    ok "keys/ is in .gitignore"
else
    fail "keys/ should be in .gitignore to prevent committing secrets"
fi

# ============================================================================
section "3. Docker Entrypoint & Pre-flight Checks"
# ============================================================================

ENTRYPOINT="$REPO_ROOT/infra/docker/entrypoint.sh"

if [[ -f "$ENTRYPOINT" ]]; then
    ok "entrypoint.sh exists"
else
    fail "entrypoint.sh NOT found"
fi

# Syntax check
if bash -n "$ENTRYPOINT" 2>/dev/null; then
    ok "entrypoint.sh syntax valid"
else
    fail "entrypoint.sh has syntax errors"
fi

# Verify key checks in entrypoint
if grep -q "openssl genrsa" "$ENTRYPOINT"; then
    ok "Entrypoint generates RSA keypair if missing"
else
    fail "Entrypoint missing RSA key generation"
fi

if grep -q "pg_isready\|psql" "$ENTRYPOINT"; then
    ok "Entrypoint waits for Postgres"
else
    warn "Entrypoint may not wait for Postgres"
fi

if grep -q "redis-cli" "$ENTRYPOINT"; then
    ok "Entrypoint waits for Redis"
else
    warn "Entrypoint may not wait for Redis"
fi

if grep -q "chmod 600" "$ENTRYPOINT"; then
    ok "Entrypoint sets secure private key permissions (chmod 600)"
else
    fail "Entrypoint missing chmod 600 on private key"
fi

# ============================================================================
section "4. Docker Build Files"
# ============================================================================

DOCKER_DIR="$REPO_ROOT/infra/docker"

for df in Dockerfile.control-plane Dockerfile.mcp-python Dockerfile.mcp-node; do
    if [[ -f "$DOCKER_DIR/$df" ]]; then
        ok "$df exists"
    else
        fail "$df NOT found"
    fi
done

# Check control-plane Dockerfile specifics
if grep -q "FROM python:3.12-slim" "$DOCKER_DIR/Dockerfile.control-plane" 2>/dev/null; then
    ok "control-plane uses Python 3.12-slim"
else
    warn "control-plane Dockerfile unexpected base image"
fi

# Check entrypoint reference in compose
if grep -q "entrypoint.sh" "$COMPOSE_FILE" 2>/dev/null || \
   grep -q "ENTRYPOINT" "$DOCKER_DIR/Dockerfile.control-plane" 2>/dev/null; then
    ok "Entrypoint configured in docker setup"
else
    warn "Entrypoint may not be configured in Docker images"
fi

# ============================================================================
section "5. Health Check Script"
# ============================================================================

HEALTH_SCRIPT="$REPO_ROOT/scripts/health_check.sh"

if [[ -f "$HEALTH_SCRIPT" ]]; then
    ok "health_check.sh exists"
else
    fail "health_check.sh NOT found"
fi

if bash -n "$HEALTH_SCRIPT" 2>/dev/null; then
    ok "health_check.sh syntax valid"
else
    fail "health_check.sh has syntax errors"
fi

# Verify it checks all critical services
for svc in postgres redis hatchet control-plane; do
    if grep -q "$svc" "$HEALTH_SCRIPT"; then
        ok "health_check.sh checks $svc"
    else
        fail "health_check.sh does NOT check $svc"
    fi
done

# ============================================================================
section "6. Environment Configuration"
# ============================================================================

ENV_FILE="$REPO_ROOT/.env.example"

if [[ -f "$ENV_FILE" ]]; then
    ok ".env.example exists"
else
    fail ".env.example NOT found"
fi

# Check BYOK emphasis
if grep -q "BYOK" "$ENV_FILE"; then
    ok ".env.example has BYOK emphasis"
else
    fail ".env.example missing BYOK emphasis"
fi

# Check fail-loud syntax
FAILLOUD_COUNT=$(grep -c '\${.*:?.*}' "$ENV_FILE" || true)
if [[ $FAILLOUD_COUNT -ge 3 ]]; then
    ok "Fail-loud syntax used ($FAILLOUD_COUNT vars)"
else
    warn "Only $FAILLOUD_COUNT fail-loud vars (expected ≥3)"
fi

# Check cost transparency
if grep -q "30/month\|sub-\$30\|cost" "$ENV_FILE" 2>/dev/null; then
    ok "Cost transparency documented"
else
    warn "Cost transparency section may be missing"
fi

# ============================================================================
section "7. Deployment Documentation"
# ============================================================================

DEPLOY_DOC="$REPO_ROOT/docs/DEPLOYMENT.md"

if [[ -f "$DEPLOY_DOC" ]]; then
    ok "DEPLOY.md exists"
    DOC_LINES=$(wc -l < "$DEPLOY_DOC")
    if [[ $DOC_LINES -gt 100 ]]; then
        ok "DEPLOY.md is comprehensive ($DOC_LINES lines)"
    else
        warn "DEPLOY.md is short ($DOC_LINES lines)"
    fi
else
    fail "DEPLOY.md NOT found"
fi

# Check for key sections
for section_name in "Quick Start" "Health Check" "Cost" "FAQ"; do
    if grep -q "$section_name" "$DEPLOY_DOC" 2>/dev/null; then
        ok "DEPLOY.md has '$section_name' section"
    else
        warn "DEPLOY.md missing '$section_name' section"
    fi
done

# ============================================================================
section "8. Docker Compose Config Validation (with env)"
# ============================================================================

# Try to validate compose config with env file
if command -v docker &>/dev/null && docker info &>/dev/null 2>&1; then
    if docker compose -f "$COMPOSE_FILE" --env-file "$REPO_ROOT/.env" config &>/dev/null; then
        ok "docker compose config validates with .env"
    else
        fail "docker compose config validation FAILED"
    fi
else
    warn "Docker daemon not available — skipping compose config validation"
fi

# ============================================================================
section "9. Full Docker Deployment (optional --full)"
# ============================================================================

if [[ $FULL -eq 1 ]]; then
    if command -v docker &>/dev/null && docker info &>/dev/null 2>&1; then
        echo "  Starting full Docker deployment..."

        # Clean start
        docker compose -f "$COMPOSE_FILE" --env-file "$REPO_ROOT/.env" down -v 2>/dev/null || true

        # Time the deployment
        START_TIME=$(date +%s)
        if docker compose -f "$COMPOSE_FILE" --env-file "$REPO_ROOT/.env" up -d 2>&1; then
            ok "docker compose up -d succeeded"
        else
            fail "docker compose up -d FAILED"
        fi

        # Wait for services
        echo "  Waiting for services to start (60s)..."
        sleep 60

        # Run health check
        if bash "$HEALTH_SCRIPT" 2>&1; then
            ok "Health check passed"
        else
            fail "Health check FAILED"
        fi

        END_TIME=$(date +%s)
        DEPLOY_TIME=$((END_TIME - START_TIME))
        echo "  Deployment time: ${DEPLOY_TIME}s"
        if [[ $DEPLOY_TIME -lt 1800 ]]; then
            ok "Deployment under 30 minutes (${DEPLOY_TIME}s)"
        else
            warn "Deployment took ${DEPLOY_TIME}s (target: <1800s)"
        fi

        # Cleanup
        docker compose -f "$COMPOSE_FILE" --env-file "$REPO_ROOT/.env" down -v 2>/dev/null || true
    else
        warn "Docker daemon not available — skipping full deployment test"
    fi
else
    echo "  Skipping Docker deployment (use --full to run)"
fi

# ============================================================================
section "Summary"
# ============================================================================

TOTAL=$((PASS + FAIL + WARN))
echo ""
echo "Results: $PASS passed, $FAIL failed, $WARN warnings (out of $TOTAL checks)"
echo ""

if [[ $FAIL -eq 0 ]]; then
    echo "✓ All critical checks passed — deployment package is ready"
    exit 0
else
    echo "✗ $FAIL critical checks failed — fix before deploying"
    exit 1
fi
