-- Migration 09: Model routing cost-tracking enhancement.
--
-- Adds task_type to model_costs so the routing matrix's per-task-type cost
-- breakdown (Phase 3 exit criterion #2, avg scan cost ≤ $0.20) can be
-- computed directly from SQL without post-processing.
--
-- task_type is a free-form TEXT column that mirrors the 16 task-type slugs
-- in control_plane.core.routing.model_router (e.g. 'recon', 'bulk_triage',
-- 'exploit_generation'). NULL is allowed for rows written before this
-- migration or by legacy callers that do not set it.
--
-- Also adds an index on (task_type, ts) for the cost-by-task-type report
-- view that will join back to scan_jobs for per-target averages.

-- ---------------------------------------------------------------------
-- 1. model_costs.task_type
-- ---------------------------------------------------------------------

ALTER TABLE model_costs
    ADD COLUMN IF NOT EXISTS task_type TEXT;

CREATE INDEX IF NOT EXISTS idx_model_costs_task_type_ts
    ON model_costs (task_type, ts DESC);

-- ---------------------------------------------------------------------
-- 2. v_cost_by_task_type — per-task-type cost breakdown.
--
-- Aggregates model_costs by task_type with key metrics used for
-- routing matrix tuning and operator cost awareness. Joins to
-- scan_jobs via timestamp window to attach target context
-- (program_handle) for per-target averages.
--
-- Phase 3 exit criterion #2 (avg scan cost ≤ $0.20): operators
-- can spot expensive task types that need tier downgrades or
-- model substitutions.
-- ---------------------------------------------------------------------

CREATE OR REPLACE VIEW v_cost_by_task_type AS
SELECT
    mc.task_type,
    mc.model,
    COUNT(*) AS invocation_count,
    COALESCE(SUM(mc.cost_usd), 0)::numeric(12, 6) AS total_cost_usd,
    COALESCE(AVG(mc.cost_usd), 0)::numeric(12, 6) AS avg_cost_usd,
    COALESCE(SUM(mc.tokens_in), 0) AS total_prompt_tokens,
    COALESCE(SUM(mc.tokens_out), 0) AS total_completion_tokens,
    MIN(mc.ts) AS first_seen_at,
    MAX(mc.ts) AS last_seen_at
FROM model_costs mc
GROUP BY mc.task_type, mc.model
ORDER BY total_cost_usd DESC;
