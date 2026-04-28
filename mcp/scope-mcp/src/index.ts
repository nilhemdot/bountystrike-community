// scope-mcp — MCP server for scope enforcement (Phase 0c will implement 7 tools).
// This Phase 0a skeleton verifies the toolchain only.

import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";

const server = new McpServer({
  name: "scope-mcp",
  version: "0.1.0",
});

// Tools to implement in Phase 0c:
//   check_target, list_in_scope_assets, get_program_rules,
//   issue_scope_jwt, revoke_scope_jwt, get_scope_changes, rank_programs

async function main(): Promise<void> {
  const transport = new StdioServerTransport();
  await server.connect(transport);
  console.error("scope-mcp v0.1.0 running on stdio (skeleton — Phase 0c pending)");
}

main().catch((err) => {
  console.error("scope-mcp fatal:", err);
  process.exit(1);
});
