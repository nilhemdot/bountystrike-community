#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Standalone runner for the Phase 1.1d SSRF field-validation suite.

Boots the OAST collector (port 5097) and SSRF lab (port 5098) if they
aren't already running, points the InteractshClient at the local
collector, runs the 10-target corpus, and writes
``tests/reports/phase1_ssrf_tpr_fpr.json``. Exits non-zero if the
Phase 1 exit gate (TPR ≥ 0.90, FPR == 0) is not met.

Usage::

    cd mcp/oracle-mcp
    uv pip install -e .[dev] flask httpx
    python ../../scripts/run_ssrf_field_validation.py
"""

from __future__ import annotations

import asyncio
import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ORACLE_DIR = ROOT / "mcp" / "oracle-mcp"
FIXTURE = ORACLE_DIR / "tests" / "fixtures" / "ssrf_targets.json"
OAST_APP = ORACLE_DIR / "tests" / "fixtures" / "oast_collector" / "app.py"
SSRF_APP = ORACLE_DIR / "tests" / "fixtures" / "ssrf_lab" / "app.py"
REPORT = ORACLE_DIR / "tests" / "reports" / "phase1_ssrf_tpr_fpr.json"

OAST_HOST, OAST_PORT = "127.0.0.1", 5097
SSRF_HOST, SSRF_PORT = "127.0.0.1", 5098


def _port_open(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=0.5):
            return True
    except OSError:
        return False


def _wait_health(host: str, port: int, deadline_s: float = 30.0) -> None:
    started = time.monotonic()
    last_err: str | None = None
    url = f"http://{host}:{port}/healthz"
    while time.monotonic() - started < deadline_s:
        try:
            with urllib.request.urlopen(url, timeout=1.0) as resp:
                if resp.read().decode().strip() == "ok":
                    return
        except Exception as exc:  # noqa: BLE001
            last_err = f"{type(exc).__name__}: {exc}"
        time.sleep(0.5)
    raise RuntimeError(f"{host}:{port} not healthy after {deadline_s}s: {last_err}")


def main() -> int:
    sys.path.insert(0, str(ORACLE_DIR / "src"))

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

    os.environ["INTERACTSH_SERVER_URL"] = f"http://{OAST_HOST}:{OAST_PORT}"

    try:
        _wait_health(OAST_HOST, OAST_PORT)
        _wait_health(SSRF_HOST, SSRF_PORT)

        # Reset the oracle's lazy-built default client AFTER the env
        # is set so it picks up the local collector URL.
        import oracle_mcp.oast.interactsh as interactsh_mod
        interactsh_mod._DEFAULT_CLIENT = None

        from oracle_mcp.field_validation import (
            FieldValidationRunner,
            load_fixtures,
        )

        fixtures = load_fixtures(FIXTURE)
        report = asyncio.run(FieldValidationRunner().run(fixtures))

        REPORT.parent.mkdir(parents=True, exist_ok=True)
        REPORT.write_text(json.dumps(report.to_dict(), indent=2))

        passed = report.passes_exit_criterion(min_tpr=0.90, max_fpr=0.0)
        print(
            f"Phase 1.1d SSRF field validation: "
            f"tpr={report.tpr:.3f} fpr={report.fpr:.3f} "
            f"tp={report.true_positives} fp={report.false_positives} "
            f"fn={report.false_negatives} tn={report.true_negatives} "
            f"=> {'PASS' if passed else 'FAIL'}"
        )
        print(f"Report: {REPORT}")
        return 0 if passed else 1
    finally:
        for p in procs:
            p.terminate()
            try:
                p.wait(timeout=5)
            except subprocess.TimeoutExpired:
                p.kill()


if __name__ == "__main__":
    raise SystemExit(main())
