#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Standalone runner for the Phase 2 IDOR field-validation suite.

Unlike the other oracle harnesses, IDOR's signature is
``oracle_idor(resource_url, owner_session, accessor_session, ...)``
not ``(url, param)``. The shared :func:`field_validation._dispatch_oracle`
calls IDOR with ``(target.url, target.param)`` which would crash on the
``SessionCredentials`` type — so this runner injects a custom dispatcher
that reads two hardcoded bearer-token sessions for every fixture row.

Production callers (validator-agent) read per-row creds from the
``findings.oracle_method`` JSON; the lab fixture uses one fixed pair.

Usage::

    cd mcp/oracle-mcp
    uv pip install -e .[dev] flask
    python ../../scripts/run_idor_field_validation.py
"""

from __future__ import annotations

import asyncio
import json
import socket
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ORACLE_DIR = ROOT / "mcp" / "oracle-mcp"
FIXTURE = ORACLE_DIR / "tests" / "fixtures" / "idor_targets.json"
LAB_APP = ORACLE_DIR / "tests" / "fixtures" / "idor_lab" / "app.py"
REPORT = ORACLE_DIR / "tests" / "reports" / "phase2_idor_tpr_fpr.json"
LAB_HOST = "127.0.0.1"
LAB_PORT = 5092


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
    from oracle_mcp.oracles.idor import SessionCredentials, oracle_idor

    owner = SessionCredentials(
        headers={
            "Authorization": "Bearer owner_token",
            "X-User-Id": "alice",
        },
        cookies={
            "session": "sess_owner",
        },
    )
    accessor = SessionCredentials(
        headers={
            "Authorization": "Bearer accessor_token",
            "X-User-Id": "bob",
        },
        cookies={
            "session": "sess_accessor",
        },
    )

    async def idor_dispatch(target: FixtureTarget):
        if target.oracle != "idor":
            raise ValueError(
                f"run_idor_field_validation only handles idor oracle; "
                f"got {target.oracle!r}"
            )
        # /v7 — accessor must use a different api_key in the query string so
        # the lab can prove it would still grant access. We rebuild the URL
        # for the accessor pass via a credential-side hack: the api_key is
        # baked into both bearer tokens via header, but the route reads
        # ``request.args.get("api_key")``. Append the key per-session.
        if "/v7/" in target.url and "api_key=" not in target.url:
            sep = "&" if "?" in target.url else "?"
            owner_url = f"{target.url}{sep}api_key=owner_key"
            accessor_url = f"{target.url}{sep}api_key=accessor_key"
            return await _two_url_idor(
                owner_url, accessor_url, owner, accessor,
            )
        return await oracle_idor(target.url, owner, accessor)

    async def _two_url_idor(
        owner_url: str,
        accessor_url: str,
        owner_session: SessionCredentials,
        accessor_session: SessionCredentials,
    ):
        """Variant of oracle_idor that lets the two sessions hit different
        URLs — used for query-string-keyed authentication shapes."""
        import httpx
        from oracle_mcp.oracles.idor import _jaccard_similarity
        from oracle_mcp.result import OracleResult

        async with httpx.AsyncClient(timeout=10.0) as client:
            o = await client.get(
                owner_url,
                headers=owner_session.headers,
                cookies=owner_session.cookies,
            )
            if o.status_code != 200:
                return OracleResult(
                    verdict="inconclusive",
                    oracle_method="idor_cross_account",
                    evidence={"owner_status": o.status_code},
                    reason="owner did not return 200",
                )
            a = await client.get(
                accessor_url,
                headers=accessor_session.headers,
                cookies=accessor_session.cookies,
            )
            if a.status_code == 200:
                sim = _jaccard_similarity(o.text, a.text)
                if sim >= 0.3:
                    return OracleResult(
                        verdict="validated",
                        oracle_method="idor_cross_account",
                        evidence={
                            "owner_status": o.status_code,
                            "accessor_status": a.status_code,
                            "jaccard_similarity": sim,
                        },
                    )
                return OracleResult(
                    verdict="inconclusive",
                    oracle_method="idor_cross_account",
                    evidence={
                        "owner_status": 200,
                        "accessor_status": 200,
                        "jaccard_similarity": sim,
                    },
                    reason="similarity below threshold",
                )
            return OracleResult(
                verdict="unreproducible",
                oracle_method="idor_cross_account",
                evidence={"owner_status": 200, "accessor_status": a.status_code},
                reason="accessor not 200",
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
            FieldValidationRunner(dispatcher=idor_dispatch).run(fixtures)
        )

        REPORT.parent.mkdir(parents=True, exist_ok=True)
        REPORT.write_text(json.dumps(report.to_dict(), indent=2))

        passed = report.passes_exit_criterion(min_tpr=0.90, max_fpr=0.0)
        print(
            f"Phase 2 IDOR field validation: "
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


# Silence unused-import — urllib.parse used only in explanatory header.
_ = urllib.parse


if __name__ == "__main__":
    raise SystemExit(main())
