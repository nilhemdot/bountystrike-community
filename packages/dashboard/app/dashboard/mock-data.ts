// ─── Finding Status ENUM (16 states from 01_schema.sql) ──────────────────────
export type FindingStatus =
  | "hypothesis"
  | "exploit_attempt"
  | "exploit_candidate"
  | "validation_pending"
  | "validated"
  | "dedup_check"
  | "approval_pending_t1"
  | "approval_pending_t2"
  | "approval_pending_t3"
  | "approved"
  | "submitted"
  | "confirmed"
  | "rejected"
  | "duplicate"
  | "wont_fix"
  | "archived";

export type VulnClass =
  | "XSS"
  | "SSRF"
  | "SQLi"
  | "SSTI"
  | "IDOR"
  | "RCE"
  | "Open Redirect"
  | "SSRF→IMDS";

export type Platform = "hackerone" | "bugcrowd" | "intigriti" | "yeswehack" | "immunefi";

export interface Finding {
  id: string;
  title: string;
  program: string;
  platform: Platform;
  vuln_class: VulnClass;
  status: FindingStatus;
  severity: "critical" | "high" | "medium" | "low";
  payout_estimate: number;
  created_at: string;
  updated_at: string;
  oracle_tpr: number | null;
  chain_hash: string;
  agent: string;
}

export const FINDINGS: Finding[] = [
  {
    id: "f-9a3b",
    title: "Reflected XSS in search parameter via DOM sink",
    program: "acme-corp",
    platform: "hackerone",
    vuln_class: "XSS",
    status: "confirmed",
    severity: "high",
    payout_estimate: 1500,
    created_at: "2026-06-09T04:12:00Z",
    updated_at: "2026-06-09T07:31:00Z",
    oracle_tpr: 1.0,
    chain_hash: "a3f9c2d1",
    agent: "validator",
  },
  {
    id: "f-2e7f",
    title: "SSRF via webhook URL leading to internal metadata endpoint",
    program: "globalbank",
    platform: "bugcrowd",
    vuln_class: "SSRF→IMDS",
    status: "approval_pending_t3",
    severity: "critical",
    payout_estimate: 8000,
    created_at: "2026-06-09T02:44:00Z",
    updated_at: "2026-06-09T08:05:00Z",
    oracle_tpr: 1.0,
    chain_hash: "7bc4e1a9",
    agent: "validator",
  },
  {
    id: "f-6c1d",
    title: "IDOR on /api/v2/users/{id}/settings — cross-tenant read",
    program: "shopcloud",
    platform: "hackerone",
    vuln_class: "IDOR",
    status: "validated",
    severity: "high",
    payout_estimate: 3000,
    created_at: "2026-06-09T01:00:00Z",
    updated_at: "2026-06-09T06:22:00Z",
    oracle_tpr: 1.0,
    chain_hash: "d5f0b3c2",
    agent: "validator",
  },
  {
    id: "f-4a8e",
    title: "SSTI via Jinja2 template in report name field",
    program: "devtools-beta",
    platform: "intigriti",
    vuln_class: "SSTI",
    status: "approval_pending_t2",
    severity: "critical",
    payout_estimate: 5000,
    created_at: "2026-06-08T22:15:00Z",
    updated_at: "2026-06-09T05:47:00Z",
    oracle_tpr: 1.0,
    chain_hash: "e1a7c9f4",
    agent: "validator",
  },
  {
    id: "f-b3c5",
    title: "Open Redirect in OAuth callback — phishing vector",
    program: "cryptopay",
    platform: "immunefi",
    vuln_class: "Open Redirect",
    status: "submitted",
    severity: "medium",
    payout_estimate: 750,
    created_at: "2026-06-08T18:30:00Z",
    updated_at: "2026-06-09T03:11:00Z",
    oracle_tpr: 1.0,
    chain_hash: "9c2d5f8a",
    agent: "reporter",
  },
  {
    id: "f-d7e2",
    title: "RCE via deserialization in Java upload endpoint",
    program: "enterpriseapp",
    platform: "bugcrowd",
    vuln_class: "RCE",
    status: "exploit_candidate",
    severity: "critical",
    payout_estimate: 12000,
    created_at: "2026-06-09T06:00:00Z",
    updated_at: "2026-06-09T08:45:00Z",
    oracle_tpr: null,
    chain_hash: "f4b1d6e3",
    agent: "exploit",
  },
  {
    id: "f-c1f9",
    title: "SQLi in product search — timing-based blind injection",
    program: "retailmax",
    platform: "hackerone",
    vuln_class: "SQLi",
    status: "validation_pending",
    severity: "high",
    payout_estimate: 4000,
    created_at: "2026-06-09T07:30:00Z",
    updated_at: "2026-06-09T08:50:00Z",
    oracle_tpr: null,
    chain_hash: "a8e3c7d1",
    agent: "scanner",
  },
  {
    id: "f-5d0a",
    title: "Stored XSS in user bio field — admin context",
    program: "socialnet",
    platform: "yeswehack",
    vuln_class: "XSS",
    status: "dedup_check",
    severity: "medium",
    payout_estimate: 500,
    created_at: "2026-06-09T08:10:00Z",
    updated_at: "2026-06-09T08:55:00Z",
    oracle_tpr: 1.0,
    chain_hash: "b6f2a0c9",
    agent: "validator",
  },
  {
    id: "f-e2b4",
    title: "SSRF via image proxy endpoint",
    program: "cloudfiles",
    platform: "bugcrowd",
    vuln_class: "SSRF",
    status: "duplicate",
    severity: "high",
    payout_estimate: 0,
    created_at: "2026-06-08T14:20:00Z",
    updated_at: "2026-06-08T16:45:00Z",
    oracle_tpr: 1.0,
    chain_hash: "c3d9e5b7",
    agent: "validator",
  },
  {
    id: "f-7f3c",
    title: "Hypothesis: path traversal in file download API",
    program: "acme-corp",
    platform: "hackerone",
    vuln_class: "IDOR",
    status: "hypothesis",
    severity: "medium",
    payout_estimate: 800,
    created_at: "2026-06-09T09:00:00Z",
    updated_at: "2026-06-09T09:00:00Z",
    oracle_tpr: null,
    chain_hash: "00000000",
    agent: "scanner",
  },
];

// ─── Status ordering for pipeline view ───────────────────────────────────────
export const STATUS_ORDER: FindingStatus[] = [
  "hypothesis",
  "exploit_attempt",
  "exploit_candidate",
  "validation_pending",
  "validated",
  "dedup_check",
  "approval_pending_t1",
  "approval_pending_t2",
  "approval_pending_t3",
  "approved",
  "submitted",
  "confirmed",
  "rejected",
  "duplicate",
  "wont_fix",
  "archived",
];

export const STATUS_LABEL: Record<FindingStatus, string> = {
  hypothesis: "Hypothesis",
  exploit_attempt: "Exploit Attempt",
  exploit_candidate: "Exploit Candidate",
  validation_pending: "Validation Pending",
  validated: "Validated",
  dedup_check: "Dedup Check",
  approval_pending_t1: "T1 Approval",
  approval_pending_t2: "T2 Approval",
  approval_pending_t3: "T3 Approval",
  approved: "Approved",
  submitted: "Submitted",
  confirmed: "Confirmed",
  rejected: "Rejected",
  duplicate: "Duplicate",
  wont_fix: "Won't Fix",
  archived: "Archived",
};

// ─── Program EV Rankings ──────────────────────────────────────────────────────
export interface Program {
  handle: string;
  platform: Platform;
  ev_score: number;
  f_payout: number;
  f_saturation: number;
  f_ops: number;
  f_fit: number;
  f_cve: number;
  payout_min: number;
  payout_max: number;
  active_findings: number;
  dup_rate: number;
  kev_matches: number;
  last_scan: string | null;
}

export const PROGRAMS: Program[] = [
  {
    handle: "globalbank",
    platform: "bugcrowd",
    ev_score: 0.912,
    f_payout: 0.95,
    f_saturation: 0.85,
    f_ops: 0.90,
    f_fit: 0.92,
    f_cve: 0.88,
    payout_min: 500,
    payout_max: 20000,
    active_findings: 3,
    dup_rate: 0.08,
    kev_matches: 2,
    last_scan: "2026-06-09T08:05:00Z",
  },
  {
    handle: "enterpriseapp",
    platform: "bugcrowd",
    ev_score: 0.878,
    f_payout: 0.92,
    f_saturation: 0.78,
    f_ops: 0.88,
    f_fit: 0.85,
    f_cve: 0.91,
    payout_min: 250,
    payout_max: 15000,
    active_findings: 1,
    dup_rate: 0.12,
    kev_matches: 3,
    last_scan: "2026-06-09T08:45:00Z",
  },
  {
    handle: "devtools-beta",
    platform: "intigriti",
    ev_score: 0.841,
    f_payout: 0.88,
    f_saturation: 0.72,
    f_ops: 0.86,
    f_fit: 0.90,
    f_cve: 0.75,
    payout_min: 100,
    payout_max: 10000,
    active_findings: 2,
    dup_rate: 0.09,
    kev_matches: 1,
    last_scan: "2026-06-09T07:00:00Z",
  },
  {
    handle: "acme-corp",
    platform: "hackerone",
    ev_score: 0.803,
    f_payout: 0.82,
    f_saturation: 0.68,
    f_ops: 0.85,
    f_fit: 0.88,
    f_cve: 0.70,
    payout_min: 200,
    payout_max: 5000,
    active_findings: 4,
    dup_rate: 0.15,
    kev_matches: 0,
    last_scan: "2026-06-09T07:31:00Z",
  },
  {
    handle: "retailmax",
    platform: "hackerone",
    ev_score: 0.769,
    f_payout: 0.79,
    f_saturation: 0.71,
    f_ops: 0.82,
    f_fit: 0.75,
    f_cve: 0.73,
    payout_min: 150,
    payout_max: 8000,
    active_findings: 1,
    dup_rate: 0.18,
    kev_matches: 1,
    last_scan: "2026-06-09T08:50:00Z",
  },
  {
    handle: "cryptopay",
    platform: "immunefi",
    ev_score: 0.744,
    f_payout: 0.97,
    f_saturation: 0.55,
    f_ops: 0.80,
    f_fit: 0.68,
    f_cve: 0.62,
    payout_min: 1000,
    payout_max: 100000,
    active_findings: 1,
    dup_rate: 0.28,
    kev_matches: 0,
    last_scan: "2026-06-08T22:00:00Z",
  },
  {
    handle: "shopcloud",
    platform: "hackerone",
    ev_score: 0.711,
    f_payout: 0.74,
    f_saturation: 0.62,
    f_ops: 0.77,
    f_fit: 0.81,
    f_cve: 0.55,
    payout_min: 100,
    payout_max: 6500,
    active_findings: 1,
    dup_rate: 0.21,
    kev_matches: 0,
    last_scan: "2026-06-09T06:22:00Z",
  },
];

// ─── Approval Queue ───────────────────────────────────────────────────────────
export type ApprovalTier = "T1" | "T2" | "T3";
export type ApprovalStatus = "pending" | "approved" | "rejected" | "expired";

export interface ApprovalRequest {
  id: string;
  finding_id: string;
  finding_title: string;
  program: string;
  tier: ApprovalTier;
  status: ApprovalStatus;
  requested_at: string;
  expires_at: string;
  approver_id: string | null;
  approver_id_2: string | null;
  reason: string | null;
  severity: "critical" | "high" | "medium" | "low";
  payout_estimate: number;
}

export const APPROVAL_QUEUE: ApprovalRequest[] = [
  {
    id: "aq-001",
    finding_id: "f-2e7f",
    finding_title: "SSRF via webhook URL leading to internal metadata endpoint",
    program: "globalbank",
    tier: "T3",
    status: "pending",
    requested_at: "2026-06-09T08:05:00Z",
    expires_at: "2026-06-09T20:05:00Z",
    approver_id: "op-alice",
    approver_id_2: null,
    reason: null,
    severity: "critical",
    payout_estimate: 8000,
  },
  {
    id: "aq-002",
    finding_id: "f-4a8e",
    finding_title: "SSTI via Jinja2 template in report name field",
    program: "devtools-beta",
    tier: "T2",
    status: "pending",
    requested_at: "2026-06-09T05:47:00Z",
    expires_at: "2026-06-09T17:47:00Z",
    approver_id: null,
    approver_id_2: null,
    reason: null,
    severity: "critical",
    payout_estimate: 5000,
  },
  {
    id: "aq-003",
    finding_id: "f-9a3b",
    finding_title: "Reflected XSS in search parameter via DOM sink",
    program: "acme-corp",
    tier: "T1",
    status: "approved",
    requested_at: "2026-06-09T06:10:00Z",
    expires_at: "2026-06-09T10:10:00Z",
    approver_id: "llm-sonnet",
    approver_id_2: null,
    reason: "Oracle TPR=1.0, clean reproduction, within scope.",
    severity: "high",
    payout_estimate: 1500,
  },
  {
    id: "aq-004",
    finding_id: "f-6c1d",
    finding_title: "IDOR on /api/v2/users/{id}/settings — cross-tenant read",
    program: "shopcloud",
    tier: "T2",
    status: "pending",
    requested_at: "2026-06-09T06:22:00Z",
    expires_at: "2026-06-09T18:22:00Z",
    approver_id: null,
    approver_id_2: null,
    reason: null,
    severity: "high",
    payout_estimate: 3000,
  },
];

// ─── Agent Activity Feed ──────────────────────────────────────────────────────
export type AgentName =
  | "recon"
  | "scanner"
  | "exploit"
  | "validator"
  | "reporter"
  | "scope-guard"
  | "program-selector"
  | "ai-vuln-hunter"
  | "cloud-recon";

export interface AgentEvent {
  id: string;
  ts: string;
  agent: AgentName;
  tool: string;
  action: string;
  finding_id: string | null;
  program: string | null;
  cost_usd: number;
  tokens_in: number;
  tokens_out: number;
  model: string;
  outcome: "ok" | "warn" | "error" | "blocked";
}

export const AGENT_EVENTS: AgentEvent[] = [
  {
    id: "ev-100",
    ts: "2026-06-09T09:01:22Z",
    agent: "validator",
    tool: "oracle-mcp::verify_rce",
    action: "Running RCE oracle on f-d7e2 (enterpriseapp)",
    finding_id: "f-d7e2",
    program: "enterpriseapp",
    cost_usd: 0.0032,
    tokens_in: 1840,
    tokens_out: 412,
    model: "claude-opus-4-5",
    outcome: "ok",
  },
  {
    id: "ev-099",
    ts: "2026-06-09T09:00:55Z",
    agent: "scanner",
    tool: "oracle-mcp::verify_sqli",
    action: "Timing-based SQLi oracle on f-c1f9 — Welch t-test pending",
    finding_id: "f-c1f9",
    program: "retailmax",
    cost_usd: 0.0018,
    tokens_in: 980,
    tokens_out: 220,
    model: "deepseek-v3",
    outcome: "ok",
  },
  {
    id: "ev-098",
    ts: "2026-06-09T09:00:31Z",
    agent: "scope-guard",
    tool: "scope-mcp::validate_target",
    action: "Scope check: 192.168.1.1 — OUT OF SCOPE, blocked",
    finding_id: null,
    program: "acme-corp",
    cost_usd: 0.0001,
    tokens_in: 120,
    tokens_out: 45,
    model: "claude-haiku-3-5",
    outcome: "blocked",
  },
  {
    id: "ev-097",
    ts: "2026-06-09T09:00:08Z",
    agent: "exploit",
    tool: "sandbox-mcp::exec_safe",
    action: "Executing deserialization payload in sandboxed VM",
    finding_id: "f-d7e2",
    program: "enterpriseapp",
    cost_usd: 0.0051,
    tokens_in: 2100,
    tokens_out: 890,
    model: "claude-opus-4-5",
    outcome: "ok",
  },
  {
    id: "ev-096",
    ts: "2026-06-09T08:59:44Z",
    agent: "reporter",
    tool: "h1-mcp::submit_report",
    action: "Submitted f-b3c5 to yeswehack — Open Redirect confirmed",
    finding_id: "f-b3c5",
    program: "cryptopay",
    cost_usd: 0.0024,
    tokens_in: 1560,
    tokens_out: 680,
    model: "claude-sonnet-4-5",
    outcome: "ok",
  },
  {
    id: "ev-095",
    ts: "2026-06-09T08:58:12Z",
    agent: "recon",
    tool: "recon::subfinder",
    action: "Subdomain enum: retailmax.com — 47 hosts found",
    finding_id: null,
    program: "retailmax",
    cost_usd: 0.0008,
    tokens_in: 450,
    tokens_out: 98,
    model: "deepseek-v3",
    outcome: "ok",
  },
  {
    id: "ev-094",
    ts: "2026-06-09T08:57:33Z",
    agent: "validator",
    tool: "oracle-mcp::verify_idor",
    action: "IDOR oracle on f-6c1d: cross-tenant access confirmed",
    finding_id: "f-6c1d",
    program: "shopcloud",
    cost_usd: 0.0029,
    tokens_in: 1720,
    tokens_out: 380,
    model: "claude-opus-4-5",
    outcome: "ok",
  },
  {
    id: "ev-093",
    ts: "2026-06-09T08:56:01Z",
    agent: "ai-vuln-hunter",
    tool: "dedup-mcp::check_semantic_duplicate",
    action: "Semantic dedup check on f-5d0a — no match (cosine=0.31)",
    finding_id: "f-5d0a",
    program: "socialnet",
    cost_usd: 0.0014,
    tokens_in: 820,
    tokens_out: 185,
    model: "deepseek-v3",
    outcome: "ok",
  },
  {
    id: "ev-092",
    ts: "2026-06-09T08:55:22Z",
    agent: "program-selector",
    tool: "ev-mcp::rank_programs",
    action: "EV re-rank triggered — globalbank promoted to #1",
    finding_id: null,
    program: null,
    cost_usd: 0.0006,
    tokens_in: 340,
    tokens_out: 72,
    model: "claude-haiku-3-5",
    outcome: "ok",
  },
  {
    id: "ev-091",
    ts: "2026-06-09T08:54:10Z",
    agent: "scanner",
    tool: "oracle-mcp::verify_ssrf",
    action: "SSRF OAST callback NOT received for candidate — rejected",
    finding_id: null,
    program: "cloudfiles",
    cost_usd: 0.0011,
    tokens_in: 610,
    tokens_out: 140,
    model: "deepseek-v3",
    outcome: "warn",
  },
];

// ─── Kill Switch / Safety ─────────────────────────────────────────────────────
export interface SafetyStatus {
  kill_switch_active: boolean;
  kill_switch_backend: "redis" | "memory";
  redis_connected: boolean;
  oracle_health: Record<string, "ok" | "degraded" | "down">;
  hook_status: Record<string, "active" | "bypassed" | "error">;
  scope_violations_24h: number;
  cost_usd_24h: number;
  cost_ceiling_usd: number;
  rate_limit_hits_1h: number;
}

export const SAFETY_STATUS: SafetyStatus = {
  kill_switch_active: false,
  kill_switch_backend: "redis",
  redis_connected: true,
  oracle_health: {
    xss: "ok",
    ssrf: "ok",
    sqli: "degraded",
    ssti: "ok",
    idor: "ok",
    rce: "ok",
    open_redirect: "ok",
    "ssrf_imds": "ok",
  },
  hook_status: {
    pretool_killswitch: "active",
    pretool_antislop: "active",
    pretool_approval_gate: "active",
    "pre-task-scope-check": "active",
    "post-task-scan-complete": "active",
  },
  scope_violations_24h: 0,
  cost_usd_24h: 3.84,
  cost_ceiling_usd: 30.0,
  rate_limit_hits_1h: 3,
};

// ─── Evidence Audit Chain ─────────────────────────────────────────────────────
export interface EvidenceArtifact {
  id: string;
  finding_id: string;
  finding_title: string;
  content_hash: string;
  prev_audit_hash: string;
  artifact_type: "request_transcript" | "response_transcript" | "oracle_data" | "repro_command" | "scope_jwt";
  r2_key: string;
  scope_token_jti: string;
  created_at: string;
  size_bytes: number;
  chain_valid: boolean;
}

export const EVIDENCE_CHAIN: EvidenceArtifact[] = [
  {
    id: "ev-art-001",
    finding_id: "f-9a3b",
    finding_title: "Reflected XSS — acme-corp",
    content_hash: "sha256:a3f9c2d1e4b5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a1",
    prev_audit_hash: "sha256:0000000000000000000000000000000000000000000000000000000000000000",
    artifact_type: "oracle_data",
    r2_key: "evidence/acme-corp/f-9a3b/oracle_data.json",
    scope_token_jti: "jti-acme-20260609",
    created_at: "2026-06-09T07:28:00Z",
    size_bytes: 4812,
    chain_valid: true,
  },
  {
    id: "ev-art-002",
    finding_id: "f-9a3b",
    finding_title: "Reflected XSS — acme-corp",
    content_hash: "sha256:b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5",
    prev_audit_hash: "sha256:a3f9c2d1e4b5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a1",
    artifact_type: "request_transcript",
    r2_key: "evidence/acme-corp/f-9a3b/request.har",
    scope_token_jti: "jti-acme-20260609",
    created_at: "2026-06-09T07:29:00Z",
    size_bytes: 12440,
    chain_valid: true,
  },
  {
    id: "ev-art-003",
    finding_id: "f-2e7f",
    finding_title: "SSRF→IMDS — globalbank",
    content_hash: "sha256:c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6",
    prev_audit_hash: "sha256:b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5",
    artifact_type: "oracle_data",
    r2_key: "evidence/globalbank/f-2e7f/oracle_data.json",
    scope_token_jti: "jti-globalbank-20260609",
    created_at: "2026-06-09T08:03:00Z",
    size_bytes: 6218,
    chain_valid: true,
  },
  {
    id: "ev-art-004",
    finding_id: "f-2e7f",
    finding_title: "SSRF→IMDS — globalbank",
    content_hash: "sha256:d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7",
    prev_audit_hash: "sha256:c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6",
    artifact_type: "response_transcript",
    r2_key: "evidence/globalbank/f-2e7f/response.har",
    scope_token_jti: "jti-globalbank-20260609",
    created_at: "2026-06-09T08:04:00Z",
    size_bytes: 9340,
    chain_valid: true,
  },
  {
    id: "ev-art-005",
    finding_id: "f-6c1d",
    finding_title: "IDOR — shopcloud",
    content_hash: "sha256:e7f8a9b0c1d2e3f4a5b6c7d8e9f0a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8",
    prev_audit_hash: "sha256:d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7",
    artifact_type: "repro_command",
    r2_key: "evidence/shopcloud/f-6c1d/repro.sh",
    scope_token_jti: "jti-shopcloud-20260609",
    created_at: "2026-06-09T06:20:00Z",
    size_bytes: 1024,
    chain_valid: true,
  },
  {
    id: "ev-art-006",
    finding_id: "f-4a8e",
    finding_title: "SSTI — devtools-beta",
    content_hash: "sha256:f8a9b0c1d2e3f4a5b6c7d8e9f0a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9",
    prev_audit_hash: "sha256:e7f8a9b0c1d2e3f4a5b6c7d8e9f0a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8",
    artifact_type: "oracle_data",
    r2_key: "evidence/devtools-beta/f-4a8e/oracle_data.json",
    scope_token_jti: "jti-devtools-20260609",
    created_at: "2026-06-09T05:45:00Z",
    size_bytes: 7622,
    chain_valid: true,
  },
];

// ─── Dashboard summary stats ──────────────────────────────────────────────────
export const SUMMARY_STATS = {
  total_findings: FINDINGS.length,
  confirmed_24h: FINDINGS.filter((f) => f.status === "confirmed").length,
  pending_approval: APPROVAL_QUEUE.filter((a) => a.status === "pending").length,
  cost_usd_today: SAFETY_STATUS.cost_usd_24h,
  oracle_accuracy: "7/8 TPR=1.0",
  scope_violations: SAFETY_STATUS.scope_violations_24h,
  agents_active: 5,
  total_payout_potential: FINDINGS.filter(
    (f) => !["rejected", "duplicate", "wont_fix", "archived"].includes(f.status)
  ).reduce((sum, f) => sum + f.payout_estimate, 0),
};
