"""Pure normalizers — convert raw platform JSON into the canonical scope dict.

Each function returns a `CanonicalScope` mapping suitable for upserting into
the `scopes` table:

    {
        "program_handle": str,
        "asset_type":     str,
        "identifier":     str,
        "in_scope":       bool,
        "exclusion_reason": str | None,
        "tags":           list[str],
    }

These helpers are platform-agnostic and side-effect-free. They never raise on
missing optional fields — they return ``None`` so the caller can drop bad
records without aborting an ingest run.
"""

from __future__ import annotations

from typing import Any, TypedDict


class CanonicalScope(TypedDict):
    program_handle: str
    asset_type: str
    identifier: str
    in_scope: bool
    exclusion_reason: str | None
    tags: list[str]


# ---------------------------------------------------------------------------
# HackerOne (April 2026 org_assets API)
# ---------------------------------------------------------------------------


_H1_ASSET_TYPE_MAP = {
    "URL": "web-application",
    "API": "api",
    "WILDCARD": "web-application",
    "CIDR": "cidr",
    "IP_ADDRESS": "cidr",
    "GOOGLE_PLAY_APP_ID": "android",
    "APPLE_STORE_APP_ID": "ios",
    "OTHER_APK": "android",
    "OTHER_IPA": "ios",
    "EXECUTABLE": "executable",
    "HARDWARE": "executable",
    "SOURCE_CODE": "source-code",
    "AI_MODEL": "ai_model",
    "SMART_CONTRACT": "smart_contract",
    "OTHER": "other",
}


def normalize_h1_org_asset(
    asset: dict[str, Any],
    *,
    program_handle: str | None = None,
) -> CanonicalScope | None:
    """Normalize a HackerOne April-2026 org-asset record.

    `program_handle` may be supplied by the caller (when the asset belongs to
    multiple programs and we want to fan it out one-by-one). Otherwise we use
    the first entry of `program_handles[]`.
    """
    identifier = asset.get("identifier") or asset.get("asset_identifier")
    raw_type = asset.get("asset_type") or asset.get("type")
    if not identifier or not raw_type:
        return None

    handle = program_handle
    if handle is None:
        handles = asset.get("program_handles") or []
        if not handles:
            return None
        handle = handles[0]

    tags = list(asset.get("tags") or [])
    notes = asset.get("notes")
    in_scope = bool(asset.get("in_scope", True))
    exclusion = None if in_scope else (notes or "out of scope")

    return CanonicalScope(
        program_handle=str(handle),
        asset_type=_H1_ASSET_TYPE_MAP.get(str(raw_type).upper(), str(raw_type).lower()),
        identifier=str(identifier),
        in_scope=in_scope,
        exclusion_reason=exclusion,
        tags=tags,
    )


# ---------------------------------------------------------------------------
# Bugcrowd (programs.json + per-program JSON)
# ---------------------------------------------------------------------------


_BUGCROWD_CATEGORY_MAP = {
    "website": "web-application",
    "api": "api",
    "android": "android",
    "ios": "ios",
    "hardware": "executable",
    "other": "other",
}


def normalize_bugcrowd_target(
    target: dict[str, Any],
    *,
    program_handle: str,
    in_scope: bool = True,
) -> CanonicalScope | None:
    """Bugcrowd `target_groups[].targets[]` records."""
    identifier = target.get("target") or target.get("name") or target.get("uri")
    if not identifier:
        return None

    raw_category = (target.get("category") or target.get("type") or "other").lower()
    asset_type = _BUGCROWD_CATEGORY_MAP.get(raw_category, raw_category)

    tags: list[str] = []
    if target.get("point") is not None:
        tags.append(f"point:{target['point']}")
    if reward := target.get("reward_range"):
        tags.append(f"reward:{reward}")

    return CanonicalScope(
        program_handle=program_handle,
        asset_type=asset_type,
        identifier=str(identifier),
        in_scope=in_scope,
        exclusion_reason=None if in_scope else "out of scope",
        tags=tags,
    )


# ---------------------------------------------------------------------------
# Intigriti (researcher API v1 scopes)
# ---------------------------------------------------------------------------


_INTIGRITI_TYPE_MAP = {
    "url": "web-application",
    "wildcard": "web-application",
    "api": "api",
    "ios": "ios",
    "android": "android",
    "ip_range": "cidr",
    "ip": "cidr",
    "device": "executable",
    "other": "other",
}


def normalize_intigriti_scope(
    scope: dict[str, Any],
    *,
    program_handle: str,
) -> CanonicalScope | None:
    """Intigriti per-endpoint scope entry."""
    identifier = scope.get("endpoint") or scope.get("identifier") or scope.get("target")
    if not identifier:
        return None

    raw_type = (scope.get("type") or scope.get("scope_type") or "other").lower()
    asset_type = _INTIGRITI_TYPE_MAP.get(raw_type, raw_type)

    in_scope = bool(scope.get("in_scope", True))
    tier = scope.get("tier")
    tags: list[str] = []
    if tier:
        tags.append(f"tier:{tier}")
    if (mb := scope.get("maxBounty")) is not None:
        tags.append(f"max_bounty:{mb}")

    return CanonicalScope(
        program_handle=program_handle,
        asset_type=asset_type,
        identifier=str(identifier),
        in_scope=in_scope,
        exclusion_reason=None if in_scope else (scope.get("description") or "out of scope"),
        tags=tags,
    )


# ---------------------------------------------------------------------------
# YesWeHack (programs API)
# ---------------------------------------------------------------------------


_YWH_TYPE_MAP = {
    "web-application": "web-application",
    "web_application": "web-application",
    "api": "api",
    "mobile-application-android": "android",
    "mobile-application-ios": "ios",
    "ip-address": "cidr",
    "ip_range": "cidr",
    "executable": "executable",
    "other": "other",
}

_YWH_ASSET_VALUE_TAG = {"low": "value:low", "medium": "value:medium", "high": "value:high"}


def normalize_yeswehack_program(
    scope: dict[str, Any],
    *,
    program_handle: str,
) -> CanonicalScope | None:
    """YesWeHack scope record. `asset_value` is preserved as a tag for EV."""
    identifier = scope.get("scope") or scope.get("target") or scope.get("identifier")
    if not identifier:
        return None

    raw_type = (scope.get("scope_type") or scope.get("type") or "other").lower()
    asset_type = _YWH_TYPE_MAP.get(raw_type, raw_type)

    tags: list[str] = []
    if asset_value := scope.get("asset_value"):
        if mapped := _YWH_ASSET_VALUE_TAG.get(str(asset_value).lower()):
            tags.append(mapped)
        else:
            tags.append(f"value:{asset_value}")

    in_scope = bool(scope.get("in_scope", True))
    return CanonicalScope(
        program_handle=program_handle,
        asset_type=asset_type,
        identifier=str(identifier),
        in_scope=in_scope,
        exclusion_reason=None if in_scope else (scope.get("description") or "out of scope"),
        tags=tags,
    )


# ---------------------------------------------------------------------------
# Immunefi (impacts[] in /bounty/{project}/json)
# ---------------------------------------------------------------------------


def normalize_immunefi_impact(
    impact: dict[str, Any],
    *,
    program_handle: str,
) -> CanonicalScope | None:
    """Immunefi exposes assets as `impacts[]` plus an `assets[]` array.

    We treat every impact record as a smart-contract asset (with the impact
    description tagged) so it routes through the EV smart_contract weight
    (1.40×, see research/02 §Asset-type weights).
    """
    identifier = (
        impact.get("asset")
        or impact.get("contract")
        or impact.get("identifier")
        or impact.get("target")
    )
    if not identifier:
        return None

    severity = impact.get("severity") or impact.get("level")
    tags: list[str] = []
    if severity:
        tags.append(f"severity:{severity}")
    if (b := impact.get("bounty") or impact.get("maxBounty")) is not None:
        tags.append(f"max_bounty:{b}")

    return CanonicalScope(
        program_handle=program_handle,
        asset_type="smart_contract",
        identifier=str(identifier),
        in_scope=bool(impact.get("in_scope", True)),
        exclusion_reason=None,
        tags=tags,
    )


__all__ = [
    "CanonicalScope",
    "normalize_bugcrowd_target",
    "normalize_h1_org_asset",
    "normalize_immunefi_impact",
    "normalize_intigriti_scope",
    "normalize_yeswehack_program",
]
