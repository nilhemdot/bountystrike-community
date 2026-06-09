"use client";

import { clsx } from "clsx";
import type { ReactNode } from "react";

// ─── Panel card ───────────────────────────────────────────────────────────────
export function Panel({
  title,
  subtitle,
  actions,
  children,
  className,
}: {
  title: string;
  subtitle?: string;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section
      className={clsx(
        "flex flex-col bg-surface border border-border rounded-lg overflow-hidden",
        className
      )}
    >
      <header className="flex items-center justify-between px-4 py-3 border-b border-border shrink-0">
        <div className="flex flex-col gap-0.5">
          <h2 className="text-xs font-semibold tracking-widest uppercase text-muted font-mono">
            {title}
          </h2>
          {subtitle && (
            <p className="text-xs text-muted opacity-60">{subtitle}</p>
          )}
        </div>
        {actions && <div className="flex items-center gap-2">{actions}</div>}
      </header>
      <div className="flex-1 overflow-auto">{children}</div>
    </section>
  );
}

// ─── Status dot ──────────────────────────────────────────────────────────────
export function StatusDot({
  status,
  pulse = false,
}: {
  status: "ok" | "warn" | "error" | "neutral" | "blocked";
  pulse?: boolean;
}) {
  const color = {
    ok: "bg-success",
    warn: "bg-warning",
    error: "bg-danger",
    neutral: "bg-muted",
    blocked: "bg-danger",
  }[status];
  return (
    <span
      className={clsx(
        "inline-block w-2 h-2 rounded-full shrink-0",
        color,
        pulse && "pulse-dot"
      )}
      aria-hidden
    />
  );
}

// ─── Severity badge ───────────────────────────────────────────────────────────
export function SeverityBadge({
  severity,
}: {
  severity: "critical" | "high" | "medium" | "low";
}) {
  const styles = {
    critical: "bg-danger/15 text-danger border-danger/30",
    high: "bg-warning/15 text-warning border-warning/30",
    medium: "bg-info/15 text-info border-info/30",
    low: "bg-success/15 text-success border-success/30",
  };
  return (
    <span
      className={clsx(
        "inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-mono font-semibold uppercase border",
        styles[severity]
      )}
    >
      {severity}
    </span>
  );
}

// ─── Platform chip ────────────────────────────────────────────────────────────
export function PlatformChip({ platform }: { platform: string }) {
  const colors: Record<string, string> = {
    hackerone: "bg-accent/10 text-accent border-accent/20",
    bugcrowd: "bg-warning/10 text-warning border-warning/20",
    intigriti: "bg-info/10 text-info border-info/20",
    yeswehack: "bg-success/10 text-success border-success/20",
    immunefi: "bg-[#a78bfa]/10 text-[#a78bfa] border-[#a78bfa]/20",
  };
  return (
    <span
      className={clsx(
        "inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-mono border",
        colors[platform] ?? "bg-muted/10 text-muted border-muted/20"
      )}
    >
      {platform}
    </span>
  );
}

// ─── Tier badge ───────────────────────────────────────────────────────────────
export function TierBadge({ tier }: { tier: "T1" | "T2" | "T3" | "T0" }) {
  const styles: Record<string, string> = {
    T0: "bg-muted/10 text-muted border-muted/20",
    T1: "bg-info/10 text-info border-info/30",
    T2: "bg-warning/10 text-warning border-warning/30",
    T3: "bg-danger/10 text-danger border-danger/30",
  };
  return (
    <span
      className={clsx(
        "inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-mono font-bold border",
        styles[tier]
      )}
    >
      {tier}
    </span>
  );
}

// ─── Score bar ────────────────────────────────────────────────────────────────
export function ScoreBar({
  value,
  label,
  color = "accent",
}: {
  value: number;
  label?: string;
  color?: string;
}) {
  const pct = Math.round(value * 100);
  return (
    <div className="flex items-center gap-2">
      {label && <span className="text-[10px] font-mono text-muted w-16 shrink-0">{label}</span>}
      <div className="flex-1 h-1 bg-surface-raised rounded-full overflow-hidden">
        <div
          className={clsx("h-full rounded-full", `bg-${color}`)}
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="text-[10px] font-mono text-muted w-8 text-right">{pct}%</span>
    </div>
  );
}

// ─── Mono hash ───────────────────────────────────────────────────────────────
export function HashSpan({ hash }: { hash: string }) {
  return (
    <span className="font-mono text-[10px] text-muted tracking-tight">
      {hash.slice(0, 8)}…
    </span>
  );
}

// ─── Timestamp ────────────────────────────────────────────────────────────────
export function RelativeTime({ iso }: { iso: string }) {
  const date = new Date(iso);
  const now = new Date("2026-06-09T09:02:00Z");
  const diffMs = now.getTime() - date.getTime();
  const diffMin = Math.floor(diffMs / 60000);
  const diffH = Math.floor(diffMin / 60);

  let label: string;
  if (diffMin < 1) label = "just now";
  else if (diffMin < 60) label = `${diffMin}m ago`;
  else if (diffH < 24) label = `${diffH}h ago`;
  else label = `${Math.floor(diffH / 24)}d ago`;

  return (
    <time dateTime={iso} title={iso} className="font-mono text-[10px] text-muted">
      {label}
    </time>
  );
}

// ─── Agent name chip ─────────────────────────────────────────────────────────
export function AgentChip({ name }: { name: string }) {
  return (
    <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-accent/5 border border-accent/15 text-[10px] font-mono text-accent">
      {name}
    </span>
  );
}
