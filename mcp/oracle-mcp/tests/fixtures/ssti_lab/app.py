"""SSTI vulnerable lab for Phase 2 W9-10 field validation.

20 routes total:
  - /v1 .. /v10  → vulnerable (evaluate template-literal math syntax in body)
  - /c1 .. /c10  → clean      (HTML-escape, reject curlies, static, etc.)

The oracle injects ``{{a*b}}`` / ``${a*b}`` / ``{a*b}`` / ``<%= a*b %>``
/ ``@{a*b}`` etc. across 7 dialects with random ``a`` and ``b`` per
invocation, then checks whether the numeric product appears in the body.
A "vulnerable" route detects the dialect-specific syntax with a regex
and substitutes the computed product before rendering — simulating a
template engine that evaluates user input. A "clean" route either
HTML-escapes the payload, rejects curly braces, or returns content that
never reflects the parameter at all.

Run standalone::

    pip install flask
    python app.py            # listens on 0.0.0.0:5094
"""

from __future__ import annotations

import re

from flask import Flask, jsonify, request

app = Flask(__name__)

# Dialect-aware regex patterns. Each captures the two integer operands so
# the lab can compute the product the oracle expects to see in the body.
_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("jinja2_twig", re.compile(r"\{\{\s*(\d+)\s*\*\s*(\d+)\s*\}\}")),
    ("velocity_set", re.compile(r"#set\s*\(\s*\$r\s*=\s*(\d+)\s*\*\s*(\d+)\s*\)\s*\$\{r\}")),
    ("freemarker_velocity", re.compile(r"\$\{\s*(\d+)\s*\*\s*(\d+)\s*\}")),
    ("smarty", re.compile(r"(?<!\{)\{\s*(\d+)\s*\*\s*(\d+)\s*\}(?!\})")),
    ("erb", re.compile(r"<%=\s*(\d+)\s*\*\s*(\d+)\s*%>")),
    ("mvel", re.compile(r"@\{\s*(\d+)\s*\*\s*(\d+)\s*\}")),
]


def _q() -> str:
    return request.args.get("q", "")


def _eval_dialect(value: str, dialect_name: str | None = None) -> str | None:
    """Return the product as a string when *value* matches a template
    expression. Optionally restrict to a single named dialect.
    """
    for name, pat in _PATTERNS:
        if dialect_name is not None and name != dialect_name:
            continue
        m = pat.search(value)
        if m:
            return str(int(m.group(1)) * int(m.group(2)))
    return None


@app.route("/healthz")
def healthz() -> str:
    return "ok"


# ---------------------------------------------------------------------------
# Vulnerable routes — each "evaluates" one or more dialects.
# ---------------------------------------------------------------------------


@app.route("/v1")
def v1() -> str:
    """Jinja2 / Twig — {{a*b}} ."""
    q = _q()
    out = _eval_dialect(q, "jinja2_twig") or q
    return f"<html><body>result: {out}</body></html>"


@app.route("/v2")
def v2() -> str:
    """Jinja2 / Twig with extra body content — same dialect."""
    q = _q()
    out = _eval_dialect(q, "jinja2_twig") or q
    return f"<html><body><h1>page</h1><p>computed: {out}</p></body></html>"


@app.route("/v3")
def v3() -> str:
    """Freemarker / Velocity simple — ${a*b} ."""
    q = _q()
    out = _eval_dialect(q, "freemarker_velocity") or q
    return f"<html><body>val={out}</body></html>"


@app.route("/v4")
def v4() -> str:
    """Velocity #set form — #set($r=a*b)${r}."""
    q = _q()
    out = _eval_dialect(q, "velocity_set") or q
    return f"<html><body>res={out}</body></html>"


@app.route("/v5")
def v5() -> str:
    """Smarty — {a*b}."""
    q = _q()
    out = _eval_dialect(q, "smarty") or q
    return f"<html><body>smarty: {out}</body></html>"


@app.route("/v6")
def v6() -> str:
    """ERB (Ruby) — <%= a*b %>."""
    q = _q()
    out = _eval_dialect(q, "erb") or q
    return f"<html><body>erb: {out}</body></html>"


@app.route("/v7")
def v7() -> str:
    """MVEL — @{a*b}."""
    q = _q()
    out = _eval_dialect(q, "mvel") or q
    return f"<html><body>mvel: {out}</body></html>"


@app.route("/v8")
def v8():
    """Multi-dialect JSON endpoint — tries every pattern."""
    q = _q()
    out = _eval_dialect(q) or q
    return jsonify({"result": out})


@app.route("/v9")
def v9() -> str:
    """Jinja2 inside an attribute — still evaluated by template engines."""
    q = _q()
    out = _eval_dialect(q, "jinja2_twig") or q
    return f'<html><body><div data-x="{out}">hi</div></body></html>'


@app.route("/v10")
def v10() -> str:
    """Mixed dialects in plain text response."""
    q = _q()
    out = _eval_dialect(q) or q
    return f"value: {out}", 200, {"Content-Type": "text/plain"}


# ---------------------------------------------------------------------------
# Clean routes — none execute the template syntax.
# ---------------------------------------------------------------------------


@app.route("/c1")
def c1() -> str:
    """HTML-escape — payload echoes back as text, no eval."""
    from html import escape

    return f"<html><body>{escape(_q())}</body></html>"


@app.route("/c2")
def c2():
    """Reject any input containing curly braces."""
    q = _q()
    if "{" in q or "}" in q:
        return jsonify({"error": "curlies not allowed"}), 400
    return jsonify({"q": q})


@app.route("/c3")
def c3() -> str:
    """Static response — never reflects the param."""
    return "<html><body>static</body></html>"


@app.route("/c4")
def c4():
    """Numeric-only allowlist — payloads with operators rejected."""
    q = _q()
    if not q.isdigit():
        return jsonify({"error": "numeric only"}), 400
    return jsonify({"value": int(q)})


@app.route("/c5")
def c5():
    """Regex allowlist — rejects template metacharacters."""
    q = _q()
    if not re.fullmatch(r"[a-zA-Z0-9 _-]{1,64}", q):
        return jsonify({"error": "invalid"}), 400
    return jsonify({"q": q})


@app.route("/c6")
def c6():
    """Strips template-syntax characters before reflection."""
    q = _q()
    cleaned = re.sub(r"[{}$#@<>%]", "", q)
    return f"<html><body>q={cleaned}</body></html>"


@app.route("/c7")
def c7():
    """Returns 404 regardless of input — no reflection."""
    return jsonify({"error": "not found"}), 404


@app.route("/c8")
def c8():
    """Returns the length of the param — never the param itself."""
    return jsonify({"length": len(_q())})


@app.route("/c9")
def c9():
    """Cached static page — safe under any payload."""
    return ("ok", 200, {"Cache-Control": "max-age=300", "Content-Type": "text/plain"})


@app.route("/c10")
def c10():
    """Echoes only the SHA-256 hash of the input."""
    import hashlib

    return jsonify({"hash": hashlib.sha256(_q().encode()).hexdigest()})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5094, threaded=True)
