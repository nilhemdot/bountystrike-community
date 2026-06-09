"use client";

import { useState, useEffect, useRef } from "react";
import { Activity } from "lucide-react";
import { AGENT_EVENTS, type AgentEvent } from "../mock-data";
import { Panel, AgentChip, RelativeTime } from "./ui";

const OUTCOME_STYLE: Record<AgentEvent["outcome"], string> = {
  ok: "text-success",
  warn: "text-warning",
  error: "text-danger",
  blocked: "text-danger",
};

const OUTCOME_GLYPH: Record<AgentEvent["outcome"], string> = {
  ok: "●",
  warn: "▲",
  error: "✕",
  blocked: "⊘",
};

const MODEL_SHORTNAME: Record<string, string> = {
  "claude-opus-4-5": "opus",
  "claude-sonnet-4-5": "sonnet",
  "claude-haiku-3-5": "haiku",
  "deepseek-v3": "deepseek",
  "pentest-r1": "pentest",
};

function EventRow({ event }: { event: AgentEvent }) {
  return (
    <div className="flex items-start gap-2 px-4 py-2 border-b border-border-subtle font-mono text-[10px] hover:bg-surface-raised transition-colors">
      <span className={`shrink-0 mt-0.5 ${OUTCOME_STYLE[event.outcome]}`}>
        {OUTCOME_GLYPH[event.outcome]}
      </span>
      <div className="flex-1 min-w-0 space-y-0.5">
        <div className="flex items-center gap-2 flex-wrap">
          <AgentChip name={event.agent} />
          <span className="text-muted truncate">{event.tool}</span>
        </div>
        <p className="text-foreground leading-relaxed break-words">{event.action}</p>
        <div className="flex items-center gap-3 text-muted">
          <span title="Model">
            {MODEL_SHORTNAME[event.model] ?? event.model}
          </span>
          <span title="Cost">${event.cost_usd.toFixed(4)}</span>
          <span title="Tokens in/out">
            {event.tokens_in}↑ {event.tokens_out}↓
          </span>
          {event.program && (
            <span className="text-accent opacity-70">{event.program}</span>
          )}
          <RelativeTime iso={event.ts} />
        </div>
      </div>
    </div>
  );
}

// Simulated new events ticker
const SIMULATED_EVENTS: Omit<AgentEvent, "id" | "ts">[] = [
  {
    agent: "recon",
    tool: "recon::httpx",
    action: "Live probing 47 hosts on retailmax.com — 12 responsive",
    finding_id: null,
    program: "retailmax",
    cost_usd: 0.0005,
    tokens_in: 280,
    tokens_out: 60,
    model: "deepseek-v3",
    outcome: "ok",
  },
  {
    agent: "validator",
    tool: "oracle-mcp::verify_sqli",
    action: "SQLi Welch t-test complete — p=0.003, significant",
    finding_id: "f-c1f9",
    program: "retailmax",
    cost_usd: 0.0041,
    tokens_in: 2100,
    tokens_out: 440,
    model: "claude-opus-4-5",
    outcome: "ok",
  },
  {
    agent: "scope-guard",
    tool: "scope-mcp::validate_target",
    action: "Scope check: api.retailmax.com — IN SCOPE ✓",
    finding_id: null,
    program: "retailmax",
    cost_usd: 0.0001,
    tokens_in: 95,
    tokens_out: 30,
    model: "claude-haiku-3-5",
    outcome: "ok",
  },
];

export default function AgentActivityFeed({ className }: { className?: string }) {
  const [events, setEvents] = useState<AgentEvent[]>(AGENT_EVENTS);
  const [live, setLive] = useState(true);
  const [simIdx, setSimIdx] = useState(0);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!live) return;
    const id = setInterval(() => {
      const template = SIMULATED_EVENTS[simIdx % SIMULATED_EVENTS.length];
      const newEvent: AgentEvent = {
        ...template,
        id: `ev-sim-${Date.now()}`,
        ts: new Date().toISOString(),
      };
      setEvents((prev) => [newEvent, ...prev.slice(0, 49)]);
      setSimIdx((i) => i + 1);
    }, 4000);
    return () => clearInterval(id);
  }, [live, simIdx]);

  // Cost/token summary
  const totalCost = events.reduce((s, e) => s + e.cost_usd, 0);
  const totalTokens = events.reduce((s, e) => s + e.tokens_in + e.tokens_out, 0);
  const blockedCount = events.filter((e) => e.outcome === "blocked").length;
  const warnCount = events.filter((e) => e.outcome === "warn").length;

  return (
    <Panel
      title="Agent Activity"
      subtitle="Sub-agent tool calls, cost, model routing"
      className={className}
      actions={
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2 text-[10px] font-mono text-muted">
            <span className="text-accent">${totalCost.toFixed(4)}</span>
            <span>{(totalTokens / 1000).toFixed(1)}k tok</span>
            {blockedCount > 0 && (
              <span className="text-danger">{blockedCount} blocked</span>
            )}
            {warnCount > 0 && (
              <span className="text-warning">{warnCount} warn</span>
            )}
          </div>
          <button
            onClick={() => setLive((v) => !v)}
            className={`flex items-center gap-1 px-2 py-1 rounded text-[10px] font-mono border transition-colors ${
              live
                ? "bg-accent/10 border-accent/30 text-accent"
                : "bg-muted/5 border-muted/20 text-muted"
            }`}
          >
            <Activity size={9} className={live ? "pulse-dot" : ""} />
            {live ? "live" : "paused"}
          </button>
        </div>
      }
    >
      <div ref={scrollRef} className="overflow-y-auto h-full">
        {events.map((ev) => (
          <EventRow key={ev.id} event={ev} />
        ))}
      </div>
    </Panel>
  );
}
