"""Phase 1.1c integration test — XSS oracle TPR/FPR over the 40-target lab.

Opt-in: skipped unless ``RUN_XSS_FIELD_VALIDATION=1`` is set. The test
brings up the local Flask lab on port 5099, polls /healthz until ready,
runs the FieldValidationRunner against the committed
``tests/fixtures/xss_targets.json`` corpus, and asserts the Phase 1
exit gate (TPR ≥ 0.90 AND FPR == 0).

Why opt-in:
  - Playwright + Chromium is large; CI without the browser would hang.
  - 40 oracle calls × 3 attempts × ~1s per nav = ~2 minutes wall clock.
  - The unit suite already covers the runner's pure logic.

To run::

    cd mcp/oracle-mcp
    uv pip install -e .[dev] flask playwright
    playwright install chromium
    RUN_XSS_FIELD_VALIDATION=1 pytest tests/integration/test_xss_field_validation.py -v

The harness writes the resulting report to
``tests/reports/phase1_xss_tpr_fpr.json`` next to the fixture so a
successful run can be committed alongside the corpus as the sign-off
artifact.
"""

from __future__ import annotations

import asyncio
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

from oracle_mcp.field_validation import (
    FieldValidationRunner,
    load_fixtures,
)

FIXTURE_PATH = (
    Path(__file__).resolve().parents[1] / "fixtures" / "xss_targets.json"
)
LAB_APP = (
    Path(__file__).resolve().parents[1] / "fixtures" / "xss_lab" / "app.py"
)
REPORT_PATH = (
    Path(__file__).resolve().parents[1] / "reports" / "phase1_xss_tpr_fpr.json"
)
LAB_HOST = "127.0.0.1"
LAB_PORT = 5099
HEALTH_URL = f"http://{LAB_HOST}:{LAB_PORT}/healthz"

OPT_IN_ENV = "RUN_XSS_FIELD_VALIDATION"

pytestmark = pytest.mark.skipif(
    os.environ.get(OPT_IN_ENV) != "1",
    reason=f"opt-in: set {OPT_IN_ENV}=1 to run Phase 1.1c integration",
)


def _port_open(host: str, port: int, timeout: float = 0.5) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _wait_for_health(deadline_s: float = 30.0) -> None:
    """Poll /healthz until the lab returns 'ok' or the deadline elapses."""
    import urllib.request

    started = time.monotonic()
    last_err: str | None = None
    while time.monotonic() - started < deadline_s:
        try:
            with urllib.request.urlopen(HEALTH_URL, timeout=1.0) as resp:
                body = resp.read().decode()
            if body.strip() == "ok":
                return
            last_err = f"unexpected body: {body!r}"
        except Exception as exc:  # noqa: BLE001
            last_err = f"{type(exc).__name__}: {exc}"
        time.sleep(0.5)
    raise RuntimeError(f"lab did not become healthy within {deadline_s}s: {last_err}")


@pytest.fixture(scope="module")
def lab_process():
    """Spawn the Flask lab as a subprocess; tear it down on teardown.

    Skipped automatically if port 5099 is already bound — that's the
    docker-compose case (``docker compose up xss-lab``). Either way the
    test reaches the same lab over HTTP.
    """
    spawned = None
    if not _port_open(LAB_HOST, LAB_PORT):
        spawned = subprocess.Popen(
            [sys.executable, str(LAB_APP)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
    try:
        _wait_for_health()
        yield spawned
    finally:
        if spawned is not None:
            spawned.terminate()
            try:
                spawned.wait(timeout=5)
            except subprocess.TimeoutExpired:
                spawned.kill()


def test_xss_field_validation_meets_phase1_gate(lab_process) -> None:
    fixtures = load_fixtures(FIXTURE_PATH)
    assert len(fixtures) == 40, f"expected 40 targets, got {len(fixtures)}"

    runner = FieldValidationRunner()
    report = asyncio.run(runner.run(fixtures))

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report.to_dict(), indent=2))

    assert report.passes_exit_criterion(min_tpr=0.90, max_fpr=0.0), (
        f"Phase 1.1c gate failed: tpr={report.tpr:.3f} (need ≥0.90), "
        f"fpr={report.fpr:.3f} (need =0.0). "
        f"TP={report.true_positives} FP={report.false_positives} "
        f"FN={report.false_negatives} TN={report.true_negatives}. "
        f"Report written to {REPORT_PATH}."
    )
