#!/usr/bin/env bash
# Health check script for BountyStrike v5 Solo Mode deployment
#
# Usage:
#     bash scripts/health_check.sh [--verbose]
#
# Options:
#     --verbose    Show detailed output for each service check
#
# Exit codes:
#     0    All critical services are healthy
#     1    One or more critical services are unhealthy
#     2    Docker compose is not running

set -euo pipefail

# Determine repo root (one directory up from this script)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

VERBOSE=0
FAILED=0

# Parse arguments
for arg in "$@"; do
    case "$arg" in
        --verbose)
            VERBOSE=1
            ;;
        *)
            echo "Unknown argument: $arg" >&2
            echo "Usage: $0 [--verbose]" >&2
            exit 1
            ;;
    esac
done

# Colors for output (if terminal supports it)
if [[ -t 1 ]]; then
    RED='\033[0;31m'
    GREEN='\033[0;32m'
    YELLOW='\033[1;33m'
    NC='\033[0m' # No Color
else
    RED=''
    GREEN=''
    YELLOW=''
    NC=''
fi

# Helper function to print status
print_status() {
    local service="$1"
    local status="$2"
    local message="${3:-}"

    if [[ "$status" == "healthy" ]]; then
        echo -e "${GREEN}✓${NC} $service: healthy $message"
    elif [[ "$status" == "starting" ]]; then
        echo -e "${YELLOW}⧗${NC} $service: starting $message"
    else
        echo -e "${RED}✗${NC} $service: unhealthy $message"
        FAILED=1
    fi
}

# Helper function to check if a container is running
container_running() {
    local container="$1"
    docker inspect -f '{{.State.Running}}' "$container" 2>/dev/null | grep -q true
}

# Helper function to get container health status
container_health() {
    local container="$1"
    docker inspect -f '{{.State.Health.Status}}' "$container" 2>/dev/null || echo "no-healthcheck"
}

echo "BountyStrike v5 — Health Check"
echo "================================"
echo ""

# Check if docker compose is running
if ! docker compose -f "$REPO_ROOT/infra/docker/docker-compose.yml" ps --quiet 2>/dev/null | grep -q .; then
    echo -e "${RED}✗${NC} Docker compose stack is not running"
    echo ""
    echo "Start the stack with:"
    echo "  docker compose -f infra/docker/docker-compose.yml up -d"
    exit 2
fi

# Check postgres
if container_running "bs-postgres"; then
    HEALTH=$(container_health "bs-postgres")
    if [[ "$HEALTH" == "healthy" ]]; then
        print_status "postgres" "healthy" "(port 5432)"
    elif [[ "$HEALTH" == "starting" ]]; then
        print_status "postgres" "starting" "(initializing database)"
    else
        print_status "postgres" "unhealthy" "(check logs: docker logs bs-postgres)"
    fi
else
    print_status "postgres" "unhealthy" "(container not running)"
fi

# Check redis
if container_running "bs-redis"; then
    HEALTH=$(container_health "bs-redis")
    if [[ "$HEALTH" == "healthy" ]]; then
        print_status "redis" "healthy" "(port 6379)"
    elif [[ "$HEALTH" == "starting" ]]; then
        print_status "redis" "starting"
    else
        print_status "redis" "unhealthy" "(check logs: docker logs bs-redis)"
    fi
else
    print_status "redis" "unhealthy" "(container not running)"
fi

# Check hatchet
if container_running "bs-hatchet"; then
    HEALTH=$(container_health "bs-hatchet")
    if [[ "$HEALTH" == "healthy" ]]; then
        print_status "hatchet" "healthy" "(gRPC: 7070, HTTP: 8080)"
    elif [[ "$HEALTH" == "starting" ]]; then
        print_status "hatchet" "starting" "(waiting for postgres)"
    else
        print_status "hatchet" "unhealthy" "(check logs: docker logs bs-hatchet)"
    fi
else
    print_status "hatchet" "unhealthy" "(container not running)"
fi

# Check langfuse
if container_running "bs-langfuse"; then
    # langfuse doesn't have a built-in healthcheck, so just check if running
    if docker exec bs-langfuse nc -z localhost 3000 2>/dev/null; then
        print_status "langfuse" "healthy" "(port 3000)"
    else
        print_status "langfuse" "starting" "(port not yet ready)"
    fi
else
    print_status "langfuse" "unhealthy" "(container not running)"
fi

# Check control-plane
if container_running "bs-control-plane"; then
    HEALTH=$(container_health "bs-control-plane")
    if [[ "$HEALTH" == "healthy" ]]; then
        print_status "control-plane" "healthy" "(port 8001)"
    elif [[ "$HEALTH" == "starting" ]]; then
        print_status "control-plane" "starting" "(waiting for dependencies)"
    else
        print_status "control-plane" "unhealthy" "(check logs: docker logs bs-control-plane)"
    fi
else
    print_status "control-plane" "unhealthy" "(container not running)"
fi

# Check caddy
if container_running "bs-caddy"; then
    if docker exec bs-caddy wget --quiet --tries=1 --spider http://localhost:80/health 2>/dev/null || \
       docker exec bs-caddy nc -z localhost 80 2>/dev/null; then
        print_status "caddy" "healthy" "(ports 80, 443)"
    else
        print_status "caddy" "starting" "(proxy not yet ready)"
    fi
else
    print_status "caddy" "unhealthy" "(container not running)"
fi

# Check MCP servers (quick count, not individual status)
MCP_RUNNING=$(docker compose -f "$REPO_ROOT/infra/docker/docker-compose.yml" ps --filter "name=bs-mcp-" --quiet 2>/dev/null | wc -l)
MCP_EXPECTED=15

if [[ $MCP_RUNNING -eq $MCP_EXPECTED ]]; then
    print_status "mcp-servers" "healthy" "($MCP_RUNNING/$MCP_EXPECTED running)"
elif [[ $MCP_RUNNING -gt 0 ]]; then
    print_status "mcp-servers" "starting" "($MCP_RUNNING/$MCP_EXPECTED running)"
else
    print_status "mcp-servers" "unhealthy" "(0/$MCP_EXPECTED running)"
fi

echo ""

# Verbose mode: show container status details
if [[ $VERBOSE -eq 1 ]]; then
    echo "Container Details:"
    echo "===================="
    docker compose -f "$REPO_ROOT/infra/docker/docker-compose.yml" ps
    echo ""
fi

# Summary
if [[ $FAILED -eq 0 ]]; then
    echo -e "${GREEN}All services are healthy${NC}"
    exit 0
else
    echo -e "${YELLOW}Some services are unhealthy or still starting${NC}"
    echo ""
    echo "Troubleshooting:"
    echo "  • View logs: docker compose -f infra/docker/docker-compose.yml logs [service]"
    echo "  • Restart service: docker compose -f infra/docker/docker-compose.yml restart [service]"
    echo "  • Full restart: docker compose -f infra/docker/docker-compose.yml down && docker compose -f infra/docker/docker-compose.yml up -d"
    exit 1
fi
