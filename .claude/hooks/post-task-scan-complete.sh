#!/usr/bin/env bash
# Hook: post-task-scan-complete
# Emits a ScanJobCompleted event after the recon-agent task finishes.
# Runs only when SCAN_JOB_ID is set (i.e. inside a recon-agent session).

set -euo pipefail

if [[ -z "${SCAN_JOB_ID:-}" || -z "${DATABASE_URL:-}" ]]; then
  exit 0  # Not a recon-agent task; skip silently.
fi

status="${TASK_STATUS:-recon_failed}"
echo "post-task-scan-complete: scan_job=${SCAN_JOB_ID} status=${status}" >&2

# Update scan_jobs row with final status (idempotent; orchestrator may already set it).
python3 - <<PYEOF
import asyncio, os
import asyncpg

async def main():
    conn = await asyncpg.connect(os.environ["DATABASE_URL"].replace("+asyncpg", ""))
    await conn.execute(
        "UPDATE scan_jobs SET status = \$1 WHERE id = \$2::uuid AND status != 'recon_complete'",
        os.environ.get("TASK_STATUS", "recon_failed"),
        os.environ["SCAN_JOB_ID"],
    )
    await conn.close()

asyncio.run(main())
PYEOF

echo "post-task-scan-complete: done" >&2
exit 0
