"""SQLi vulnerable lab for Phase 2 W9-10 field validation.

20 routes total:
  - /v1 .. /v10  → vulnerable (honor SLEEP(N) in `q` — no input sanitisation)
  - /c1 .. /c10  → clean      (parameterised, numeric-only, or no DB lookup)

The lab is purpose-built for the oracle's MySQL time-delay payload
``' OR SLEEP({delay})-- -``. A "vulnerable" route extracts ``SLEEP(N)``
from the parameter value (mirroring how a real string-concat SQL query
would unconditionally execute the SLEEP) and pauses for ``N`` seconds
before responding. A "clean" route either rejects non-numeric input,
fully escapes the payload, or returns content that never depends on
the parameter — none of these sleep on payload presence.

The lab is **not** backed by a real MySQL/Postgres engine. Phase 2's
exit gate is "the SQLi oracle's Welch t-test correctly distinguishes
vulnerable timing-injection sites from clean ones"; a Flask server
that simulates the timing semantics is sufficient. Phase 3 calibration
against real databases is a separate workstream.

Run standalone::

    pip install flask
    python app.py            # listens on 0.0.0.0:5096

Or via docker-compose::

    docker compose -f tests/fixtures/docker-compose.yml up sqli-lab
"""

from __future__ import annotations

import contextlib
import re
import time

from flask import Flask, jsonify, request

app = Flask(__name__)

# Maximum sleep we honour even when SLEEP(N) is parsed — caps the worst-case
# wall-clock cost of a runaway test or stray payload. 12s gives enough
# headroom over the oracle's default 5s delay while preventing unbounded
# pauses if a test passes a huge value by mistake.
_MAX_SLEEP_SECONDS = 12.0

# Matches the relevant chunk of the oracle's MySQL payload — and any
# similarly-shaped string-concat SQLi attempt. Greedy on the inner number
# so callers can pass floats during fast smoke-testing.
_SLEEP_RE = re.compile(r"SLEEP\(\s*(\d+(?:\.\d+)?)\s*\)", re.IGNORECASE)


def _q() -> str:
    return request.args.get("q", "")


def _vulnerable_sleep(value: str) -> None:
    """Pause for the SLEEP(N) duration embedded in *value*, if any.

    A vulnerable route uses string-concatenation SQL of the form
    ``"SELECT ... WHERE x = '" + value + "'"``; if the user supplies
    ``' OR SLEEP(5)-- -`` the database evaluates the SLEEP function and
    the response stalls. We simulate that timing without a real DB.
    """
    m = _SLEEP_RE.search(value)
    if not m:
        return
    delay = min(float(m.group(1)), _MAX_SLEEP_SECONDS)
    if delay > 0:
        time.sleep(delay)


@app.route("/healthz")
def healthz() -> str:
    return "ok"


# ---------------------------------------------------------------------------
# Vulnerable routes — each is naively concatenating user input into SQL.
# Variants differ in response shape so the oracle's t-test must rely on
# timing alone, not response-body inspection.
# ---------------------------------------------------------------------------


@app.route("/v1")
def v1() -> str:
    """Vulnerable HTML page returning the q value verbatim after SQL exec."""
    q = _q()
    _vulnerable_sleep(q)
    return f"<html><body>row: {q}</body></html>"


@app.route("/v2")
def v2():
    """Vulnerable JSON endpoint."""
    q = _q()
    _vulnerable_sleep(q)
    return jsonify({"row": q, "found": False})


@app.route("/v3")
def v3() -> str:
    """Vulnerable plaintext endpoint."""
    q = _q()
    _vulnerable_sleep(q)
    return f"value={q}", 200, {"Content-Type": "text/plain"}


@app.route("/v4")
def v4():
    """Vulnerable redirect — but we still execute SQL before redirecting."""
    q = _q()
    _vulnerable_sleep(q)
    return ("", 302, {"Location": "/login"})


@app.route("/v5")
def v5():
    """Vulnerable empty 200 — no body but still slow on payload."""
    q = _q()
    _vulnerable_sleep(q)
    return ("", 200)


@app.route("/v6")
def v6():
    """Vulnerable with numeric coercion attempt that fails open on string."""
    q = _q()
    # Naive: tries int() but on failure still does string-concat SQL.
    with contextlib.suppress(ValueError):
        int(q)
    _vulnerable_sleep(q)
    return jsonify({"q": q, "kind": "fallback-string-concat"})


@app.route("/v7")
def v7():
    """Vulnerable with response that varies in length (still sleep-driven)."""
    q = _q()
    _vulnerable_sleep(q)
    body = "row\n" * 50
    return body, 200, {"Content-Type": "text/plain"}


@app.route("/v8")
def v8():
    """Vulnerable behind a permissive header check."""
    if request.headers.get("X-Skip-DB") == "yes":
        return jsonify({"row": "skipped"})
    q = _q()
    _vulnerable_sleep(q)
    return jsonify({"row": q})


@app.route("/v9")
def v9():
    """Vulnerable with quoted reflection in body — payload echoes back."""
    q = _q()
    _vulnerable_sleep(q)
    return f"<html><body><pre>'{q}'</pre></body></html>"


@app.route("/v10")
def v10():
    """Vulnerable with response cookies set after SQL runs."""
    q = _q()
    _vulnerable_sleep(q)
    resp = app.make_response(jsonify({"row": q}))
    resp.set_cookie("last_query", q[:32])
    return resp


# ---------------------------------------------------------------------------
# Clean routes — each ignores the SLEEP() payload because the underlying
# SQL is parameterised, the input is rejected, or no DB call happens.
# ---------------------------------------------------------------------------


@app.route("/c1")
def c1():
    """Clean: numeric-only input, rejects everything else."""
    q = _q()
    if not q.isdigit():
        return jsonify({"error": "numeric only"}), 400
    return jsonify({"row": int(q)})


@app.route("/c2")
def c2():
    """Clean: parameterised — payload is treated as literal data."""
    return jsonify({"row": _q()})


@app.route("/c3")
def c3():
    """Clean: static response regardless of input."""
    return "static-response", 200, {"Content-Type": "text/plain"}


@app.route("/c4")
def c4():
    """Clean: regex allowlist [a-z0-9-]{1,32}."""
    q = _q()
    if not re.fullmatch(r"[a-z0-9-]{1,32}", q):
        return jsonify({"error": "invalid"}), 400
    return jsonify({"row": q})


@app.route("/c5")
def c5():
    """Clean: input is hashed before the (non-time-sensitive) DB lookup."""
    import hashlib

    q = _q()
    digest = hashlib.sha256(q.encode()).hexdigest()
    return jsonify({"hash": digest, "found": False})


@app.route("/c6")
def c6():
    """Clean: HTML escape + parameterised — no SLEEP expansion path."""
    from html import escape

    q = _q()
    return f"<html><body>row: {escape(q)}</body></html>"


@app.route("/c7")
def c7():
    """Clean: short-circuits before any DB call when payload too long."""
    q = _q()
    if len(q) > 16:
        return jsonify({"error": "too long"}), 400
    return jsonify({"row": q})


@app.route("/c8")
def c8():
    """Clean: rejects on common SQL keywords (defence in depth)."""
    q = _q().upper()
    for kw in ("SELECT", "UNION", "SLEEP", "WAITFOR", "BENCHMARK", "PG_SLEEP"):
        if kw in q:
            return jsonify({"error": f"forbidden token {kw}"}), 400
    return jsonify({"row": _q()})


@app.route("/c9")
def c9():
    """Clean: parameterised JSON endpoint (cache-friendly)."""
    return jsonify({"q": _q(), "cached": True}), 200, {"Cache-Control": "max-age=60"}


@app.route("/c10")
def c10():
    """Clean: 404 on every input — DB never queried."""
    return jsonify({"error": "not found"}), 404


if __name__ == "__main__":
    # Threaded so concurrent requests during the oracle's baseline+inject
    # bursts don't queue behind one another. Honour the explicit lab port.
    app.run(host="0.0.0.0", port=5096, threaded=True)
