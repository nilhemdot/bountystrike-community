// RS256 scope-JWT issuer + verifier — TypeScript mirror of
// control-plane/src/control_plane/scope_jwt.py. Claim shape is identical so
// tokens minted by either side validate on the other.

import { randomBytes } from "node:crypto";
import { readFileSync } from "node:fs";
import path from "node:path";
import jwt, {
  type Algorithm,
  type JwtPayload,
  type SignOptions,
  type VerifyOptions,
} from "jsonwebtoken";

import type { Platform, ScopeJwtClaims } from "./schemas.js";

export const ISSUER = "bountystrike-v5-control-plane";
export const ALGORITHM: Algorithm = "RS256";
export const MAX_EXPIRY_SECONDS = 168 * 3600; // 168h hard cap per build plan §4.9
export const DEFAULT_EXPIRY_SECONDS = 24 * 3600;

const REPO_ROOT = path.resolve(new URL("../../..", import.meta.url).pathname);
const DEFAULT_PRIVATE_KEY = path.join(REPO_ROOT, "keys", "scope_jwt_private.pem");
const DEFAULT_PUBLIC_KEY = path.join(REPO_ROOT, "keys", "scope_jwt_public.pem");

export interface ScopeTargets {
  wildcards: string[];
  exact_hosts: string[];
  ips: string[];
  android_packages: string[];
  ios_bundles: string[];
}

export interface ScopeExclusions {
  hostnames: string[];
  paths: string[];
  notes: string;
}

export interface RateLimits {
  default_rps: number;
  relaxed_hosts: Record<string, number>;
}

export interface IssueArgs {
  operator_id: string;
  program_handle: string;
  platform: Platform;
  targets: ScopeTargets;
  exclusions?: ScopeExclusions;
  rate_limits?: RateLimits;
  expiry_hours?: number; // <= 168
  engagement_id?: string;
}

export interface IssueResult {
  token: string;
  jti: string;
  issued_at: string; // ISO-8601
}

const EMPTY_TARGETS: ScopeTargets = {
  wildcards: [],
  exact_hosts: [],
  ips: [],
  android_packages: [],
  ios_bundles: [],
};

const EMPTY_EXCLUSIONS: ScopeExclusions = {
  hostnames: [],
  paths: [],
  notes: "",
};

const DEFAULT_RATE_LIMITS: RateLimits = {
  default_rps: 5,
  relaxed_hosts: {},
};

function generateJti(now: number): string {
  return `jwt_${now}_${randomBytes(8).toString("hex")}`;
}

function generateEngagementId(now: number): string {
  return `eng_${now}_${randomBytes(8).toString("hex")}`;
}

export function resolveKeyPath(
  envVar: string,
  fallback: string,
): string {
  const fromEnv = process.env[envVar];
  return fromEnv && fromEnv.length > 0 ? fromEnv : fallback;
}

export class ScopeJwtIssuer {
  private readonly privateKey: Buffer;

  constructor(privateKeyPath?: string) {
    const keyPath =
      privateKeyPath ?? resolveKeyPath("SCOPE_JWT_PRIVATE_KEY", DEFAULT_PRIVATE_KEY);
    this.privateKey = readFileSync(keyPath);
  }

  issue(args: IssueArgs): IssueResult {
    const expiryHours = args.expiry_hours ?? 24;
    if (!Number.isFinite(expiryHours) || expiryHours <= 0) {
      throw new RangeError("expiry_hours must be a positive number");
    }
    const expirySeconds = Math.floor(expiryHours * 3600);
    if (expirySeconds > MAX_EXPIRY_SECONDS) {
      throw new RangeError(
        `expiry_hours=${expiryHours} exceeds max 168 (${MAX_EXPIRY_SECONDS}s)`,
      );
    }

    const now = Math.floor(Date.now() / 1000);
    const jti = generateJti(now);
    const engagementId = args.engagement_id ?? generateEngagementId(now);

    const targets: ScopeTargets = { ...EMPTY_TARGETS, ...args.targets };
    const exclusions: ScopeExclusions = { ...EMPTY_EXCLUSIONS, ...args.exclusions };
    const rateLimits: RateLimits = {
      default_rps: args.rate_limits?.default_rps ?? DEFAULT_RATE_LIMITS.default_rps,
      relaxed_hosts: args.rate_limits?.relaxed_hosts ?? {},
    };

    const payload: ScopeJwtClaims = {
      jti,
      iss: ISSUER,
      sub: `operator:${args.operator_id}`,
      iat: now,
      exp: now + expirySeconds,
      program_handle: args.program_handle,
      platform: args.platform,
      targets,
      exclusions,
      rate_limits: rateLimits,
      engagement_id: engagementId,
    };

    const signOpts: SignOptions = { algorithm: ALGORITHM };
    // Hand jsonwebtoken a plain object so it does not re-add iat/exp.
    const token = jwt.sign(payload as unknown as object, this.privateKey, signOpts);
    return {
      token,
      jti,
      issued_at: new Date(now * 1000).toISOString(),
    };
  }
}

export interface VerifyResult {
  payload: ScopeJwtClaims;
  jti: string;
}

export class ScopeJwtVerifier {
  private readonly publicKey: Buffer;
  private readonly revoked: Set<string> = new Set();

  constructor(publicKeyPath?: string) {
    const keyPath =
      publicKeyPath ?? resolveKeyPath("SCOPE_JWT_PUBLIC_KEY", DEFAULT_PUBLIC_KEY);
    this.publicKey = readFileSync(keyPath);
  }

  revoke(jti: string): boolean {
    if (this.revoked.has(jti)) {
      return false;
    }
    this.revoked.add(jti);
    return true;
  }

  isRevoked(jti: string): boolean {
    return this.revoked.has(jti);
  }

  verify(token: string): VerifyResult {
    const opts: VerifyOptions = {
      algorithms: [ALGORITHM],
      issuer: ISSUER,
      clockTolerance: 5,
    };
    const decoded = jwt.verify(token, this.publicKey, opts);
    if (typeof decoded === "string") {
      throw new Error("scope-jwt payload was a string, expected object");
    }
    const payload = decoded as JwtPayload & Partial<ScopeJwtClaims>;
    for (const required of ["jti", "iss", "sub", "iat", "exp"] as const) {
      if (payload[required] === undefined || payload[required] === null) {
        throw new Error(`scope-jwt missing required claim: ${required}`);
      }
    }
    const jti = String(payload.jti);
    if (this.revoked.has(jti)) {
      throw new Error(`scope-jwt jti revoked: ${jti}`);
    }
    return { payload: payload as ScopeJwtClaims, jti };
  }
}
