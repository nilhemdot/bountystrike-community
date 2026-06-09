import { SUMMARY_STATS, SAFETY_STATUS } from "../mock-data";
import { StatusDot } from "./ui";

interface StatItem {
  label: string;
  value: string | number;
  sub?: string;
  accent?: boolean;
  warn?: boolean;
  danger?: boolean;
}

const stats: StatItem[] = [
  {
    label: "total findings",
    value: SUMMARY_STATS.total_findings,
  },
  {
    label: "confirmed 24h",
    value: SUMMARY_STATS.confirmed_24h,
    accent: true,
  },
  {
    label: "pending approval",
    value: SUMMARY_STATS.pending_approval,
    warn: SUMMARY_STATS.pending_approval > 0,
  },
  {
    label: "payout potential",
    value: `$${SUMMARY_STATS.total_payout_potential.toLocaleString()}`,
    accent: true,
  },
  {
    label: "cost today",
    value: `$${SUMMARY_STATS.cost_usd_today.toFixed(2)}`,
    sub: `/ $${SAFETY_STATUS.cost_ceiling_usd}`,
  },
  {
    label: "oracle accuracy",
    value: SUMMARY_STATS.oracle_accuracy,
    accent: true,
  },
  {
    label: "scope violations",
    value: SUMMARY_STATS.scope_violations_24h,
    danger: SUMMARY_STATS.scope_violations_24h > 0,
  },
  {
    label: "agents active",
    value: SUMMARY_STATS.agents_active,
  },
];

export default function StatsBar() {
  const killActive = SAFETY_STATUS.kill_switch_active;
  return (
    <div className="flex items-stretch gap-0 border-b border-border bg-surface overflow-x-auto shrink-0">
      {/* System status pill */}
      <div
        className={`flex items-center gap-2 px-4 border-r border-border shrink-0 ${
          killActive ? "bg-danger/5" : ""
        }`}
      >
        <StatusDot status={killActive ? "error" : "ok"} pulse={!killActive} />
        <span className="font-mono text-[10px] uppercase tracking-widest text-muted">
          {killActive ? "kill switch active" : "operational"}
        </span>
      </div>

      {stats.map((s) => (
        <div
          key={s.label}
          className="flex flex-col justify-center px-4 py-2.5 border-r border-border shrink-0 min-w-[80px]"
        >
          <div className="flex items-baseline gap-1">
            <span
              className={`font-mono text-sm font-bold ${
                s.accent
                  ? "text-accent"
                  : s.warn
                  ? "text-warning"
                  : s.danger
                  ? "text-danger"
                  : "text-foreground"
              }`}
            >
              {s.value}
            </span>
            {s.sub && (
              <span className="font-mono text-[9px] text-muted">{s.sub}</span>
            )}
          </div>
          <span className="font-mono text-[9px] text-muted uppercase tracking-wide">
            {s.label}
          </span>
        </div>
      ))}
    </div>
  );
}
