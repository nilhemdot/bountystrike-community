-- Migration 04: approval_queue — operator-side T2/T3 approval requests.
--
-- The .claude/agents/exploit-agent.md spec (Step 5) requires a T2 sign-off
-- before sandbox execution. The Phase 2 W7-8 sprint operationalizes this:
-- the exploit-agent enqueues a request, the operator runs `scripts/approve.py`
-- to approve, and the orchestrator polls this table for the issued token.
--
-- Tier classification logic lives in the approval_gate domain
-- (control-plane/src/control_plane/domains/approval_gate); this table is
-- the durable queue that backs `wait_for_approval`.
--
-- Idempotent: re-running is a no-op when the table already exists.

CREATE TABLE IF NOT EXISTS approval_queue (
    finding_id    UUID         PRIMARY KEY REFERENCES findings(id) ON DELETE CASCADE,
    tier          TEXT         NOT NULL CHECK (tier IN ('T0', 'T1', 'T2', 'T3')),
    poc_text      TEXT,                                            -- proposed PoC text shown to operator
    status        TEXT         NOT NULL DEFAULT 'pending'
                                CHECK (status IN ('pending', 'approved', 'rejected', 'expired')),
    token         UUID,                                            -- issued on approval; APPROVAL_TOKEN env value
    requested_at  TIMESTAMPTZ  NOT NULL DEFAULT now(),
    approved_at   TIMESTAMPTZ,
    approver_id   TEXT,                                            -- distinct-actor identifier (T3 must differ from approver_id_2)
    approver_id_2 TEXT,                                            -- second approver for T3
    reason        TEXT,
    expires_at    TIMESTAMPTZ  NOT NULL                            -- enforced by sweeper, not a CHECK
);

CREATE INDEX IF NOT EXISTS idx_approval_queue_status
    ON approval_queue (status);

CREATE INDEX IF NOT EXISTS idx_approval_queue_tier_status
    ON approval_queue (tier, status);

CREATE INDEX IF NOT EXISTS idx_approval_queue_requested_at
    ON approval_queue (requested_at DESC);

-- The orchestrator polls (finding_id, status='approved') with exponential
-- backoff. The token is the value the exploit-agent receives in the
-- APPROVAL_TOKEN env var — pretool_approval_gate.py validates it (future
-- extension) or simply reads cache state via the existing Redis path.
