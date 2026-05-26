#!/usr/bin/env bash
# Generate RS256 key pair for BountyStrike v5 scope JWT signing
#
# Usage:
#     bash scripts/generate_keys.sh [--force]
#
# Options:
#     --force    Regenerate keys even if they already exist
#
# Keys are written to:
#     keys/scope_jwt_private.pem  (RSA-4096 private key, chmod 600)
#     keys/scope_jwt_public.pem   (RSA-4096 public key)

set -euo pipefail

# Determine repo root (one directory up from this script)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

KEYS_DIR="$REPO_ROOT/keys"
PRIVATE_KEY="$KEYS_DIR/scope_jwt_private.pem"
PUBLIC_KEY="$KEYS_DIR/scope_jwt_public.pem"

FORCE=0

# Parse arguments
for arg in "$@"; do
    case "$arg" in
        --force)
            FORCE=1
            ;;
        *)
            echo "Unknown argument: $arg" >&2
            echo "Usage: $0 [--force]" >&2
            exit 1
            ;;
    esac
done

# Check if keys already exist
if [[ -f "$PRIVATE_KEY" && -f "$PUBLIC_KEY" && $FORCE -eq 0 ]]; then
    echo "Keys already exist at:" >&2
    echo "  private → $PRIVATE_KEY" >&2
    echo "  public  → $PUBLIC_KEY" >&2
    echo "Use --force to regenerate" >&2
    exit 0
fi

# Create keys directory if it doesn't exist
mkdir -p "$KEYS_DIR"

echo "Generating RSA-4096 key pair..." >&2

# Generate private key (RSA-4096, no passphrase)
openssl genrsa -out "$PRIVATE_KEY" 4096 2>/dev/null

# Extract public key from private key
openssl rsa -in "$PRIVATE_KEY" -pubout -out "$PUBLIC_KEY" 2>/dev/null

# Set secure permissions on private key
chmod 600 "$PRIVATE_KEY"

echo "  private → $PRIVATE_KEY" >&2
echo "  public  → $PUBLIC_KEY" >&2
echo "Keys generated successfully" >&2
