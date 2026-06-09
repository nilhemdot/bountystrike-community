"use client";

import { useState, useEffect } from "react";
import { Terminal, Shield } from "lucide-react";

export default function Header() {
  const [time, setTime] = useState<string>("");

  useEffect(() => {
    const update = () =>
      setTime(
        new Date().toLocaleTimeString("en-US", {
          hour: "2-digit",
          minute: "2-digit",
          second: "2-digit",
          hour12: false,
        })
      );
    update();
    const id = setInterval(update, 1000);
    return () => clearInterval(id);
  }, []);

  return (
    <header className="flex items-center justify-between px-5 py-3 border-b border-border bg-surface shrink-0">
      <div className="flex items-center gap-3">
        <div className="flex items-center justify-center w-7 h-7 rounded bg-accent/10 border border-accent/20">
          <Shield size={14} className="text-accent" />
        </div>
        <div>
          <h1 className="font-mono text-sm font-bold text-foreground tracking-tight">
            BountyStrike
          </h1>
          <p className="font-mono text-[9px] text-muted uppercase tracking-widest">
            v5 control plane · community edition
          </p>
        </div>
      </div>

      <div className="flex items-center gap-5">
        <div className="hidden md:flex items-center gap-4 text-[10px] font-mono text-muted">
          <span>claude-opus-4-5 · deepseek-v3 · haiku-3-5</span>
          <span className="text-border">|</span>
          <span>postgres 17 + pgvector</span>
          <span className="text-border">|</span>
          <span>15 MCP servers</span>
        </div>
        <div className="flex items-center gap-2">
          <Terminal size={12} className="text-muted" />
          <span className="font-mono text-xs text-muted tabular-nums">{time}</span>
        </div>
      </div>
    </header>
  );
}
