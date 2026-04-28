"""Per-platform normalizer tests using realistic fixture JSON."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from control_plane.integrations.normalize import (
    normalize_bugcrowd_target,
    normalize_h1_org_asset,
    normalize_immunefi_impact,
    normalize_intigriti_scope,
    normalize_yeswehack_program,
)

FIXTURES = Path(__file__).parent / "fixtures"


def _load(name: str) -> Any:
    return json.loads((FIXTURES / name).read_text())


# ---------------------------------------------------------------------------
# HackerOne
# ---------------------------------------------------------------------------


def test_normalize_h1_url_asset() -> None:
    page = _load("h1_org_assets_page.json")
    asset = page["data"][0]["attributes"]
    out = normalize_h1_org_asset(asset)
    assert out is not None
    assert out["program_handle"] == "acme-corp"
    assert out["asset_type"] == "web-application"
    assert out["identifier"] == "*.acme.com"
    assert out["in_scope"] is True
    assert out["tags"] == ["primary", "production"]


def test_normalize_h1_api_asset() -> None:
    page = _load("h1_org_assets_page.json")
    asset = page["data"][1]["attributes"]
    out = normalize_h1_org_asset(asset)
    assert out is not None
    assert out["asset_type"] == "api"
    assert out["identifier"] == "api.acme.com"


def test_normalize_h1_android_asset() -> None:
    page = _load("h1_org_assets_page.json")
    asset = page["data"][2]["attributes"]
    out = normalize_h1_org_asset(asset)
    assert out is not None
    assert out["asset_type"] == "android"
    assert out["identifier"] == "com.acme.app"


def test_normalize_h1_returns_none_when_identifier_missing() -> None:
    out = normalize_h1_org_asset({"asset_type": "URL", "program_handles": ["x"]})
    assert out is None


# ---------------------------------------------------------------------------
# Bugcrowd
# ---------------------------------------------------------------------------


def test_normalize_bugcrowd_in_scope() -> None:
    program = _load("bugcrowd_program.json")
    target = program["targets"]["in_scope"][0]
    out = normalize_bugcrowd_target(target, program_handle=program["code"], in_scope=True)
    assert out is not None
    assert out["program_handle"] == "globex-public"
    assert out["asset_type"] == "web-application"
    assert out["identifier"] == "*.globex.io"
    assert out["in_scope"] is True
    assert "point:7" in out["tags"]
    assert "reward:p1-p3" in out["tags"]


def test_normalize_bugcrowd_out_of_scope() -> None:
    program = _load("bugcrowd_program.json")
    target = program["targets"]["out_of_scope"][0]
    out = normalize_bugcrowd_target(target, program_handle=program["code"], in_scope=False)
    assert out is not None
    assert out["in_scope"] is False
    assert out["exclusion_reason"] == "out of scope"


# ---------------------------------------------------------------------------
# Intigriti
# ---------------------------------------------------------------------------


def test_normalize_intigriti_elite() -> None:
    program = _load("intigriti_program.json")
    scope = program["targets"]["in_scope"][0]
    out = normalize_intigriti_scope(scope, program_handle=program["handle"])
    assert out is not None
    assert out["asset_type"] == "web-application"
    assert out["identifier"] == "https://www.acmebank.eu/*"
    assert "tier:elite" in out["tags"]
    assert "max_bounty:12000" in out["tags"]


def test_normalize_intigriti_api_professional() -> None:
    program = _load("intigriti_program.json")
    scope = program["targets"]["in_scope"][1]
    out = normalize_intigriti_scope(scope, program_handle=program["handle"])
    assert out is not None
    assert out["asset_type"] == "api"
    assert "tier:professional" in out["tags"]


# ---------------------------------------------------------------------------
# YesWeHack
# ---------------------------------------------------------------------------


def test_normalize_ywh_high_value() -> None:
    program = _load("yeswehack_program.json")
    scope = program["scopes"][0]
    out = normalize_yeswehack_program(scope, program_handle=program["slug"])
    assert out is not None
    assert out["asset_type"] == "web-application"
    assert out["identifier"] == "*.acmecloud.io"
    assert "value:high" in out["tags"]


def test_normalize_ywh_medium_value() -> None:
    program = _load("yeswehack_program.json")
    scope = program["scopes"][1]
    out = normalize_yeswehack_program(scope, program_handle=program["slug"])
    assert out is not None
    assert out["asset_type"] == "api"
    assert "value:medium" in out["tags"]


# ---------------------------------------------------------------------------
# Immunefi
# ---------------------------------------------------------------------------


def test_normalize_immunefi_critical_smart_contract() -> None:
    program = _load("immunefi_bounty.json")
    impact = program["impacts"][0]
    out = normalize_immunefi_impact(impact, program_handle=program["id"])
    assert out is not None
    assert out["asset_type"] == "smart_contract"
    assert out["identifier"].startswith("0xACME")
    assert "severity:critical" in out["tags"]
    assert "max_bounty:1000000" in out["tags"]


def test_normalize_immunefi_returns_none_without_asset() -> None:
    out = normalize_immunefi_impact({"severity": "high"}, program_handle="x")
    assert out is None


@pytest.mark.parametrize(
    "fixture_name,count",
    [
        ("h1_org_assets_page.json", 3),
        ("bugcrowd_program.json", 2),
        ("intigriti_program.json", 2),
        ("yeswehack_program.json", 2),
        ("immunefi_bounty.json", 2),
    ],
)
def test_fixtures_have_expected_record_count(fixture_name: str, count: int) -> None:
    """Sanity check our fixture shapes haven't drifted."""
    payload = _load(fixture_name)
    if fixture_name == "h1_org_assets_page.json":
        assert len(payload["data"]) == count
    elif fixture_name == "bugcrowd_program.json" or fixture_name == "intigriti_program.json":
        assert len(payload["targets"]["in_scope"]) == count
    elif fixture_name == "yeswehack_program.json":
        assert len(payload["scopes"]) == count
    elif fixture_name == "immunefi_bounty.json":
        assert len(payload["impacts"]) == count
