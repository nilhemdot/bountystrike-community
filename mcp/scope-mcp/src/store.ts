// SPDX-License-Identifier: AGPL-3.0-or-later

// In-memory mock store for Phase 0c. Postgres-backed implementation lands in
// Phase 1; tables programs/scopes/scope_changes are defined in
// infra/sql/01_schema.sql.

import type {
  NormalizedScope,
  OperatorProfile,
  Platform,
  RankedProgram,
  ScopeChange,
} from "./schemas.js";

export interface ProgramRecord {
  handle: string;
  platform: Platform;
  name: string;
  rules_text: string;
  rules_last_updated: string; // ISO
  payout_min: number | null;
  payout_max: number | null;
  bounty_paid_ratio: number | null;
  triage_acceptance_rate: number | null;
  dup_rate: number | null;
  last_modified_at: string;
}

export interface ListAssetFilter {
  program_handle: string;
  platform: Platform;
  asset_types?: string[];
}

export interface ScopeChangesFilter {
  since: string; // ISO-8601
  program_handle?: string;
  include_platforms?: string[];
}

export interface RankProgramsArgs {
  operator_profile: OperatorProfile;
  min_ev_score?: number;
  platforms?: string[];
  require_bounty?: boolean;
  limit?: number;
}

export class ScopeStore {
  private readonly programs: Map<string, ProgramRecord> = new Map();
  private readonly scopes: NormalizedScope[] = [];
  private readonly scopeChanges: ScopeChange[] = [];

  upsertProgram(p: ProgramRecord): void {
    this.programs.set(p.handle, p);
  }

  addScope(s: NormalizedScope): void {
    this.scopes.push(s);
  }

  addScopeChange(c: ScopeChange): void {
    this.scopeChanges.push(c);
  }

  getProgramRules(
    handle: string,
    platform: string,
  ): { rules_text: string; last_updated: string } | undefined {
    const program = this.programs.get(handle);
    if (!program || program.platform !== platform) return undefined;
    return {
      rules_text: program.rules_text,
      last_updated: program.rules_last_updated,
    };
  }

  listInScopeAssets(filter: ListAssetFilter): NormalizedScope[] {
    return this.scopes.filter((s) => {
      if (s.program_handle !== filter.program_handle) return false;
      if (s.platform !== filter.platform) return false;
      if (!s.in_scope) return false;
      if (filter.asset_types && filter.asset_types.length > 0) {
        if (!filter.asset_types.includes(s.asset_type)) return false;
      }
      return true;
    });
  }

  getScopeChanges(filter: ScopeChangesFilter): ScopeChange[] {
    const sinceMs = Date.parse(filter.since);
    if (Number.isNaN(sinceMs)) {
      throw new Error(`invalid since timestamp: ${filter.since}`);
    }
    return this.scopeChanges.filter((c) => {
      if (Date.parse(c.detected_at) < sinceMs) return false;
      if (filter.program_handle && c.program_handle !== filter.program_handle) return false;
      if (
        filter.include_platforms &&
        filter.include_platforms.length > 0 &&
        !filter.include_platforms.includes(c.platform)
      ) {
        return false;
      }
      return true;
    });
  }

  /**
   * Placeholder ranker — Phase 1 swaps this for the EV engine in
   * docs/research/02-routing-ev.md §EV Formula. For now we approximate
   * `payout_max * (1 - dup_rate)` and apply naive operator filters.
   */
  rankPrograms(args: RankProgramsArgs): RankedProgram[] {
    const minEv = args.min_ev_score ?? 0;
    const platforms = new Set(args.platforms ?? []);
    const limit = args.limit ?? 50;

    const candidates: RankedProgram[] = [];
    let maxScore = 0;
    const interim: Array<{ score: number; record: ProgramRecord }> = [];

    for (const program of this.programs.values()) {
      if (platforms.size > 0 && !platforms.has(program.platform)) continue;
      const payoutMax = program.payout_max ?? 0;
      if (args.require_bounty && payoutMax <= 0) continue;
      if (args.operator_profile.min_payout_usd > payoutMax) continue;

      const dup = program.dup_rate ?? 0.5;
      const rawScore = payoutMax * (1 - dup);
      if (rawScore > maxScore) maxScore = rawScore;
      interim.push({ score: rawScore, record: program });
    }

    for (const { score, record } of interim) {
      const evScore = maxScore > 0 ? Math.min(score / maxScore, 1) : 0;
      if (evScore < minEv) continue;
      candidates.push({
        program_handle: record.handle,
        platform: record.platform,
        ev_score: Number(evScore.toFixed(4)),
        payout_min: record.payout_min,
        payout_max: record.payout_max,
        dup_rate: record.dup_rate,
        rationale: `placeholder = payout_max(${record.payout_max ?? 0}) * (1 - dup_rate(${
          record.dup_rate ?? 0.5
        }))`,
      });
    }
    candidates.sort((a, b) => b.ev_score - a.ev_score);
    return candidates.slice(0, limit);
  }
}

/**
 * Seed the store with a single sample program (acme-corp / hackerone) so the
 * tools return non-empty data during smoke tests. Real ingestion pipelines
 * land in Phase 1.
 */
export function createSeededStore(): ScopeStore {
  const store = new ScopeStore();
  const now = new Date().toISOString();
  store.upsertProgram({
    handle: "acme-corp",
    platform: "hackerone",
    name: "Acme Corp",
    rules_text:
      "No DoS. No social engineering. Test only assets listed below.",
    rules_last_updated: now,
    payout_min: 250,
    payout_max: 10000,
    bounty_paid_ratio: 0.85,
    triage_acceptance_rate: 0.71,
    dup_rate: 0.18,
    last_modified_at: now,
  });
  store.addScope({
    program_handle: "acme-corp",
    platform: "hackerone",
    asset_type: "url",
    identifier: "*.acme.com",
    in_scope: true,
    tags: ["primary"],
    updated_at: now,
  });
  store.addScope({
    program_handle: "acme-corp",
    platform: "hackerone",
    asset_type: "url",
    identifier: "legacy.acme.com",
    in_scope: true,
    tags: [],
    updated_at: now,
  });
  store.addScope({
    program_handle: "acme-corp",
    platform: "hackerone",
    asset_type: "cidr",
    identifier: "1.2.3.0/24",
    in_scope: true,
    tags: [],
    updated_at: now,
  });
  return store;
}
