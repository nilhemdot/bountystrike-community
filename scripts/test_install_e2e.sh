#!/usr/bin/env bash
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# test_install_e2e.sh — offline test harness for the one-line installer.
#
# Runs fully offline: a stub `docker` (and `curl`) shim is prepended to PATH so
# no daemon or network is needed, and everything happens inside an isolated temp
# copy of the repo — the real ./.env and ./keys are never touched.
#
# Usage: bash scripts/test_install_e2e.sh
# Exit codes: 0 all cases pass | 1 one or more failed.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

PASS=0
FAIL=0
ok()   { echo "  ✓ $*"; PASS=$((PASS + 1)); }
bad()  { echo "  ✗ $*"; FAIL=$((FAIL + 1)); }
section() { echo ""; echo "$1"; echo "$(printf '─%.0s' $(seq 1 ${#1}))"; }

# --- Isolated temp copy of the install surface ---
TESTROOT="$(mktemp -d)"
trap 'rm -rf "$TESTROOT"' EXIT

mkdir -p "$TESTROOT/scripts" "$TESTROOT/infra/docker"
cp "$REPO_ROOT/scripts/install.sh"        "$TESTROOT/scripts/"
cp "$REPO_ROOT/scripts/seed_env.sh"       "$TESTROOT/scripts/"
cp "$REPO_ROOT/scripts/generate_keys.sh"  "$TESTROOT/scripts/"
cp "$REPO_ROOT/scripts/health_check.sh"   "$TESTROOT/scripts/"
cp "$REPO_ROOT/infra/docker/docker-compose.yml" "$TESTROOT/infra/docker/"
cp "$REPO_ROOT/.env.example"              "$TESTROOT/.env.example"
[[ -f "$REPO_ROOT/.gitignore" ]] && cp "$REPO_ROOT/.gitignore" "$TESTROOT/.gitignore"

COMPOSE="$TESTROOT/infra/docker/docker-compose.yml"
INSTALL="$TESTROOT/scripts/install.sh"
SEED="$TESTROOT/scripts/seed_env.sh"
INSTALL_ENV="$TESTROOT/.env"
PRIV="$TESTROOT/keys/scope_jwt_private.pem"

INFRA_SECRETS=(POSTGRES_PASSWORD REDIS_PASSWORD HATCHET_COOKIE_SECRET HATCHET_POSTGRES_PASSWORD LANGFUSE_SECRET LANGFUSE_SALT)

# --- Stub bin: docker + curl shims (record argv, simulate healthy stack) ---
STUBDIR="$TESTROOT/stubbin"
mkdir -p "$STUBDIR"

cat > "$STUBDIR/docker" <<'STUB'
#!/usr/bin/env bash
echo "$*" >> "${DOCKER_ARGV_LOG:-/dev/null}"
if [ "${DOCKER_STUB_MODE:-healthy}" = "broken" ]; then
    # Simulate: docker binary present but the compose plugin is unusable.
    exit 1
fi
case "$*" in
    *"compose version"*)        exit 0 ;;
    *"config -q"*)              exit 0 ;;
    *"up -d --build"*)          exit 0 ;;
    *"--filter name=bs-mcp-"*)  for i in $(seq 1 15); do echo "mcp$i"; done; exit 0 ;;
    *"State.Running"*)          echo true; exit 0 ;;
    *"State.Health"*)           echo healthy; exit 0 ;;
    *exec*)                     exit 0 ;;
    *" ps --quiet"*)            echo fakecontainer; exit 0 ;;
    *" ps"*)                    echo fakecontainer; exit 0 ;;
    *)                          exit 0 ;;
esac
STUB
chmod +x "$STUBDIR/docker"

cat > "$STUBDIR/curl" <<'STUB'
#!/usr/bin/env bash
echo "$*" >> "${CURL_ARGV_LOG:-/dev/null}"
exit 0
STUB
chmod +x "$STUBDIR/curl"

STUB_PATH="$STUBDIR:$PATH"

reset_state() { rm -f "$INSTALL_ENV" "$TESTROOT/.env.snap" "$TESTROOT/.env.x" 2>/dev/null; rm -rf "$TESTROOT/keys"; }
secret_val()  { grep -E "^$1=" "$INSTALL_ENV" 2>/dev/null | head -1 | cut -d= -f2-; }

# compose_default KEY -> the ${KEY:-DEFAULT} fallback string, or "" if none.
compose_default() {
    grep -oE "\\\$\{$1:-[^}]*\}" "$COMPOSE" | head -1 | sed -E "s/^\\\$\{$1:-//; s/\}\$//"
}

# ============================================================================
section "C1 — Fresh unattended provision (--no-up) [AC-1]"
# ============================================================================
reset_state
DOCKER_ARGV_LOG="$TESTROOT/argv_c1.log"
: > "$DOCKER_ARGV_LOG"
if PATH="$STUB_PATH" DOCKER_ARGV_LOG="$DOCKER_ARGV_LOG" bash "$INSTALL" --no-up --unattended >"$TESTROOT/out_c1.txt" 2>&1; then
    ok "install.sh --no-up --unattended exits 0"
else
    bad "install.sh --no-up --unattended exited non-zero"; cat "$TESTROOT/out_c1.txt"
fi
[[ -f "$INSTALL_ENV" ]] && ok ".env created" || bad ".env not created"
c1_all_filled=1
for k in "${INFRA_SECRETS[@]}"; do
    [[ -n "$(secret_val "$k")" ]] || { c1_all_filled=0; bad "$k empty after provision"; }
done
[[ $c1_all_filled -eq 1 ]] && ok "all 6 infra secrets non-empty"
[[ -z "$(secret_val ANTHROPIC_API_KEY)" ]] && ok "ANTHROPIC_API_KEY left blank (BYOK)" || bad "ANTHROPIC_API_KEY was filled"
[[ -f "$PRIV" && -f "$TESTROOT/keys/scope_jwt_public.pem" ]] && ok "keypair generated" || bad "keypair missing"

# ============================================================================
section "C2 — Idempotent re-run, secrets byte-identical [AC-2]"
# ============================================================================
cp "$INSTALL_ENV" "$TESTROOT/.env.snap"
priv_mtime_before="$(stat -c %Y "$PRIV" 2>/dev/null || echo 0)"
if PATH="$STUB_PATH" bash "$INSTALL" --no-up --unattended >/dev/null 2>&1; then
    if diff -q "$TESTROOT/.env.snap" "$INSTALL_ENV" >/dev/null; then
        ok ".env byte-identical after re-run"
    else
        bad ".env changed on re-run"
    fi
else
    bad "second install run exited non-zero"
fi
priv_mtime_after="$(stat -c %Y "$PRIV" 2>/dev/null || echo 1)"
[[ "$priv_mtime_before" == "$priv_mtime_after" ]] && ok "private key not regenerated" || bad "private key was regenerated"

# ============================================================================
section "C3 — Full run: config -q THEN up -d --build, banner printed [AC-3]"
# ============================================================================
reset_state
DOCKER_ARGV_LOG="$TESTROOT/argv_c3.log"; : > "$DOCKER_ARGV_LOG"
if PATH="$STUB_PATH" DOCKER_ARGV_LOG="$DOCKER_ARGV_LOG" \
   INSTALL_HEALTH_RETRIES=3 INSTALL_HEALTH_INTERVAL=1 \
   bash "$INSTALL" --unattended >"$TESTROOT/out_c3.txt" 2>&1; then
    ok "full run exits 0 (healthy stub)"
else
    bad "full run exited non-zero"; cat "$TESTROOT/out_c3.txt"
fi
cfg_line="$(grep -n 'config -q' "$DOCKER_ARGV_LOG" | head -1 | cut -d: -f1)"
up_line="$(grep -n 'up -d --build' "$DOCKER_ARGV_LOG" | head -1 | cut -d: -f1)"
if [[ -n "$cfg_line" && -n "$up_line" && "$cfg_line" -lt "$up_line" ]]; then
    ok "compose 'config -q' recorded BEFORE 'up -d --build'"
else
    bad "expected config -q (line $cfg_line) before up -d --build (line $up_line)"
fi
grep -q 'provisioning complete' "$TESTROOT/out_c3.txt" && ok "next-steps banner printed" || bad "next-steps banner missing"
grep -q 'gen_scope_jwt.py' "$TESTROOT/out_c3.txt" && ok "scope-JWT command in next-steps" || bad "scope-JWT command missing"

# ============================================================================
section "C4 — Missing/unusable Docker never pipes curl|sh [AC-4/S1]"
# ============================================================================
reset_state
DOCKER_ARGV_LOG="$TESTROOT/argv_c4.log"; : > "$DOCKER_ARGV_LOG"
CURL_ARGV_LOG="$TESTROOT/curl_c4.log"; : > "$CURL_ARGV_LOG"
if PATH="$STUB_PATH" DOCKER_STUB_MODE=broken \
   DOCKER_ARGV_LOG="$DOCKER_ARGV_LOG" CURL_ARGV_LOG="$CURL_ARGV_LOG" \
   bash "$INSTALL" --unattended >"$TESTROOT/out_c4.txt" 2>&1; then
    bad "install should have exited non-zero with no usable docker"
else
    ok "install exits non-zero when docker unusable + no --install-docker"
fi
grep -q 'get.docker.com' "$TESTROOT/out_c4.txt" && ok "actionable get.docker.com message shown" || bad "no get.docker.com guidance"
[[ ! -s "$CURL_ARGV_LOG" ]] && ok "curl was never invoked (no implicit curl|sh)" || bad "curl was invoked: $(cat "$CURL_ARGV_LOG")"
grep -q 'up -d --build' "$DOCKER_ARGV_LOG" && bad "stack was started despite no docker" || ok "stack NOT started"

# ============================================================================
section "C5 — Seeded secrets never equal compose-baked defaults [AC-5/M2]"
# ============================================================================
reset_state
PATH="$STUB_PATH" bash "$INSTALL" --no-up --unattended >/dev/null 2>&1
c5_fail=0
for k in "${INFRA_SECRETS[@]}"; do
    grep -qE "^$k=" "$TESTROOT/.env.example" || { bad "$k has no placeholder in .env.example"; c5_fail=1; }
    def="$(compose_default "$k")"
    val="$(secret_val "$k")"
    if [[ -n "$def" && "$val" == "$def" ]]; then
        bad "$k equals compose-baked default '$def'"; c5_fail=1
    fi
done
[[ $c5_fail -eq 0 ]] && ok "all 6 secrets have placeholders and differ from compose defaults"
# specifically the one with a real :- default
hpp_def="$(compose_default HATCHET_POSTGRES_PASSWORD)"
[[ "$hpp_def" == "hatchet" && "$(secret_val HATCHET_POSTGRES_PASSWORD)" != "hatchet" ]] \
    && ok "HATCHET_POSTGRES_PASSWORD ('$hpp_def' default) overridden in .env" \
    || bad "HATCHET_POSTGRES_PASSWORD default not overridden (def='$hpp_def')"

# ============================================================================
section "C6 — Secret files are 0600, not world-readable [AC-7]"
# ============================================================================
env_mode="$(stat -c %a "$INSTALL_ENV" 2>/dev/null || echo '?')"
priv_mode="$(stat -c %a "$PRIV" 2>/dev/null || echo '?')"
[[ "$env_mode" == "600" ]] && ok ".env is mode 600" || bad ".env mode is $env_mode (expected 600)"
[[ "$priv_mode" == "600" ]] && ok "private key is mode 600" || bad "private key mode is $priv_mode (expected 600)"

# ============================================================================
section "C7 — Mixed-state: fill blanks, never touch operator values [AC-10]"
# ============================================================================
reset_state
cp "$TESTROOT/.env.example" "$INSTALL_ENV"
awk '$0=="POSTGRES_PASSWORD="{print "POSTGRES_PASSWORD=operator-chosen-pw";next}{print}' "$INSTALL_ENV" > "$INSTALL_ENV.x" && mv "$INSTALL_ENV.x" "$INSTALL_ENV"
PATH="$STUB_PATH" bash "$SEED" >/dev/null 2>&1
[[ "$(secret_val POSTGRES_PASSWORD)" == "operator-chosen-pw" ]] && ok "pre-set POSTGRES_PASSWORD untouched" || bad "operator POSTGRES_PASSWORD clobbered"
[[ -n "$(secret_val LANGFUSE_SALT)" ]] && ok "blank LANGFUSE_SALT filled" || bad "LANGFUSE_SALT not filled"

# ============================================================================
section "C8 — Health timeout fails loud, no success banner [AC-8]"
# ============================================================================
reset_state
cp "$TESTROOT/scripts/health_check.sh" "$TESTROOT/scripts/health_check.sh.real"
printf '#!/usr/bin/env bash\nexit 1\n' > "$TESTROOT/scripts/health_check.sh"
chmod +x "$TESTROOT/scripts/health_check.sh"
DOCKER_ARGV_LOG="$TESTROOT/argv_c8.log"; : > "$DOCKER_ARGV_LOG"
if PATH="$STUB_PATH" DOCKER_ARGV_LOG="$DOCKER_ARGV_LOG" \
   INSTALL_HEALTH_RETRIES=2 INSTALL_HEALTH_INTERVAL=0 \
   bash "$INSTALL" --unattended >"$TESTROOT/out_c8.txt" 2>&1; then
    bad "install exited 0 despite unhealthy stack"
else
    ok "install exits non-zero on health timeout"
fi
grep -q 'provisioning complete' "$TESTROOT/out_c8.txt" && bad "success banner printed on half-up stack" || ok "no success banner on half-up stack"
grep -qi 'did NOT become healthy' "$TESTROOT/out_c8.txt" && ok "timeout message shown" || bad "no timeout message"
mv "$TESTROOT/scripts/health_check.sh.real" "$TESTROOT/scripts/health_check.sh"

# ============================================================================
section "C9 — Preflight: openssl absent → fail before writing .env [AC-9]"
# ============================================================================
C9ROOT="$(mktemp -d)"
mkdir -p "$C9ROOT/scripts"
cp "$TESTROOT/scripts/seed_env.sh" "$C9ROOT/scripts/"
cp "$TESTROOT/.env.example" "$C9ROOT/.env.example"
NOSSL="$TESTROOT/nossl"; mkdir -p "$NOSSL"
for t in cp chmod grep awk mktemp mv stat dirname sed cat sleep seq head cut diff env; do
    p="$(command -v "$t" 2>/dev/null || true)"
    [[ -n "$p" ]] && ln -sf "$p" "$NOSSL/$t"
done
BASH_BIN="$(command -v bash)"
if PATH="$NOSSL" "$BASH_BIN" "$C9ROOT/scripts/seed_env.sh" >/dev/null 2>&1; then
    bad "seed_env exited 0 with openssl absent"
else
    ok "seed_env exits non-zero when openssl missing"
fi
[[ ! -f "$C9ROOT/.env" ]] && ok ".env not created when prerequisite missing" || bad ".env was written despite missing openssl"
rm -rf "$C9ROOT"

# ============================================================================
section "Summary"
# ============================================================================
echo ""
echo "Results: $PASS passed, $FAIL failed"
echo ""
if [[ $FAIL -eq 0 ]]; then
    echo "✓ All installer test cases passed"
    exit 0
else
    echo "✗ $FAIL case(s) failed"
    exit 1
fi
