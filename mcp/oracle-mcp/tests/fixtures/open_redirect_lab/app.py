"""Open Redirect vulnerable lab for Phase 2 W9-10 field validation.

20 routes total:
  - /v1 .. /v10  → vulnerable (issue 302/301/307 to user-supplied target)
  - /c1 .. /c10  → clean      (allowlist, relative-only, strict origin check)

The oracle injects ``target=https://example.com`` into the parameter and
follows redirects. A "vulnerable" route issues an HTTP redirect whose
final destination is ``example.com``; a "clean" route either does not
redirect, redirects only to allowlisted hosts, or rejects external hosts.

Variants exist so the oracle's `_matches_target` netloc check is
exercised across realistic open-redirect bypass shapes (case-flip,
scheme-flip, weak prefix check, etc).

Run standalone::

    pip install flask
    python app.py            # listens on 0.0.0.0:5095
"""

from __future__ import annotations

import re
import urllib.parse

from flask import Flask, jsonify, redirect, request

app = Flask(__name__)


def _to() -> str:
    return request.args.get("to", "")


@app.route("/healthz")
def healthz() -> str:
    return "ok"


# ---------------------------------------------------------------------------
# Vulnerable routes — each issues a redirect that ends on the user-supplied
# host. The oracle's `_matches_target` compares the final response URL's
# netloc against the injected target, so any path that lands the user on
# example.com (under default oracle config) counts as validated.
# ---------------------------------------------------------------------------


@app.route("/v1")
def v1():
    """Naive 302 to whatever the param says."""
    return redirect(_to(), code=302)


@app.route("/v2")
def v2():
    """301 permanent redirect — same naive shape."""
    return redirect(_to(), code=301)


@app.route("/v3")
def v3():
    """307 temporary redirect — preserves method, still external."""
    return redirect(_to(), code=307)


@app.route("/v4")
def v4():
    """Weak prefix check: rejects only if startswith literal 'evil://' ."""
    target = _to()
    if target.startswith("evil://"):
        return jsonify({"error": "blocked"}), 400
    return redirect(target, code=302)


@app.route("/v5")
def v5():
    """Two-hop chain: /v5 → /v5/step → external."""
    target = _to()
    if request.path.endswith("/step"):
        return redirect(target, code=302)
    return redirect(f"/v5/step?to={urllib.parse.quote(target)}", code=302)


@app.route("/v5/step")
def v5_step():
    return redirect(_to(), code=302)


@app.route("/v6")
def v6():
    """Allows arbitrary scheme — only checks for `javascript:` ."""
    target = _to()
    if target.lower().startswith("javascript:"):
        return jsonify({"error": "blocked"}), 400
    return redirect(target, code=302)


@app.route("/v7")
def v7():
    """Naive substring check: rejects only if 'evil' literally appears."""
    target = _to()
    if "evil" in target.lower():
        return jsonify({"error": "blocked"}), 400
    return redirect(target, code=302)


@app.route("/v8")
def v8():
    """Sets Location header directly — Flask passes the raw value."""
    return ("", 302, {"Location": _to()})


@app.route("/v9")
def v9():
    """Validates scheme is https — but otherwise lets host be anything."""
    target = _to()
    if not target.lower().startswith("https://"):
        return jsonify({"error": "https only"}), 400
    return redirect(target, code=302)


@app.route("/v10")
def v10():
    """`/?next=` style — same broken shape under a different param name."""
    return redirect(request.args.get("to", "") or request.args.get("next", ""), code=302)


# ---------------------------------------------------------------------------
# Clean routes — each blocks the external redirect.
# ---------------------------------------------------------------------------


@app.route("/c1")
def c1():
    """Allowlist of internal paths only — rejects anything starting with a scheme."""
    target = _to()
    if "://" in target or target.startswith("//"):
        return jsonify({"error": "external blocked"}), 400
    return redirect(f"/{target.lstrip('/')}", code=302)


@app.route("/c2")
def c2():
    """Strict allowlist of two known hosts."""
    target = _to()
    parsed = urllib.parse.urlparse(target)
    if parsed.netloc not in ("partner.example.org", "legit.example.net"):
        return jsonify({"error": "host not allowed"}), 400
    return redirect(target, code=302)


@app.route("/c3")
def c3():
    """No redirect — always returns the same 200 page regardless of input."""
    return "<html><body>welcome</body></html>"


@app.route("/c4")
def c4():
    """Always redirects to a fixed internal path, ignoring the param."""
    return redirect("/home", code=302)


@app.route("/c5")
def c5():
    """Regex allowlist: relative path with safe characters only."""
    target = _to()
    if not re.fullmatch(r"/[a-zA-Z0-9/_-]{1,64}", target):
        return jsonify({"error": "invalid path"}), 400
    return redirect(target, code=302)


@app.route("/c6")
def c6():
    """Rejects when the URL parser yields any netloc."""
    target = _to()
    parsed = urllib.parse.urlparse(target)
    if parsed.netloc or parsed.scheme:
        return jsonify({"error": "absolute URLs blocked"}), 400
    return redirect(target if target.startswith("/") else "/home", code=302)


@app.route("/c7")
def c7():
    """Hash-based redirect — param can't influence destination."""
    target = _to()
    options = ["/home", "/dashboard", "/profile"]
    return redirect(options[abs(hash(target)) % len(options)], code=302)


@app.route("/c8")
def c8():
    """Same-origin check — rejects when host differs from server."""
    target = _to()
    parsed = urllib.parse.urlparse(target)
    if parsed.netloc and parsed.netloc != request.host:
        return jsonify({"error": "off-origin blocked"}), 400
    return redirect(target or "/home", code=302)


@app.route("/c9")
def c9():
    """Returns 200 with a meta-refresh — oracle uses HTTP redirects only,
    so even though the meta tag points externally, the oracle won't follow it."""
    target = _to()
    return (
        f'<html><head><meta http-equiv="refresh" content="3; url={target}"></head>'
        f'<body>redirecting...</body></html>'
    )


@app.route("/c10")
def c10():
    """Returns a 200 with an external `Link: <...>` header (not a redirect)."""
    target = _to()
    return ("ok", 200, {"Link": f"<{target}>; rel=alternate"})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5095, threaded=True)
