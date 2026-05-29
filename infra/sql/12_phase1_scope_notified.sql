-- SPDX-License-Identifier: AGPL-3.0-or-later
-- Phase 1: scope-change notification delivery marker (plan 01-05).
-- Adds a per-row delivery high-water mark so the notification service can
-- select undelivered scope_changes, POST them to the operator webhook, and
-- mark them delivered. Closes the 01-04 gap (diff events are persisted but
-- never leave the DB).
--
-- ADDITIVE ONLY: 01_schema.sql is phase-locked. This migration ALTERs in place.
--
-- NOTE (audit M1 / AC-6): go-forward-only. 01-04 already seeded the table
-- (~4104 rows from the first projectdiscovery poll) BEFORE this column existed.
-- A NULL notified_at means "not yet delivered", so after ADD COLUMN every
-- historical row would be NULL and the first delivery run would retro-flood the
-- webhook with thousands of stale changes. We BACKFILL those rows as
-- already-delivered (notified_at = now()) so only events detected AFTER the
-- feature ships are ever sent. The backfill is naturally idempotent on re-apply
-- (no NULLs remain -> 0 rows updated).
--
-- NOTE (audit / 01-01 doctrine): plain CREATE INDEX, no CONCURRENTLY — this
-- runs in the first-boot init path; IF NOT EXISTS provides idempotency.

ALTER TABLE scope_changes
  ADD COLUMN IF NOT EXISTS notified_at TIMESTAMPTZ;

-- Backfill pre-existing rows as already-delivered (go-forward-only, M1/AC-6).
UPDATE scope_changes SET notified_at = now() WHERE notified_at IS NULL;

-- Hot read path: the notification service only ever scans undelivered rows.
CREATE INDEX IF NOT EXISTS idx_scope_changes_undelivered
  ON scope_changes (id)
  WHERE notified_at IS NULL;
