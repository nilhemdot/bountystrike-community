"""SSRF vulnerable lab for Phase 1.1d field validation.

10 routes total:
  - /v1 .. /v5  → vulnerable: server fetches the URL in `q` and the
                   OAST callback is hit on the way through
  - /c1 .. /c5  → clean: validates / allowlists / refuses external URLs

The oracle (oracle_mcp.oracles.ssrf) injects an Interactsh callback URL
into ``q`` and waits for an out-of-band callback. A "vulnerable" route
is anything that passes ``q`` to an HTTP client and follows it. Clean
routes either ignore ``q``, validate against an allowlist, or strip the
scheme.

Run standalone::

    pip install flask httpx
    python app.py            # listens on 0.0.0.0:5098

Or via docker-compose (paired with the oast_collector service)::

    docker compose -f tests/fixtures/docker-compose.yml up
"""

from __future__ import annotations

import re
from urllib.parse import urlparse

import httpx
from flask import Flask, Response, request

app = Flask(__name__)

# Short HTTP timeout — the lab MUST not hang the oracle if a probe URL
# is unreachable. The oracle's own timeout is the upper bound.
_HTTP_TIMEOUT_S = 4.0


def _q() -> str:
    return request.args.get("q", "")


def _fetch(url: str) -> str:
    """Issue a GET to ``url`` and swallow errors.

    The lab does not need the response body; the SSRF oracle only cares
    that the OAST callback receiver was reached. Any errors are
    converted to a sentinel string so the route still returns 200.
    """
    try:
        with httpx.Client(timeout=_HTTP_TIMEOUT_S, follow_redirects=False) as c:
            r = c.get(url)
            return f"fetched status={r.status_code}"
    except httpx.HTTPError as exc:
        return f"fetch failed: {type(exc).__name__}"


# ---------------------------------------------------------------------------
# Vulnerable routes — fetch the user-supplied URL.
# ---------------------------------------------------------------------------


@app.route("/v1")
def v1() -> str:
    """Naive: fetch q verbatim."""
    out = _fetch(_q())
    return f"<html><body><p>{out}</p></body></html>"


@app.route("/v2")
def v2() -> str:
    """Webhook-style: fetch q after extracting it from a 'destination' alias."""
    target = request.args.get("q") or request.args.get("destination") or ""
    out = _fetch(target)
    return f"<html><body><p>{out}</p></body></html>"


@app.route("/v3")
def v3() -> str:
    """Image-proxy: blindly fetches the URL and returns content-length."""
    try:
        with httpx.Client(timeout=_HTTP_TIMEOUT_S) as c:
            r = c.get(_q())
        return f"<html><body><p>length={len(r.content)}</p></body></html>"
    except httpx.HTTPError:
        return "<html><body><p>err</p></body></html>"


@app.route("/v4")
def v4() -> str:
    """URL-fetcher with redirect following enabled (still SSRF)."""
    try:
        with httpx.Client(timeout=_HTTP_TIMEOUT_S, follow_redirects=True) as c:
            c.get(_q())
    except httpx.HTTPError:
        pass
    return "<html><body><p>ok</p></body></html>"


@app.route("/v5")
def v5() -> str:
    """Naive scheme check (accepts http and https) but no host validation."""
    target = _q()
    parsed = urlparse(target)
    if parsed.scheme not in ("http", "https"):
        return "<html><body>scheme rejected</body></html>"
    out = _fetch(target)
    return f"<html><body><p>{out}</p></body></html>"


# ---------------------------------------------------------------------------
# Clean routes — never fetch the user URL.
# ---------------------------------------------------------------------------


@app.route("/c1")
def c1() -> str:
    """Echo-only: returns the param value as text, no fetch."""
    return f"<html><body>echo: {_q()}</body></html>"


@app.route("/c2")
def c2() -> str:
    """Hostname allowlist: only fetches if the URL's host is in the set."""
    allowed_hosts = {"images.acme.internal", "cdn.acme.internal"}
    parsed = urlparse(_q())
    if parsed.hostname not in allowed_hosts:
        return "<html><body>denied</body></html>"
    out = _fetch(_q())
    return f"<html><body>{out}</body></html>"


@app.route("/c3")
def c3() -> str:
    """Regex check: requires hostname under acme.com."""
    parsed = urlparse(_q())
    if not parsed.hostname or not re.match(r".*\.acme\.com$", parsed.hostname):
        return "<html><body>denied</body></html>"
    out = _fetch(_q())
    return f"<html><body>{out}</body></html>"


@app.route("/c4")
def c4() -> str:
    """Map lookup: q is a key into an internal id→URL map; never user URL."""
    INTERNAL = {
        "logo": "http://acme.internal/static/logo.png",
        "favicon": "http://acme.internal/static/favicon.ico",
    }
    target = INTERNAL.get(_q())
    if not target:
        return "<html><body>not found</body></html>"
    # Fetch the safe internal URL — never the user value.
    out = _fetch(target)
    return f"<html><body>{out}</body></html>"


@app.route("/c5")
def c5() -> str:
    """Rejects any value containing a colon (eliminates http://, file://, …)."""
    if ":" in _q():
        return "<html><body>denied</body></html>"
    return f"<html><body>echo: {_q()}</body></html>"


# ---------------------------------------------------------------------------
# Health endpoint
# ---------------------------------------------------------------------------


@app.route("/healthz")
def healthz() -> Response:
    return Response("ok", mimetype="text/plain")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5098, debug=False, threaded=True)
