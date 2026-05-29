// SPDX-License-Identifier: AGPL-3.0-or-later

// JWT roundtrip + edge cases.

import { strict as assert } from "node:assert";
import { readFileSync } from "node:fs";
import path from "node:path";
import { describe, it } from "node:test";
import jwt from "jsonwebtoken";

import {
  ALGORITHM,
  MAX_EXPIRY_SECONDS,
  ScopeJwtIssuer,
  ScopeJwtVerifier,
} from "../src/jwt.js";
import type { ScopeTargets } from "../src/jwt.js";

const sampleTargets: ScopeTargets = {
  wildcards: ["*.acme.com"],
  exact_hosts: ["legacy.acme.com"],
  ips: ["1.2.3.0/24"],
  android_packages: [],
  ios_bundles: [],
};

function makeIssuerVerifier(): { issuer: ScopeJwtIssuer; verifier: ScopeJwtVerifier } {
  return {
    issuer: new ScopeJwtIssuer(),
    verifier: new ScopeJwtVerifier(),
  };
}

describe("ScopeJwtIssuer + Verifier", () => {
  it("roundtrips a freshly minted token", () => {
    const { issuer, verifier } = makeIssuerVerifier();
    const { token, jti, issued_at } = issuer.issue({
      operator_id: "alice",
      program_handle: "acme-corp",
      platform: "hackerone",
      targets: sampleTargets,
      expiry_hours: 24,
    });
    assert.match(jti, /^jwt_\d+_[0-9a-f]{16}$/);
    assert.ok(issued_at.endsWith("Z"));
    const { payload } = verifier.verify(token);
    assert.equal(payload.iss, "bountystrike-v5-control-plane");
    assert.equal(payload.sub, "operator:alice");
    assert.equal(payload.program_handle, "acme-corp");
    assert.equal(payload.platform, "hackerone");
    assert.deepEqual(payload.targets.wildcards, ["*.acme.com"]);
    assert.equal(payload.jti, jti);
  });

  it("accepts maximum expiry (168h)", () => {
    const { issuer, verifier } = makeIssuerVerifier();
    const { token, jti } = issuer.issue({
      operator_id: "alice",
      program_handle: "acme-corp",
      platform: "hackerone",
      targets: sampleTargets,
      expiry_hours: 168,
    });
    const { payload } = verifier.verify(token);
    const lifespan = payload.exp - payload.iat;
    assert.equal(lifespan, MAX_EXPIRY_SECONDS);
    assert.equal(payload.jti, jti);
  });

  it("rejects expiry > 168h", () => {
    const { issuer } = makeIssuerVerifier();
    assert.throws(
      () =>
        issuer.issue({
          operator_id: "alice",
          program_handle: "acme-corp",
          platform: "hackerone",
          targets: sampleTargets,
          expiry_hours: 169,
        }),
      /exceeds max 168/,
    );
  });

  it("rejects revoked jti", () => {
    const { issuer, verifier } = makeIssuerVerifier();
    const { token, jti } = issuer.issue({
      operator_id: "alice",
      program_handle: "acme-corp",
      platform: "hackerone",
      targets: sampleTargets,
      expiry_hours: 1,
    });
    assert.equal(verifier.revoke(jti), true);
    assert.equal(verifier.revoke(jti), false); // idempotent — second time already revoked
    assert.throws(() => verifier.verify(token), /revoked/);
  });

  it("rejects tampered tokens", () => {
    const { issuer, verifier } = makeIssuerVerifier();
    const { token } = issuer.issue({
      operator_id: "alice",
      program_handle: "acme-corp",
      platform: "hackerone",
      targets: sampleTargets,
      expiry_hours: 1,
    });
    // Flip a single character in the signature segment.
    const segments = token.split(".");
    assert.equal(segments.length, 3);
    const sig = segments[2];
    const flipped = sig.startsWith("A") ? `B${sig.slice(1)}` : `A${sig.slice(1)}`;
    const tampered = [segments[0], segments[1], flipped].join(".");
    assert.throws(() => verifier.verify(tampered));
  });

  it("rejects expired tokens", () => {
    // Sign a manual payload with exp in the past using the same private key.
    const { verifier } = makeIssuerVerifier();
    const repoRoot = path.resolve(new URL("../../..", import.meta.url).pathname);
    const privateKey = readFileSync(
      path.join(repoRoot, "keys", "scope_jwt_private.pem"),
    );
    const past = Math.floor(Date.now() / 1000) - 3600;
    const expiredToken = jwt.sign(
      {
        jti: `jwt_${past}_0123456789abcdef`,
        iss: "bountystrike-v5-control-plane",
        sub: "operator:alice",
        iat: past - 60,
        exp: past,
        program_handle: "acme-corp",
        platform: "hackerone",
        targets: sampleTargets,
        exclusions: { hostnames: [], paths: [], notes: "" },
        rate_limits: { default_rps: 5, relaxed_hosts: {} },
        engagement_id: `eng_${past}_deadbeefdeadbeef`,
      },
      privateKey,
      { algorithm: ALGORITHM },
    );
    assert.throws(() => verifier.verify(expiredToken), /jwt expired/);
  });

  it("rejects non-RS256 algorithm", () => {
    const { verifier } = makeIssuerVerifier();
    const hsToken = jwt.sign({ foo: 1 }, "shared-secret", { algorithm: "HS256" });
    assert.throws(() => verifier.verify(hsToken));
  });
});
