"use client";

import { useState } from "react";
import { ChevronRight } from "lucide-react";
import {
  FINDINGS,
  STATUS_ORDER,
  STATUS_LABEL,
  type Finding,
  type FindingStatus,
} from "../mock-data";
import { Panel, SeverityBadge, PlatformChip, RelativeTime, HashSpan } from "./ui";

const STATUS_COLOR: Record<FindingStatus, string> = {
  hypothesis: "text-muted border-muted/20 bg-muted/5",
  exploit_attempt: "text-info border-info/20 bg-info/5",
  exploit_candidate: "text-info border-info/30 bg-info/10",
  validation_pending: "text-warning border-warning/20 bg-warning/5",
  validated: "text-warning border-warning/30 bg-warning/10",
  dedup_check: "text-[#e879f9] border-[#e879f9]/20 bg-[#e879f9]/5",
  approval_pending_t1: "text-info border-info/30 bg-info/10",
  approval_pending_t2: "text-warning border-warning/30 bg-warning/10",
  approval_pending_t3: "text-danger border-danger/30 bg-danger/10",
  approved: "text-accent border-accent/30 bg-accent/10",
  submitted: "text-accent border-accent/30 bg-accent/10",
  confirmed: "text-success border-success/30 bg-success/10",
  rejected: "text-danger border-danger/20 bg-danger/5",
  duplicate: "text-muted border-muted/20 bg-muted/5",
  wont_fix: "text-muted border-muted/20 bg-muted/5",
  archived: "text-muted border-muted/10 bg-transparent",
};

function StatusBadge({ status }: { status: FindingStatus }) {
  return (
    <span
      className={`inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-mono font-medium border ${STATUS_COLOR[status]}`}
    >
      {STATUS_LABEL[status]}
    </span>
  );
}

function FindingRow({
  finding,
  onClick,
  selected,
}: {
  finding: Finding;
  onClick: () => void;
  selected: boolean;
}) {
  return (
    <button
      onClick={onClick}
      className={`w-full text-left flex items-start gap-3 px-4 py-3 border-b border-border-subtle hover:bg-surface-raised transition-colors ${
        selected ? "bg-surface-raised" : ""
      }`}
    >
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 flex-wrap mb-1">
          <StatusBadge status={finding.status} />
          <SeverityBadge severity={finding.severity} />
          <PlatformChip platform={finding.platform} />
        </div>
        <p className="text-xs font-medium text-foreground truncate leading-relaxed">
          {finding.title}
        </p>
        <div className="flex items-center gap-3 mt-1">
          <span className="font-mono text-[10px] text-muted">{finding.program}</span>
          <span className="font-mono text-[10px] text-muted">{finding.vuln_class}</span>
          <HashSpan hash={finding.chain_hash} />
          <RelativeTime iso={finding.updated_at} />
        </div>
      </div>
      <div className="flex flex-col items-end gap-1 shrink-0">
        <span className="font-mono text-xs text-accent font-semibold">
          ${finding.payout_estimate.toLocaleString()}
        </span>
        <ChevronRight size={12} className="text-muted" />
      </div>
    </button>
  );
}

function FindingDetail({ finding }: { finding: Finding }) {
  const stageIdx = STATUS_ORDER.indexOf(finding.status);

  return (
    <div className="p-4 space-y-4">
      <div>
        <p className="text-sm font-semibold text-foreground leading-relaxed">
          {finding.title}
        </p>
        <div className="flex items-center gap-2 mt-2 flex-wrap">
          <StatusBadge status={finding.status} />
          <SeverityBadge severity={finding.severity} />
          <PlatformChip platform={finding.platform} />
        </div>
      </div>

      {/* Pipeline progress */}
      <div>
        <p className="text-[10px] uppercase tracking-widest text-muted font-mono mb-2">
          Pipeline stage
        </p>
        <div className="flex items-center gap-0.5 overflow-x-auto pb-1">
          {STATUS_ORDER.slice(0, 12).map((s, i) => (
            <div
              key={s}
              className={`h-1.5 flex-1 rounded-sm min-w-[6px] ${
                i < stageIdx
                  ? "bg-success"
                  : i === stageIdx
                  ? "bg-accent"
                  : "bg-surface-raised"
              }`}
              title={STATUS_LABEL[s]}
            />
          ))}
        </div>
        <p className="text-[10px] font-mono text-muted mt-1">
          Stage {stageIdx + 1} / {STATUS_ORDER.length} — {STATUS_LABEL[finding.status]}
        </p>
      </div>

      {/* Metadata grid */}
      <div className="grid grid-cols-2 gap-x-4 gap-y-2">
        {[
          ["ID", finding.id],
          ["Program", finding.program],
          ["Vuln class", finding.vuln_class],
          ["Agent", finding.agent],
          ["Payout est.", `$${finding.payout_estimate.toLocaleString()}`],
          ["Oracle TPR", finding.oracle_tpr !== null ? finding.oracle_tpr.toString() : "—"],
        ].map(([k, v]) => (
          <div key={k}>
            <p className="text-[10px] text-muted font-mono uppercase tracking-wide">{k}</p>
            <p className="text-xs text-foreground font-mono">{v}</p>
          </div>
        ))}
      </div>

      <div>
        <p className="text-[10px] uppercase tracking-widest text-muted font-mono mb-1">
          Chain hash
        </p>
        <p className="font-mono text-[10px] text-accent break-all">
          sha256:{finding.chain_hash}
        </p>
      </div>
    </div>
  );
}

export default function FindingsPipeline({ className }: { className?: string }) {
  const [filter, setFilter] = useState<"active" | "terminal" | "all">("active");
  const [selected, setSelected] = useState<Finding | null>(FINDINGS[0]);

  const activeStatuses: FindingStatus[] = [
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
  ];
  const terminalStatuses: FindingStatus[] = ["confirmed", "rejected", "duplicate", "wont_fix", "archived"];

  const visible = FINDINGS.filter((f) => {
    if (filter === "active") return activeStatuses.includes(f.status);
    if (filter === "terminal") return terminalStatuses.includes(f.status);
    return true;
  });

  const countByStatus = STATUS_ORDER.reduce(
    (acc, s) => {
      acc[s] = FINDINGS.filter((f) => f.status === s).length;
      return acc;
    },
    {} as Record<FindingStatus, number>
  );

  return (
    <Panel
      title="Findings Pipeline"
      subtitle={`${FINDINGS.length} total findings · 16-state ENUM`}
      actions={
        <div className="flex gap-1">
          {(["active", "terminal", "all"] as const).map((f) => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              className={`px-2 py-1 rounded text-[10px] font-mono uppercase tracking-wide transition-colors ${
                filter === f
                  ? "bg-accent text-background"
                  : "text-muted hover:text-foreground"
              }`}
            >
              {f}
            </button>
          ))}
        </div>
      }
      className={className}
    >
      {/* Status count strip */}
      <div className="flex gap-1 px-4 py-2 border-b border-border-subtle overflow-x-auto shrink-0">
        {STATUS_ORDER.filter((s) => countByStatus[s] > 0).map((s) => (
          <span
            key={s}
            className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[9px] font-mono border whitespace-nowrap ${STATUS_COLOR[s]}`}
          >
            {STATUS_LABEL[s].replace(" Approval", "")} {countByStatus[s]}
          </span>
        ))}
      </div>

      <div className="flex h-full min-h-0">
        {/* List */}
        <div className="flex-1 overflow-y-auto">
          {visible.length === 0 && (
            <p className="text-xs text-muted text-center p-8">No findings in this view</p>
          )}
          {visible.map((f) => (
            <FindingRow
              key={f.id}
              finding={f}
              selected={selected?.id === f.id}
              onClick={() => setSelected(f)}
            />
          ))}
        </div>

        {/* Detail pane */}
        {selected && (
          <div className="w-64 border-l border-border overflow-y-auto shrink-0">
            <FindingDetail finding={selected} />
          </div>
        )}
      </div>
    </Panel>
  );
}
