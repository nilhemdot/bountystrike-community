"""RCE vulnerable lab for Phase 2 W9-10 field validation.

20 routes total:
  - /v1 .. /v10  → vulnerable (echo back the ``{nonce}_rce_marker`` payload)
  - /c1 .. /c10  → clean      (HTML-escape, denylist shell metachars, etc.)

The oracle injects four shell-style payloads (Unix semicolon-echo, Unix
backtick-echo, Windows ``&echo``, PowerShell ``Write-Output``) and
checks whether ``{nonce}_rce_marker`` appears in the response body. A
"vulnerable" route detects the marker pattern in the query string and
echoes it back verbatim — simulating an underlying shell that executed
the injected command. A "clean" route either reflects nothing,
HTML-escapes the param, denies shell metacharacters, or returns content
that never echoes the marker.

Run standalone::

    pip install flask
    python app.py            # listens on 0.0.0.0:5093
"""

from __future__ import annotations

import re

from flask import Flask, jsonify, request

app = Flask(__name__)

# Captures the nonce when any of the oracle's four injection patterns
# appears in the parameter value. Anchored loosely so a vulnerable route
# can pretend the shell *executed* the echo regardless of which form was
# used.
_MARKER_RE = re.compile(r"([0-9a-f]{16})_rce_marker", re.IGNORECASE)

# Per-style detector regexes — used by the single-style vulnerable routes
# so we can prove each style independently triggers the oracle.
_STYLE_RE: dict[str, re.Pattern[str]] = {
    "unix_semicolon": re.compile(r";\s*echo\s+([0-9a-f]{16})_rce_marker", re.IGNORECASE),
    "unix_backtick":  re.compile(r"`echo\s+([0-9a-f]{16})_rce_marker`", re.IGNORECASE),
    "windows":        re.compile(r"&\s*echo\s+([0-9a-f]{16})_rce_marker", re.IGNORECASE),
    "powershell":     re.compile(r"\|\s*Write-Output\s+([0-9a-f]{16})_rce_marker", re.IGNORECASE),
}


def _q() -> str:
    return request.args.get("q", "")


def _echo_if_match(value: str, style: str | None = None) -> str | None:
    """Return the matching ``{nonce}_rce_marker`` from *value*, or None."""
    pat = _STYLE_RE[style] if style else _MARKER_RE
    m = pat.search(value)
    return f"{m.group(1)}_rce_marker" if m else None


@app.route("/healthz")
def healthz() -> str:
    return "ok"


# ---------------------------------------------------------------------------
# Vulnerable routes — each "executes" the injected shell command by
# detecting the oracle's marker pattern and echoing it back in the body.
# ---------------------------------------------------------------------------


@app.route("/v1")
def v1() -> str:
    """Unix semicolon — ``;echo NONCE_rce_marker``."""
    out = _echo_if_match(_q(), "unix_semicolon") or ""
    return f"<html><body>cmd output: {out}</body></html>"


@app.route("/v2")
def v2() -> str:
    """Unix backtick — `` `echo NONCE_rce_marker` ``."""
    out = _echo_if_match(_q(), "unix_backtick") or ""
    return f"<html><body>{out}</body></html>"


@app.route("/v3")
def v3() -> str:
    """Windows cmd — ``&echo NONCE_rce_marker``."""
    out = _echo_if_match(_q(), "windows") or ""
    return f"<pre>{out}</pre>"


@app.route("/v4")
def v4() -> str:
    """PowerShell — ``|Write-Output NONCE_rce_marker``."""
    out = _echo_if_match(_q(), "powershell") or ""
    return f"<html><body>ps: {out}</body></html>"


@app.route("/v5")
def v5():
    """Multi-style JSON endpoint — accepts any of the four shells."""
    out = _echo_if_match(_q()) or ""
    return jsonify({"output": out})


@app.route("/v6")
def v6() -> str:
    """Multi-style with marker embedded mid-text."""
    out = _echo_if_match(_q()) or ""
    return f"hello\n{out}\nbye", 200, {"Content-Type": "text/plain"}


@app.route("/v7")
def v7() -> str:
    """Multi-style — marker inside attribute."""
    out = _echo_if_match(_q()) or ""
    return f'<html><body><span title="{out}">x</span></body></html>'


@app.route("/v8")
def v8() -> str:
    """Multi-style — marker in CSS comment-like content."""
    out = _echo_if_match(_q()) or ""
    return f"<style>/* {out} */</style><body>page</body>"


@app.route("/v9")
def v9():
    """Multi-style with cookie set after exec."""
    out = _echo_if_match(_q()) or ""
    resp = app.make_response(f"<body>{out}</body>")
    resp.set_cookie("last_output", out[:64])
    return resp


@app.route("/v10")
def v10():
    """Multi-style behind a permissive header check."""
    if request.headers.get("X-Skip-Exec") == "yes":
        return jsonify({"output": "skipped"})
    out = _echo_if_match(_q()) or ""
    return jsonify({"output": out})


# ---------------------------------------------------------------------------
# Clean routes — none echo the marker.
# ---------------------------------------------------------------------------


@app.route("/c1")
def c1():
    """HTML escape PLUS truncation — payload echoes back but the marker
    substring can't survive an 8-character cap. Defends against the
    oracle's substring check (HTML escape alone isn't enough, since the
    oracle does a literal-text search of the response body)."""
    from html import escape

    return f"<html><body>{escape(_q()[:8])}</body></html>"


@app.route("/c2")
def c2():
    """Reject any input containing shell metacharacters."""
    q = _q()
    if any(ch in q for ch in (";", "&", "|", "`", "$")):
        return jsonify({"error": "shell metachars not allowed"}), 400
    return jsonify({"q": q})


@app.route("/c3")
def c3():
    """Static response — never reflects param."""
    return "<html><body>static</body></html>"


@app.route("/c4")
def c4():
    """Numeric-only allowlist."""
    q = _q()
    if not q.isdigit():
        return jsonify({"error": "numeric only"}), 400
    return jsonify({"value": int(q)})


@app.route("/c5")
def c5():
    """Regex allowlist — alphanumerics + underscore + dash only."""
    q = _q()
    if not re.fullmatch(r"[a-zA-Z0-9_-]{1,64}", q):
        return jsonify({"error": "invalid"}), 400
    return jsonify({"q": q})


@app.route("/c6")
def c6():
    """404 regardless of input — no reflection."""
    return jsonify({"error": "not found"}), 404


@app.route("/c7")
def c7():
    """Returns only the SHA-256 hash of the param."""
    import hashlib

    return jsonify({"hash": hashlib.sha256(_q().encode()).hexdigest()})


@app.route("/c8")
def c8():
    """Strips shell metacharacters AND drops the entire param if the
    cleaned form would contain a marker-shaped substring. Mirrors a
    real-world shell-input filter that knows about reflection FPs."""
    q = _q()
    cleaned = re.sub(r"[;&|`$_]", "", q)
    if "rcemarker" in cleaned.lower() or "echo" in cleaned.lower():
        cleaned = ""
    return f"<body>q={cleaned}</body>"


@app.route("/c9")
def c9():
    """Returns length only, never the param."""
    return jsonify({"length": len(_q())})


@app.route("/c10")
def c10():
    """Cached static page — safe under any payload."""
    return ("ok", 200, {"Cache-Control": "max-age=300", "Content-Type": "text/plain"})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5093, threaded=True)
