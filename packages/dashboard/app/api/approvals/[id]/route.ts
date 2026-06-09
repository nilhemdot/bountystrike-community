// SPDX-License-Identifier: AGPL-3.0-or-later
// POST /api/approvals/[id] — approve or reject an approval request.
//
// Body: { decision: "approve" | "reject", approver_id?: string, reason?: string }
// Proxies to the control-plane's approval_gate domain when configured,
// otherwise mutates the local live store (T3 two-person logic included).

import { NextResponse } from "next/server";
import { controlPlaneConfigured, proxyControlPlane } from "@/app/lib/control-plane";
import { decideApproval } from "@/app/lib/store";

export const dynamic = "force-dynamic";

export async function POST(req: Request, ctx: { params: Promise<{ id: string }> }) {
  const { id } = await ctx.params;
  let body: { decision?: string; approver_id?: string; reason?: string };
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "invalid JSON body" }, { status: 400 });
  }

  const decision = body.decision;
  if (decision !== "approve" && decision !== "reject") {
    return NextResponse.json({ error: "decision must be 'approve' or 'reject'" }, { status: 400 });
  }
  const approverId = body.approver_id ?? "op-console";

  if (controlPlaneConfigured()) {
    try {
      const result = await proxyControlPlane(`/api/approvals/${id}`, {
        method: "POST",
        body: { decision, approver_id: approverId, reason: body.reason ?? null },
      });
      return NextResponse.json({ request: result, source: "control-plane" });
    } catch (err) {
      return NextResponse.json(
        { error: "control-plane unavailable", detail: (err as Error).message },
        { status: 502 },
      );
    }
  }

  const updated = decideApproval(id, decision, approverId, body.reason ?? null);
  if (!updated) {
    return NextResponse.json({ error: "approval request not found" }, { status: 404 });
  }
  return NextResponse.json({ request: updated, source: "local" });
}
