# BountyStrike Operator Dashboard — Design Spec

Date: 2026-06-09
Status: Approved (brainstorming session)
Scope: v1 = hunt monitoring + approval/kill-switch action center. Findings browser is v1-minimal; cost/EV analytics and hunt-launch are fast-follow (out of this spec's build scope).

## Goals

A multi-user web operator console for BountyStrike:

1. **Hunt monitoring** — live view of the agent pipeline (recon → scan → exploit → validate → report) per program.
2. **Approval workflow** — act on `approval_queue` entries (T2/T3 sign-offs) from the browser.
3. **Kill-switch & safety** — view and toggle the kill switch with audit trail.
4. **Findings (minimal)** — filterable findings table + detail drawer so monitoring drill-downs land somewhere.

Deferred (explicitly out of v1): full findings browser, cost/EV analytics pages, launching/configuring hunts from the UI (orchestrator is CLI-only today; needs a service trigger first), external OIDC.

## Key facts about current state (verified 2026-06-09)

- Control-plane is a **library of domains + Hatchet tasks; no FastAPI app entry exists**. Caddy already proxies `/api/*` → port 8000, but nothing listens. This spec includes bootstrapping the HTTP server.
- `approval_gate` domain already ships `enqueue / approve / reject / get / list_pending / wait_for_approval` (`control-plane/src/control_plane/domains/approval_gate/queue.py`) over the `approval_queue` table (migration 04). Tiers T0–T3; T3 requires two distinct approvers (`approver_id` ≠ `approver_id_2`).
- `safety` domain ships `KillSwitchStore` protocol with `RedisKillSwitchStore` (get_state / set_state with TTL / clear) and an in-memory variant.
- `approve.py` CLI talks directly to the same queue helpers — it keeps working unchanged; dashboard is a second front door over the same domain functions.
- Existing SQL migrations 00–13; next is **14**.
- No frontend exists anywhere in the repo (only Grafana JSON dashboards in `infra/grafana/dashboards`).

## Architecture

```
browser ── Caddy :80
            ├── /            → dashboard SPA (static files, Caddy file_server + SPA fallback)
            └── /api/*       → control-plane :8000 (FastAPI, NEW main.py)
                                 ├── core/http/         app factory, asyncpg pool lifespan
                                 ├── domains/dashboard/  auth (users, sessions, roles)
                                 │                       read endpoints (overview, hunts, findings, approvals)
                                 │                       SSE activity stream
                                 │                       action endpoints → approval_gate.queue
                                 │                                        → safety.KillSwitchStore
                                 └── existing domains untouched
dashboard/   (NEW top-level dir: Vite + React 18 + TS + Tailwind + shadcn/ui)
```

Decisions and rationale:

- **BFF inside control-plane** (chosen over a separate dashboard-api service): reuses asyncpg pool, Pydantic models, DDD layout, docker network; approval/kill-switch logic stays in one place. A separate service would duplicate DB models and domain logic for no isolation benefit at this scale.
- **SPA static, no Node at runtime**: `dashboard/` builds to `dashboard/dist`; Caddy volume-mounts and serves it.
- **Hybrid freshness**: REST polling for tables/analytics; one SSE stream for the activity feed. Kill-switch state additionally polls every 5 s independent of SSE health — safety state never relies on push alone.
- **SSE transport**: Postgres `LISTEN/NOTIFY` on channel `dashboard_events`. v1 emitters: the dashboard API itself (its own mutations) plus a lightweight DB-poll bridge inside the server that diffs hot tables and synthesizes events — agent/orchestrator code is NOT touched in v1. NOTIFY emitters can be added to agents incrementally later.

## Auth & roles

- `users`: `id, username (unique), password_hash (argon2id), role ('viewer'|'operator'), disabled, created_at`.
- `sessions`: `id` is a random 256-bit token **stored hashed**; `user_id, expires_at, created_at, ip`. 7-day expiry, sliding renewal.
- Cookie: `__Host-bs_session`, HttpOnly, Secure, SameSite=Lax.
- CSRF: double-submit token via `X-CSRF-Token` header, required on every mutating route.
- Login rate-limited 5/min/IP via existing Redis.
- Bootstrap: `scripts/dashboard_user.py create <username> --role operator` (mirrors approve.py pattern; prompts for password, never takes it as argv). No self-registration. Password change via same CLI in v1.
- Role enforcement server-side per route: `viewer` = read-only (403 on all mutations); `operator` = approve/reject, kill-switch.
- Every mutation writes an `audit_log` row with actor = dashboard username.

Migration `infra/sql/14_dashboard_auth.sql` creates both tables (idempotent, matching existing migration style).

## API surface (all under `/api/dashboard/`)

| Route | Method | Role | Serves |
|---|---|---|---|
| `auth/login` | POST | — | verify password, set session cookie, return user+role+CSRF token |
| `auth/logout` | POST | session | destroy session |
| `auth/me` | GET | session | current user, role, CSRF token |
| `overview` | GET | viewer | findings counts by status, pending approval count + worst SLA, active-hunt summary, kill-switch state |
| `hunts/active` | GET | viewer | per-program finding counts per pipeline stage, recent agent activity (from audit_log) |
| `findings` | GET | viewer | paged list; filters: status, program, CWE |
| `findings/{id}` | GET | viewer | detail + audit-chain entries |
| `approvals` | GET | viewer | pending queue entries: tier, age, SLA remaining, poc_text, program |
| `approvals/{finding_id}/approve` | POST | operator | wraps `queue_approve`; body: `{reason}`; T3 second-distinct-approver enforced by domain |
| `approvals/{finding_id}/reject` | POST | operator | wraps `queue_reject`; `reason` required |
| `killswitch` | GET | viewer | current state |
| `killswitch` | POST | operator | engage/clear; `reason` required; audit row |
| `events` | GET (SSE) | viewer | activity stream |

Conventions:

- Pydantic response models on every endpoint (project rule: Pydantic at every input boundary; applied to outputs too for typed client generation).
- Pipeline stages derived from `finding_status` enum groupings (recon → scan → exploit → validate → report buckets).
- `poc_text` is plain text end-to-end; the UI renders it in a monospace block, never as HTML.

SSE event types: `finding_status_changed`, `approval_requested`, `approval_decided`, `killswitch_changed`, `agent_activity`. Envelope: `{type, ts, program_handle?, finding_id?, payload}`.

## Frontend

Stack: Vite + React 18 + TypeScript, Tailwind + shadcn/ui, TanStack Query (polling/cache/mutations), TanStack Router, Recharts. Dark theme default.

Pages:

1. **Login** (`/login`) — plain form.
2. **Overview** (`/`) — status cards (active hunt, findings by status, pending approvals + worst SLA, kill-switch banner when engaged), pipeline funnel chart, live activity feed (SSE) in right rail.
3. **Approvals** (`/approvals`) — action center. Table: finding, tier badge, age, SLA countdown, program. Row → drawer: PoC text (monospace plain text), finding context, evidence summary, Approve/Reject with reason field + confirm step. T3 shows "needs second approver" state. Viewer sees table without action buttons.
4. **Hunt monitor** (`/hunts`) — per-program pipeline board (stage columns with finding counts), recent agent events grouped by agent, kill-switch control block (engage/clear with reason; red; double-confirm).
5. **Findings** (`/findings`) — v1-minimal filterable table + detail drawer with audit chain.

Data flow:

- TanStack Query polling: overview + approvals every 10 s, hunts every 15 s, findings on demand, kill-switch every 5 s. Mutations invalidate affected queries.
- Single `EventSource` on `/api/dashboard/events`: events append to the activity feed and trigger targeted query invalidation. Feed feels live; tables self-correct within one poll regardless.
- SSE reconnects with backoff; on disconnect show "feed disconnected" banner — polling keeps every page functional. Never blank a page on feed loss.
- Mutations are never optimistic: approval and kill-switch UI shows server-confirmed state only.

## Error handling

- Error envelope: `{error: {code, message}}` on all non-2xx.
- Domain exceptions (`ApprovalQueueError`, `NotApprovableError`, `DuplicateApprovalError`) → 409/422 with human-readable message, surfaced as toast.
- 401 anywhere → redirect to login.
- Approve/reject race (already decided elsewhere) → 409; drawer refreshes to decided state; no silent retry.
- Kill-switch POST failure is loud: persistent red banner until server-confirmed, not a transient toast.
- SSE bridge/LISTEN failure: server logs, clients degrade to polling automatically.

## Testing

- Backend unit (pytest-asyncio, `tests/`): auth (argon2 hashing, session expiry, CSRF, role gates), endpoint tests using existing `InMemoryApprovalRequestStore` / `InMemoryKillSwitchStore`.
- Backend integration (`tests/integration/`, `@pytest.mark.integration`): login → approve → audit-row flow; T3 distinct-approver; viewer-403 on every mutation; SSE event delivery via LISTEN/NOTIFY.
- Frontend: Vitest + Testing Library for approval drawer + kill-switch confirm flows; one Playwright smoke (login → see pending approval → approve → row leaves queue) against local Docker stack, integration-marked.
- Security invariants as explicit tests: viewer cannot mutate; cookie flags; CSRF rejection; `poc_text` inert rendering (`dangerouslySetInnerHTML` banned by lint rule).

## Deployment

- `dashboard/` builds to `dashboard/dist`; Caddy volume-mounts it; Caddyfile gains static route with SPA fallback (existing `/api/*`, `/langfuse/*`, `/hatchet/*` routes unchanged).
- control-plane image gains uvicorn entrypoint `control_plane.main:app` on :8000 (Caddy route already points there).
- New migration `14_dashboard_auth.sql` applied by existing init path.
- New deps: control-plane — `argon2-cffi`, `sse-starlette` only (`fastapi>=0.115` and `uvicorn[standard]>=0.32` already declared in `control-plane/pyproject.toml`, verified 2026-06-09). Dashboard — standard Vite/React toolchain, lockfile committed.

## Build order (for the implementation plan)

1. Migration 14 + FastAPI app bootstrap (`main.py`, app factory, pool lifespan, health route).
2. Auth domain + user CLI + session middleware + CSRF.
3. Read endpoints (overview, hunts, approvals, findings).
4. Action endpoints (approve/reject, kill-switch) + audit rows.
5. SSE stream + DB-poll bridge.
6. SPA scaffold + login + overview.
7. Approvals page + hunt monitor + findings-minimal.
8. Caddy/static deployment + Playwright smoke.
