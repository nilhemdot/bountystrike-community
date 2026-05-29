-- Migration 08: Phase 3 oracle FP rate view + Grafana dashboard.
--
-- Phase 3 §10.5 exit criterion #4 says: "any oracle > 2% FP disabled".
-- The kill-switch watcher (scripts/kill_switch_watch.py) reads this view
-- every minute and trips Layer-3 HALT_SUBMISSIONS when any oracle's
-- 7-day FP rate breaches the threshold.
--
-- Oracle proxy: findings.cwe (eight active CWEs map 1:1 to the eight
-- field-validation suites in scripts/run_*_field_validation.py).
-- "FP" = explicit program rejection. Duplicates and informational
-- statuses are excluded so dedup misses don't pollute the gate.
--
-- Idempotent — only adds a view; safe to re-run.

CREATE OR REPLACE VIEW v_oracle_fp_rate AS
WITH windowed AS (
    SELECT
        f.cwe                                              AS cwe,
        rs.status                                          AS status,
        rs.submitted_at                                    AS submitted_at
    FROM report_submissions rs
    JOIN findings f ON f.id = rs.finding_id
    WHERE rs.submitted_at >= now() - INTERVAL '7 days'
      AND f.cwe IS NOT NULL
)
SELECT
    cwe,
    COUNT(*)                                               AS total_submitted,
    COUNT(*) FILTER (WHERE status = 'confirmed')           AS confirmed,
    COUNT(*) FILTER (WHERE status = 'rejected')            AS rejected,
    -- FP rate denominator excludes 'duplicate' and 'informational' so
    -- dedup misses + low-severity dispositions don't inflate the gate.
    COUNT(*) FILTER (
        WHERE status IN ('confirmed', 'rejected')
    )                                                      AS adjudicated,
    CASE
        WHEN COUNT(*) FILTER (WHERE status IN ('confirmed', 'rejected')) = 0
        THEN 0::float
        ELSE COUNT(*) FILTER (WHERE status = 'rejected')::float
             / COUNT(*) FILTER (WHERE status IN ('confirmed', 'rejected'))
    END                                                    AS fp_rate,
    -- 0.02 mirrors Phase 3 §10.5 #4. Hard-coded here so the view is
    -- self-documenting; the watcher reads the same constant from
    -- scripts/kill_switch_watch.py for consistency.
    CASE
        WHEN COUNT(*) FILTER (WHERE status IN ('confirmed', 'rejected')) = 0
        THEN FALSE
        ELSE COUNT(*) FILTER (WHERE status = 'rejected')::float
             / COUNT(*) FILTER (WHERE status IN ('confirmed', 'rejected')) > 0.02
    END                                                    AS exceeds_threshold
FROM windowed
GROUP BY cwe
ORDER BY fp_rate DESC;
