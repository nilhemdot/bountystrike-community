-- Migration 02: dedup_fingerprints table + scan_jobs columns
-- Idempotent (IF NOT EXISTS / IF column does not exist pattern).

-- ============================================================================
-- dedup_fingerprints — cross-session finding deduplication (dedup-mcp)
-- Fingerprint: sha256(platform\x00program\x00vuln_type\x00host\x00path)
-- ============================================================================

CREATE TABLE IF NOT EXISTS dedup_fingerprints (
    fingerprint_hex  TEXT        PRIMARY KEY,
    platform         TEXT        NOT NULL,
    program_handle   TEXT        NOT NULL,
    vuln_type        TEXT        NOT NULL,
    finding_id       TEXT        NOT NULL,
    first_seen_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_dedup_platform_program
    ON dedup_fingerprints (platform, program_handle);

CREATE INDEX IF NOT EXISTS idx_dedup_first_seen_at
    ON dedup_fingerprints (first_seen_at DESC);

-- ============================================================================
-- scan_jobs — add columns referenced by recon-agent but missing from 01_schema
-- ============================================================================

DO $$ BEGIN
    ALTER TABLE scan_jobs ADD COLUMN IF NOT EXISTS hosts_found     INTEGER DEFAULT 0;
    ALTER TABLE scan_jobs ADD COLUMN IF NOT EXISTS endpoints_found INTEGER DEFAULT 0;
    ALTER TABLE scan_jobs ADD COLUMN IF NOT EXISTS completed_at    TIMESTAMPTZ;
EXCEPTION
    WHEN undefined_table THEN NULL;
END $$;
