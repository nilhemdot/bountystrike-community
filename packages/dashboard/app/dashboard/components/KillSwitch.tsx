"use client";

import { useState } from "react";
import { ShieldOff, ShieldCheck, Zap, AlertTriangle } from "lucide-react";
import { SAFETY_STATUS, type SafetyStatus } from "../mock-data";
import { Panel, StatusDot } from "./ui";

export default function KillSwitch({ className }: { className?: string }) {
  const [safety, setSafety] = useState<SafetyStatus>(SAFETY_STATUS);
  const [confirming, setConfirming] = useState(false);

  const handleKillSwitch = () => {
    if (!confirming) {
      setConfirming(true);
      return;
    }
    setSafety((prev) => ({
      ...prev,
      kill_switch_active: !prev.kill_switch_active,
    }));
    setConfirming(false);
  };

  const isActive = safety.kill_switch_active;
  const costPct = (safety.cost_usd_24h / safety.cost_ceiling_usd) * 100;

  return (
    <Panel
      title="Kill Switch & Safety"
      subtitle="Layer 1: Redis · Layer 2: PreToolUse · Layer 3: SIGTERM"
      className={className}
    >
      <div className="p-4 space-y-5">
        {/* Main kill switch */}
        <div
          className={`rounded-lg border p-4 transition-colors ${
            isActive
              ? "border-danger/50 bg-danger/5"
              : "border-success/30 bg-success/5"
          }`}
        >
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2">
              {isActive ? (
                <ShieldOff size={16} className="text-danger" />
              ) : (
                <ShieldCheck size={16} className="text-success" />
              )}
              <span className="text-sm font-semibold font-mono">
                {isActive ? (
                  <span className="text-danger">KILL SWITCH ACTIVE</span>
                ) : (
                  <span className="text-success">SYSTEM OPERATIONAL</span>
                )}
              </span>
            </div>
            <div className="font-mono text-[10px] text-muted">
              backend: {safety.kill_switch_backend}
            </div>
          </div>

          {isActive && (
            <p className="text-[10px] font-mono text-danger mb-3">
              All agent tool calls are blocked. Redis flag `bountystrike:killswitch:global` is SET.
            </p>
          )}

          <button
            onClick={handleKillSwitch}
            className={`w-full py-2 rounded font-mono text-xs font-bold uppercase tracking-widest border transition-all ${
              confirming
                ? "bg-danger border-danger text-background animate-pulse"
                : isActive
                ? "bg-success/10 border-success/40 text-success hover:bg-success/20"
                : "bg-danger/10 border-danger/40 text-danger hover:bg-danger/20"
            }`}
          >
            {confirming
              ? "Click again to confirm"
              : isActive
              ? "Deactivate Kill Switch"
              : "Activate Kill Switch"}
          </button>
          {confirming && (
            <button
              onClick={() => setConfirming(false)}
              className="w-full mt-1 py-1 text-[10px] font-mono text-muted hover:text-foreground transition-colors"
            >
              Cancel
            </button>
          )}
        </div>

        {/* Redis + scope violations */}
        <div className="grid grid-cols-3 gap-3">
          <div className="bg-surface-raised rounded-lg border border-border p-3 text-center">
            <StatusDot
              status={safety.redis_connected ? "ok" : "error"}
              pulse={safety.redis_connected}
            />
            <p className="text-[10px] font-mono text-muted mt-1">Redis</p>
            <p className={`text-xs font-mono font-semibold ${safety.redis_connected ? "text-success" : "text-danger"}`}>
              {safety.redis_connected ? "connected" : "down"}
            </p>
          </div>
          <div className="bg-surface-raised rounded-lg border border-border p-3 text-center">
            <p className="text-lg font-mono font-bold text-foreground">
              {safety.scope_violations_24h}
            </p>
            <p className="text-[10px] font-mono text-muted">scope violations</p>
            <p className="text-[9px] font-mono text-muted">24h</p>
          </div>
          <div className="bg-surface-raised rounded-lg border border-border p-3 text-center">
            <p className="text-lg font-mono font-bold text-foreground">
              {safety.rate_limit_hits_1h}
            </p>
            <p className="text-[10px] font-mono text-muted">rate limit hits</p>
            <p className="text-[9px] font-mono text-muted">1h</p>
          </div>
        </div>

        {/* Cost meter */}
        <div>
          <div className="flex items-center justify-between mb-1">
            <span className="text-[10px] font-mono text-muted uppercase tracking-wide">
              Cost 24h
            </span>
            <span className="text-[10px] font-mono text-accent">
              ${safety.cost_usd_24h.toFixed(2)} / ${safety.cost_ceiling_usd.toFixed(0)}
            </span>
          </div>
          <div className="h-1.5 bg-surface-raised rounded-full overflow-hidden">
            <div
              className={`h-full rounded-full transition-all ${
                costPct > 80 ? "bg-danger" : costPct > 50 ? "bg-warning" : "bg-accent"
              }`}
              style={{ width: `${Math.min(costPct, 100)}%` }}
            />
          </div>
          <p className="text-[9px] font-mono text-muted mt-0.5">
            {costPct.toFixed(1)}% of daily ceiling
          </p>
        </div>

        {/* Oracle health */}
        <div>
          <p className="text-[10px] uppercase tracking-widest text-muted font-mono mb-2">
            Oracle health
          </p>
          <div className="grid grid-cols-2 gap-1.5">
            {Object.entries(safety.oracle_health).map(([oracle, health]) => (
              <div
                key={oracle}
                className="flex items-center gap-2 bg-surface-raised rounded px-2 py-1.5 border border-border"
              >
                <StatusDot
                  status={
                    health === "ok" ? "ok" : health === "degraded" ? "warn" : "error"
                  }
                  pulse={health === "ok"}
                />
                <span className="font-mono text-[10px] text-foreground flex-1">
                  {oracle}
                </span>
                <span
                  className={`font-mono text-[9px] ${
                    health === "ok"
                      ? "text-success"
                      : health === "degraded"
                      ? "text-warning"
                      : "text-danger"
                  }`}
                >
                  {health}
                </span>
              </div>
            ))}
          </div>
        </div>

        {/* Hook status */}
        <div>
          <p className="text-[10px] uppercase tracking-widest text-muted font-mono mb-2">
            Hooks (PreToolUse)
          </p>
          <div className="space-y-1">
            {Object.entries(safety.hook_status).map(([hook, status]) => (
              <div key={hook} className="flex items-center gap-2">
                <StatusDot
                  status={
                    status === "active" ? "ok" : status === "bypassed" ? "warn" : "error"
                  }
                />
                <span className="font-mono text-[10px] text-foreground flex-1">
                  {hook}
                </span>
                <span
                  className={`font-mono text-[9px] ${
                    status === "active"
                      ? "text-success"
                      : status === "bypassed"
                      ? "text-warning"
                      : "text-danger"
                  }`}
                >
                  {status}
                </span>
              </div>
            ))}
          </div>
        </div>

        {/* Scope JWT */}
        <div className="bg-surface-raised rounded-lg border border-border p-3">
          <div className="flex items-center gap-2 mb-1">
            <Zap size={10} className="text-accent" />
            <span className="text-[10px] font-mono text-muted uppercase tracking-wide">
              Scope JWT (RS256)
            </span>
          </div>
          <p className="font-mono text-[10px] text-foreground">4096-bit · 168h max TTL</p>
          <p className="font-mono text-[9px] text-muted mt-0.5">
            JTI revocation active · Per-host rate-limit claims
          </p>
        </div>
      </div>
    </Panel>
  );
}
