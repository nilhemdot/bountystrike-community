-- BountyStrike v5 — Core Schema
-- File: 01_schema.sql
-- Postgres 17 + pgvector. Single-DB-centric per research/01 §Storage Architecture.
--
-- Tables (11): programs, scopes, scope_changes, ev_score_history,
--              scan_jobs, findings, evidence_artifacts, audit_log,
--              agent_sessions, model_costs, report_submissions
--
-- ENUM: finding_status (research/03 §Finding Status ENUM)

-- ============================================================================
-- ENUMs
-- ============================================================================

DO $$ BEGIN
  CREATE TYPE finding_status AS ENUM (
    'hypothesis',
    'exploit_attempt',
    'exploit_candidate',
    'validation_pending',
    'validated',
    'dedup_check',
    'approval_pending_t1',
    'approval_pending_t2',
    'approval_pending_t3',
    'approved',
    'submitted',
    'confirmed',
    'rejected',
    'duplicate',
    'wont_fix',
    'archived'
  );
EXCEPTION
  WHEN duplicate_object THEN NULL;
END $$;

-- ============================================================================
-- programs — federated bounty program registry
-- (research/01 Tables list, research/02 §Scope Ingestion APIs)
-- ============================================================================

CREATE TABLE IF NOT EXISTS programs (
  handle                  TEXT PRIMARY KEY,
  platform                TEXT NOT NULL,
  name                    TEXT,
  last_modified_at        TIMESTAMPTZ,
  payout_min              NUMERIC(12, 2),
  payout_max              NUMERIC(12, 2),
  bounty_paid_ratio       NUMERIC(5, 4),
  triage_acceptance_rate  NUMERIC(5, 4),
  dup_rate                NUMERIC(5, 4),
  last_seen_at            TIMESTAMPTZ DEFAULT now(),
  raw                     JSONB
);

CREATE INDEX IF NOT EXISTS idx_programs_platform ON programs (platform);
CREATE INDEX IF NOT EXISTS idx_programs_last_modified ON programs (last_modified_at DESC);

-- ============================================================================
-- scopes — normalized assets per program (H1 org_assets-style)
-- (research/02 §HackerOne migration; identifier replaces asset_identifier)
-- ============================================================================

CREATE TABLE IF NOT EXISTS scopes (
  id                BIGSERIAL PRIMARY KEY,
  program_handle    TEXT NOT NULL REFERENCES programs(handle) ON DELETE CASCADE,
  asset_type        TEXT NOT NULL,
  identifier        TEXT NOT NULL,
  in_scope          BOOLEAN NOT NULL DEFAULT TRUE,
  exclusion_reason  TEXT,
  tags              TEXT[],
  updated_at        TIMESTAMPTZ DEFAULT now(),
  raw               JSONB,
  UNIQUE (program_handle, asset_type, identifier)
);

CREATE INDEX IF NOT EXISTS idx_scopes_program_handle ON scopes (program_handle);
CREATE INDEX IF NOT EXISTS idx_scopes_asset_type ON scopes (asset_type);
CREATE INDEX IF NOT EXISTS idx_scopes_in_scope ON scopes (in_scope) WHERE in_scope = TRUE;
-- pg_trgm GIN: wildcard/substring lookups on identifier (e.g., "*.acme.com")
CREATE INDEX IF NOT EXISTS idx_scopes_identifier_trgm ON scopes USING GIN (identifier gin_trgm_ops);

-- ============================================================================
-- scope_changes — change-event log (research/02 §Change-Event Architecture)
-- ============================================================================

CREATE TABLE IF NOT EXISTS scope_changes (
  id                BIGSERIAL PRIMARY KEY,
  event_type        TEXT NOT NULL,
  program_handle    TEXT,
  platform          TEXT,
  asset_identifier  TEXT,
  old_value         JSONB,
  new_value         JSONB,
  detected_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  source            TEXT
);

CREATE INDEX IF NOT EXISTS idx_scope_changes_program ON scope_changes (program_handle);
CREATE INDEX IF NOT EXISTS idx_scope_changes_detected_at ON scope_changes (detected_at DESC);
CREATE INDEX IF NOT EXISTS idx_scope_changes_event_type ON scope_changes (event_type);

-- ============================================================================
-- ev_score_history — EV time-series (research/02 §EV Formula + Weights)
-- ============================================================================

CREATE TABLE IF NOT EXISTS ev_score_history (
  id                     BIGSERIAL PRIMARY KEY,
  program_handle         TEXT NOT NULL,
  computed_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
  ev_score               NUMERIC(6, 4) NOT NULL,
  f_payout               NUMERIC(6, 4),
  f_saturation           NUMERIC(6, 4),
  f_ops                  NUMERIC(6, 4),
  f_fit                  NUMERIC(6, 4),
  f_cve                  NUMERIC(6, 4),
  weights_version        TEXT,
  computed_for_operator  TEXT
);

CREATE INDEX IF NOT EXISTS idx_ev_history_program_handle ON ev_score_history (program_handle);
CREATE INDEX IF NOT EXISTS idx_ev_history_computed_at ON ev_score_history (computed_at DESC);
CREATE INDEX IF NOT EXISTS idx_ev_history_ev_score ON ev_score_history (ev_score DESC);

-- ============================================================================
-- scan_jobs — orchestrated scan invocations (research/01 §Message Contracts)
-- ============================================================================

CREATE TABLE IF NOT EXISTS scan_jobs (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  program_handle    TEXT,
  platform          TEXT,
  scope_jwt_jti     TEXT,
  status            TEXT NOT NULL DEFAULT 'queued',
  operator_id       TEXT,
  cost_budget_usd   NUMERIC(10, 4),
  ev_score          NUMERIC(6, 4),
  started_at        TIMESTAMPTZ,
  completed_at      TIMESTAMPTZ,
  raw               JSONB
);

CREATE INDEX IF NOT EXISTS idx_scan_jobs_program_handle ON scan_jobs (program_handle);
CREATE INDEX IF NOT EXISTS idx_scan_jobs_status ON scan_jobs (status);
CREATE INDEX IF NOT EXISTS idx_scan_jobs_started_at ON scan_jobs (started_at DESC);
CREATE INDEX IF NOT EXISTS idx_scan_jobs_operator ON scan_jobs (operator_id);
CREATE INDEX IF NOT EXISTS idx_scan_jobs_jti ON scan_jobs (scope_jwt_jti);

-- ============================================================================
-- findings — vuln candidates / validated bugs (research/03 §Semantic Dedup)
-- Embedding: 1536-dim OpenAI text-embedding-3-large (cosine via <=>)
-- Structural fingerprint: UNIQUE (cwe, platform, program_handle, deduplication_key)
-- ============================================================================

CREATE TABLE IF NOT EXISTS findings (
  id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  job_id              UUID REFERENCES scan_jobs(id) ON DELETE SET NULL,
  program_handle      TEXT,
  platform            TEXT,
  cwe                 TEXT,
  url                 TEXT,
  parameter           TEXT,
  status              finding_status NOT NULL DEFAULT 'hypothesis',
  evidence_hash       TEXT,
  oracle_method       TEXT,
  validator_model     TEXT,
  deduplication_key   TEXT,
  embedding           vector(1536),
  created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT findings_structural_fingerprint
    UNIQUE (cwe, platform, program_handle, deduplication_key)
);

CREATE INDEX IF NOT EXISTS idx_findings_program_handle ON findings (program_handle);
CREATE INDEX IF NOT EXISTS idx_findings_status ON findings (status);
CREATE INDEX IF NOT EXISTS idx_findings_created_at ON findings (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_findings_job_id ON findings (job_id);
CREATE INDEX IF NOT EXISTS idx_findings_cwe ON findings (cwe);

-- HNSW vector index (research/00b-context7-extended.md — solo mode <500K vectors).
-- m=16, ef_construction=64 are pgvector defaults; tune at scale.
CREATE INDEX IF NOT EXISTS idx_findings_embedding_hnsw
  ON findings USING hnsw (embedding vector_cosine_ops)
  WITH (m = 16, ef_construction = 64);

-- ============================================================================
-- evidence_artifacts — content-addressable PoC blobs + hash chain link
-- (research/03 §Evidence Schema)
-- ============================================================================

CREATE TABLE IF NOT EXISTS evidence_artifacts (
  id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  finding_id           UUID NOT NULL REFERENCES findings(id) ON DELETE CASCADE,
  content_hash         TEXT NOT NULL,
  prev_audit_hash      TEXT,
  request_transcript   BYTEA,
  response_transcript  BYTEA,
  oracle_data          JSONB,
  reproduction_command TEXT,
  scope_token_jti      TEXT,
  sandbox_vm_id        TEXT,
  r2_key               TEXT,
  created_at           TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_evidence_finding_id ON evidence_artifacts (finding_id);
CREATE INDEX IF NOT EXISTS idx_evidence_content_hash ON evidence_artifacts (content_hash);
CREATE INDEX IF NOT EXISTS idx_evidence_created_at ON evidence_artifacts (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_evidence_scope_jti ON evidence_artifacts (scope_token_jti);

-- ============================================================================
-- audit_log — hash-chained tamper-evident log
-- (research/01 §Storage Architecture; full hash-chain trigger in Phase 1)
-- ============================================================================

CREATE TABLE IF NOT EXISTS audit_log (
  id         BIGSERIAL PRIMARY KEY,
  ts         TIMESTAMPTZ NOT NULL DEFAULT now(),
  actor      TEXT,
  action     TEXT,
  resource   TEXT,
  payload    JSONB,
  prev_hash  BYTEA,
  row_hash   BYTEA
);

CREATE INDEX IF NOT EXISTS idx_audit_log_ts ON audit_log (ts DESC);
CREATE INDEX IF NOT EXISTS idx_audit_log_actor ON audit_log (actor);
CREATE INDEX IF NOT EXISTS idx_audit_log_action ON audit_log (action);

-- TODO Phase 1: BEFORE INSERT trigger to compute row_hash = sha256(prev_hash || payload)
-- and enforce monotonic chain. Optional Sigstore Rekor anchoring of daily root hash.
-- Reference: research/01-strategy-architecture.md §Storage Architecture.

-- ============================================================================
-- agent_sessions — Claude Agent / Langfuse trace anchor
-- ============================================================================

CREATE TABLE IF NOT EXISTS agent_sessions (
  id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  agent_type          TEXT,
  model               TEXT,
  started_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
  ended_at            TIMESTAMPTZ,
  tokens_in           BIGINT DEFAULT 0,
  tokens_out          BIGINT DEFAULT 0,
  cost_usd            NUMERIC(12, 6) DEFAULT 0,
  langfuse_trace_id   TEXT
);

CREATE INDEX IF NOT EXISTS idx_agent_sessions_started_at ON agent_sessions (started_at DESC);
CREATE INDEX IF NOT EXISTS idx_agent_sessions_agent_type ON agent_sessions (agent_type);
CREATE INDEX IF NOT EXISTS idx_agent_sessions_model ON agent_sessions (model);
CREATE INDEX IF NOT EXISTS idx_agent_sessions_trace ON agent_sessions (langfuse_trace_id);

-- ============================================================================
-- model_costs — per-call cost ledger (research/02 §Cost Guardrails)
-- ============================================================================

CREATE TABLE IF NOT EXISTS model_costs (
  id                 BIGSERIAL PRIMARY KEY,
  ts                 TIMESTAMPTZ NOT NULL DEFAULT now(),
  agent_session_id   UUID REFERENCES agent_sessions(id) ON DELETE SET NULL,
  model              TEXT,
  tokens_in          INTEGER DEFAULT 0,
  tokens_out         INTEGER DEFAULT 0,
  cost_usd           NUMERIC(12, 6) DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_model_costs_ts ON model_costs (ts DESC);
CREATE INDEX IF NOT EXISTS idx_model_costs_session ON model_costs (agent_session_id);
CREATE INDEX IF NOT EXISTS idx_model_costs_model ON model_costs (model);

-- ============================================================================
-- report_submissions — platform submission tracking (T3 outbound)
-- ============================================================================

CREATE TABLE IF NOT EXISTS report_submissions (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  finding_id      UUID NOT NULL REFERENCES findings(id) ON DELETE CASCADE,
  platform        TEXT NOT NULL,
  submitted_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  submission_id   TEXT,
  status          TEXT,
  payout_usd      NUMERIC(12, 2),
  raw_response    JSONB
);

CREATE INDEX IF NOT EXISTS idx_report_finding_id ON report_submissions (finding_id);
CREATE INDEX IF NOT EXISTS idx_report_platform ON report_submissions (platform);
CREATE INDEX IF NOT EXISTS idx_report_submitted_at ON report_submissions (submitted_at DESC);
CREATE INDEX IF NOT EXISTS idx_report_status ON report_submissions (status);

-- ============================================================================
-- updated_at trigger for findings (auto-bump)
-- ============================================================================

CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_findings_updated_at ON findings;
CREATE TRIGGER trg_findings_updated_at
  BEFORE UPDATE ON findings
  FOR EACH ROW
  EXECUTE FUNCTION set_updated_at();
