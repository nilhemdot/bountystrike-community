// SPDX-License-Identifier: AGPL-3.0-or-later

// Wildcard / CIDR / exclusion semantics for check_target.

import { strict as assert } from "node:assert";
import { describe, it } from "node:test";

import {
  checkTargetAgainstClaims,
  ipInCidr,
  parseTarget,
  wildcardMatch,
} from "../src/scope.js";
import type { ScopeJwtClaims } from "../src/schemas.js";

const baseClaims: ScopeJwtClaims = {
  jti: "jwt_1700000000_0123456789abcdef",
  iss: "bountystrike-v5-control-plane",
  sub: "operator:alice",
  iat: 1700000000,
  exp: 1700100000,
  program_handle: "acme-corp",
  platform: "hackerone",
  targets: {
    wildcards: ["*.acme.com"],
    exact_hosts: ["legacy.acme.com"],
    ips: ["1.2.3.0/24", "2001:db8::/32"],
    android_packages: ["com.acme.app"],
    ios_bundles: [],
  },
  exclusions: {
    hostnames: ["staging-internal.acme.com"],
    paths: ["/admin", "/internal"],
    notes: "no DoS",
  },
  rate_limits: { default_rps: 5, relaxed_hosts: {} },
  engagement_id: "eng_1700000000_aaaaaaaaaaaaaaaa",
};

describe("wildcardMatch", () => {
  it("matches direct subdomain", () => {
    assert.equal(wildcardMatch("*.acme.com", "foo.acme.com"), true);
  });
  it("matches recursive subdomain (a.b.acme.com)", () => {
    assert.equal(wildcardMatch("*.acme.com", "a.b.acme.com"), true);
  });
  it("does NOT match the apex itself", () => {
    assert.equal(wildcardMatch("*.acme.com", "acme.com"), false);
  });
  it("rejects sibling domain", () => {
    assert.equal(wildcardMatch("*.acme.com", "fakeacme.com"), false);
  });
  it("matches deeper-prefixed wildcard", () => {
    assert.equal(wildcardMatch("*.api.acme.com", "v1.api.acme.com"), true);
    assert.equal(wildcardMatch("*.api.acme.com", "api.acme.com"), false);
  });
  it("non-wildcard requires exact match", () => {
    assert.equal(wildcardMatch("legacy.acme.com", "legacy.acme.com"), true);
    assert.equal(wildcardMatch("legacy.acme.com", "x.legacy.acme.com"), false);
  });
});

describe("ipInCidr", () => {
  it("IPv4 inside /24", () => {
    assert.equal(ipInCidr("1.2.3.50", "1.2.3.0/24"), true);
  });
  it("IPv4 outside /24", () => {
    assert.equal(ipInCidr("1.2.4.50", "1.2.3.0/24"), false);
  });
  it("IPv4 boundary ip == network", () => {
    assert.equal(ipInCidr("1.2.3.0", "1.2.3.0/24"), true);
    assert.equal(ipInCidr("1.2.3.255", "1.2.3.0/24"), true);
  });
  it("IPv4 /32 single host", () => {
    assert.equal(ipInCidr("8.8.8.8", "8.8.8.8/32"), true);
    assert.equal(ipInCidr("8.8.8.9", "8.8.8.8/32"), false);
  });
  it("IPv6 prefix membership", () => {
    assert.equal(ipInCidr("2001:db8::1", "2001:db8::/32"), true);
    assert.equal(ipInCidr("2001:db9::1", "2001:db8::/32"), false);
  });
});

describe("parseTarget", () => {
  it("classifies bare host", () => {
    assert.equal(parseTarget("foo.acme.com").kind, "host");
  });
  it("classifies URL", () => {
    const p = parseTarget("https://foo.acme.com/admin/login");
    assert.equal(p.kind, "url");
    assert.equal(p.hostname, "foo.acme.com");
    assert.equal(p.pathname, "/admin/login");
  });
  it("classifies ipv4", () => {
    assert.equal(parseTarget("1.2.3.50").kind, "ipv4");
  });
  it("classifies android", () => {
    const p = parseTarget("android:com.acme.app");
    assert.equal(p.kind, "android");
    assert.equal(p.packageId, "com.acme.app");
  });
});

describe("checkTargetAgainstClaims", () => {
  it("in-scope wildcard hostname", () => {
    const r = checkTargetAgainstClaims("foo.acme.com", baseClaims);
    assert.equal(r.in_scope, true);
    assert.equal(r.requires_defer, false);
    assert.match(r.audit_id, /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/);
  });

  it("in-scope exact host", () => {
    const r = checkTargetAgainstClaims("legacy.acme.com", baseClaims);
    assert.equal(r.in_scope, true);
  });

  it("apex with only wildcard scope is OUT (acme.com without *.acme.com match)", () => {
    const r = checkTargetAgainstClaims("acme.com", baseClaims);
    assert.equal(r.in_scope, false);
  });

  it("URL inside excluded path is rejected", () => {
    const r = checkTargetAgainstClaims(
      "https://foo.acme.com/admin/users",
      baseClaims,
    );
    assert.equal(r.in_scope, false);
    assert.match(r.exclusion_reason ?? "", /path excluded/);
  });

  it("host in exclusions list rejected", () => {
    const r = checkTargetAgainstClaims(
      "staging-internal.acme.com",
      baseClaims,
    );
    assert.equal(r.in_scope, false);
    assert.match(r.exclusion_reason ?? "", /hostname excluded/);
  });

  it("CIDR in-scope IP", () => {
    const r = checkTargetAgainstClaims("1.2.3.50", baseClaims);
    assert.equal(r.in_scope, true);
  });

  it("CIDR out-of-scope IP", () => {
    const r = checkTargetAgainstClaims("1.2.4.50", baseClaims);
    assert.equal(r.in_scope, false);
  });

  it("android package in-scope", () => {
    const r = checkTargetAgainstClaims("android:com.acme.app", baseClaims);
    assert.equal(r.in_scope, true);
  });

  it("URL inside wildcard but on excluded path returns out-of-scope, no defer", () => {
    const r = checkTargetAgainstClaims(
      "https://api.acme.com/internal/debug",
      baseClaims,
    );
    assert.equal(r.in_scope, false);
    assert.equal(r.requires_defer, false);
  });
});
