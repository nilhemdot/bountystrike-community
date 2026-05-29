-- SPDX-License-Identifier: AGPL-3.0-or-later
-- Phase 1: BM25 index on findings via ParadeDB pg_search (CURRENT API).
-- Enables hybrid keyword + vector search for triage ranking.
-- Reference: Context7 /paradedb/paradedb §Create a Basic BM25 Index.
--
-- NOTE (audit G2): uses the CURRENT `CREATE INDEX ... USING bm25` API, NOT the
-- deprecated legacy function-call API (removed in modern ParadeDB).
-- Maintainers: "Avoid legacy docs — syntax changed dramatically."
--
-- NOTE (audit G1): the findings table exposes no rich-text columns (schema
-- frozen). We index the existing text columns meaningful for keyword triage:
-- id, url, parameter, cwe, oracle_method. key_field MUST be the primary key (id).
--
-- Requires `shared_preload_libraries = 'pg_search'` at server start (set in
-- docker-compose.yml postgres command) — the BM25 index AM is unavailable
-- otherwise. IF NOT EXISTS provides idempotency directly.

CREATE INDEX IF NOT EXISTS idx_findings_bm25
  ON findings
  USING bm25 (id, url, parameter, cwe, oracle_method)
  WITH (key_field = 'id');
