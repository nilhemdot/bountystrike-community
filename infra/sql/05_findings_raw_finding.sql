-- Migration 05: add findings.raw_finding JSONB column.
--
-- Discovered while running the Phase 2 W7-8 dry-run: the exploit-agent and
-- validator-agent specs reference ``findings.raw_finding`` (raw scanner /
-- recon output, plus exploit-agent's ``chain_steps``) but the column was
-- never added to ``01_schema.sql``. The scanner-agent spec also INSERTs
-- ``raw_finding`` directly. This migration closes that gap.
--
-- Idempotent: re-running is a no-op when the column already exists.

ALTER TABLE findings
    ADD COLUMN IF NOT EXISTS raw_finding JSONB DEFAULT '{}'::jsonb;

-- Hot path: orchestrator reads ``raw_finding->'chain_steps'`` after the
-- exploit-agent run. A small expression index keeps the lookup cheap when
-- the table grows; expression must match the operator the orchestrator
-- uses (``->`` returns jsonb, ``->>`` returns text).
CREATE INDEX IF NOT EXISTS idx_findings_chain_steps
    ON findings ((raw_finding -> 'chain_steps'))
    WHERE raw_finding ? 'chain_steps';
