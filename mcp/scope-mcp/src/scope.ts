// SPDX-License-Identifier: AGPL-3.0-or-later

// Target classification + scope-vs-target matching.
// All matching mirrors the build-plan §4.9 semantics (recursive wildcard,
// path exclusions, IPv4/IPv6 CIDR membership, ambiguous → requires_defer).

import { randomUUID } from "node:crypto";

import type { ScopeJwtClaims } from "./schemas.js";

export type TargetKind = "host" | "url" | "ipv4" | "ipv6" | "android" | "ios";

export interface ParsedTarget {
  kind: TargetKind;
  raw: string;
  host?: string;
  hostname?: string; // lowercased host without port
  pathname?: string; // for URLs
  ip?: string;
  packageId?: string; // android/ios
}

const ANDROID_PKG_RE = /^[a-zA-Z][a-zA-Z0-9_]*(\.[a-zA-Z][a-zA-Z0-9_]*)+$/;
const IPV4_RE = /^(\d{1,3}\.){3}\d{1,3}$/;
const HEX_RE = /^[0-9a-fA-F:]+$/;

function isIpv4(literal: string): boolean {
  if (!IPV4_RE.test(literal)) {
    return false;
  }
  return literal.split(".").every((part) => {
    const n = Number(part);
    return Number.isInteger(n) && n >= 0 && n <= 255;
  });
}

function looksLikeIpv6(literal: string): boolean {
  if (!literal.includes(":")) return false;
  if (!HEX_RE.test(literal)) return false;
  // very loose check — full validation happens in CIDR utilities
  return true;
}

export function parseTarget(target: string): ParsedTarget {
  const raw = target.trim();
  if (raw.length === 0) {
    throw new Error("target is empty");
  }
  // android package
  if (raw.startsWith("android:")) {
    const pkg = raw.slice("android:".length);
    return { kind: "android", raw, packageId: pkg };
  }
  if (raw.startsWith("ios:")) {
    const pkg = raw.slice("ios:".length);
    return { kind: "ios", raw, packageId: pkg };
  }
  if (raw.startsWith("http://") || raw.startsWith("https://")) {
    const url = new URL(raw);
    return {
      kind: "url",
      raw,
      host: url.host,
      hostname: url.hostname.toLowerCase(),
      pathname: url.pathname,
    };
  }
  if (isIpv4(raw)) {
    return { kind: "ipv4", raw, ip: raw };
  }
  if (looksLikeIpv6(raw)) {
    return { kind: "ipv6", raw, ip: raw };
  }
  if (ANDROID_PKG_RE.test(raw) && !raw.includes("/")) {
    // ambiguous: could be hostname (e.g., a.b.c) — treat as host but note ambiguity
    return { kind: "host", raw, hostname: raw.toLowerCase() };
  }
  // assume bare hostname
  return { kind: "host", raw, hostname: raw.toLowerCase() };
}

// ---------------------------------------------------------------------------
// Wildcard matching: `*.acme.com` matches foo.acme.com AND a.b.acme.com
// (recursive). Must NOT match acme.com itself.
// `*.api.acme.com` matches v1.api.acme.com but not api.acme.com.
// ---------------------------------------------------------------------------

export function wildcardMatch(pattern: string, hostname: string): boolean {
  const pat = pattern.toLowerCase();
  const host = hostname.toLowerCase();
  if (!pat.startsWith("*.")) {
    return pat === host;
  }
  const suffix = pat.slice(1); // ".acme.com"
  if (!host.endsWith(suffix)) return false;
  // disallow exact match against the bare apex (acme.com vs *.acme.com)
  if (host === suffix.slice(1)) return false;
  // there must be at least one label before the suffix
  const headLen = host.length - suffix.length;
  if (headLen <= 0) return false;
  return true;
}

// ---------------------------------------------------------------------------
// CIDR membership — IPv4 + IPv6, no external deps.
// ~30 LOC core logic per spec.
// ---------------------------------------------------------------------------

function ipv4ToInt(ip: string): bigint {
  const parts = ip.split(".").map(Number);
  if (parts.length !== 4 || parts.some((p) => !Number.isInteger(p) || p < 0 || p > 255)) {
    throw new Error(`invalid IPv4: ${ip}`);
  }
  return (
    (BigInt(parts[0]) << 24n) +
    (BigInt(parts[1]) << 16n) +
    (BigInt(parts[2]) << 8n) +
    BigInt(parts[3])
  );
}

function ipv6ToBigInt(ip: string): bigint {
  // Expand `::` and pad to 8 groups of 16 bits.
  let head: string[] = [];
  let tail: string[] = [];
  if (ip.includes("::")) {
    const [h, t] = ip.split("::", 2);
    head = h ? h.split(":") : [];
    tail = t ? t.split(":") : [];
  } else {
    head = ip.split(":");
  }
  const missing = 8 - (head.length + tail.length);
  if (missing < 0) throw new Error(`invalid IPv6: ${ip}`);
  const groups = [...head, ...Array<string>(missing).fill("0"), ...tail];
  let acc = 0n;
  for (const g of groups) {
    const val = parseInt(g.length === 0 ? "0" : g, 16);
    if (Number.isNaN(val) || val < 0 || val > 0xffff) {
      throw new Error(`invalid IPv6 group "${g}" in ${ip}`);
    }
    acc = (acc << 16n) | BigInt(val);
  }
  return acc;
}

export function ipInCidr(ip: string, cidr: string): boolean {
  const slash = cidr.indexOf("/");
  if (slash < 0) {
    return ip === cidr;
  }
  const network = cidr.slice(0, slash);
  const prefix = Number(cidr.slice(slash + 1));
  if (!Number.isInteger(prefix) || prefix < 0) return false;
  const isV6 = ip.includes(":") || network.includes(":");
  const totalBits = isV6 ? 128 : 32;
  if (prefix > totalBits) return false;
  const ipInt = isV6 ? ipv6ToBigInt(ip) : ipv4ToInt(ip);
  const netInt = isV6 ? ipv6ToBigInt(network) : ipv4ToInt(network);
  if (prefix === 0) return true;
  const mask = ((1n << BigInt(totalBits)) - 1n) ^ ((1n << BigInt(totalBits - prefix)) - 1n);
  return (ipInt & mask) === (netInt & mask);
}

// ---------------------------------------------------------------------------
// check_target — main eligibility decision.
// ---------------------------------------------------------------------------

export interface CheckTargetOutput {
  in_scope: boolean;
  exclusion_reason?: string;
  requires_defer: boolean;
  audit_id: string;
}

export function checkTargetAgainstClaims(
  target: string,
  claims: ScopeJwtClaims,
): CheckTargetOutput {
  const audit_id = randomUUID();
  let parsed: ParsedTarget;
  try {
    parsed = parseTarget(target);
  } catch (err) {
    return {
      in_scope: false,
      exclusion_reason: `unparseable target: ${(err as Error).message}`,
      requires_defer: true,
      audit_id,
    };
  }

  const { targets, exclusions } = claims;

  // 1. Path exclusion (URLs only — exclusions.paths)
  if (parsed.kind === "url" && parsed.pathname) {
    for (const blockedPath of exclusions.paths) {
      if (parsed.pathname.startsWith(blockedPath)) {
        return {
          in_scope: false,
          exclusion_reason: `path excluded: ${blockedPath}`,
          requires_defer: false,
          audit_id,
        };
      }
    }
  }

  // 2. Hostname exclusion (URLs + hosts)
  const hostname = parsed.hostname ?? "";
  if (hostname.length > 0) {
    for (const blockedHost of exclusions.hostnames) {
      if (blockedHost.toLowerCase() === hostname) {
        return {
          in_scope: false,
          exclusion_reason: `hostname excluded: ${blockedHost}`,
          requires_defer: false,
          audit_id,
        };
      }
    }
  }

  // 3. Positive scope checks
  switch (parsed.kind) {
    case "host":
    case "url": {
      if (!hostname) {
        return {
          in_scope: false,
          exclusion_reason: "host could not be determined",
          requires_defer: true,
          audit_id,
        };
      }
      if (targets.exact_hosts.some((h) => h.toLowerCase() === hostname)) {
        return { in_scope: true, requires_defer: false, audit_id };
      }
      if (targets.wildcards.some((w) => wildcardMatch(w, hostname))) {
        return { in_scope: true, requires_defer: false, audit_id };
      }
      return {
        in_scope: false,
        exclusion_reason: `hostname not covered by any wildcard or exact host: ${hostname}`,
        requires_defer: false,
        audit_id,
      };
    }
    case "ipv4":
    case "ipv6": {
      const ip = parsed.ip ?? parsed.raw;
      for (const cidr of targets.ips) {
        try {
          if (ipInCidr(ip, cidr)) {
            return { in_scope: true, requires_defer: false, audit_id };
          }
        } catch {
          // skip malformed cidr in scope, but flag for defer
          return {
            in_scope: false,
            exclusion_reason: `malformed scope CIDR: ${cidr}`,
            requires_defer: true,
            audit_id,
          };
        }
      }
      return {
        in_scope: false,
        exclusion_reason: `IP ${ip} not in any scope CIDR`,
        requires_defer: false,
        audit_id,
      };
    }
    case "android": {
      const pkg = parsed.packageId ?? "";
      if (targets.android_packages.includes(pkg)) {
        return { in_scope: true, requires_defer: false, audit_id };
      }
      return {
        in_scope: false,
        exclusion_reason: `android package not in scope: ${pkg}`,
        requires_defer: false,
        audit_id,
      };
    }
    case "ios": {
      const pkg = parsed.packageId ?? "";
      if (targets.ios_bundles.includes(pkg)) {
        return { in_scope: true, requires_defer: false, audit_id };
      }
      return {
        in_scope: false,
        exclusion_reason: `iOS bundle not in scope: ${pkg}`,
        requires_defer: false,
        audit_id,
      };
    }
    default: {
      return {
        in_scope: false,
        exclusion_reason: "ambiguous target kind",
        requires_defer: true,
        audit_id,
      };
    }
  }
}
