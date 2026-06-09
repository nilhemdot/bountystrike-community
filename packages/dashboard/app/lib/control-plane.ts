// SPDX-License-Identifier: AGPL-3.0-or-later
// Control-plane proxy switch.
//
// The dashboard is a backend-for-frontend (BFF). Every /api route first asks
// whether a real control-plane is configured. If CONTROL_PLANE_URL is set, the
// request is forwarded to the Python FastAPI service and its JSON returned
// verbatim. Otherwise the route falls back to the in-process live store
// (store.ts), so the dashboard is fully functional in local/dev/demo mode.
//
// This is the single integration seam: when the FastAPI routes land in
// control-plane/, set CONTROL_PLANE_URL (and optionally CONTROL_PLANE_TOKEN)
// and the dashboard goes live against the real backend with zero UI changes.

export function controlPlaneConfigured(): boolean {
  return Boolean(process.env.CONTROL_PLANE_URL);
}

export function controlPlaneBaseUrl(): string | null {
  const raw = process.env.CONTROL_PLANE_URL;
  if (!raw) return null;
  return raw.replace(/\/$/, "");
}

interface ProxyOptions {
  method?: string;
  body?: unknown;
  // Revalidation window (seconds) for GET proxying. 0 = always fresh.
  revalidate?: number;
}

/**
 * Forward a request to the real control-plane. Returns the parsed JSON on
 * success, or throws so the caller can fall back to the local store.
 */
export async function proxyControlPlane<T>(path: string, opts: ProxyOptions = {}): Promise<T> {
  const base = controlPlaneBaseUrl();
  if (!base) throw new Error("control-plane not configured");

  const token = process.env.CONTROL_PLANE_TOKEN;
  const headers: Record<string, string> = { "content-type": "application/json" };
  if (token) headers["authorization"] = `Bearer ${token}`;

  const res = await fetch(`${base}${path}`, {
    method: opts.method ?? "GET",
    headers,
    body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
    // GETs use ISR-style revalidation; mutations always hit the network.
    next: opts.method && opts.method !== "GET" ? undefined : { revalidate: opts.revalidate ?? 0 },
    cache: opts.method && opts.method !== "GET" ? "no-store" : undefined,
  });

  if (!res.ok) {
    throw new Error(`control-plane ${path} responded ${res.status}`);
  }
  return (await res.json()) as T;
}
