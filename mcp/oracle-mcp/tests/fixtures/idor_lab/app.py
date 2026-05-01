"""IDOR vulnerable lab for Phase 2 W9-10 field validation.

20 routes total:
  - /v1 .. /v10  → vulnerable (accessor sees owner's resource)
  - /c1 .. /c10  → clean      (accessor denied / different content)

The oracle issues two GETs per target — one as the owner, one as the
accessor — using ``SessionCredentials`` (headers + cookies). It confirms
IDOR when (owner_status == 200) AND (accessor_status == 200) AND
(jaccard_similarity(bodies) >= 0.3). Clean routes deny the accessor
(401/403/404), redirect to login (302), 500 out, or return content too
dissimilar to the owner's body to clear the Jaccard threshold.

Sessions are bearer-token-based:
  - owner    → Authorization: Bearer owner_token
  - accessor → Authorization: Bearer accessor_token

Run standalone::

    pip install flask
    python app.py            # listens on 0.0.0.0:5092
"""

from __future__ import annotations

from flask import Flask, jsonify, request

app = Flask(__name__)

# Shared resource body — both vulnerable owner and accessor see this on
# vuln routes. Long enough that Jaccard similarity >= 0.3 trivially.
_OWNER_BODY = (
    "name: Alice\n"
    "email: alice@example.com\n"
    "role: admin\n"
    "profile: long-form description of Alice's account profile data\n"
    "membership: gold tier since 2024\n"
    "billing: invoice 0001 paid 2026-01\n"
    "billing: invoice 0002 paid 2026-02\n"
    "billing: invoice 0003 paid 2026-03\n"
    "preferences: timezone US/Pacific\n"
)


def _bearer() -> str:
    auth = request.headers.get("Authorization", "")
    return auth.removeprefix("Bearer ").strip()


@app.route("/healthz")
def healthz() -> str:
    return "ok"


# ---------------------------------------------------------------------------
# Vulnerable routes — accessor receives owner's data despite distinct creds.
# ---------------------------------------------------------------------------


@app.route("/v1/profile")
def v1_profile():
    """Returns owner profile to anyone with any bearer token."""
    if not _bearer():
        return jsonify({"error": "auth required"}), 401
    return _OWNER_BODY, 200, {"Content-Type": "text/plain"}


@app.route("/v2/profile")
def v2_profile():
    """No auth at all — returns owner profile to anyone."""
    return _OWNER_BODY, 200, {"Content-Type": "text/plain"}


@app.route("/v3/profile")
def v3_profile():
    """Token presence check only — both tokens map to owner data."""
    token = _bearer()
    if token not in ("owner_token", "accessor_token"):
        return jsonify({"error": "unauth"}), 401
    return _OWNER_BODY, 200, {"Content-Type": "text/plain"}


@app.route("/v4/profile")
def v4_profile():
    """Cookie-based session — any session cookie value grants access."""
    if not request.cookies.get("session"):
        return jsonify({"error": "auth required"}), 401
    return _OWNER_BODY, 200, {"Content-Type": "text/plain"}


@app.route("/v5/profile")
def v5_profile():
    """JSON owner profile — same shape regardless of caller."""
    if not _bearer():
        return jsonify({"error": "auth"}), 401
    return jsonify({
        "name": "Alice",
        "email": "alice@example.com",
        "role": "admin",
        "membership": "gold tier since 2024",
        "billing": ["invoice 0001 paid 2026-01", "invoice 0002 paid 2026-02"],
        "preferences": {"timezone": "US/Pacific"},
    })


@app.route("/v6/profile")
def v6_profile():
    """User-id in path is ignored — always returns owner profile."""
    if not _bearer():
        return jsonify({"error": "auth"}), 401
    return _OWNER_BODY, 200, {"Content-Type": "text/plain"}


@app.route("/v7/profile")
def v7_profile():
    """API key in query string — both keys grant identical access."""
    key = request.args.get("api_key", "")
    if not key:
        return jsonify({"error": "auth"}), 401
    return _OWNER_BODY, 200, {"Content-Type": "text/plain"}


@app.route("/v8/profile")
def v8_profile():
    """Header-based — X-User-Id is trusted client-side."""
    if not request.headers.get("X-User-Id"):
        return jsonify({"error": "auth"}), 401
    return _OWNER_BODY, 200, {"Content-Type": "text/plain"}


@app.route("/v9/profile")
def v9_profile():
    """Returns owner profile to any caller with a non-empty Auth header."""
    if not request.headers.get("Authorization"):
        return jsonify({"error": "auth"}), 401
    return _OWNER_BODY, 200, {"Content-Type": "text/plain"}


@app.route("/v10/profile")
def v10_profile():
    """Token format-check only — both expected tokens pass the regex."""
    import re

    token = _bearer()
    if not re.fullmatch(r"[a-z_]+", token):
        return jsonify({"error": "auth"}), 401
    return _OWNER_BODY, 200, {"Content-Type": "text/plain"}


# ---------------------------------------------------------------------------
# Clean routes — accessor cannot read owner's data.
# ---------------------------------------------------------------------------


@app.route("/c1/profile")
def c1_profile():
    """401 unless the bearer is exactly owner_token."""
    if _bearer() != "owner_token":
        return jsonify({"error": "unauthorized"}), 401
    return _OWNER_BODY, 200, {"Content-Type": "text/plain"}


@app.route("/c2/profile")
def c2_profile():
    """403 for any non-owner bearer."""
    if _bearer() != "owner_token":
        return jsonify({"error": "forbidden"}), 403
    return _OWNER_BODY, 200, {"Content-Type": "text/plain"}


@app.route("/c3/profile")
def c3_profile():
    """404 for non-owner — hides resource existence."""
    if _bearer() != "owner_token":
        return jsonify({"error": "not found"}), 404
    return _OWNER_BODY, 200, {"Content-Type": "text/plain"}


@app.route("/c4/profile")
def c4_profile():
    """200 for both, but accessor sees a stripped, dissimilar body."""
    if _bearer() == "owner_token":
        return _OWNER_BODY, 200, {"Content-Type": "text/plain"}
    return "redacted", 200, {"Content-Type": "text/plain"}


@app.route("/c5/profile")
def c5_profile():
    """401 with WWW-Authenticate challenge for accessor."""
    if _bearer() != "owner_token":
        return ("", 401, {"WWW-Authenticate": 'Bearer realm="profile"'})
    return _OWNER_BODY, 200, {"Content-Type": "text/plain"}


@app.route("/c6/profile")
def c6_profile():
    """403 + JSON error body for accessor."""
    if _bearer() != "owner_token":
        return jsonify({"error": "forbidden", "code": "RBAC_DENY"}), 403
    return _OWNER_BODY, 200, {"Content-Type": "text/plain"}


@app.route("/c7/profile")
def c7_profile():
    """200 + completely different content for accessor — Jaccard < 0.3."""
    if _bearer() == "owner_token":
        return _OWNER_BODY, 200, {"Content-Type": "text/plain"}
    return "x y z", 200, {"Content-Type": "text/plain"}


@app.route("/c8/profile")
def c8_profile():
    """302 redirect to login for accessor."""
    if _bearer() != "owner_token":
        return ("", 302, {"Location": "/login"})
    return _OWNER_BODY, 200, {"Content-Type": "text/plain"}


@app.route("/c9/profile")
def c9_profile():
    """200 + empty body for accessor — Jaccard with empty set = 0."""
    if _bearer() == "owner_token":
        return _OWNER_BODY, 200, {"Content-Type": "text/plain"}
    return "", 200, {"Content-Type": "text/plain"}


@app.route("/c10/profile")
def c10_profile():
    """500 server error for accessor — oracle treats unexpected status as inconclusive."""
    if _bearer() != "owner_token":
        return jsonify({"error": "server error"}), 500
    return _OWNER_BODY, 200, {"Content-Type": "text/plain"}


@app.route("/login")
def login():
    """Bare login redirect target — not part of the 20 fixture rows."""
    return "login page", 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5092, threaded=True)
