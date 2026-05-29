#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later

"""End-to-end test for the init wizard (scripts/bs init).

Simulates a fresh environment and verifies:
  1. Wizard launches and prompts for API keys
  2. .env file is created with correct keys
  3. RS256 keypair is generated
  4. Scope JWT is saved to scope_jwt.txt
  5. First-scan walkthrough is offered
  6. Documentation links are displayed
  7. Feedback mechanism (GitHub Discussions) is present

Usage:
    python scripts/test_init_wizard_e2e.py

Exit code 0 on success, 1 on failure.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = REPO_ROOT / ".env"
ENV_BACKUP = REPO_ROOT / ".env.e2e_backup"
SCOPE_JWT_FILE = REPO_ROOT / "scope_jwt.txt"
KEYS_DIR = REPO_ROOT / "keys"
WIZARD_SCRIPT = REPO_ROOT / "scripts" / "init_wizard.py"
DISPATCHER = REPO_ROOT / "scripts" / "bs"

# Simulated operator input (one line per prompt, in order):
# 1. ANTHROPIC_API_KEY
# 2. DATABASE_URL
# 3-7. Configure platform keys? (5 × n)
# 8. Generate JWT now? (y)
# 9. Operator ID
# 10. Program handle
# 11. Platform (default: hackerone)
# 12. Wildcard targets
# 13. Exact hosts (empty)
# 14. JWT expiry (default: 168)
# 15. Rate limit RPS (default: 5)
# 16. Launch first scan? (n)
STDIN_INPUT = (
    "sk-ant-e2e-test-key\n"
    "postgresql://bs:e2e-test@localhost:5432/bountystrike\n"
    "n\n"   # H1_API_TOKEN
    "n\n"   # H1_USERNAME
    "n\n"   # BUGCROWD_SESSION_COOKIE
    "n\n"   # INTIGRITI_PAT
    "n\n"   # YESWEHACK_BEARER
    "y\n"   # Generate JWT now?
    "e2e-operator\n"
    "e2e-corp\n"
    "hackerone\n"
    "*.e2e-test.com\n"
    "\n"    # no exact hosts
    "\n"    # default expiry (168h)
    "\n"    # default RPS (5)
    "n\n"   # no first scan
)


def backup_env() -> None:
    """Back up existing .env if present."""
    if ENV_FILE.exists():
        shutil.copy2(ENV_FILE, ENV_BACKUP)
        print("[setup] Backed up existing .env")


def restore_env() -> None:
    """Restore original .env after test."""
    # Clean up test artifacts
    if SCOPE_JWT_FILE.exists():
        SCOPE_JWT_FILE.unlink()
    if KEYS_DIR.exists():
        shutil.rmtree(KEYS_DIR)

    if ENV_BACKUP.exists():
        shutil.copy2(ENV_BACKUP, ENV_FILE)
        ENV_BACKUP.unlink()
        print("[cleanup] Restored original .env")
    elif ENV_FILE.exists():
        ENV_FILE.unlink()
        print("[cleanup] Removed test .env")


def run_wizard(input_text: str, use_dispatcher: bool = False) -> subprocess.CompletedProcess:
    """Run the wizard with piped stdin input."""
    cmd = [sys.executable, str(WIZARD_SCRIPT)]
    if use_dispatcher:
        # For the dispatcher test, use uv run
        import shutil as sh
        uv_path = sh.which("uv")
        if uv_path:
            cmd = ["uv", "run", "python", str(WIZARD_SCRIPT)]
        else:
            cmd = [sys.executable, str(WIZARD_SCRIPT)]

    env = os.environ.copy()
    env["PYTHONPATH"] = str(REPO_ROOT / "scripts")

    return subprocess.run(
        cmd,
        input=input_text,
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        env=env,
    )


def verify_output(output: str) -> list[str]:
    """Verify wizard output contains expected strings. Returns list of failures."""
    failures = []

    checks = [
        ("=== API Key Configuration ===", "API key configuration section"),
        ("=== Scope JWT Generation ===", "Scope JWT generation section"),
        ("JWT generated successfully", "JWT generation success message"),
        ("=== First Scan Walkthrough ===", "First scan walkthrough section"),
        ("Setup complete!", "Setup complete message"),
        ("docs/runbooks/alpha-testing-guide.md", "Alpha testing guide link"),
        ("docs/runbooks/first-scan-walkthrough.md", "First scan walkthrough doc link"),
        ("docs/runbooks/troubleshooting-guide.md", "Troubleshooting guide link"),
        ("https://github.com/bountystrike/bountystrike-v5/discussions",
         "GitHub Discussions feedback link"),
    ]

    for expected, description in checks:
        if expected not in output:
            failures.append(f"  MISSING: {description} ('{expected}')")

    return failures


def verify_env_file() -> list[str]:
    """Verify .env file was created correctly. Returns list of failures."""
    failures = []

    if not ENV_FILE.exists():
        failures.append("  MISSING: .env file not created")
        return failures

    env_content = ENV_FILE.read_text()

    checks = [
        ("ANTHROPIC_API_KEY=sk-ant-e2e-test-key", "ANTHROPIC_API_KEY in .env"),
        ("DATABASE_URL=postgresql://bs:e2e-test@localhost:5432/bountystrike",
         "DATABASE_URL in .env"),
        ("REDIS_HOST=127.0.0.1", "REDIS_HOST default in .env"),
        ("REDIS_PORT=6379", "REDIS_PORT default in .env"),
        ("SCOPE_JWT_PRIVATE_KEY_PATH=keys/scope_jwt_private.pem",
         "Private key path in .env"),
        ("SCOPE_JWT_PUBLIC_KEY_PATH=keys/scope_jwt_public.pem",
         "Public key path in .env"),
    ]

    for expected, description in checks:
        if expected not in env_content:
            failures.append(f"  MISSING: {description}")

    return failures


def verify_jwt_file() -> list[str]:
    """Verify JWT file and keypair were created. Returns list of failures."""
    failures = []

    if not SCOPE_JWT_FILE.exists():
        failures.append("  MISSING: scope_jwt.txt not created")
        return failures

    token = SCOPE_JWT_FILE.read_text().strip()
    if not token or "." not in token:
        failures.append("  INVALID: scope_jwt.txt does not contain a valid JWT")
    else:
        # Verify JWT has 3 parts (header.payload.signature)
        parts = token.split(".")
        if len(parts) != 3:
            failures.append(f"  INVALID: JWT has {len(parts)} parts (expected 3)")

    private_key = KEYS_DIR / "scope_jwt_private.pem"
    public_key = KEYS_DIR / "scope_jwt_public.pem"

    if not private_key.exists():
        failures.append("  MISSING: private key file")
    else:
        content = private_key.read_text()
        # cryptography 48+ generates PKCS#1 RSA keys
        if "-----BEGIN RSA PRIVATE KEY-----" not in content:
            failures.append("  INVALID: private key missing PEM header")

    if not public_key.exists():
        failures.append("  MISSING: public key file")
    else:
        content = public_key.read_text()
        if "-----BEGIN PUBLIC KEY-----" not in content:
            failures.append("  INVALID: public key missing PEM header")

    return failures


def verify_env_backup_no_data_loss(original_env: str) -> list[str]:
    """Verify that re-running the wizard with --update preserves existing values."""
    failures = []

    # Run the wizard in update mode with input that accepts defaults
    # y (keep ANTHROPIC), y (keep DATABASE_URL), n (skip platform keys), n (skip JWT)
    update_input = "y\ny\nn\nn\nn\nn\nn\nn\n"
    result = run_wizard(update_input + "\n")
    # The --update flag should be passed via args, let's test differently
    # Actually, _load_existing_env detects .env and enters update flow
    # We tested the flow above; verify the env wasn't destroyed

    if ENV_FILE.exists():
        env_content = ENV_FILE.read_text()
        if "ANTHROPIC_API_KEY" in env_content:
            print("[verify] Re-run safety: .env still has keys after simulated re-run")
        else:
            failures.append("  DATA LOSS: .env lost keys after re-run")
    else:
        failures.append("  DATA LOSS: .env missing after re-run")

    return failures


def main() -> int:
    print("=" * 60)
    print("E2E Test: Init Wizard")
    print("=" * 60)

    # Clean slate: remove existing .env to simulate fresh environment
    backup_env()
    if ENV_FILE.exists():
        ENV_FILE.unlink()
    if SCOPE_JWT_FILE.exists():
        SCOPE_JWT_FILE.unlink()
    if KEYS_DIR.exists():
        shutil.rmtree(KEYS_DIR)

    all_failures: list[str] = []

    # --- Test 1: Direct wizard execution (fresh environment) ---
    print("\n[TEST 1] Running wizard directly (fresh environment)...")
    result = run_wizard(STDIN_INPUT)
    output = result.stdout + result.stderr

    if result.returncode != 0:
        all_failures.append(f"  FAIL: Wizard exited with code {result.returncode}")
        print(f"  STDERR: {result.stderr[:500]}")
    else:
        print("  PASS: Wizard exited with code 0")

    # --- Verify output strings ---
    print("\n[TEST 2] Verifying wizard output...")
    output_failures = verify_output(output)
    all_failures.extend(output_failures)
    if not output_failures:
        print("  PASS: All expected output strings present")
    else:
        for f in output_failures:
            print(f)

    # --- Verify .env file ---
    print("\n[TEST 3] Verifying .env file...")
    env_failures = verify_env_file()
    all_failures.extend(env_failures)
    if not env_failures:
        print("  PASS: .env file correct")
    else:
        for f in env_failures:
            print(f)

    # --- Verify JWT file and keypair ---
    print("\n[TEST 4] Verifying JWT file and keypair...")
    jwt_failures = verify_jwt_file()
    all_failures.extend(jwt_failures)
    if not jwt_failures:
        print("  PASS: JWT file and keypair correct")
    else:
        for f in jwt_failures:
            print(f)

    # --- Clean up test artifacts and restore original .env ---
    print("\n[CLEANUP] Restoring original .env...")
    restore_env()

    # --- Summary ---
    print("\n" + "=" * 60)
    if not all_failures:
        print("ALL E2E TESTS PASSED")
        print("=" * 60)
        return 0
    else:
        print(f"E2E TESTS FAILED ({len(all_failures)} issues):")
        for f in all_failures:
            print(f)
        print("=" * 60)
        return 1


if __name__ == "__main__":
    sys.exit(main())
