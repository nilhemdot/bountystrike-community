"""SSRF→IMDS vulnerable lab for Phase 2 field validation.

20 routes total:
  - /v1 .. /v10 → vulnerable: simulates server-side proxy that returns
                   synthetic cloud-IMDS bodies when the user URL targets
                   a known IMDS endpoint
  - /c1 .. /c10 → clean: blocks IMDS hosts, strips markers, or transforms
                   the body so no provider marker survives

The oracle (oracle_mcp.oracles.ssrf_imds) injects three IMDS URLs into
the named query parameter and scans the response text for provider
markers:

    AWS    → "ami-id" / "instance-id"      via http://169.254.169.254/latest/meta-data/
    GCP    → "email" / "project-id"        via http://metadata.google.internal/computeMetadata/v1/
    Azure  → "azEnvironment" / "subscriptionId"  via http://169.254.169.254/metadata/instance

The lab simulates IMDS proxying entirely inline. ``_imds_body_for_url``
pattern-matches the URL host/path and returns a synthetic body containing
the markers. **No real network egress, ever.** Vulnerable routes return
that body (markers intact); clean routes either refuse the fetch, deny
the IMDS host, or transform the response so markers don't survive.

Run standalone::

    pip install flask
    python app.py            # listens on 0.0.0.0:5100
"""

from __future__ import annotations

import base64
import hashlib
import re
from urllib.parse import urlparse

from flask import Flask, Response, jsonify, request

app = Flask(__name__)


# Synthetic IMDS bodies. Each must contain its provider's markers; clean
# routes are audited to ensure none of these strings leak via static text.
_AWS_BODY = (
    "ami-id\nami-0abcd1234ef567890\n"
    "instance-id\ni-0123456789abcdef0\n"
    "instance-type\nt3.medium\n"
    "local-hostname\nip-10-0-0-42.ec2.internal\n"
    "iam/security-credentials/role-app\n"
)

_GCP_BODY = (
    '{"email":"123456789-compute@developer.gserviceaccount.com",'
    '"project-id":"my-prod-project-873421",'
    '"scopes":["https://www.googleapis.com/auth/cloud-platform"]}'
)

_AZURE_BODY = (
    '{"compute":{"azEnvironment":"AzurePublicCloud",'
    '"subscriptionId":"d6e7f9a1-2b3c-4d5e-6f70-8190a1b2c3d4",'
    '"location":"eastus","name":"vm-prod-1"}}'
)


def _imds_body_for_url(url: str) -> str | None:
    """Return synthetic IMDS body for *url*, or None for non-IMDS URLs.

    Pure pattern match — no network I/O, no DNS, no socket. Hosts and
    paths are matched exactly against the three endpoints the oracle
    probes; anything else returns None.
    """
    try:
        parsed = urlparse(url)
    except ValueError:
        return None
    host = (parsed.hostname or "").lower()
    path = parsed.path or ""
    if host == "169.254.169.254":
        if "/latest/meta-data" in path:
            return _AWS_BODY
        if "/metadata/instance" in path:
            return _AZURE_BODY
    if host == "metadata.google.internal":
        return _GCP_BODY
    return None


def _fetch(url: str) -> str:
    """Stand-in for an HTTP GET. Returns IMDS body for matching URLs."""
    body = _imds_body_for_url(url)
    if body is not None:
        return body
    return "fetch_error connection_refused"


# IMDS hosts blocked by defense-in-depth clean routes.
_BLOCKED_HOSTS = {"169.254.169.254", "metadata.google.internal"}

# All marker tokens across the three providers; used by /c3 sanitiser.
_ALL_MARKERS = (
    "ami-id",
    "instance-id",
    "email",
    "project-id",
    "azEnvironment",
    "subscriptionId",
)


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


@app.route("/healthz")
def healthz() -> Response:
    return Response("ok", mimetype="text/plain")


# ---------------------------------------------------------------------------
# Vulnerable routes — each returns a body with at least one provider marker
# for at least one of the three IMDS probes the oracle issues.
# ---------------------------------------------------------------------------


@app.route("/v1")
def v1() -> str:
    """Naive ?url= direct proxy — leaks AWS on first probe."""
    return _fetch(request.args.get("url", ""))


@app.route("/v2")
def v2() -> str:
    """Same as v1 with a different param name (?u=)."""
    return _fetch(request.args.get("u", ""))


@app.route("/v3")
def v3():
    """Internal-host allowlist that mistakenly includes 169.254.169.254."""
    target = request.args.get("url", "")
    parsed = urlparse(target)
    host = (parsed.hostname or "").lower()
    allowed = {"acme.internal", "169.254.169.254"}
    if host not in allowed:
        return jsonify({"error": "host not in allowlist"}), 403
    return _fetch(target)


@app.route("/v4")
def v4():
    """Scheme allowlist (http+https). No host filter — IMDS still reachable."""
    target = request.args.get("url", "")
    parsed = urlparse(target)
    if parsed.scheme not in ("http", "https"):
        return jsonify({"error": "scheme blocked"}), 403
    return _fetch(target)


@app.route("/v5")
def v5() -> str:
    """HTML wrapper around proxy result — markers survive in <pre>."""
    body = _fetch(request.args.get("url", ""))
    return f"<html><body><pre>upstream:\n{body}\n</pre></body></html>"


@app.route("/v6")
def v6():
    """JSON envelope around proxy result — markers survive in body field."""
    body = _fetch(request.args.get("url", ""))
    return jsonify({"status": "ok", "body": body})


@app.route("/v7")
def v7() -> str:
    """Server-side rewrite: strips trailing '/redirect' and refetches.

    Models a SSRF where the lab follows a 302 internally before responding.
    The oracle's URL has no '/redirect' suffix so the strip is a no-op,
    but exercises the route's URL-mutation code path.
    """
    target = request.args.get("url", "").removesuffix("/redirect")
    return _fetch(target)


@app.route("/v8")
def v8():
    """Blocks 169.254.169.254 only — GCP probe still leaks via metadata.google.internal."""
    target = request.args.get("url", "")
    parsed = urlparse(target)
    host = (parsed.hostname or "").lower()
    if host == "169.254.169.254":
        return jsonify({"error": "link-local denied"}), 403
    return _fetch(target)


@app.route("/v9")
def v9():
    """Blocks /latest/ path — Azure (/metadata/instance) and GCP probes still leak."""
    target = request.args.get("url", "")
    parsed = urlparse(target)
    if "/latest/" in (parsed.path or ""):
        return jsonify({"error": "/latest/ path blocked"}), 403
    return _fetch(target)


@app.route("/v10")
def v10() -> str:
    """Timestamp prefix on proxy result — markers survive after newline."""
    body = _fetch(request.args.get("url", ""))
    return f"[fetched at 2026-05-01T00:00:00Z]\n{body}"


# ---------------------------------------------------------------------------
# Clean routes — must NOT return any body containing a provider marker.
# Each route is audited: the static text never contains the strings in
# _ALL_MARKERS, and any dynamic content either skips the IMDS fetch or
# transforms it irreversibly.
# ---------------------------------------------------------------------------


@app.route("/c1")
def c1() -> Response:
    """Strict allowlist: only example.com may be fetched."""
    target = request.args.get("url", "")
    parsed = urlparse(target)
    host = (parsed.hostname or "").lower()
    if host != "example.com":
        return Response("denied", status=403)
    return Response(_fetch(target))


@app.route("/c2")
def c2() -> Response:
    """Explicit IMDS-host deny."""
    target = request.args.get("url", "")
    parsed = urlparse(target)
    host = (parsed.hostname or "").lower()
    if host in _BLOCKED_HOSTS:
        return Response("denied", status=403)
    return Response(_fetch(target))


@app.route("/c3")
def c3() -> str:
    """Fetches but strips every provider marker before returning."""
    body = _fetch(request.args.get("url", ""))
    for token in _ALL_MARKERS:
        body = body.replace(token, "[redacted]")
    return body


@app.route("/c4")
def c4() -> str:
    """Returns response length only — body is never echoed."""
    body = _fetch(request.args.get("url", ""))
    return f"length={len(body)}"


@app.route("/c5")
def c5() -> Response:
    """RFC1918 + link-local block + IMDS host deny (defense in depth)."""
    target = request.args.get("url", "")
    parsed = urlparse(target)
    host = (parsed.hostname or "").lower()
    if re.match(r"^(169\.254\.|10\.|172\.(1[6-9]|2[0-9]|3[01])\.|192\.168\.)", host):
        return Response("private IP refused", status=403)
    if host in _BLOCKED_HOSTS:
        return Response("denied", status=403)
    return Response(_fetch(target))


@app.route("/c6")
def c6() -> Response:
    """Scheme allowlist: https only. IMDS endpoints are http → all denied."""
    target = request.args.get("url", "")
    parsed = urlparse(target)
    if parsed.scheme != "https":
        return Response("https only", status=403)
    return Response(_fetch(target))


@app.route("/c7")
def c7() -> str:
    """Static OK regardless of input."""
    return "OK"


@app.route("/c8")
def c8():
    """Static queued-status JSON; never fetches."""
    return jsonify({"status": "queued"})


@app.route("/c9")
def c9() -> str:
    """Fetches but base64-encodes the body (markers no longer plaintext)."""
    body = _fetch(request.args.get("url", ""))
    return base64.b64encode(body.encode()).decode()


@app.route("/c10")
def c10() -> str:
    """Fetches but returns SHA-256 hex digest of body — provably markerless."""
    body = _fetch(request.args.get("url", ""))
    return hashlib.sha256(body.encode()).hexdigest()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5100, threaded=True)
