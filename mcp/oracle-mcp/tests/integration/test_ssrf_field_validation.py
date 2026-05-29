# SPDX-License-Identifier: AGPL-3.0-or-later

"""Phase 1.1d integration test — SSRF oracle TPR/FPR over the 10-target lab.

Opt-in: skipped unless ``RUN_SSRF_FIELD_VALIDATION=1`` is set. The test
brings up the local OAST collector (port 5097) and the SSRF lab
(port 5098), polls /healthz on both, points the InteractshClient at the
local collector via ``INTERACTSH_SERVER_URL``, runs the
FieldValidationRunner against ``tests/fixtures/ssrf_targets.json``, and
asserts the Phase 1 exit gate (TPR ≥ 0.90 AND FPR == 0).

Two services rather than one: the SSRF lab and the OAST collector are
distinct because the lab makes outbound HTTP requests to the collector,
and the OAST collector cannot host the lab's vulnerable routes (its
URL space is dedicated to ``/cb/<token>``).

To run::

    cd mcp/oracle-mcp
    uv pip install -e .[dev] flask httpx
    RUN_SSRF_FIELD_VALIDATION=1 pytest \\
        tests/integration/test_ssrf_field_validation.py -v
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

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
FIXTURE_PATH = FIXTURES / "ssrf_targets.json"
OAST_APP = FIXTURES / "oast_collector" / "app.py"
SSRF_APP = FIXTURES / "ssrf_lab" / "app.py"
REPORT_PATH = (
    Path(__file__).resolve().parents[1] / "reports" / "phase1_ssrf_tpr_fpr.json"
)

OAST_HOST, OAST_PORT = "127.0.0.1", 5097
SSRF_HOST, SSRF_PORT = "127.0.0.1", 5098

OPT_IN_ENV = "RUN_SSRF_FIELD_VALIDATION"

pytestmark = pytest.mark.skipif(
    os.environ.get(OPT_IN_ENV) != "1",
    reason=f"opt-in: set {OPT_IN_ENV}=1 to run Phase 1.1d integration",
)


def _port_open(host: str, port: int, timeout: float = 0.5) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _wait_health(host: str, port: int, deadline_s: float = 30.0) -> None:
    import urllib.request

    url = f"http://{host}:{port}/healthz"
    started = time.monotonic()
    last_err: str | None = None
    while time.monotonic() - started < deadline_s:
        try:
            with urllib.request.urlopen(url, timeout=1.0) as resp:
                if resp.read().decode().strip() == "ok":
                    return
        except Exception as exc:  # noqa: BLE001
            last_err = f"{type(exc).__name__}: {exc}"
        time.sleep(0.5)
    raise RuntimeError(f"{host}:{port} not healthy after {deadline_s}s: {last_err}")


@pytest.fixture(scope="module")
def lab_processes(monkeypatch_module):
    """Spawn OAST collector + SSRF lab; tear them down on teardown.

    Skips spawn for any port already bound (docker-compose case).
    Sets INTERACTSH_SERVER_URL so the oracle's default client points at
    the local collector.
    """
    procs: list[subprocess.Popen] = []
    if not _port_open(OAST_HOST, OAST_PORT):
        procs.append(subprocess.Popen(
            [sys.executable, str(OAST_APP)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        ))
    if not _port_open(SSRF_HOST, SSRF_PORT):
        procs.append(subprocess.Popen(
            [sys.executable, str(SSRF_APP)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        ))

    monkeypatch_module.setenv(
        "INTERACTSH_SERVER_URL", f"http://{OAST_HOST}:{OAST_PORT}"
    )
    # Reset the oracle's lazy-built default client so it picks up the env.
    import oracle_mcp.oast.interactsh as interactsh_mod
    interactsh_mod._DEFAULT_CLIENT = None

    try:
        _wait_health(OAST_HOST, OAST_PORT)
        _wait_health(SSRF_HOST, SSRF_PORT)
        yield procs
    finally:
        for p in procs:
            p.terminate()
            try:
                p.wait(timeout=5)
            except subprocess.TimeoutExpired:
                p.kill()


@pytest.fixture(scope="module")
def monkeypatch_module():
    """Module-scoped monkeypatch (pytest only ships function-scoped)."""
    from _pytest.monkeypatch import MonkeyPatch

    mp = MonkeyPatch()
    yield mp
    mp.undo()


def test_ssrf_field_validation_meets_phase1_gate(lab_processes) -> None:
    fixtures = load_fixtures(FIXTURE_PATH)
    assert len(fixtures) == 10, f"expected 10 targets, got {len(fixtures)}"

    runner = FieldValidationRunner()
    report = asyncio.run(runner.run(fixtures))

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report.to_dict(), indent=2))

    assert report.passes_exit_criterion(min_tpr=0.90, max_fpr=0.0), (
        f"Phase 1.1d gate failed: tpr={report.tpr:.3f} (need ≥0.90), "
        f"fpr={report.fpr:.3f} (need =0.0). "
        f"TP={report.true_positives} FP={report.false_positives} "
        f"FN={report.false_negatives} TN={report.true_negatives}. "
        f"Report written to {REPORT_PATH}."
    )
