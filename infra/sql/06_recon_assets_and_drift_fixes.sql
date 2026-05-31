-- Migration 06: close the schema-vs-spec drifts caught by the F2
-- contract test (`tests/integration/test_schema_vs_spec_contract.py`).
--
-- Three independent drifts surfaced when every ```sql``` fence in
-- `.claude/agents/*.md` was prepared against migrations 00-05:
--
--   1. `recon_assets` table referenced by scanner-agent (and
--      ai-vuln-hunter prose) but never created.
--   2. `scan_jobs.findings_emitted` column referenced by
--      scanner-agent / ai-vuln-hunter / cloud-recon-agent UPDATEs.
--   3. `exploit_pending_validation` value missing from
--      `finding_status` ENUM despite exploit-agent + validator-agent
--      using it on the `hypothesis -> exploit_pending_validation ->
--      validated` path.
--
-- Idempotent: every change uses IF NOT EXISTS / ADD VALUE IF NOT
-- EXISTS so re-running the migration is a no-op.

-- ---------------------------------------------------------------------
-- 1. recon_assets — output of recon-agent, consumed by scanner-agent.
--
-- Recon currently writes vulnerability candidates straight to
-- `findings`; this table separately captures the discovered host /
-- URL / tech surface so scanner-agent can group by tech cluster
-- without re-running the recon pipeline.
-- ---------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS recon_assets (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id       UUID NOT NULL REFERENCES scan_jobs(id) ON DELETE CASCADE,
    host         TEXT NOT NULL,
    url          TEXT,
    tech         TEXT,
    status_code  INTEGER,
    raw          JSONB,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (job_id, host, url)
);

CREATE INDEX IF NOT EXISTS idx_recon_assets_job_id ON recon_assets (job_id);
CREATE INDEX IF NOT EXISTS idx_recon_assets_host   ON recon_assets (host);
CREATE INDEX IF NOT EXISTS idx_recon_assets_tech   ON recon_assets (tech);

-- ---------------------------------------------------------------------
-- 2. scan_jobs.findings_emitted — running tally maintained by every
--    agent that lands findings rows (scanner / ai-vuln-hunter /
--    cloud-recon).
-- ---------------------------------------------------------------------

DO $$ BEGIN
    ALTER TABLE scan_jobs
        ADD COLUMN IF NOT EXISTS findings_emitted INTEGER DEFAULT 0;
EXCEPTION
    WHEN undefined_table THEN NULL;
END $$;

-- ---------------------------------------------------------------------
-- 3. finding_status += 'exploit_pending_validation' — the state the
--    exploit-agent flips a finding to before validator-agent picks it
--    up. Position it next to its neighbours (exploit_attempt ->
--    exploit_pending_validation -> validation_pending) so SQL ORDER
--    BYs against the enum ordinal still read top-to-bottom.
-- ---------------------------------------------------------------------

ALTER TYPE finding_status
    ADD VALUE IF NOT EXISTS 'exploit_pending_validation' BEFORE 'validation_pending';
