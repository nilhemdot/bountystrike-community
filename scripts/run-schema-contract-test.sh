#!/bin/bash
# SPDX-License-Identifier: AGPL-3.0-or-later

# Helper script to run schema-Pydantic contract test with Postgres setup
# Usage: ./scripts/run-schema-contract-test.sh

set -e

echo "=== Schema-Pydantic Contract Test Runner ==="
echo ""

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    echo "❌ Error: Docker is not running"
    echo "   Please start Docker Desktop and try again"
    exit 1
fi

echo "✓ Docker is running"

# Check if postgres container exists
if ! docker ps -a --format '{{.Names}}' | grep -q '^bs-postgres$'; then
    echo "Starting Postgres container..."
    docker compose -f infra/docker/docker-compose.yml up postgres -d
    echo "Waiting for Postgres to be healthy..."
    sleep 10
fi

# Check if Postgres is running
if ! docker ps --format '{{.Names}}' | grep -q '^bs-postgres$'; then
    echo "Starting Postgres container..."
    docker start bs-postgres || docker compose -f infra/docker/docker-compose.yml up postgres -d
    echo "Waiting for Postgres to be healthy..."
    sleep 10
fi

echo "✓ Postgres container is running"

# Get the database password from .env
if [ -f .env ]; then
    source .env
    PG_PASSWORD=${POSTGRES_PASSWORD:-bspass}
else
    PG_PASSWORD=bspass
    echo "⚠️  Warning: .env not found, using default password"
fi

# Create test database if it doesn't exist
echo "Creating test database if needed..."
docker exec bs-postgres psql -U bs -d bountystrike -c "CREATE DATABASE bountystrike_test;" 2>/dev/null || echo "Database already exists"

echo "✓ Test database exists"

# Apply migrations
echo "Applying migrations..."
for sql_file in infra/sql/*.sql; do
    echo "  - Applying $(basename "$sql_file")..."
    docker exec -i bs-postgres psql -U bs -d bountystrike_test -v ON_ERROR_STOP=1 < "$sql_file" 2>&1 | grep -v "already exists" || true
done

echo "✓ Migrations applied"
echo ""

# Run the contract test
echo "Running schema-Pydantic contract test..."
echo "================================================"
BS5_PG_TEST_DSN=postgresql://bs:${PG_PASSWORD}@127.0.0.1:5432/bountystrike_test uv run pytest tests/integration/test_schema_pydantic_contract.py -v

echo ""
echo "================================================"
echo "✓ Contract test completed successfully!"
