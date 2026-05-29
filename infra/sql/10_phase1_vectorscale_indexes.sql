-- SPDX-License-Identifier: AGPL-3.0-or-later
-- Phase 1: DiskANN index on findings.embedding via the vectorscale extension.
-- Replaces HNSW when vector count exceeds ~500K (solo-mode threshold); the
-- existing HNSW index (01_schema.sql) coexists and stays primary until then.
-- Reference: research/01-strategy-architecture.md §Storage Architecture.
-- IMPORTANT: index method is 'diskann' (registered by the vectorscale extension).
--
-- NOTE (audit G6): plain CREATE INDEX, built atomically. This file runs at
-- first boot via /docker-entrypoint-initdb.d on an EMPTY table; a non-blocking
-- (concurrent) build buys nothing there, cannot run in the init single-tx
-- path, and — if interrupted — leaves an INVALID index that a later
-- IF NOT EXISTS silently skips, masking the failure permanently.

CREATE INDEX IF NOT EXISTS idx_findings_embedding_diskann
  ON findings
  USING diskann (embedding vector_cosine_ops)
  WITH (num_neighbors = 64, search_list_size = 100);
