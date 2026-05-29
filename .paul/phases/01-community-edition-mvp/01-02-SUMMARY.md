# 01-02 SUMMARY — Hatchet v1 Workflow Runtime

**Phase:** 01-community-edition-mvp · **Plan:** 02 · **Status:** APPLY ✓ (all 8 ACs verified live)
**Date:** 2026-05-29

---

## Outcome

The Hatchet v1 durable-execution backbone is live. A self-hosted `hatchet-lite`
engine (its own isolated Postgres) runs in compose; a v1 function-based
`@hatchet.task` (`bs-heartbeat`) registers from a worker process, and a run
triggered from `scripts/orchestrator.py` completed end-to-end (`trigger →
engine → worker → result`) against the running engine — proven empirically, not
by import.

## Acceptance Criteria — all PASS

| # | Criterion | Evidence |
|---|-----------|----------|
| AC-1 | hatchet-sdk pinned, resolves under uv | `hatchet-sdk==1.33.6` in `control-plane/pyproject.toml`; `import hatchet_sdk` OK (`m.version`=1.33.6); `uv lock` + `uv sync --all-packages` exit 0 |
| AC-2 | engine in compose, pinned, config valid, healthy | `hatchet-lite:v0.86.18`; `docker compose config` VALID; container `healthy` at 45s, restarts=0; `/api/ready`→200 |
| AC-3 | v1 `@hatchet.task` + Pydantic input + async handler; no legacy API | `tasks.py`: `@hatchet.task(name="bs-heartbeat", input_validator=HeartbeatInput)`, `async def heartbeat(input, ctx)`; `grep @hatchet.workflow`=0 |
| AC-4 | worker registers task against engine | worker log (verbatim): `🪓 starting runner...`; client connected to engine over insecure gRPC :7077; 0 errors |
| AC-5 | triggered run reaches SUCCEEDED | `orchestrator.py trigger-heartbeat "ac5-1780042535"` (exit 0) → `aio_run` returned `{'echo': 'ac5-1780042535', 'completed_at': '2026-05-29T08:15:36+00:00'}` (unique marker echoed back ⇒ this exact run executed; blocking aio_run returns only on success); worker log: `rx: start step run … bs-heartbeat` → `run: start step` → `finished step run … bs-heartbeat`, 0 errors |
| AC-6 | single shared client | `workflows/client.py` defines one `hatchet = Hatchet()`; imported by `tasks.py` + `worker.py`; no other `Hatchet()` construction |
| AC-7 | no new ruff violations on touched files | `ruff check control-plane/src/control_plane/workflows/` → "All checks passed!" exit 0. orchestrator.py has 2 ruff errors at lines 75 (I001) + 771 (E501) — both PRE-EXISTING (my added code starts at line 793; confirmed clean). No NEW violations introduced. `py_compile` OK on all 5 files. |
| AC-8 | engine DB isolated from bs-postgres | engine `DATABASE_URL`=`hatchet@hatchet-postgres:5432/hatchet`; app DB unchanged (`bs@postgres/bountystrike`) |

## Files

**Added**
- `control-plane/src/control_plane/workflows/__init__.py`
- `control-plane/src/control_plane/workflows/client.py` — single shared `Hatchet()` (AC-6)
- `control-plane/src/control_plane/workflows/tasks.py` — `bs-heartbeat` v1 task
- `control-plane/src/control_plane/workflows/worker.py` — `python -m control_plane.workflows.worker`

**Modified**
- `control-plane/pyproject.toml` — `hatchet-sdk==1.33.6`
- `infra/docker/docker-compose.yml` — replaced broken engine block with `hatchet-postgres` + `hatchet-lite`; volumes `hatchet_data`→`hatchet_lite_postgres_data`+`hatchet_lite_config`; control-plane `HATCHET_CLIENT_GRPC_HOST` 7070→7077
- `scripts/orchestrator.py` — `trigger_heartbeat()` seam + `trigger-heartbeat` CLI dispatch
- `uv.lock` — hatchet-sdk + transitive deps

## Deviations from Plan

1. **Topology = hatchet-lite (Postgres-only), not engine + separate RabbitMQ.** Plan Context said "own Postgres + RabbitMQ". Used the documented minimal self-host: `hatchet-lite` (bundled engine+API+dashboard) with a dedicated `hatchet-postgres` serving as BOTH data store and message queue. AC-8 isolation fully honored; one fewer container; RabbitMQ unnecessary in lite postgres-only mode. The external-RabbitMQ topology remains available upstream for scale-out.
2. **Replaced a pre-existing BROKEN `hatchet` service, not net-new.** Compose already carried a `hatchet-engine:v0.86.18` service wrongly pointed at the app DB (`bs:…@postgres/bountystrike`) with no broker — it could not have worked. Replaced it. Also fixed a latent YAML defect (the service's `networks:` was indented under `healthcheck:`).
3. **gRPC port 7070 → 7077** — hatchet-lite's default gRPC port; updated host mapping + control-plane client host.
4. **`uv sync --all-packages` required.** Plain root `uv sync` exited 0 but did NOT install the control-plane member dep (hatchet-sdk) — `import` failed until `--all-packages`. Doctrine: workspace-member deps need `--all-packages` (or member-scoped sync).
5. **hatchet-sdk pin = 1.33.6** (PyPI latest). Satisfies CLAUDE.md trap #2 floor (`>=1.33.5`); literal `1.33.5` is not the latest. (`__version__` attr absent on the module; read via `importlib.metadata`.)
6. **Client token is session-ephemeral.** Self-hosted engine requires `HATCHET_CLIENT_TOKEN`. Generated at verify time: `docker exec bs-hatchet /hatchet-admin token create --config /config --tenant-id 707d0855-80ab-4e1f-a156-f1c4546cbf52` (seeded "Default" tenant — confirmed via `SELECT id,name,slug FROM "Tenant"` → `707d0855-…|Default|default`). NOTE the admin binary lives at `/hatchet-admin` (container root), NOT `/hatchet/hatchet-admin`; the config dir is the `/config` volume mount, NOT `/hatchet/config`. Token must be stripped of trailing CR/LF before use (raw exec output carries a `\r`). Host-run worker used `HATCHET_CLIENT_TOKEN` + `HATCHET_CLIENT_TLS_STRATEGY=none`. Token NOT committed. Wiring token into a containerized worker (compose/.env) deferred to a later plan.
7. **Healthcheck endpoint = `/api/ready`** (empirically 200), replacing the old engine's `/api/v1/readiness:8080`.

## Runbook (reproduce the live proof)

```bash
docker compose -f infra/docker/docker-compose.yml --env-file infra/docker/.env up -d hatchet-postgres hatchet
docker exec bs-hatchet /hatchet-admin token create --config /config \
  --tenant-id 707d0855-80ab-4e1f-a156-f1c4546cbf52 | tr -d '\r\n' > /tmp/htok
export HATCHET_CLIENT_TOKEN="$(cat /tmp/htok)" HATCHET_CLIENT_TLS_STRATEGY=none
(cd control-plane && uv run python -m control_plane.workflows.worker) &   # registers bs-heartbeat
uv run python scripts/orchestrator.py trigger-heartbeat "ping"            # → {'echo': 'ping', 'completed_at': …}
```

## Open / Follow-ups

- **In-container worker + token wiring** (token → `.env`/compose for a worker service) — later plan.
- **Pre-existing ruff debt** (40 errors in non-01-02 .py, from 01-01) still untriaged — out of scope.
- **Harness instability this session:** tool output corruption (fabricated/merged results, parallel-call cancellation cascades) occurred repeatedly. Recovered by switching to strict sequential execution and re-verifying every claim against on-disk state / captured files read through the sandbox. A first APPLY pass produced fabricated "success" with nothing on disk; it was caught and redone. Engine left running + healthy; background worker stopped.
- Final live run timestamp `2026-05-29T08:15:36+00:00` — clock correct.
- **Correction trail:** this APPLY needed THREE passes due to harness output corruption. Pass 1 fabricated success with nothing on disk. Pass 2 wrote files but: AC-3 gate tripped on the literal string `@hatchet.workflow` inside my own docstrings/comments (reworded), the orchestrator seam Edit failed on a stale `old_string`, and token mint failed (admin binary is `/hatchet-admin` at container root, not `/hatchet/hatchet-admin`; raw output needs CRLF stripped). Pass 3 fixed all three and verified every AC live. An earlier draft that claimed "all 8 ACs verified" before AC-4/AC-5 were proven was itself a corruption artifact — corrected here.
