-- BountyStrike v5 — Postgres Extensions
-- File: 00_extensions.sql
-- Runs first via /docker-entrypoint-initdb.d alphabetic ordering.
--
-- Required extensions for Phase 0b:
--   vector    — pgvector for 1536-dim OpenAI text-embedding-3-large semantic dedup
--               (research/03-verifier-antislop.md §Semantic Dedup)
--   pg_trgm   — trigram GIN index on scopes.identifier for wildcard/substring lookup
--   pgcrypto  — gen_random_uuid() for scan_jobs.id, findings.id, evidence_artifacts.id

CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- Phase 1 extensions (activated — custom bs-postgres:pg17 image required):
--   vectorscale — Timescale DiskANN vector index. NOTE: the extension is named
--                 'vectorscale' (CLAUDE.md trap #17); CASCADE pulls in vector.
--   pg_search   — ParadeDB BM25 keyword/hybrid search (CREATE INDEX ... USING bm25).
-- See research/00b-context7-extended.md and research/01-strategy-architecture.md §Storage Architecture.
CREATE EXTENSION IF NOT EXISTS vectorscale CASCADE;  -- DiskANN vector index
CREATE EXTENSION IF NOT EXISTS pg_search;            -- ParadeDB BM25 hybrid search
