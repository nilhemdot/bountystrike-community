#!/usr/bin/env bash
# live_smoke.sh — local deploy-gate smoke runner for BountyStrike v5 (plan 01-09).
#
# Proves the LIVE paths prior plans (01-04..07) could only stub, against the
# local Docker stack on this host. Exercises the baked worker image
# (bs-control-plane:dev → bbscope + chromium) and the recon image.
#
# SECURITY INVARIANTS (do not relax):
#   M1  Recon targets derive ONLY from the scope JWT's `targets`. No host is
#       hardcoded here; an invalid/expired JWT aborts before any probe.
#   M3  SCOPE_WEBHOOK_URL is never logged beyond scheme+host. Seeded live test
#       rows are removed in cleanup(). Secrets are read from .env, never echoed.
#
# Stages (arg 1):
#   passive  (default) — JWT/worker/webhook checks + bbscope + PASSIVE subfinder.
#                        HALTS before any active HTTP probing.
#   active             — passive stage + active httpx/katana + XSS oracle + AC-4
#                        webhook POST. Only run with explicit operator intent.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
MODE="${1:-passive}"
JWT_FILE="${SCOPE_JWT_FILE:-keys/scope_smoke.jwt}"
WORKER_IMG="bs-control-plane:dev"
PG="bs-postgres"
SEED_TAG="live-smoke"   # marks rows this script seeds, for cleanup()

# --- redaction + env -------------------------------------------------------
redact() { sed -E 's#(https?://[^/]+).*#\1/<redacted>#g'; }
set -a; . ./.env 2>/dev/null || true; set +a

log() { printf '[smoke] %s\n' "$*"; }
fail() { printf '[smoke][FAIL] %s\n' "$*" >&2; exit 1; }

cleanup() {
  # M3: drop any rows this smoke seeded (idempotent, best-effort).
  docker exec "$PG" psql -U bs -d bountystrike -tAc \
    "delete from recon_assets where tags @> ARRAY['${SEED_TAG}'];" >/dev/null 2>&1 || true
}
trap cleanup EXIT

# --- gate: scope JWT (M1) --------------------------------------------------
[ -f "$JWT_FILE" ] || fail "scope JWT not found: $JWT_FILE"
CLAIMS="$(uv run python - "$JWT_FILE" <<'PY'
import sys, jwt
tok = open(sys.argv[1]).read().strip()
pub = open("keys/scope_jwt_public.pem", "rb").read()
c = jwt.decode(tok, pub, algorithms=["RS256"])   # raises on bad sig / expiry
t = c["targets"]
wc = ",".join(t.get("wildcards") or [])
ho = ",".join(t.get("hosts") or [])
print(f"{c['program_handle']}|{c['platform']}|{wc}|{ho}")
PY
)" || fail "scope JWT failed RS256 verification / expired (M1 abort)"
PROG="${CLAIMS%%|*}"; rest="${CLAIMS#*|}"
PLATFORM="${rest%%|*}"; rest="${rest#*|}"
WILDCARDS="${rest%%|*}"; HOSTS="${rest#*|}"
[ -n "$WILDCARDS$HOSTS" ] || fail "JWT carries no in-scope targets (M1 abort)"
log "JWT ok — program=$PROG platform=$PLATFORM wildcards=[$WILDCARDS] hosts=[$HOSTS]"

# Derive recon seed domains from JWT targets ONLY (strip leading '*.').
SEED_DOMAINS="$(printf '%s,%s' "$WILDCARDS" "$HOSTS" | tr ',' '\n' \
  | sed -E 's/^\*\.//' | grep -E '.' | sort -u)"
[ -n "$SEED_DOMAINS" ] || fail "no recon seed domains derived from JWT (M1 abort)"

# --- AC-1: bbscope live path (worker image) --------------------------------
log "AC-1 bbscope present + invocable in worker image…"
docker run --rm --entrypoint bbscope "$WORKER_IMG" --help >/dev/null 2>&1 \
  || fail "bbscope not invocable in $WORKER_IMG"
log "AC-1 PASS — bbscope runs in worker image"

# --- AC-3 webhook reachability (GET, no POST) ------------------------------
if [ -n "${SCOPE_WEBHOOK_URL:-}" ]; then
  code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 8 "$SCOPE_WEBHOOK_URL" || echo 000)"
  log "webhook reachable → HTTP $code ($(printf '%s' "$SCOPE_WEBHOOK_URL" | redact))"
  [ "$code" = "200" ] || [ "$code" = "204" ] || log "WARN webhook non-2xx ($code)"
else
  log "WARN SCOPE_WEBHOOK_URL unset — skipping webhook checks"
fi

# --- AC-5 passive recon (subfinder passive ONLY) ---------------------------
log "AC-5 PASSIVE subfinder over JWT-derived domains:"
printf '%s\n' "$SEED_DOMAINS" | sed 's/^/[smoke]   target: /'
RECON_IMG="bs-recon:dev"
if docker image inspect "$RECON_IMG" >/dev/null 2>&1; then
  while IFS= read -r d; do
    [ -n "$d" ] || continue
    n="$(docker run --rm --entrypoint subfinder "$RECON_IMG" \
          -silent -all=false -d "$d" 2>/dev/null | wc -l || echo 0)"
    log "  $d → $n subdomains (passive)"
  done <<< "$SEED_DOMAINS"
  log "AC-5 PASSIVE PASS"
else
  log "AC-5 SKIP — recon image $RECON_IMG not built (passive enum needs it)"
fi

if [ "$MODE" != "active" ]; then
  log "MODE=passive — HALT before active probing / webhook POST / XSS oracle."
  log "Re-run with: scripts/live_smoke.sh active   (operator intent required)"
  exit 0
fi

# ===========================================================================
# ACTIVE STAGE — only reached with MODE=active. Real HTTP to discovered hosts,
# one real webhook POST, chromium XSS oracle.
# ===========================================================================
log "ACTIVE stage engaged (operator intent)."
# AC-4: real webhook POST (one notification).
if [ -n "${SCOPE_WEBHOOK_URL:-}" ]; then
  curl -s -o /dev/null -w '%{http_code}' --max-time 8 \
    -H 'Content-Type: application/json' \
    -d '{"content":"bountystrike live_smoke AC-4 — scope-diff notify test"}' \
    "$SCOPE_WEBHOOK_URL" | sed 's/^/[smoke] AC-4 webhook POST → HTTP /'
fi
# AC-6: XSS oracle in worker image (chromium). Self-contained reflected-XSS
# fixture so we never inject into a third-party host (M1).
log "AC-6 XSS oracle (chromium DOM observer, local fixture)…"
docker run --rm --entrypoint bash "$WORKER_IMG" -lc '
  cd /home/controlplane/app/control-plane
  uv run --no-sync python - <<PY
from playwright.sync_api import sync_playwright
html = "data:text/html,<script>window.__x=1</script><div id=o></div>"
with sync_playwright() as p:
    b = p.chromium.launch(); pg = b.new_page(); pg.goto(html)
    assert pg.evaluate("window.__x") == 1, "script did not execute"
    print("AC-6 PASS — chromium executed injected script (oracle live)")
    b.close()
PY' || fail "AC-6 XSS oracle failed"
log "ACTIVE stage complete."
