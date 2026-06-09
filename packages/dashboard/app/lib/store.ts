// SPDX-License-Identifier: AGPL-3.0-or-later
// Server-side live store for the dashboard BFF.
//
// This is the single source of truth the API route handlers read/write when the
// dashboard is running WITHOUT a real control-plane (CONTROL_PLANE_URL unset).
// It is seeded from the static dataset but is genuinely mutable: approvals
// transition state, the kill switch flips, and the agent feed advances on a
// timer so SWR polling reflects live movement.
//
// When CONTROL_PLANE_URL is set, the route handlers bypass this store entirely
// and proxy to the Python FastAPI control-plane instead (see control-plane.ts).

import {
  FINDINGS,
  PROGRAMS,
  APPROVAL_QUEUE,
  AGENT_EVENTS,
  SAFETY_STATUS,
  EVIDENCE_CHAIN,
  type Finding,
  type Program,
  type ApprovalRequest,
  type AgentEvent,
  type SafetyStatus,
  type EvidenceArtifact,
  type AgentName,
} from "@/app/dashboard/mock-data";

// ─── Module-level singleton state ─────────────────────────────────────────────
// Next.js dev can re-evaluate modules; persist on globalThis so timers + state
// survive HMR and are shared across all route handlers in the same process.
interface LiveState {
  findings: Finding[];
  programs: Program[];
  approvals: ApprovalRequest[];
  events: AgentEvent[];
  safety: SafetyStatus;
  evidence: EvidenceArtifact[];
  seq: number;
  lastTick: number;
}

declare global {
  // eslint-disable-next-line no-var
  var __BS_LIVE_STORE__: LiveState | undefined;
}

function seed(): LiveState {
  return {
    findings: structuredClone(FINDINGS),
    programs: structuredClone(PROGRAMS),
    approvals: structuredClone(APPROVAL_QUEUE),
    events: structuredClone(AGENT_EVENTS),
    safety: structuredClone(SAFETY_STATUS),
    evidence: structuredClone(EVIDENCE_CHAIN),
    seq: 1000,
    lastTick: Date.now(),
  };
}

function store(): LiveState {
  if (!globalThis.__BS_LIVE_STORE__) {
    globalThis.__BS_LIVE_STORE__ = seed();
  }
  return globalThis.__BS_LIVE_STORE__;
}

// ─── Simulated agent activity ─────────────────────────────────────────────────
// Each read of the feed advances the simulation based on elapsed wall-clock time
// (one synthetic event roughly every 4s) so the feed looks alive under polling
// without requiring a background process.
const AGENTS: AgentName[] = [
  "recon",
  "scanner",
  "exploit",
  "validator",
  "reporter",
  "scope-guard",
  "program-selector",
  "ai-vuln-hunter",
  "cloud-recon",
];

const TOOLS: Record<string, { tool: string; action: string; model: string }[]> = {
  validator: [
    { tool: "oracle-mcp::verify_rce", action: "RCE oracle replay", model: "claude-opus-4-5" },
    { tool: "oracle-mcp::verify_idor", action: "IDOR cross-tenant probe", model: "claude-opus-4-5" },
  ],
  scanner: [
    { tool: "oracle-mcp::verify_sqli", action: "Timing SQLi Welch t-test", model: "deepseek-v3" },
    { tool: "oracle-mcp::verify_ssrf", action: "SSRF OAST callback wait", model: "deepseek-v3" },
  ],
  recon: [
    { tool: "recon::subfinder", action: "Subdomain enumeration sweep", model: "deepseek-v3" },
    { tool: "recon::httpx", action: "Live-host fingerprinting", model: "deepseek-v3" },
  ],
  exploit: [
    { tool: "sandbox-mcp::exec_safe", action: "Sandboxed payload execution", model: "claude-opus-4-5" },
  ],
  reporter: [
    { tool: "h1-mcp::submit_report", action: "Drafting platform submission", model: "claude-sonnet-4-5" },
  ],
  "scope-guard": [
    { tool: "scope-mcp::validate_target", action: "Scope boundary check", model: "claude-haiku-3-5" },
  ],
  "program-selector": [
    { tool: "ev-mcp::rank_programs", action: "EV re-ranking pass", model: "claude-haiku-3-5" },
  ],
  "ai-vuln-hunter": [
    { tool: "dedup-mcp::check_semantic_duplicate", action: "Semantic dedup cosine match", model: "deepseek-v3" },
  ],
  "cloud-recon": [
    { tool: "cloud-mcp::enum_buckets", action: "Cloud asset discovery", model: "deepseek-v3" },
  ],
};

const PROGRAM_HANDLES = ["globalbank", "enterpriseapp", "devtools-beta", "acme-corp", "retailmax", "cryptopay", "shopcloud"];

function rand<T>(arr: T[]): T {
  return arr[Math.floor(Math.random() * arr.length)];
}

function synthesizeEvent(s: LiveState): AgentEvent {
  const agent = rand(AGENTS);
  const t = rand(TOOLS[agent] ?? TOOLS.recon);
  const blocked = agent === "scope-guard" && Math.random() < 0.25;
  const program = rand(PROGRAM_HANDLES);
  s.seq += 1;
  const tokensIn = 120 + Math.floor(Math.random() * 2000);
  const tokensOut = 40 + Math.floor(Math.random() * 800);
  return {
    id: `ev-${s.seq}`,
    ts: new Date().toISOString(),
    agent,
    tool: t.tool,
    action: blocked ? `${t.action} — OUT OF SCOPE, blocked` : t.action,
    finding_id: Math.random() < 0.5 ? `f-${Math.random().toString(16).slice(2, 6)}` : null,
    program,
    cost_usd: Number(((tokensIn + tokensOut) * 0.0000015).toFixed(4)),
    tokens_in: tokensIn,
    tokens_out: tokensOut,
    model: t.model,
    outcome: blocked ? "blocked" : Math.random() < 0.1 ? "warn" : "ok",
  };
}

// Advance the simulation. Killing the switch freezes new agent activity.
function tick(): void {
  const s = store();
  if (s.safety.kill_switch_active) {
    s.lastTick = Date.now();
    return;
  }
  const now = Date.now();
  const elapsed = now - s.lastTick;
  const newCount = Math.min(5, Math.floor(elapsed / 4000));
  if (newCount <= 0) return;
  for (let i = 0; i < newCount; i++) {
    const ev = synthesizeEvent(s);
    s.events.unshift(ev);
    s.safety.cost_usd_24h = Number((s.safety.cost_usd_24h + ev.cost_usd).toFixed(4));
    if (ev.outcome === "blocked") s.safety.scope_violations_24h += 1;
  }
  s.events = s.events.slice(0, 60);
  s.lastTick = now;
}

// ─── Read accessors (used by GET route handlers) ──────────────────────────────
export function getFindings(): Finding[] {
  return store().findings;
}

export function getPrograms(): Program[] {
  return [...store().programs].sort((a, b) => b.ev_score - a.ev_score);
}

export function getApprovals(): ApprovalRequest[] {
  return store().approvals;
}

export function getEvents(): AgentEvent[] {
  tick();
  return store().events;
}

export function getSafety(): SafetyStatus {
  tick();
  return store().safety;
}

export function getEvidence(): EvidenceArtifact[] {
  return store().evidence;
}

export function getSummary() {
  const s = store();
  const activePayout = s.findings
    .filter((f) => !["rejected", "duplicate", "wont_fix", "archived"].includes(f.status))
    .reduce((sum, f) => sum + f.payout_estimate, 0);
  return {
    total_findings: s.findings.length,
    confirmed_24h: s.findings.filter((f) => f.status === "confirmed").length,
    pending_approval: s.approvals.filter((a) => a.status === "pending").length,
    cost_usd_today: s.safety.cost_usd_24h,
    oracle_accuracy: "7/8 TPR=1.0",
    scope_violations: s.safety.scope_violations_24h,
    agents_active: s.safety.kill_switch_active ? 0 : 5,
    total_payout_potential: activePayout,
  };
}

// ─── Mutations (used by POST route handlers) ──────────────────────────────────
export function decideApproval(
  id: string,
  decision: "approve" | "reject",
  approverId: string,
  reason: string | null,
): ApprovalRequest | null {
  const s = store();
  const req = s.approvals.find((a) => a.id === id);
  if (!req || req.status !== "pending") return req ?? null;

  // T3 requires two-person approval: first approve assigns the second approver.
  if (decision === "approve" && req.tier === "T3" && !req.approver_id_2 && req.approver_id && req.approver_id !== approverId) {
    req.approver_id_2 = approverId;
    req.status = "approved";
  } else if (decision === "approve") {
    if (!req.approver_id) req.approver_id = approverId;
    else if (req.tier === "T3") req.approver_id_2 = approverId;
    req.status = "approved";
  } else {
    req.status = "rejected";
    req.reason = reason ?? "Rejected by operator";
    if (!req.approver_id) req.approver_id = approverId;
  }

  // Reflect the decision onto the underlying finding.
  const finding = s.findings.find((f) => f.id === req.finding_id);
  if (finding) {
    finding.status = decision === "approve" ? "approved" : "rejected";
    finding.updated_at = new Date().toISOString();
  }
  return req;
}

export function setKillSwitch(active: boolean): SafetyStatus {
  const s = store();
  s.safety.kill_switch_active = active;
  s.lastTick = Date.now();
  return s.safety;
}

export function resetStore(): void {
  globalThis.__BS_LIVE_STORE__ = seed();
}
