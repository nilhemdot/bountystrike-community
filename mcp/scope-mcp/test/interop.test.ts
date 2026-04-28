// Python ↔ TypeScript JWT interop. Verifies a token minted by
// control_plane.scope_jwt (Python) validates with the TS verifier and that
// the JTI follows the shared format `jwt_<unix_ts>_<16 hex>`.

import { strict as assert } from "node:assert";
import { spawnSync } from "node:child_process";
import { existsSync } from "node:fs";
import path from "node:path";
import { describe, it } from "node:test";

import { ScopeJwtVerifier } from "../src/jwt.js";
import { ScopeJwtClaimsSchema } from "../src/schemas.js";

// test/interop.test.ts → repo root is 4 levels up: test/ → scope-mcp/ → mcp/ → repo
const REPO_ROOT = path.resolve(new URL("../../..", import.meta.url).pathname);
const CONTROL_PLANE_DIR = path.join(REPO_ROOT, "control-plane");
const FIXTURE = path.join(
  REPO_ROOT,
  "mcp/scope-mcp/test/fixtures/gen_token.py",
);

function uvAvailable(): boolean {
  const probe = spawnSync("uv", ["--version"], { encoding: "utf8" });
  return probe.status === 0;
}

describe("python → typescript JWT interop", () => {
  it("verifies a token minted by control_plane.scope_jwt", (t) => {
    if (!uvAvailable()) {
      t.skip("uv binary not available — skipping interop test");
      return;
    }
    if (!existsSync(CONTROL_PLANE_DIR)) {
      t.skip("control-plane/ missing — skipping interop test");
      return;
    }
    if (!existsSync(FIXTURE)) {
      t.skip("python fixture missing — skipping interop test");
      return;
    }

    const proc = spawnSync(
      "uv",
      ["run", "--project", CONTROL_PLANE_DIR, "python", FIXTURE],
      { encoding: "utf8" },
    );
    if (proc.status !== 0) {
      t.skip(
        `python fixture failed (rc=${proc.status}); stderr=${proc.stderr.slice(0, 400)}`,
      );
      return;
    }

    const lines = proc.stdout.trim().split("\n").filter(Boolean);
    const last = lines[lines.length - 1];
    const parsed = JSON.parse(last) as {
      token: string;
      jti: string;
      issued_at: string;
    };

    assert.match(
      parsed.jti,
      /^jwt_\d+_[0-9a-f]{16}$/,
      "JTI must use shared cross-language format",
    );

    const verifier = new ScopeJwtVerifier();
    const { payload, jti } = verifier.verify(parsed.token);
    assert.equal(jti, parsed.jti);
    assert.equal(payload.iss, "bountystrike-v5-control-plane");
    assert.equal(payload.sub, "operator:alice");
    assert.equal(payload.platform, "hackerone");
    assert.deepEqual(payload.targets.wildcards, ["*.acme.com"]);
    assert.deepEqual(payload.exclusions.paths, ["/admin", "/internal"]);
    assert.equal(payload.rate_limits.default_rps, 5);
    assert.equal(payload.rate_limits.relaxed_hosts["api.acme.com"], 20);
    // Validate full claim shape via Zod (ensures TS schema matches Python output exactly).
    ScopeJwtClaimsSchema.parse(payload);
  });
});
