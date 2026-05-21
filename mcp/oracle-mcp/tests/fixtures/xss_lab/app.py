"""XSS vulnerable lab for Phase 1.1c field validation.

40 routes total:
  - /v1 .. /v20  → vulnerable (raw HTML reflection of `q`)
  - /c1 .. /c20  → clean    (auto-escape OR no reflection OR CSP)

The lab is purpose-built for the oracle's specific payload
``<img src=x onerror="window.__bs5xss=1">``. A "vulnerable" route
renders this payload as a real ``<img>`` element in body context so
Chromium parses it and the onerror handler fires. A "clean" route
either escapes the payload to text, never reflects it, or sends a
strict Content-Security-Policy header that blocks inline event
handlers.

The lab intentionally exposes 20 reflection contexts (different paths,
positions in the document, and content types) rather than re-using one
template 20 times. The oracle's robustness across contexts is what the
TPR measurement is designed to validate.

Run standalone for development::

    pip install flask
    python app.py            # listens on 0.0.0.0:5099

Or via docker-compose::

    docker compose -f tests/fixtures/docker-compose.yml up xss-lab
"""

from __future__ import annotations

from flask import Flask, Response, make_response, request

app = Flask(__name__)


def _q() -> str:
    """Read the ``q`` query parameter (no decoding tricks)."""
    return request.args.get("q", "")


# ---------------------------------------------------------------------------
# Vulnerable routes — each renders the user-supplied value as raw HTML.
# Differences across routes are positional / structural so the oracle's
# robustness across DOM contexts is what's being measured.
# ---------------------------------------------------------------------------


@app.route("/v1")
def v1() -> str:
    """Naive reflection in body."""
    return f"<html><body>{_q()}</body></html>"


@app.route("/v2")
def v2() -> str:
    """Reflection inside a div with sibling text."""
    return (
        f"<html><body><h1>Welcome</h1><div>You searched: {_q()}</div>"
        f"</body></html>"
    )


@app.route("/v3")
def v3() -> str:
    """Reflection before any structural tags (still in body context)."""
    return f"{_q()}<html><body><p>page</p></body></html>"


@app.route("/v4")
def v4() -> str:
    """Reflection after the title, before body."""
    return (
        f"<html><head><title>Search</title></head><body>{_q()}<p>x</p>"
        f"</body></html>"
    )


@app.route("/v5")
def v5() -> str:
    """Reflection inside an h1 element."""
    return f"<html><body><h1>{_q()}</h1></body></html>"


@app.route("/v6")
def v6() -> str:
    """Reflection inside a paragraph that wraps a list."""
    return (
        f"<html><body><p>{_q()}</p><ul><li>x</li></ul></body></html>"
    )


@app.route("/v7")
def v7() -> str:
    """Reflection inside a section after a nav."""
    return (
        f"<html><body><nav>menu</nav><section>{_q()}</section></body></html>"
    )


@app.route("/v8")
def v8() -> str:
    """Reflection inside a footer."""
    return (
        f"<html><body><main>main</main><footer>{_q()}</footer></body></html>"
    )


@app.route("/v9")
def v9() -> str:
    """Reflection after an aside."""
    return (
        f"<html><body><aside>x</aside>{_q()}<p>y</p></body></html>"
    )


@app.route("/v10")
def v10() -> str:
    """Reflection between two sibling divs."""
    return (
        f"<html><body><div>a</div>{_q()}<div>b</div></body></html>"
    )


@app.route("/v11")
def v11() -> str:
    """Document.write reflection — JS injects the user value into the DOM."""
    q = _q().replace("\\", "\\\\").replace("'", "\\'")
    return f"""<html><body><script>document.write('{q}');</script></body></html>"""


@app.route("/v12")
def v12() -> str:
    """innerHTML reflection of URL search param."""
    q = _q().replace("\\", "\\\\").replace("'", "\\'")
    return f"""<html><body><div id=t></div><script>
document.getElementById('t').innerHTML='{q}';
</script></body></html>"""


@app.route("/v13")
def v13() -> str:
    """innerHTML via window.location.search parse."""
    return """<html><body><div id=t></div><script>
const p=new URLSearchParams(window.location.search).get('q')||'';
document.getElementById('t').innerHTML=p;
</script></body></html>"""


@app.route("/v14")
def v14() -> str:
    """document.write of the location query string."""
    return """<html><body><script>
document.write(new URLSearchParams(window.location.search).get('q')||'');
</script></body></html>"""


@app.route("/v15")
def v15() -> str:
    """Reflection wrapped in a template tag clone."""
    q = _q()
    return (
        f"<html><body><template id=tpl>{q}</template>"
        f"<div id=out></div><script>"
        f"document.getElementById('out').appendChild("
        f"document.getElementById('tpl').content.cloneNode(true));"
        f"</script></body></html>"
    )


@app.route("/v16")
def v16() -> str:
    """Reflection after stripping the literal string '<script' (img survives)."""
    q = _q().replace("<script", "")
    return f"<html><body>{q}</body></html>"


@app.route("/v17")
def v17() -> str:
    """Reflection after lower-casing (payload is already lower)."""
    q = _q().lower()
    return f"<html><body>{q}</body></html>"


@app.route("/v18")
def v18() -> str:
    """Reflection after URL-decoding once via Flask + once manually."""
    import urllib.parse as up
    q = up.unquote(_q())
    return f"<html><body>{q}</body></html>"


@app.route("/v19")
def v19() -> str:
    """Reflection inside a custom data tag (still parsed as HTML)."""
    return f"<html><body><x-widget>{_q()}</x-widget></body></html>"


@app.route("/v20")
def v20() -> str:
    """Reflection at the end of the document, after </body></html>."""
    return f"<html><body><p>page</p></body></html>{_q()}"


# ---------------------------------------------------------------------------
# Clean routes — same payload must NOT trigger.
# ---------------------------------------------------------------------------


def _escape(s: str) -> str:
    """Minimal HTML escape — sufficient for the oracle's payload."""
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )


@app.route("/c1")
def c1() -> str:
    """Properly escaped reflection in body."""
    return f"<html><body>{_escape(_q())}</body></html>"


@app.route("/c2")
def c2() -> str:
    """Escaped reflection inside a div."""
    return (
        f"<html><body><h1>Welcome</h1><div>You searched: "
        f"{_escape(_q())}</div></body></html>"
    )


@app.route("/c3")
def c3() -> str:
    """Static page that ignores ``q`` entirely."""
    return "<html><body><p>Static — no reflection.</p></body></html>"


@app.route("/c4")
def c4() -> str:
    """Echoes a generic greeting; param is read but never rendered."""
    _ = _q()
    return "<html><body><p>Hello, friend!</p></body></html>"


@app.route("/c5")
def c5() -> str:
    """Reflection escaped inside an h1."""
    return f"<html><body><h1>{_escape(_q())}</h1></body></html>"


@app.route("/c6")
def c6() -> str:
    """JSON response — Chromium does not render HTML in JSON content type."""
    payload = '{{"echo": "{}"}}'.format(_q().replace('"', '\\"'))
    return Response(payload, mimetype="application/json")


@app.route("/c7")
def c7() -> str:
    """Plain text content type."""
    return Response(_q(), mimetype="text/plain")


@app.route("/c8")
def c8() -> Response:
    """CSP blocks inline event handlers — img.onerror won't fire."""
    body = f"<html><body>{_q()}</body></html>"
    resp = make_response(body)
    resp.headers["Content-Security-Policy"] = (
        "default-src 'none'; img-src *; script-src 'self'; "
        "style-src 'self'; base-uri 'none'"
    )
    return resp


@app.route("/c9")
def c9() -> Response:
    """CSP blocks all script — defence in depth even if reflection is raw."""
    body = f"<html><body>{_q()}</body></html>"
    resp = make_response(body)
    resp.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'none'"
    )
    return resp


@app.route("/c10")
def c10() -> str:
    """Echo length only, never the value itself."""
    return f"<html><body><p>You sent {len(_q())} chars.</p></body></html>"


@app.route("/c11")
def c11() -> str:
    """Echo a fixed list of safe categories regardless of param."""
    _ = _q()
    return "<html><body><ul><li>news</li><li>sport</li></ul></body></html>"


@app.route("/c12")
def c12() -> str:
    """Reflection escaped inside a footer."""
    return (
        f"<html><body><main>main</main><footer>{_escape(_q())}</footer>"
        f"</body></html>"
    )


@app.route("/c13")
def c13() -> str:
    """Reflection escaped between two sibling divs."""
    return (
        f"<html><body><div>a</div>{_escape(_q())}<div>b</div></body></html>"
    )


@app.route("/c14")
def c14() -> str:
    """Echo only digits — strips everything else."""
    digits = "".join(ch for ch in _q() if ch.isdigit())
    return f"<html><body>{digits}</body></html>"


@app.route("/c15")
def c15() -> str:
    """Echo only ASCII letters."""
    letters = "".join(ch for ch in _q() if ch.isalpha())
    return f"<html><body>{letters}</body></html>"


@app.route("/c16")
def c16() -> str:
    """Truncates to first 5 chars after escape."""
    return f"<html><body>{_escape(_q()[:5])}</body></html>"


@app.route("/c17")
def c17() -> str:
    """JS reads the param via textContent (not innerHTML)."""
    return """<html><body><div id=t></div><script>
const p=new URLSearchParams(window.location.search).get('q')||'';
document.getElementById('t').textContent=p;
</script></body></html>"""


@app.route("/c18")
def c18() -> str:
    """Empty body — nothing rendered."""
    _ = _q()
    return ""


@app.route("/c19")
def c19() -> str:
    """Reflection inside a noscript element — not rendered when JS is on."""
    return f"<html><body><noscript>{_q()}</noscript></body></html>"


@app.route("/c20")
def c20() -> str:
    """Strict allow-list filter (drops <, >, ", ', =, /)."""
    bad = set("<>\"'=/")
    safe = "".join(ch for ch in _q() if ch not in bad)
    return f"<html><body>{safe}</body></html>"


# ---------------------------------------------------------------------------
# Health endpoint — used by the test harness to wait for the lab to boot.
# ---------------------------------------------------------------------------


@app.route("/healthz")
def healthz() -> Response:
    return Response("ok", mimetype="text/plain")


if __name__ == "__main__":
    # Bind 0.0.0.0 so the lab is reachable from a docker-compose service or
    # a host-process pytest run. Port 5099 chosen to avoid common dev
    # conflicts (5000 = AirPlay on macOS, 5001 = many tools).
    app.run(host="0.0.0.0", port=5099, debug=False)
