"""Scope ingestion worker.

Coordinates the federation feeds (`arkadiyt/bounty-targets-data`) and the
HackerOne April-2026 org-assets API, normalizes the records, upserts them into
`programs` + `scopes`, and emits `scope_changes` events for every diff.

Usage
-----
.. code-block:: python

    async with HackerOneClient() as h1, ArkadiytClient() as fed:
        async with session_factory() as session:
            await ingest_h1_org_assets(session, "12345", h1=h1)
            await ingest_arkadiyt_all(session, fed=fed)
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.engine import Dialect
from sqlalchemy.ext.asyncio import AsyncSession

from control_plane.db import Program, Scope, ScopeChange
from control_plane.integrations.arkadiyt_client import (
    ArkadiytClient,
    FederationProgram,
    Platform,
)
from control_plane.integrations.h1_client import H1Asset, HackerOneClient
from control_plane.integrations.normalize import (
    CanonicalScope,
    normalize_bugcrowd_target,
    normalize_h1_org_asset,
    normalize_immunefi_impact,
    normalize_intigriti_scope,
    normalize_yeswehack_program,
)

logger = structlog.get_logger("control_plane.workers.scope_ingest")

ScopeKey = tuple[str, str, str]  # (program_handle, asset_type, identifier)
ScopeState = dict[ScopeKey, dict[str, Any]]

VALID_EVENT_TYPES = {"scope_added", "scope_removed", "payout_changed", "program_paused"}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def ingest_h1_org_assets(
    session: AsyncSession,
    org_id: str,
    *,
    since: datetime | None = None,
    h1: HackerOneClient | None = None,
) -> dict[str, int]:
    """Pull every asset for `org_id`, upsert programs+scopes, log changes.

    Returns counters: ``{"assets": N, "programs": M, "events": K}``.
    """
    log = logger.bind(org_id=org_id, since=since.isoformat() if since else None)
    owns_client = h1 is None
    client = h1 or HackerOneClient()
    try:
        assets = await client.fetch_org_assets(org_id, since=since)
    finally:
        if owns_client:
            await client.aclose()

    log.info("h1.fetch_complete", asset_count=len(assets))
    if not assets:
        return {"assets": 0, "programs": 0, "events": 0}

    # Group H1 assets by program_handle so we can build per-program before/after
    # snapshots without re-querying.
    canonical_by_program: dict[str, list[CanonicalScope]] = {}
    program_meta: dict[str, dict[str, Any]] = {}

    for asset in assets:
        for handle in asset.program_handles or [None]:  # type: ignore[list-item]
            if handle is None:
                continue
            normalized = normalize_h1_org_asset(asset.model_dump(), program_handle=handle)
            if normalized is None:
                continue
            canonical_by_program.setdefault(handle, []).append(normalized)
            meta = program_meta.setdefault(
                handle,
                {
                    "platform": "hackerone",
                    "name": handle,
                    "last_modified_at": asset.last_modified_at,
                    "raw": {"org_id": org_id},
                },
            )
            if asset.last_modified_at and (
                meta["last_modified_at"] is None
                or asset.last_modified_at > meta["last_modified_at"]
            ):
                meta["last_modified_at"] = asset.last_modified_at

    total_events = 0
    for handle, scopes in canonical_by_program.items():
        await _upsert_program(session, handle=handle, **program_meta[handle])
        before = await _load_scope_state(session, handle)
        await _upsert_scopes(session, scopes, raw_lookup={s.identifier: s for s in assets})
        after = _state_from_canonical(scopes)
        events = await detect_scope_changes(
            session,
            before,
            after,
            program_handle=handle,
            platform="hackerone",
            source="h1_org_assets",
        )
        total_events += events

    await session.commit()
    log.info(
        "h1.ingest_complete",
        programs=len(canonical_by_program),
        events=total_events,
    )
    return {
        "assets": len(assets),
        "programs": len(canonical_by_program),
        "events": total_events,
    }


async def ingest_arkadiyt_all(
    session: AsyncSession,
    *,
    fed: ArkadiytClient | None = None,
) -> dict[str, int]:
    """Pull every federation feed and upsert all programs/scopes."""
    owns_client = fed is None
    client = fed or ArkadiytClient()
    try:
        all_feeds = await client.fetch_all()
    finally:
        if owns_client:
            await client.aclose()

    counts = {"programs": 0, "scopes": 0, "events": 0}
    for platform, programs in all_feeds.items():
        for fp in programs:
            stats = await _ingest_federation_program(session, platform, fp)
            counts["programs"] += 1
            counts["scopes"] += stats["scopes"]
            counts["events"] += stats["events"]

    await session.commit()
    logger.info("arkadiyt.ingest_complete", **counts)
    return counts


async def detect_scope_changes(
    session: AsyncSession,
    before_state: ScopeState,
    after_state: ScopeState,
    *,
    program_handle: str,
    platform: str,
    source: str,
) -> int:
    """Diff `before` vs `after`; INSERT a `scope_changes` row per change.

    Event types match `research/02 §Change-Event Architecture`:
    `scope_added`, `scope_removed`, `payout_changed`, `program_paused`.
    """
    events: list[dict[str, Any]] = []
    now = datetime.now(UTC)

    before_keys = set(before_state.keys())
    after_keys = set(after_state.keys())

    for key in after_keys - before_keys:
        events.append(
            _make_event(
                event_type="scope_added",
                program_handle=program_handle,
                platform=platform,
                identifier=key[2],
                old=None,
                new=after_state[key],
                source=source,
                detected_at=now,
            )
        )

    for key in before_keys - after_keys:
        events.append(
            _make_event(
                event_type="scope_removed",
                program_handle=program_handle,
                platform=platform,
                identifier=key[2],
                old=before_state[key],
                new=None,
                source=source,
                detected_at=now,
            )
        )

    for key in before_keys & after_keys:
        old = before_state[key]
        new = after_state[key]
        if _payout_changed(old, new):
            events.append(
                _make_event(
                    event_type="payout_changed",
                    program_handle=program_handle,
                    platform=platform,
                    identifier=key[2],
                    old=old,
                    new=new,
                    source=source,
                    detected_at=now,
                )
            )
        elif old.get("in_scope", True) and not new.get("in_scope", True):
            # Program-wide pauses surface as in_scope flips on every asset; we
            # still emit a per-asset event so subscribers can react granularly.
            events.append(
                _make_event(
                    event_type="program_paused",
                    program_handle=program_handle,
                    platform=platform,
                    identifier=key[2],
                    old=old,
                    new=new,
                    source=source,
                    detected_at=now,
                )
            )

    if not events:
        return 0

    session.add_all([ScopeChange(**e) for e in events])
    await session.flush()
    logger.info(
        "scope_changes.recorded",
        program_handle=program_handle,
        platform=platform,
        count=len(events),
    )
    return len(events)


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


async def _ingest_federation_program(
    session: AsyncSession,
    platform: Platform,
    fp: FederationProgram,
) -> dict[str, int]:
    """Upsert a single federation program + all its in-scope assets."""
    if not fp.handle:
        return {"scopes": 0, "events": 0}

    raw = fp.raw or {}
    payout_min, payout_max = _extract_payout(platform, raw)

    await _upsert_program(
        session,
        handle=fp.handle,
        platform=platform,
        name=fp.name or fp.handle,
        last_modified_at=None,
        raw=raw,
        payout_min=payout_min,
        payout_max=payout_max,
    )

    canonical = _normalize_federation(platform, fp)
    before = await _load_scope_state(session, fp.handle)
    await _upsert_scopes(session, canonical, raw_lookup=None)
    after = _state_from_canonical(canonical)

    events = await detect_scope_changes(
        session,
        before,
        after,
        program_handle=fp.handle,
        platform=platform,
        source="arkadiyt",
    )
    return {"scopes": len(canonical), "events": events}


def _normalize_federation(
    platform: Platform, fp: FederationProgram
) -> list[CanonicalScope]:
    out: list[CanonicalScope] = []
    handle = fp.handle

    if platform == "hackerone":
        for t in fp.targets_in_scope:
            asset_type = (
                t.get("asset_type") or t.get("asset_identifier_type") or "URL"
            )
            payload = {
                "identifier": t.get("asset_identifier") or t.get("identifier"),
                "asset_type": asset_type,
                "in_scope": True,
                "tags": [],
            }
            if (n := normalize_h1_org_asset(payload, program_handle=handle)) is not None:
                out.append(n)
        for t in fp.targets_out_of_scope:
            payload = {
                "identifier": t.get("asset_identifier") or t.get("identifier"),
                "asset_type": t.get("asset_type") or "URL",
                "in_scope": False,
                "tags": [],
            }
            if (n := normalize_h1_org_asset(payload, program_handle=handle)) is not None:
                out.append(n)
    elif platform == "bugcrowd":
        for t in fp.targets_in_scope:
            if (n := normalize_bugcrowd_target(t, program_handle=handle, in_scope=True)):
                out.append(n)
        for t in fp.targets_out_of_scope:
            if (n := normalize_bugcrowd_target(t, program_handle=handle, in_scope=False)):
                out.append(n)
    elif platform == "intigriti":
        for t in fp.targets_in_scope:
            if (n := normalize_intigriti_scope({**t, "in_scope": True}, program_handle=handle)):
                out.append(n)
        for t in fp.targets_out_of_scope:
            if (n := normalize_intigriti_scope({**t, "in_scope": False}, program_handle=handle)):
                out.append(n)
    elif platform == "yeswehack":
        for t in fp.targets_in_scope:
            if (
                n := normalize_yeswehack_program({**t, "in_scope": True}, program_handle=handle)
            ):
                out.append(n)
        for t in fp.targets_out_of_scope:
            if (
                n := normalize_yeswehack_program({**t, "in_scope": False}, program_handle=handle)
            ):
                out.append(n)
    elif platform == "immunefi":
        for t in fp.targets_in_scope:
            if (n := normalize_immunefi_impact({**t, "in_scope": True}, program_handle=handle)):
                out.append(n)
    return out


def _extract_payout(platform: Platform, raw: dict[str, Any]) -> tuple[float | None, float | None]:
    if platform == "bugcrowd":
        return raw.get("min_payout"), raw.get("max_payout")
    if platform == "intigriti":
        return raw.get("min_bounty"), raw.get("max_bounty")
    if platform == "yeswehack":
        return raw.get("bounty_reward_min"), raw.get("bounty_reward_max")
    if platform == "immunefi":
        return raw.get("minBounty") or raw.get("min_bounty"), raw.get("maxBounty") or raw.get(
            "max_bounty"
        )
    return None, None


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------


async def _upsert_program(
    session: AsyncSession,
    *,
    handle: str,
    platform: str,
    name: str | None = None,
    last_modified_at: datetime | None = None,
    raw: dict[str, Any] | None = None,
    payout_min: float | None = None,
    payout_max: float | None = None,
) -> None:
    """Upsert a row into `programs` (PG `ON CONFLICT (handle)`)."""
    values = {
        "handle": handle,
        "platform": platform,
        "name": name,
        "last_modified_at": last_modified_at,
        "payout_min": payout_min,
        "payout_max": payout_max,
        "last_seen_at": datetime.now(UTC),
        "raw": raw,
    }
    insert_stmt = _dialect_insert(session.bind.dialect, Program, values)  # type: ignore[arg-type]
    update_set = {
        "platform": insert_stmt.excluded.platform,
        "name": insert_stmt.excluded.name,
        "last_modified_at": insert_stmt.excluded.last_modified_at,
        "payout_min": insert_stmt.excluded.payout_min,
        "payout_max": insert_stmt.excluded.payout_max,
        "last_seen_at": insert_stmt.excluded.last_seen_at,
        "raw": insert_stmt.excluded.raw,
    }
    stmt = insert_stmt.on_conflict_do_update(index_elements=["handle"], set_=update_set)
    await session.execute(stmt)


async def _upsert_scopes(
    session: AsyncSession,
    scopes: list[CanonicalScope],
    *,
    raw_lookup: dict[str, H1Asset] | None,
) -> None:
    """Upsert into `scopes` keyed on `(program_handle, asset_type, identifier)`."""
    if not scopes:
        return

    rows: list[dict[str, Any]] = []
    now = datetime.now(UTC)
    for s in scopes:
        raw_payload = None
        if raw_lookup is not None and (asset := raw_lookup.get(s["identifier"])) is not None:
            raw_payload = asset.raw
        rows.append(
            {
                "program_handle": s["program_handle"],
                "asset_type": s["asset_type"],
                "identifier": s["identifier"],
                "in_scope": s["in_scope"],
                "exclusion_reason": s["exclusion_reason"],
                "tags": s["tags"],
                "updated_at": now,
                "raw": raw_payload,
            }
        )

    insert_stmt = _dialect_insert(session.bind.dialect, Scope, rows)  # type: ignore[arg-type]
    update_set = {
        "in_scope": insert_stmt.excluded.in_scope,
        "exclusion_reason": insert_stmt.excluded.exclusion_reason,
        "tags": insert_stmt.excluded.tags,
        "updated_at": insert_stmt.excluded.updated_at,
        "raw": insert_stmt.excluded.raw,
    }
    stmt = insert_stmt.on_conflict_do_update(
        index_elements=["program_handle", "asset_type", "identifier"],
        set_=update_set,
    )
    await session.execute(stmt)


def _dialect_insert(dialect: Dialect, model: type, values: Any) -> Any:
    """Pick the dialect-appropriate ``INSERT ... ON CONFLICT`` builder.

    Postgres in production, SQLite in tests. Both support `ON CONFLICT DO
    UPDATE` with the same surface.
    """
    name = dialect.name
    if name == "postgresql":
        return pg_insert(model).values(values)
    if name == "sqlite":
        return sqlite_insert(model).values(values)
    raise NotImplementedError(f"Upsert not implemented for dialect: {name}")


async def _load_scope_state(session: AsyncSession, program_handle: str) -> ScopeState:
    """Read the current `(handle, type, id) -> row` map for a program."""
    stmt = select(Scope).where(Scope.program_handle == program_handle)
    result = await session.execute(stmt)
    state: ScopeState = {}
    for scope in result.scalars().all():
        key: ScopeKey = (scope.program_handle, scope.asset_type, scope.identifier)
        state[key] = {
            "program_handle": scope.program_handle,
            "asset_type": scope.asset_type,
            "identifier": scope.identifier,
            "in_scope": scope.in_scope,
            "exclusion_reason": scope.exclusion_reason,
            "tags": list(scope.tags or []),
        }
    return state


def _state_from_canonical(scopes: list[CanonicalScope]) -> ScopeState:
    state: ScopeState = {}
    for s in scopes:
        key: ScopeKey = (s["program_handle"], s["asset_type"], s["identifier"])
        state[key] = dict(s)
    return state


def _payout_changed(old: dict[str, Any], new: dict[str, Any]) -> bool:
    """Detect bounty changes encoded as ``max_bounty:N`` tag deltas."""
    old_tags = {t for t in old.get("tags") or [] if t.startswith("max_bounty:")}
    new_tags = {t for t in new.get("tags") or [] if t.startswith("max_bounty:")}
    if old_tags != new_tags and (old_tags or new_tags):
        return True
    old_reward = {t for t in old.get("tags") or [] if t.startswith("reward:")}
    new_reward = {t for t in new.get("tags") or [] if t.startswith("reward:")}
    return old_reward != new_reward and bool(old_reward or new_reward)


def _make_event(
    *,
    event_type: str,
    program_handle: str,
    platform: str,
    identifier: str,
    old: dict[str, Any] | None,
    new: dict[str, Any] | None,
    source: str,
    detected_at: datetime,
) -> dict[str, Any]:
    if event_type not in VALID_EVENT_TYPES:
        raise ValueError(f"unknown event_type: {event_type}")
    return {
        "event_type": event_type,
        "program_handle": program_handle,
        "platform": platform,
        "asset_identifier": identifier,
        "old_value": old,
        "new_value": new,
        "detected_at": detected_at,
        "source": source,
    }


__all__ = [
    "detect_scope_changes",
    "ingest_arkadiyt_all",
    "ingest_h1_org_assets",
]
