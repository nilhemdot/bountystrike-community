// SPDX-License-Identifier: AGPL-3.0-or-later
// GET /api/state — full dashboard snapshot.
//
// The dashboard polls this single endpoint via SWR. It returns every panel's
// data in one round-trip plus a `source` field indicating whether the data came
// from the real control-plane proxy or the local live store.

import { NextResponse } from "next/server";
import { controlPlaneConfigured, proxyControlPlane } from "@/app/lib/control-plane";
import {
  getFindings,
  getPrograms,
  getApprovals,
  getEvents,
  getSafety,
  getEvidence,
  getSummary,
} from "@/app/lib/store";

export const dynamic = "force-dynamic";

export async function GET() {
  if (controlPlaneConfigured()) {
    try {
      const snapshot = await proxyControlPlane<Record<string, unknown>>("/api/state");
      return NextResponse.json({ ...snapshot, source: "control-plane" });
    } catch (err) {
      // Surface the proxy failure but degrade gracefully to the local store so
      // the dashboard never goes blank if the backend is momentarily down.
      console.log("[v0] control-plane proxy failed, serving local store:", (err as Error).message);
    }
  }

  return NextResponse.json({
    findings: getFindings(),
    programs: getPrograms(),
    approvals: getApprovals(),
    events: getEvents(),
    safety: getSafety(),
    evidence: getEvidence(),
    summary: getSummary(),
    source: controlPlaneConfigured() ? "control-plane-degraded" : "local",
    ts: new Date().toISOString(),
  });
}
