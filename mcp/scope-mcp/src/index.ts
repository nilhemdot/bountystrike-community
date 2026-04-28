// scope-mcp — BountyStrike v5 scope-enforcement MCP server (Phase 0c).
// Seven tools: check_target, list_in_scope_assets, get_program_rules,
// issue_scope_jwt, revoke_scope_jwt, get_scope_changes, rank_programs.
//
// JWT format mirrors control-plane/src/control_plane/scope_jwt.py exactly so
// tokens minted by either issuer validate on either side.

import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { ErrorCode, McpError } from "@modelcontextprotocol/sdk/types.js";

import { ScopeJwtIssuer, ScopeJwtVerifier } from "./jwt.js";
import {
  checkTargetAgainstClaims,
  type CheckTargetOutput,
} from "./scope.js";
import {
  CheckTargetResultSchema,
  IssueScopeJwtResultSchema,
  NormalizedScopeSchema,
  ProgramRulesResultSchema,
  RankedProgramSchema,
  RevokeScopeJwtResultSchema,
  ScopeChangeSchema,
  ScopeJwtClaimsSchema,
  checkTargetInput,
  getProgramRulesInput,
  getScopeChangesInput,
  issueScopeJwtInput,
  listInScopeAssetsInput,
  rankProgramsInput,
  revokeScopeJwtInput,
} from "./schemas.js";
import { createSeededStore, type ScopeStore } from "./store.js";
import { z } from "zod";

interface Deps {
  issuer: ScopeJwtIssuer;
  verifier: ScopeJwtVerifier;
  store: ScopeStore;
}

const TOOL_NAMES = [
  "check_target",
  "list_in_scope_assets",
  "get_program_rules",
  "issue_scope_jwt",
  "revoke_scope_jwt",
  "get_scope_changes",
  "rank_programs",
] as const;
export type ToolName = (typeof TOOL_NAMES)[number];

function jsonContent(value: unknown): {
  content: Array<{ type: "text"; text: string }>;
  structuredContent: Record<string, unknown>;
} {
  const structured =
    typeof value === "object" && value !== null && !Array.isArray(value)
      ? (value as Record<string, unknown>)
      : { value };
  return {
    content: [{ type: "text", text: JSON.stringify(value, null, 2) }],
    structuredContent: structured,
  };
}

function arrayContent<T>(items: T[]): {
  content: Array<{ type: "text"; text: string }>;
  structuredContent: { items: T[] };
} {
  return {
    content: [{ type: "text", text: JSON.stringify(items, null, 2) }],
    structuredContent: { items },
  };
}

export function buildServer(deps: Deps): McpServer {
  const server = new McpServer(
    { name: "scope-mcp", version: "0.1.0" },
    { capabilities: { tools: {} } },
  );

  // -------------------------------------------------------------------------
  // 1. check_target
  // -------------------------------------------------------------------------
  server.registerTool(
    "check_target",
    {
      title: "Check whether a target is in scope",
      description:
        "Validates a scope JWT and decides if the supplied target falls within its targets/exclusions. Returns audit_id (uuid v4) and requires_defer for ambiguous cases.",
      inputSchema: checkTargetInput,
      outputSchema: CheckTargetResultSchema.shape,
    },
    async (args) => {
      let claims;
      try {
        const { payload } = deps.verifier.verify(args.scope_jwt);
        claims = ScopeJwtClaimsSchema.parse(payload);
      } catch (err) {
        throw new McpError(
          ErrorCode.InvalidParams,
          `invalid scope_jwt: ${(err as Error).message}`,
        );
      }
      const result: CheckTargetOutput = checkTargetAgainstClaims(
        args.target,
        claims,
      );
      return jsonContent(result);
    },
  );

  // -------------------------------------------------------------------------
  // 2. list_in_scope_assets
  // -------------------------------------------------------------------------
  server.registerTool(
    "list_in_scope_assets",
    {
      title: "List in-scope assets for a program",
      description:
        "Returns NormalizedScope rows from the store, optionally filtered by asset_types.",
      inputSchema: listInScopeAssetsInput,
      outputSchema: { items: z.array(NormalizedScopeSchema) },
    },
    async (args) => {
      const items = deps.store.listInScopeAssets({
        program_handle: args.program_handle,
        platform: args.platform,
        asset_types: args.asset_types,
      });
      return arrayContent(items);
    },
  );

  // -------------------------------------------------------------------------
  // 3. get_program_rules
  // -------------------------------------------------------------------------
  server.registerTool(
    "get_program_rules",
    {
      title: "Fetch program rules text",
      description:
        "Returns rules_text + last_updated for a program. Errors when the program is not registered.",
      inputSchema: getProgramRulesInput,
      outputSchema: ProgramRulesResultSchema.shape,
    },
    async (args) => {
      const rules = deps.store.getProgramRules(
        args.program_handle,
        args.platform,
      );
      if (!rules) {
        throw new McpError(
          ErrorCode.InvalidParams,
          `program not found: ${args.program_handle} on ${args.platform}`,
        );
      }
      return jsonContent(rules);
    },
  );

  // -------------------------------------------------------------------------
  // 4. issue_scope_jwt
  // -------------------------------------------------------------------------
  server.registerTool(
    "issue_scope_jwt",
    {
      title: "Mint a scope JWT (RS256)",
      description:
        "Issues a short-lived (max 168h) RS256 JWT carrying program scope/exclusions. Targets/exclusions/rate_limits default to seeded program when omitted.",
      inputSchema: issueScopeJwtInput,
      outputSchema: IssueScopeJwtResultSchema.shape,
    },
    async (args) => {
      try {
        // Pull defaults from the seeded program if caller omitted targets.
        const seededAssets = deps.store.listInScopeAssets({
          program_handle: args.program_handle,
          platform: args.platform,
        });
        const wildcards: string[] = args.targets?.wildcards ?? [];
        const exact_hosts: string[] = args.targets?.exact_hosts ?? [];
        const ips: string[] = args.targets?.ips ?? [];
        if (
          wildcards.length === 0 &&
          exact_hosts.length === 0 &&
          ips.length === 0
        ) {
          for (const a of seededAssets) {
            if (a.asset_type === "url" && a.identifier.startsWith("*.")) {
              wildcards.push(a.identifier);
            } else if (a.asset_type === "url") {
              exact_hosts.push(a.identifier);
            } else if (a.asset_type === "cidr" || a.asset_type === "ip") {
              ips.push(a.identifier);
            }
          }
        }

        const result = deps.issuer.issue({
          operator_id: args.operator_id,
          program_handle: args.program_handle,
          platform: args.platform,
          expiry_hours: args.expiry_hours,
          targets: {
            wildcards,
            exact_hosts,
            ips,
            android_packages: args.targets?.android_packages ?? [],
            ios_bundles: args.targets?.ios_bundles ?? [],
          },
          exclusions: {
            hostnames: args.exclusions?.hostnames ?? [],
            paths: args.exclusions?.paths ?? [],
            notes: args.exclusions?.notes ?? "",
          },
          rate_limits: {
            default_rps: args.rate_limits?.default_rps ?? 5,
            relaxed_hosts: args.rate_limits?.relaxed_hosts ?? {},
          },
          engagement_id: args.engagement_id,
        });
        return jsonContent({
          jwt: result.token,
          jti: result.jti,
          issued_at: result.issued_at,
        });
      } catch (err) {
        throw new McpError(
          ErrorCode.InvalidParams,
          `issue_scope_jwt failed: ${(err as Error).message}`,
        );
      }
    },
  );

  // -------------------------------------------------------------------------
  // 5. revoke_scope_jwt
  // -------------------------------------------------------------------------
  server.registerTool(
    "revoke_scope_jwt",
    {
      title: "Revoke a scope JWT by jti",
      description:
        "Adds the jti to the in-memory revocation set. `revoked` is true on first-time revocation, false on subsequent calls.",
      inputSchema: revokeScopeJwtInput,
      outputSchema: RevokeScopeJwtResultSchema.shape,
    },
    async (args) => {
      const revoked = deps.verifier.revoke(args.jti);
      // Audit hook (Phase 1 will persist to audit_log table).
      console.error(
        `[scope-mcp] revoke jti=${args.jti} reason="${args.reason}" first_time=${revoked}`,
      );
      return jsonContent({ revoked });
    },
  );

  // -------------------------------------------------------------------------
  // 6. get_scope_changes
  // -------------------------------------------------------------------------
  server.registerTool(
    "get_scope_changes",
    {
      title: "List scope-change events since a timestamp",
      description:
        "Filters scope_changes by detected_at >= since, plus optional program_handle and include_platforms.",
      inputSchema: getScopeChangesInput,
      outputSchema: { items: z.array(ScopeChangeSchema) },
    },
    async (args) => {
      try {
        const items = deps.store.getScopeChanges({
          since: args.since,
          program_handle: args.program_handle,
          include_platforms: args.include_platforms,
        });
        return arrayContent(items);
      } catch (err) {
        throw new McpError(
          ErrorCode.InvalidParams,
          (err as Error).message,
        );
      }
    },
  );

  // -------------------------------------------------------------------------
  // 7. rank_programs
  // -------------------------------------------------------------------------
  server.registerTool(
    "rank_programs",
    {
      title: "Rank programs for an operator (placeholder EV)",
      description:
        "Placeholder ranking using payout_max * (1 - dup_rate) normalised to [0,1]. The full EV formula (research/02 §EV Formula) lands in Phase 1.",
      inputSchema: rankProgramsInput,
      outputSchema: { items: z.array(RankedProgramSchema) },
    },
    async (args) => {
      const items = deps.store.rankPrograms(args);
      return arrayContent(items);
    },
  );

  return server;
}

export const SCOPE_MCP_TOOLS: readonly ToolName[] = TOOL_NAMES;

async function main(): Promise<void> {
  const issuer = new ScopeJwtIssuer();
  const verifier = new ScopeJwtVerifier();
  const store = createSeededStore();
  const server = buildServer({ issuer, verifier, store });
  const transport = new StdioServerTransport();
  await server.connect(transport);
  console.error(
    `scope-mcp v0.1.0 ready (tools: ${SCOPE_MCP_TOOLS.join(", ")})`,
  );
}

const isMain = import.meta.url === `file://${process.argv[1]}`;
if (isMain) {
  main().catch((err) => {
    console.error("scope-mcp fatal:", err);
    process.exit(1);
  });
}
