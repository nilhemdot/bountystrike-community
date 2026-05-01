#!/usr/bin/env python3
"""Standalone runner for the Phase 2 SQLi field-validation suite.

Bypasses pytest. Boots the lab if not running, executes the 20-target
corpus through ``FieldValidationRunner`` with reduced sample/delay
parameters (2s SLEEP, 4 samples) so wall-clock stays under ~3 minutes,
prints a one-line summary, writes the JSON report, and exits non-zero
if the gate is not met (TPR ≥ 0.90 AND FPR == 0).

The reduced parameters still keep the Welch t-test well-powered against
the lab's deterministic timing — the production oracle runs with
``baseline_n=7, inject_n=7, delay_seconds=5.0`` for noisier real-world
sites. We bypass those defaults via a custom dispatcher because the
shared ``_dispatch_oracle`` does not currently expose oracle kwargs.

Usage::

    cd mcp/oracle-mcp
    uv pip install -e .[dev] flask
    python ../../scripts/run_sqli_field_validation.py
"""

from __future__ import annotations

import asyncio
import json
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ORACLE_DIR = ROOT / "mcp" / "oracle-mcp"
FIXTURE = ORACLE_DIR / "tests" / "fixtures" / "sqli_targets.json"
LAB_APP = ORACLE_DIR / "tests" / "fixtures" / "sqli_lab" / "app.py"
REPORT = ORACLE_DIR / "tests" / "reports" / "phase2_sqli_tpr_fpr.json"
LAB_HOST = "127.0.0.1"
LAB_PORT = 5096

# Fast-mode oracle params — enough samples for the t-test on a deterministic
# lab, slim enough that the full 20-target run stays under ~3 minutes wall
# clock. Production runs use the oracle's defaults (7/7/5s).
SQLI_BASELINE_N = 4
SQLI_INJECT_N = 4
SQLI_DELAY_SECONDS = 2.0
SQLI_ALPHA = 0.01


def _port_open(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=0.5):
            return True
    except OSError:
        return False


def _wait_for_health(deadline_s: float = 30.0) -> None:
    started = time.monotonic()
    last_err: str | None = None
    url = f"http://{LAB_HOST}:{LAB_PORT}/healthz"
    while time.monotonic() - started < deadline_s:
        try:
            with urllib.request.urlopen(url, timeout=1.0) as resp:  # noqa: S310
                if resp.read().decode().strip() == "ok":
                    return
        except Exception as exc:  # noqa: BLE001
            last_err = f"{type(exc).__name__}: {exc}"
        time.sleep(0.5)
    raise RuntimeError(f"lab not healthy after {deadline_s}s: {last_err}")


def main() -> int:
    sys.path.insert(0, str(ORACLE_DIR / "src"))
    from oracle_mcp.field_validation import (
        FieldValidationRunner,
        FixtureTarget,
        load_fixtures,
    )
    from oracle_mcp.oracles.sqli import oracle_sqli

    async def fast_dispatch(target: FixtureTarget):
        if target.oracle != "sqli":
            raise ValueError(
                f"run_sqli_field_validation only handles sqli oracle; "
                f"got {target.oracle!r}"
            )
        return await oracle_sqli(
            target.url,
            target.param,
            baseline_n=SQLI_BASELINE_N,
            inject_n=SQLI_INJECT_N,
            delay_seconds=SQLI_DELAY_SECONDS,
            alpha=SQLI_ALPHA,
        )

    spawned = None
    if not _port_open(LAB_HOST, LAB_PORT):
        spawned = subprocess.Popen(
            [sys.executable, str(LAB_APP)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )

    try:
        _wait_for_health()
        fixtures = load_fixtures(FIXTURE)
        report = asyncio.run(
            FieldValidationRunner(dispatcher=fast_dispatch).run(fixtures)
        )

        REPORT.parent.mkdir(parents=True, exist_ok=True)
        REPORT.write_text(json.dumps(report.to_dict(), indent=2))

        passed = report.passes_exit_criterion(min_tpr=0.90, max_fpr=0.0)
        print(
            f"Phase 2 SQLi field validation: "
            f"tpr={report.tpr:.3f} fpr={report.fpr:.3f} "
            f"tp={report.true_positives} fp={report.false_positives} "
            f"fn={report.false_negatives} tn={report.true_negatives} "
            f"=> {'PASS' if passed else 'FAIL'}"
        )
        print(f"Report: {REPORT}")
        return 0 if passed else 1
    finally:
        if spawned is not None:
            spawned.terminate()
            try:
                spawned.wait(timeout=5)
            except subprocess.TimeoutExpired:
                spawned.kill()


if __name__ == "__main__":
    raise SystemExit(main())
