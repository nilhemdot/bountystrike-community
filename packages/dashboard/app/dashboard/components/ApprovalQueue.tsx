"use client";

import { useState } from "react";
import { Check, X, Clock, AlertTriangle } from "lucide-react";
import {
  APPROVAL_QUEUE,
  type ApprovalRequest,
  type ApprovalStatus,
} from "../mock-data";
import { Panel, TierBadge, SeverityBadge, RelativeTime } from "./ui";

const STATUS_STYLE: Record<ApprovalStatus, string> = {
  pending: "text-warning border-warning/30 bg-warning/5",
  approved: "text-success border-success/30 bg-success/5",
  rejected: "text-danger border-danger/30 bg-danger/5",
  expired: "text-muted border-muted/20 bg-muted/5",
};

const STATUS_ICON: Record<ApprovalStatus, React.ReactNode> = {
  pending: <Clock size={10} />,
  approved: <Check size={10} />,
  rejected: <X size={10} />,
  expired: <AlertTriangle size={10} />,
};

function ApprovalRow({
  req,
  onApprove,
  onReject,
}: {
  req: ApprovalRequest;
  onApprove: (id: string) => void;
  onReject: (id: string) => void;
}) {
  const isPending = req.status === "pending";

  return (
    <div className="px-4 py-3 border-b border-border-subtle space-y-2">
      <div className="flex items-start justify-between gap-2">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap mb-1">
            <TierBadge tier={req.tier} />
            <span
              className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-mono border ${STATUS_STYLE[req.status]}`}
            >
              {STATUS_ICON[req.status]}
              {req.status}
            </span>
            <SeverityBadge severity={req.severity} />
          </div>
          <p className="text-xs font-medium text-foreground leading-relaxed truncate">
            {req.finding_title}
          </p>
          <div className="flex items-center gap-3 mt-1">
            <span className="font-mono text-[10px] text-muted">{req.program}</span>
            <span className="font-mono text-[10px] text-accent font-semibold">
              ${req.payout_estimate.toLocaleString()}
            </span>
            <RelativeTime iso={req.requested_at} />
          </div>
        </div>
      </div>

      {/* Approver info */}
      {req.tier === "T3" && (
        <div className="flex items-center gap-2 text-[10px] font-mono">
          <span className="text-muted">Approver 1:</span>
          <span className={req.approver_id ? "text-success" : "text-warning"}>
            {req.approver_id ?? "awaiting"}
          </span>
          <span className="text-muted">Approver 2:</span>
          <span className={req.approver_id_2 ? "text-success" : "text-warning"}>
            {req.approver_id_2 ?? "awaiting"}
          </span>
        </div>
      )}
      {req.tier === "T1" && req.approver_id && (
        <div className="flex items-center gap-2 text-[10px] font-mono">
          <span className="text-muted">LLM reviewer:</span>
          <span className="text-info">{req.approver_id}</span>
        </div>
      )}

      {/* Reason */}
      {req.reason && (
        <p className="text-[10px] font-mono text-muted bg-surface-raised rounded px-2 py-1 border border-border-subtle">
          {req.reason}
        </p>
      )}

      {/* Actions */}
      {isPending && (
        <div className="flex items-center gap-2">
          <button
            onClick={() => onApprove(req.id)}
            className="flex items-center gap-1 px-3 py-1.5 rounded bg-success/10 border border-success/30 text-success text-[10px] font-mono font-semibold hover:bg-success/20 transition-colors"
          >
            <Check size={10} />
            Approve
          </button>
          <button
            onClick={() => onReject(req.id)}
            className="flex items-center gap-1 px-3 py-1.5 rounded bg-danger/10 border border-danger/30 text-danger text-[10px] font-mono font-semibold hover:bg-danger/20 transition-colors"
          >
            <X size={10} />
            Reject
          </button>
          <div className="flex-1 text-right">
            <span className="font-mono text-[10px] text-muted">
              expires <RelativeTime iso={req.expires_at} />
            </span>
          </div>
        </div>
      )}
    </div>
  );
}

export default function ApprovalQueue({ className }: { className?: string }) {
  const [queue, setQueue] = useState<ApprovalRequest[]>(APPROVAL_QUEUE);
  const [tierFilter, setTierFilter] = useState<"all" | "T1" | "T2" | "T3">("all");

  const pendingCount = queue.filter((r) => r.status === "pending").length;

  const handleApprove = (id: string) => {
    setQueue((prev) =>
      prev.map((r) =>
        r.id === id
          ? {
              ...r,
              status: "approved",
              approver_id: r.approver_id ?? "op-self",
              reason: "Manually approved via dashboard.",
            }
          : r
      )
    );
  };

  const handleReject = (id: string) => {
    setQueue((prev) =>
      prev.map((r) =>
        r.id === id
          ? {
              ...r,
              status: "rejected",
              reason: "Rejected via dashboard.",
            }
          : r
      )
    );
  };

  const visible = queue.filter(
    (r) => tierFilter === "all" || r.tier === tierFilter
  );

  return (
    <Panel
      title="Approval Queue"
      subtitle="T1=LLM · T2=single human · T3=two-person"
      className={className}
      actions={
        <div className="flex items-center gap-2">
          {pendingCount > 0 && (
            <span className="inline-flex items-center justify-center w-5 h-5 rounded-full bg-warning text-background text-[10px] font-mono font-bold">
              {pendingCount}
            </span>
          )}
          <div className="flex gap-1">
            {(["all", "T1", "T2", "T3"] as const).map((t) => (
              <button
                key={t}
                onClick={() => setTierFilter(t)}
                className={`px-2 py-1 rounded text-[10px] font-mono transition-colors ${
                  tierFilter === t
                    ? "bg-accent text-background"
                    : "text-muted hover:text-foreground"
                }`}
              >
                {t}
              </button>
            ))}
          </div>
        </div>
      }
    >
      <div className="overflow-y-auto">
        {visible.length === 0 && (
          <p className="text-xs text-muted text-center p-8">No requests in this view</p>
        )}
        {visible.map((req) => (
          <ApprovalRow
            key={req.id}
            req={req}
            onApprove={handleApprove}
            onReject={handleReject}
          />
        ))}
      </div>
    </Panel>
  );
}
