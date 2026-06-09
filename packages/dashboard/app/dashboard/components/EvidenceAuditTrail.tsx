"use client";

import { useState } from "react";
import { Link2, CheckCircle2, FileText, Terminal, Upload, Key } from "lucide-react";
import { EVIDENCE_CHAIN, type EvidenceArtifact } from "../mock-data";
import { Panel, RelativeTime } from "./ui";

const TYPE_ICON: Record<EvidenceArtifact["artifact_type"], React.ReactNode> = {
  request_transcript: <Upload size={10} />,
  response_transcript: <FileText size={10} />,
  oracle_data: <CheckCircle2 size={10} />,
  repro_command: <Terminal size={10} />,
  scope_jwt: <Key size={10} />,
};

const TYPE_COLOR: Record<EvidenceArtifact["artifact_type"], string> = {
  request_transcript: "text-info border-info/20 bg-info/5",
  response_transcript: "text-[#e879f9] border-[#e879f9]/20 bg-[#e879f9]/5",
  oracle_data: "text-success border-success/20 bg-success/5",
  repro_command: "text-warning border-warning/20 bg-warning/5",
  scope_jwt: "text-accent border-accent/20 bg-accent/5",
};

function ArtifactCard({
  artifact,
  isFirst,
}: {
  artifact: EvidenceArtifact;
  isFirst: boolean;
}) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="relative pl-8">
      {/* Chain line */}
      {!isFirst && (
        <div className="absolute left-3.5 -top-4 bottom-1/2 w-px bg-border" />
      )}
      <div className="absolute left-3.5 top-1/2 bottom-0 w-px bg-border" />

      {/* Chain link node */}
      <div
        className={`absolute left-2 top-1/2 -translate-y-1/2 w-3 h-3 rounded-full border-2 ${
          artifact.chain_valid
            ? "border-success bg-surface"
            : "border-danger bg-surface"
        }`}
      />

      <button
        onClick={() => setExpanded((v) => !v)}
        className="w-full text-left px-3 py-2.5 mb-1 rounded-lg bg-surface-raised border border-border hover:border-accent/30 transition-colors"
      >
        <div className="flex items-start gap-2">
          <span
            className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[9px] font-mono border shrink-0 ${
              TYPE_COLOR[artifact.artifact_type]
            }`}
          >
            {TYPE_ICON[artifact.artifact_type]}
            {artifact.artifact_type.replace("_", " ")}
          </span>
          <div className="flex-1 min-w-0">
            <p className="font-mono text-[10px] text-foreground truncate">
              {artifact.finding_title}
            </p>
            <div className="flex items-center gap-2 mt-0.5">
              <span className="font-mono text-[9px] text-muted">
                {(artifact.size_bytes / 1024).toFixed(1)} KB
              </span>
              <RelativeTime iso={artifact.created_at} />
              {artifact.chain_valid ? (
                <span className="font-mono text-[9px] text-success flex items-center gap-0.5">
                  <Link2 size={8} /> chain valid
                </span>
              ) : (
                <span className="font-mono text-[9px] text-danger">chain BROKEN</span>
              )}
            </div>
          </div>
        </div>

        {expanded && (
          <div className="mt-3 space-y-2 text-left">
            <div>
              <p className="text-[9px] font-mono text-muted uppercase tracking-wide mb-0.5">
                Content hash
              </p>
              <p className="font-mono text-[9px] text-accent break-all leading-relaxed">
                {artifact.content_hash}
              </p>
            </div>
            <div>
              <p className="text-[9px] font-mono text-muted uppercase tracking-wide mb-0.5">
                Prev audit hash
              </p>
              <p className="font-mono text-[9px] text-muted break-all leading-relaxed">
                {artifact.prev_audit_hash}
              </p>
            </div>
            <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-[9px] font-mono">
              <div>
                <p className="text-muted">R2 key</p>
                <p className="text-foreground break-all">{artifact.r2_key}</p>
              </div>
              <div>
                <p className="text-muted">JTI</p>
                <p className="text-foreground">{artifact.scope_token_jti}</p>
              </div>
            </div>
          </div>
        )}
      </button>
    </div>
  );
}

export default function EvidenceAuditTrail({ className }: { className?: string }) {
  const chainOk = EVIDENCE_CHAIN.every((a) => a.chain_valid);

  return (
    <Panel
      title="Evidence / Audit Chain"
      subtitle="SHA-256 hash-chained artifacts · content-addressable"
      className={className}
      actions={
        <div className="flex items-center gap-2">
          <span
            className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-mono border ${
              chainOk
                ? "text-success border-success/30 bg-success/5"
                : "text-danger border-danger/30 bg-danger/5"
            }`}
          >
            <Link2 size={9} />
            {chainOk ? "chain intact" : "chain broken!"}
          </span>
          <span className="text-[10px] font-mono text-muted">
            {EVIDENCE_CHAIN.length} artifacts
          </span>
        </div>
      }
    >
      <div className="px-4 py-4 space-y-2 overflow-y-auto">
        <p className="text-[9px] font-mono text-muted mb-3">
          Click any artifact to inspect SHA-256 hash chain. Each prev_audit_hash anchors
          to the prior artifact — tamper-evident audit log.
        </p>
        {EVIDENCE_CHAIN.map((artifact, i) => (
          <ArtifactCard
            key={artifact.id}
            artifact={artifact}
            isFirst={i === 0}
          />
        ))}
      </div>
    </Panel>
  );
}
