#!/usr/bin/env bash
# cost_report.sh — BountyStrike cost-report alias.
#
# Thin wrapper over scripts/cost_audit.py --by-task-type so operators can
# use the shorter `bountystrike cost-report` command.
#
# Usage:
#   scripts/cost_report.sh                     # cost breakdown by task type (last 7 days)
#   scripts/cost_report.sh --summary           # headline numbers only
#   scripts/cost_report.sh --since 30          # last 30 days
#   scripts/cost_report.sh --task-type recon_synthesis
#   scripts/cost_report.sh --help              # full cost_audit.py help
#
# Environment:
#   DATABASE_URL  postgresql[+asyncpg]://...   (required)

set -euo pipefail

REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

# If --help is requested, show brief usage then forward to cost_audit.py
if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
    cat <<'EOF'
bountystrike cost-report — LLM cost breakdown by task type

Usage:
  cost-report                     breakdown for last 7 days
  cost-report --summary           headline numbers only
  cost-report --since N           last N days
  cost-report --task-type <slug>  filter to one task type
  cost-report --help              show full cost_audit.py options

Target: < $0.20 per scan (Phase 3 exit criterion #2)
EOF
    echo ""
    echo "--- Full cost_audit.py help ---"
    echo ""
fi

if command -v uv >/dev/null 2>&1; then
    exec uv run --frozen python scripts/cost_audit.py --by-task-type "$@"
else
    exec python scripts/cost_audit.py --by-task-type "$@"
fi
