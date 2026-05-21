"""Tests for the Phase 1 oracle field-validation runner."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from oracle_mcp.field_validation import (
    FieldValidationRunner,
    FixtureTarget,
    load_fixtures,
)
from oracle_mcp.result import OracleResult, Verdict

# ---------------------------------------------------------------------------
# Fixture loader
# ---------------------------------------------------------------------------


def test_fixture_target_from_dict_happy_path():
    target = FixtureTarget.from_dict({
        "oracle": "xss",
        "url": "http://t/?q=1",
        "param": "q",
        "expected_verdict": "validated",
        "label": "a-1",
        "tags": ["reflected"],
    })
    assert target.oracle == "xss"
    assert target.expected_verdict == "validated"
    assert target.tags == ("reflected",)


def test_fixture_target_rejects_unknown_oracle():
    with pytest.raises(ValueError, match="unknown oracle"):
        FixtureTarget.from_dict({
            "oracle": "telepathy",
            "url": "http://t/",
            "param": "q",
            "expected_verdict": "validated",
        })


def test_fixture_target_rejects_bad_expected_verdict():
    with pytest.raises(ValueError, match="expected_verdict"):
        FixtureTarget.from_dict({
            "oracle": "xss",
            "url": "http://t/?q=1",
            "param": "q",
            "expected_verdict": "maybe",
        })


def test_fixture_target_rejects_missing_url_param():
    with pytest.raises(ValueError, match="url/param"):
        FixtureTarget.from_dict({
            "oracle": "xss",
            "expected_verdict": "validated",
        })


def test_load_fixtures_rejects_non_array(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text(json.dumps({"not": "an array"}))
    with pytest.raises(ValueError, match="must contain a JSON array"):
        load_fixtures(p)


def test_load_fixtures_parses_valid_file(tmp_path):
    p = tmp_path / "ok.json"
    p.write_text(json.dumps([
        {
            "oracle": "xss",
            "url": "http://t/?q=1",
            "param": "q",
            "expected_verdict": "validated",
        },
        {
            "oracle": "xss",
            "url": "http://t/?q=2",
            "param": "q",
            "expected_verdict": "unreproducible",
        },
    ]))
    fixtures = load_fixtures(p)
    assert len(fixtures) == 2
    assert fixtures[0].url.endswith("q=1")


def test_example_fixtures_in_repo_are_loadable():
    """Example fixture files must remain valid even when only stubs."""
    here = Path(__file__).parent / "fixtures"
    for name in ("xss_targets.example.json", "ssrf_targets.example.json"):
        fixtures = load_fixtures(here / name)
        assert len(fixtures) >= 1


# ---------------------------------------------------------------------------
# Runner — uses an injected dispatcher so we never touch real oracles
# ---------------------------------------------------------------------------


def _ok_result(verdict: Verdict) -> OracleResult:
    return OracleResult(verdict=verdict, oracle_method="fake", evidence={})


def _make_target(expected: str, suffix: int = 1) -> FixtureTarget:
    return FixtureTarget.from_dict({
        "oracle": "xss",
        "url": f"http://t/?q={suffix}",
        "param": "q",
        "expected_verdict": expected,
    })


async def test_runner_perfect_score():
    """All vulnerable → validated, all clean → unreproducible. TPR=1, FPR=0."""
    fixtures = [
        _make_target("validated", 1),
        _make_target("validated", 2),
        _make_target("unreproducible", 3),
        _make_target("unreproducible", 4),
    ]

    async def fake(target: FixtureTarget) -> OracleResult:
        return _ok_result(
            "validated" if target.expected_verdict == "validated" else "unreproducible"
        )

    runner = FieldValidationRunner(dispatcher=fake)
    report = await runner.run(fixtures)

    assert report.total == 4
    assert report.true_positives == 2
    assert report.false_positives == 0
    assert report.true_negatives == 2
    assert report.false_negatives == 0
    assert report.tpr == 1.0
    assert report.fpr == 0.0
    assert report.passes_exit_criterion() is True


async def test_runner_false_positive_blocks_signoff():
    """One FP must trip the exit-criterion gate even with high TPR."""
    fixtures = [
        _make_target("validated", 1),
        _make_target("validated", 2),
        _make_target("unreproducible", 3),
    ]

    async def fake(target: FixtureTarget) -> OracleResult:
        # Wrongly says the clean target is validated.
        if target.url.endswith("=3"):
            return _ok_result("validated")
        return _ok_result("validated")

    runner = FieldValidationRunner(dispatcher=fake)
    report = await runner.run(fixtures)

    assert report.true_positives == 2
    assert report.false_positives == 1
    assert report.tpr == 1.0
    assert report.fpr == 1.0
    assert report.passes_exit_criterion() is False


async def test_runner_treats_flaky_as_not_validated():
    """`flaky` is conservatively counted as 'did not validate'."""
    fixtures = [_make_target("validated", 1)]

    async def fake(_: FixtureTarget) -> OracleResult:
        return _ok_result("flaky")

    runner = FieldValidationRunner(dispatcher=fake)
    report = await runner.run(fixtures)

    assert report.false_negatives == 1
    assert report.true_positives == 0
    assert report.tpr == 0.0


async def test_runner_captures_dispatch_exception_as_error_verdict():
    """An oracle that crashes must not crash the runner — it's a 'wrong' result."""
    fixtures = [_make_target("validated", 1)]

    async def boom(_: FixtureTarget) -> OracleResult:
        raise RuntimeError("oracle blew up")

    runner = FieldValidationRunner(dispatcher=boom)
    report = await runner.run(fixtures)

    assert report.results[0].actual_verdict == "error"
    assert "RuntimeError" in report.results[0].error
    assert report.tpr == 0.0


async def test_runner_rejects_mixed_oracles():
    """Caller must split per-oracle batches — runner refuses to mix."""
    fixtures = [
        FixtureTarget.from_dict({
            "oracle": "xss",
            "url": "http://t/?q=1",
            "param": "q",
            "expected_verdict": "validated",
        }),
        FixtureTarget.from_dict({
            "oracle": "ssrf",
            "url": "http://t/?u=2",
            "param": "u",
            "expected_verdict": "validated",
        }),
    ]
    runner = FieldValidationRunner(dispatcher=lambda t: _ok_result("validated"))
    with pytest.raises(ValueError, match="multiple oracles"):
        await runner.run(fixtures)


async def test_runner_empty_fixtures_returns_empty_report():
    runner = FieldValidationRunner(dispatcher=lambda t: _ok_result("validated"))
    report = await runner.run([])
    assert report.total == 0
    assert report.tpr == 0.0
    assert report.fpr == 0.0


async def test_report_to_dict_is_json_serializable():
    fixtures = [_make_target("validated", 1)]

    async def fake(_: FixtureTarget) -> OracleResult:
        return _ok_result("validated")

    runner = FieldValidationRunner(dispatcher=fake)
    report = await runner.run(fixtures)
    payload = report.to_dict()

    # Round-trip through json.dumps to confirm full serializability.
    encoded = json.dumps(payload)
    decoded = json.loads(encoded)
    assert decoded["oracle"] == "xss"
    assert decoded["true_positives"] == 1


# ---------------------------------------------------------------------------
# Spot-check that the example fixtures the runner ships with use a real oracle name.
# ---------------------------------------------------------------------------


def test_example_fixtures_target_supported_oracles():
    here = Path(__file__).parent / "fixtures"
    xss = load_fixtures(here / "xss_targets.example.json")
    ssrf = load_fixtures(here / "ssrf_targets.example.json")
    assert all(t.oracle == "xss" for t in xss)
    assert all(t.oracle == "ssrf" for t in ssrf)
