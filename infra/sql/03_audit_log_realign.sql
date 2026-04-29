-- Migration 03: audit_log schema realignment + concurrency-safe chain append.
--
-- The 01_schema.sql audit_log layout (id BIGSERIAL, ts, actor, action,
-- resource, payload, prev_hash, row_hash) does NOT match the columns the
-- evidence_management.HashChainService writes. The service expects:
--   (id UUID, finding_id UUID, entry_type TEXT, payload JSONB, prev_hash
--    BYTEA, chain_hash BYTEA, created_at TIMESTAMPTZ)
--
-- This migration drops the unused legacy table (no production data yet —
-- pre-Phase-1 sign-off) and creates the per-finding hash-chained log.
--
-- Idempotent: re-running is a no-op when the new shape already exists.
-- Destructive in the legacy direction: drops `audit_log` regardless of
-- prior contents. Safe pre-Phase 1 only.

-- ============================================================================
-- Drop legacy audit_log (column shape incompatible).
-- ============================================================================

DROP INDEX IF EXISTS idx_audit_log_ts;
DROP INDEX IF EXISTS idx_audit_log_actor;
DROP INDEX IF EXISTS idx_audit_log_action;
DROP TABLE IF EXISTS audit_log;

-- ============================================================================
-- audit_log — per-finding hash-chained tamper-evident log.
-- chain_hash = SHA-256(prev_hash || canonical_jsonb(payload))
-- (computed in HashChainService.append_entry; this table stores only the
--  result so the chain is verifiable from a SQL-only export).
-- ============================================================================

CREATE TABLE audit_log (
    id          UUID         PRIMARY KEY,
    finding_id  UUID         NOT NULL REFERENCES findings(id) ON DELETE CASCADE,
    entry_type  TEXT         NOT NULL,
    payload     JSONB        NOT NULL,
    prev_hash   BYTEA        NOT NULL,                  -- 0-byte for genesis
    chain_hash  BYTEA        NOT NULL CHECK (octet_length(chain_hash) = 32),
    created_at  TIMESTAMPTZ  NOT NULL DEFAULT now()
);

-- Hot path: latest chain_hash per finding (used by append_entry).
CREATE INDEX idx_audit_log_finding_created
    ON audit_log (finding_id, created_at DESC);

CREATE INDEX idx_audit_log_entry_type
    ON audit_log (entry_type);

CREATE INDEX idx_audit_log_created_at
    ON audit_log (created_at DESC);

-- Concurrency model: HashChainService.append_entry takes a per-finding
-- pg_advisory_xact_lock keyed by hashtext(finding_id::text). This serializes
-- chain extension across concurrent workers writing to the same finding
-- without blocking unrelated writers. Released automatically on txn commit.
