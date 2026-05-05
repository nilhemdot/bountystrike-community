-- Migration 07: Phase 3 calibration + alpha-hunter ops scaffolding.
--
-- Phase 3 (build-plan §10.5) gates on five real-world metrics that each
-- need a place to land:
--
--   1. confirmed-rate ≥ 70%        — needs report_submissions × findings join
--   2. avg scan cost  ≤ $0.20      — needs model_costs × scan_jobs aggregation
--   3. time-to-validate < 4h P1/P2 — needs findings.validated_at + severity
--   4. EV rank correlation ρ ≥ 0.6 — needs hunt_outcomes
--   5. dedup recall ≥ 95%          — handled in test harness, not schema
--
-- This migration adds:
--   * findings.validated_at (TIMESTAMPTZ, auto-stamped by trigger)
--   * findings.severity     (TEXT, P1-P4|info, NULL allowed)
--   * operators table       (alpha-hunter registry)
--   * hunt_outcomes table   (one row per (program, operator, scan_job))
--   * three SQL views       (v_confirmed_rate_weekly, v_scan_cost_by_job,
--                            v_ttv_stats)
--
-- Idempotent: every change uses IF NOT EXISTS / OR REPLACE so re-running
-- the migration is a no-op.

-- ---------------------------------------------------------------------
-- 1. findings.validated_at + severity
--
-- validated_at is auto-stamped by trigger (see step 1b) when status
-- transitions to 'validated' — keeps the validator-agent spec frozen.
-- severity is operator-set; views filter on it so NULL rows are skipped
-- gracefully until the alpha-hunter workflow populates it.
-- ---------------------------------------------------------------------

ALTER TABLE findings
    ADD COLUMN IF NOT EXISTS validated_at TIMESTAMPTZ;

ALTER TABLE findings
    ADD COLUMN IF NOT EXISTS severity TEXT
        CHECK (severity IS NULL OR severity IN ('P1', 'P2', 'P3', 'P4', 'info'));

CREATE INDEX IF NOT EXISTS idx_findings_validated_at
    ON findings (validated_at DESC) WHERE validated_at IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_findings_severity
    ON findings (severity) WHERE severity IS NOT NULL;

-- 1b. Trigger: stamp validated_at on status → 'validated'.
--     Idempotent: trigger uses CREATE OR REPLACE FUNCTION + DROP/CREATE TRIGGER.

CREATE OR REPLACE FUNCTION stamp_validated_at()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.status = 'validated' AND (OLD.status IS DISTINCT FROM 'validated')
       AND NEW.validated_at IS NULL THEN
        NEW.validated_at = now();
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_findings_validated_at ON findings;
CREATE TRIGGER trg_findings_validated_at
    BEFORE UPDATE ON findings
    FOR EACH ROW
    EXECUTE FUNCTION stamp_validated_at();

-- ---------------------------------------------------------------------
-- 2. operators — alpha-hunter registry.
--
-- id is a free-form TEXT slug (e.g. "alice", "bob-h1") used by
-- scan_jobs.operator_id and ev_score_history.computed_for_operator.
-- skill_vector is opaque JSONB consumed by EV scoring's OperatorProfile.
-- ---------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS operators (
    id            TEXT PRIMARY KEY,
    display_name  TEXT,
    skill_vector  JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------
-- 3. hunt_outcomes — per-(program, operator, scan_job) summary.
--
-- Populated by scripts/reconcile_hunt_outcomes.py from report_submissions.
-- ev_rank is the rank of the program in the EV-ranked list at scan time
-- (1 = top-ranked). Used to compute Spearman ρ vs find-rate.
-- ---------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS hunt_outcomes (
    id               BIGSERIAL PRIMARY KEY,
    program_handle   TEXT NOT NULL,
    operator_id      TEXT NOT NULL REFERENCES operators(id) ON DELETE CASCADE,
    scan_job_id      UUID REFERENCES scan_jobs(id) ON DELETE SET NULL,
    ev_rank          INTEGER,
    submitted_count  INTEGER NOT NULL DEFAULT 0,
    confirmed_count  INTEGER NOT NULL DEFAULT 0,
    period_start     TIMESTAMPTZ,
    period_end       TIMESTAMPTZ,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (program_handle, operator_id, scan_job_id)
);

CREATE INDEX IF NOT EXISTS idx_hunt_outcomes_operator
    ON hunt_outcomes (operator_id);
CREATE INDEX IF NOT EXISTS idx_hunt_outcomes_program
    ON hunt_outcomes (program_handle);
CREATE INDEX IF NOT EXISTS idx_hunt_outcomes_ev_rank
    ON hunt_outcomes (ev_rank) WHERE ev_rank IS NOT NULL;

-- ---------------------------------------------------------------------
-- 4. v_confirmed_rate_weekly — weekly confirmed/total ratio.
--
-- Phase 3 exit criterion #1 (≥ 70%). Bucketed by ISO week of
-- finding.created_at so a given finding lands in the week it was first
-- emitted, not when its program responded.
-- ---------------------------------------------------------------------

CREATE OR REPLACE VIEW v_confirmed_rate_weekly AS
SELECT
    date_trunc('week', f.created_at) AS week,
    COUNT(*) FILTER (WHERE rs.status = 'confirmed')::float
        / NULLIF(COUNT(*), 0) AS confirmed_rate,
    COUNT(*) AS total_submitted,
    COUNT(*) FILTER (WHERE rs.status = 'confirmed') AS confirmed
FROM report_submissions rs
JOIN findings f ON f.id = rs.finding_id
GROUP BY 1
ORDER BY 1 DESC;

-- ---------------------------------------------------------------------
-- 5. v_scan_cost_by_job — total LLM spend per scan_job.
--
-- Phase 3 exit criterion #2 (avg < $0.20). Joins model_costs to
-- scan_jobs via timestamp window since model_costs has no direct
-- scan_job_id FK. Conservative: includes any model_costs row whose
-- timestamp falls between started_at and completed_at.
-- ---------------------------------------------------------------------

CREATE OR REPLACE VIEW v_scan_cost_by_job AS
SELECT
    sj.id AS scan_job_id,
    sj.program_handle,
    sj.operator_id,
    sj.started_at,
    sj.completed_at,
    COALESCE(SUM(mc.cost_usd), 0)::numeric(12, 6) AS total_cost_usd,
    COALESCE(SUM(mc.cost_usd), 0) > 0.20 AS exceeds_budget,
    COUNT(DISTINCT mc.model) AS models_used
FROM scan_jobs sj
LEFT JOIN model_costs mc
    ON mc.ts >= sj.started_at
   AND mc.ts <= COALESCE(sj.completed_at, now())
GROUP BY sj.id, sj.program_handle, sj.operator_id, sj.started_at, sj.completed_at;

-- ---------------------------------------------------------------------
-- 6. v_ttv_stats — time-to-validate stats per severity.
--
-- Phase 3 exit criterion #3 (< 4h P1/P2). Uses validated_at - created_at
-- as the SLA clock. Filtered to P1/P2 since exit criterion only gates on
-- those tiers.
-- ---------------------------------------------------------------------

CREATE OR REPLACE VIEW v_ttv_stats AS
SELECT
    severity,
    percentile_cont(0.50) WITHIN GROUP (
        ORDER BY EXTRACT(EPOCH FROM (validated_at - created_at)) / 3600.0
    ) AS median_ttv_hours,
    percentile_cont(0.90) WITHIN GROUP (
        ORDER BY EXTRACT(EPOCH FROM (validated_at - created_at)) / 3600.0
    ) AS p90_ttv_hours,
    COUNT(*) FILTER (
        WHERE EXTRACT(EPOCH FROM (validated_at - created_at)) / 3600.0 > 4
    ) AS sla_breach_count,
    COUNT(*) AS total
FROM findings
WHERE validated_at IS NOT NULL
  AND severity IN ('P1', 'P2')
GROUP BY severity;
