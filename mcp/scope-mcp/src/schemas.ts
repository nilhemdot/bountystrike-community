// Zod schemas + TypeScript types shared between MCP boundary and internals.
// Mirrors control-plane/scope_jwt.py claim shape exactly.

import { z } from "zod";

export const PLATFORMS = [
  "hackerone",
  "bugcrowd",
  "intigriti",
  "yeswehack",
  "immunefi",
] as const;

export const PlatformSchema = z.enum(PLATFORMS);
export type Platform = z.infer<typeof PlatformSchema>;

// ---------------------------------------------------------------------------
// Scope JWT claims (must match Python issuer byte-for-byte)
// ---------------------------------------------------------------------------

export const ScopeTargetsSchema = z.object({
  wildcards: z.array(z.string()),
  exact_hosts: z.array(z.string()),
  ips: z.array(z.string()),
  android_packages: z.array(z.string()),
  ios_bundles: z.array(z.string()),
});
export type ScopeTargetsT = z.infer<typeof ScopeTargetsSchema>;

export const ScopeExclusionsSchema = z.object({
  hostnames: z.array(z.string()),
  paths: z.array(z.string()),
  notes: z.string(),
});
export type ScopeExclusionsT = z.infer<typeof ScopeExclusionsSchema>;

export const RateLimitsSchema = z.object({
  default_rps: z.number().int().nonnegative(),
  relaxed_hosts: z.record(z.string(), z.number().int().nonnegative()),
});
export type RateLimitsT = z.infer<typeof RateLimitsSchema>;

export const ScopeJwtClaimsSchema = z.object({
  jti: z.string().regex(/^jwt_\d+_[0-9a-f]{16}$/),
  iss: z.literal("bountystrike-v5-control-plane"),
  sub: z.string().startsWith("operator:"),
  iat: z.number().int(),
  exp: z.number().int(),
  program_handle: z.string().min(1),
  platform: PlatformSchema,
  targets: ScopeTargetsSchema,
  exclusions: ScopeExclusionsSchema,
  rate_limits: RateLimitsSchema,
  engagement_id: z.string().min(1),
});
export type ScopeJwtClaims = z.infer<typeof ScopeJwtClaimsSchema>;

// ---------------------------------------------------------------------------
// Domain types referenced by MCP tools
// ---------------------------------------------------------------------------

export const NormalizedScopeSchema = z.object({
  program_handle: z.string(),
  platform: PlatformSchema,
  asset_type: z.string(),
  identifier: z.string(),
  in_scope: z.boolean(),
  exclusion_reason: z.string().optional(),
  tags: z.array(z.string()).default([]),
  updated_at: z.string(),
});
export type NormalizedScope = z.infer<typeof NormalizedScopeSchema>;

export const ScopeChangeSchema = z.object({
  event_type: z.enum([
    "scope_added",
    "scope_removed",
    "payout_changed",
    "program_paused",
  ]),
  program_handle: z.string(),
  platform: z.string(),
  asset_identifier: z.string().optional(),
  old_value: z.unknown().optional(),
  new_value: z.unknown().optional(),
  detected_at: z.string(),
  source: z.enum(["arkadiyt", "rix4uni", "h1_org_assets", "bbscope"]),
});
export type ScopeChange = z.infer<typeof ScopeChangeSchema>;

export const OperatorProfileSchema = z.object({
  operator_id: z.string().min(1),
  skill_tags: z.array(z.string()).default([]),
  preferred_platforms: z.array(PlatformSchema).default([]),
  min_payout_usd: z.number().nonnegative().default(0),
});
export type OperatorProfile = z.infer<typeof OperatorProfileSchema>;

export const RankedProgramSchema = z.object({
  program_handle: z.string(),
  platform: PlatformSchema,
  ev_score: z.number().min(0).max(1),
  payout_min: z.number().nullable(),
  payout_max: z.number().nullable(),
  dup_rate: z.number().min(0).max(1).nullable(),
  rationale: z.string(),
});
export type RankedProgram = z.infer<typeof RankedProgramSchema>;

// ---------------------------------------------------------------------------
// Tool input shapes (Zod raw shapes for McpServer.registerTool)
// ---------------------------------------------------------------------------

export const checkTargetInput = {
  target: z.string().min(1),
  scope_jwt: z.string().min(1),
  tool_context: z.string().optional(),
};

export const listInScopeAssetsInput = {
  program_handle: z.string().min(1),
  platform: PlatformSchema,
  asset_types: z.array(z.string()).optional(),
};

export const getProgramRulesInput = {
  program_handle: z.string().min(1),
  platform: z.string().min(1),
};

export const issueScopeJwtInput = {
  program_handle: z.string().min(1),
  platform: PlatformSchema,
  operator_id: z.string().min(1),
  expiry_hours: z.number().int().positive().max(168),
  targets: ScopeTargetsSchema.partial().optional(),
  exclusions: ScopeExclusionsSchema.partial().optional(),
  rate_limits: RateLimitsSchema.partial().optional(),
  engagement_id: z.string().optional(),
};

export const revokeScopeJwtInput = {
  jti: z.string().regex(/^jwt_\d+_[0-9a-f]{16}$/),
  reason: z.string().min(1),
};

export const getScopeChangesInput = {
  since: z.string().min(1), // ISO-8601 timestamp
  program_handle: z.string().optional(),
  include_platforms: z.array(z.string()).optional(),
};

export const rankProgramsInput = {
  operator_profile: OperatorProfileSchema,
  min_ev_score: z.number().min(0).max(1).optional(),
  platforms: z.array(PlatformSchema).optional(),
  require_bounty: z.boolean().optional(),
  limit: z.number().int().positive().max(500).optional(),
};

// ---------------------------------------------------------------------------
// Tool output shapes
// ---------------------------------------------------------------------------

export const CheckTargetResultSchema = z.object({
  in_scope: z.boolean(),
  exclusion_reason: z.string().optional(),
  requires_defer: z.boolean(),
  audit_id: z.string().uuid(),
});
export type CheckTargetResult = z.infer<typeof CheckTargetResultSchema>;

export const IssueScopeJwtResultSchema = z.object({
  jwt: z.string(),
  jti: z.string(),
  issued_at: z.string(),
});
export type IssueScopeJwtResult = z.infer<typeof IssueScopeJwtResultSchema>;

export const RevokeScopeJwtResultSchema = z.object({
  revoked: z.boolean(),
});
export type RevokeScopeJwtResult = z.infer<typeof RevokeScopeJwtResultSchema>;

export const ProgramRulesResultSchema = z.object({
  rules_text: z.string(),
  last_updated: z.string(),
});
export type ProgramRulesResult = z.infer<typeof ProgramRulesResultSchema>;
