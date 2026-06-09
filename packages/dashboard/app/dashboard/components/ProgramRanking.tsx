"use client";

import { useState } from "react";
import { TrendingUp, Zap } from "lucide-react";
import { PROGRAMS, type Program } from "../mock-data";
import { Panel, PlatformChip, ScoreBar, RelativeTime } from "./ui";

function EVRing({ score }: { score: number }) {
  const pct = score * 100;
  const r = 16;
  const circ = 2 * Math.PI * r;
  const dash = (pct / 100) * circ;

  const color =
    score >= 0.85 ? "#00e5a0" : score >= 0.75 ? "#f59e0b" : "#38bdf8";

  return (
    <svg width="40" height="40" viewBox="0 0 40 40" aria-hidden>
      <circle
        cx="20"
        cy="20"
        r={r}
        fill="none"
        stroke="var(--surface-raised)"
        strokeWidth="3"
      />
      <circle
        cx="20"
        cy="20"
        r={r}
        fill="none"
        stroke={color}
        strokeWidth="3"
        strokeDasharray={`${dash} ${circ}`}
        strokeLinecap="round"
        transform="rotate(-90 20 20)"
      />
      <text
        x="20"
        y="24"
        textAnchor="middle"
        fontSize="9"
        fill={color}
        fontFamily="var(--font-geist-mono)"
        fontWeight="700"
      >
        {pct.toFixed(0)}
      </text>
    </svg>
  );
}

function ProgramRow({
  program,
  rank,
  selected,
  onClick,
}: {
  program: Program;
  rank: number;
  selected: boolean;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className={`w-full text-left flex items-center gap-3 px-4 py-3 border-b border-border-subtle hover:bg-surface-raised transition-colors ${
        selected ? "bg-surface-raised" : ""
      }`}
    >
      <span className="font-mono text-xs text-muted w-5 shrink-0">#{rank}</span>
      <EVRing score={program.ev_score} />
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 mb-0.5">
          <span className="text-xs font-semibold text-foreground font-mono">
            {program.handle}
          </span>
          <PlatformChip platform={program.platform} />
          {program.kev_matches > 0 && (
            <span className="inline-flex items-center gap-0.5 px-1 py-0.5 rounded bg-danger/10 border border-danger/20 text-[9px] font-mono text-danger">
              <Zap size={8} />
              KEV×{program.kev_matches}
            </span>
          )}
        </div>
        <div className="flex items-center gap-3">
          <span className="font-mono text-[10px] text-muted">
            ${program.payout_min.toLocaleString()}–${program.payout_max.toLocaleString()}
          </span>
          <span className="font-mono text-[10px] text-muted">
            dup {Math.round(program.dup_rate * 100)}%
          </span>
          {program.last_scan && (
            <RelativeTime iso={program.last_scan} />
          )}
        </div>
      </div>
      <div className="text-right shrink-0">
        <div className="text-xs font-mono font-bold text-accent">
          {(program.ev_score * 100).toFixed(1)}
        </div>
        <div className="text-[9px] font-mono text-muted">EV</div>
      </div>
    </button>
  );
}

function ProgramDetail({ program }: { program: Program }) {
  return (
    <div className="p-4 space-y-4">
      <div>
        <p className="text-sm font-semibold text-foreground font-mono">
          {program.handle}
        </p>
        <div className="flex items-center gap-2 mt-1">
          <PlatformChip platform={program.platform} />
          {program.kev_matches > 0 && (
            <span className="font-mono text-[10px] text-danger">
              {program.kev_matches} KEV match{program.kev_matches !== 1 ? "es" : ""}
            </span>
          )}
        </div>
      </div>

      <div className="flex items-center justify-between">
        <EVRing score={program.ev_score} />
        <div className="text-right">
          <p className="text-2xl font-mono font-bold text-accent">
            {(program.ev_score * 100).toFixed(1)}
          </p>
          <p className="text-[10px] font-mono text-muted">EV Score</p>
        </div>
      </div>

      <div className="space-y-2">
        <p className="text-[10px] uppercase tracking-widest text-muted font-mono">
          EV factors
        </p>
        <ScoreBar value={program.f_payout} label="payout" color="accent" />
        <ScoreBar value={program.f_saturation} label="saturation" color="warning" />
        <ScoreBar value={program.f_ops} label="ops_load" color="info" />
        <ScoreBar value={program.f_fit} label="fit" color="success" />
        <ScoreBar value={program.f_cve} label="cve_sig" color="danger" />
      </div>

      <div className="grid grid-cols-2 gap-x-4 gap-y-2 text-[10px] font-mono">
        {[
          ["Min payout", `$${program.payout_min.toLocaleString()}`],
          ["Max payout", `$${program.payout_max.toLocaleString()}`],
          ["Dup rate", `${Math.round(program.dup_rate * 100)}%`],
          ["Active findings", program.active_findings.toString()],
        ].map(([k, v]) => (
          <div key={k}>
            <p className="text-muted uppercase tracking-wide">{k}</p>
            <p className="text-foreground">{v}</p>
          </div>
        ))}
      </div>
    </div>
  );
}

export default function ProgramRanking({ className }: { className?: string }) {
  const sorted = [...PROGRAMS].sort((a, b) => b.ev_score - a.ev_score);
  const [selected, setSelected] = useState<Program>(sorted[0]);

  return (
    <Panel
      title="Program Ranking"
      subtitle="EV = f(payout, saturation, ops, fit, cve_signal)"
      className={className}
      actions={
        <div className="flex items-center gap-1 text-[10px] font-mono text-muted">
          <TrendingUp size={12} className="text-accent" />
          <span>{sorted.length} programs</span>
        </div>
      }
    >
      <div className="flex h-full min-h-0">
        <div className="flex-1 overflow-y-auto">
          {sorted.map((p, i) => (
            <ProgramRow
              key={p.handle}
              program={p}
              rank={i + 1}
              selected={selected.handle === p.handle}
              onClick={() => setSelected(p)}
            />
          ))}
        </div>
        <div className="w-56 border-l border-border overflow-y-auto shrink-0">
          <ProgramDetail program={selected} />
        </div>
      </div>
    </Panel>
  );
}
