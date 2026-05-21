"""Trusted in-process OAST collector for Phase 1.1d field validation.

Implements the four endpoints the simplified InteractshClient expects:

  GET  /register?token=<random>      → 200 ok
  GET  /poll?token=<random>          → 200 {"data": [Interaction…]}
  GET  /deregister?token=<random>    → 200 ok
  GET  /cb/<token>/<path>            → 200 ok (callback receiver)

The ``/cb/<token>`` route is what the SSRF lab fetches when triggered.
On hit, the collector records an Interaction (timestamp, source IP,
path) in an in-memory store keyed by token. The next ``/poll`` returns
those interactions and clears the queue (so a long-running test doesn't
get duplicates).

Threading: Flask's default WSGI server is single-threaded; for the
field-validation harness that's enough since the oracle polls
sequentially. ``threaded=True`` is enabled to avoid blocking when the
SSRF lab and the oracle interleave.

This is a TEST collector. It performs zero authentication, accepts any
token, and trusts the network it's running on (loopback). Not for prod
deployment under any circumstance.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from datetime import UTC, datetime

from flask import Flask, Response, jsonify, request

app = Flask(__name__)

# Per-token interaction queue. ``deque`` keeps memory bounded if a
# misbehaving test spams callbacks; ``lock`` serialises mutation across
# threaded request handlers.
_INTERACTIONS: dict[str, deque[dict]] = defaultdict(lambda: deque(maxlen=256))
_KNOWN_TOKENS: set[str] = set()
_LOCK = threading.Lock()


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _record(token: str, path: str) -> None:
    if not token:
        return
    entry = {
        "protocol": "http",
        "remote-address": request.remote_addr or "",
        "timestamp": _now_iso(),
        "raw-request": f"GET {request.path}?{request.query_string.decode()} HTTP/1.1",
        "path": path,
        "received_at_monotonic": time.monotonic(),
    }
    with _LOCK:
        _INTERACTIONS[token].append(entry)


@app.route("/healthz")
def healthz() -> Response:
    return Response("ok", mimetype="text/plain")


@app.route("/register")
def register() -> Response:
    token = request.args.get("token", "").strip()
    if not token:
        return Response("missing token", status=400)
    with _LOCK:
        _KNOWN_TOKENS.add(token)
        _INTERACTIONS.setdefault(token, deque(maxlen=256))
    return Response("ok", mimetype="text/plain")


@app.route("/poll")
def poll() -> Response:
    token = request.args.get("token", "").strip()
    if not token:
        return jsonify({"data": []})
    with _LOCK:
        queue = _INTERACTIONS.get(token)
        if not queue:
            return jsonify({"data": []})
        items = list(queue)
        queue.clear()
    return jsonify({"data": items})


@app.route("/deregister")
def deregister() -> Response:
    token = request.args.get("token", "").strip()
    with _LOCK:
        _KNOWN_TOKENS.discard(token)
        _INTERACTIONS.pop(token, None)
    return Response("ok", mimetype="text/plain")


@app.route("/cb/<token>", defaults={"rest": ""})
@app.route("/cb/<token>/<path:rest>")
def cb(token: str, rest: str) -> Response:
    """Callback receiver — what an SSRF target hits when exploited."""
    _record(token, "/" + rest if rest else "")
    return Response("ok", mimetype="text/plain")


# Optional: introspection endpoint for tests that want to peek without
# draining the queue. Kept distinct from ``/poll`` so the oracle's poll
# semantics aren't confused.
@app.route("/_debug/peek")
def peek() -> Response:
    token = request.args.get("token", "").strip()
    with _LOCK:
        items = list(_INTERACTIONS.get(token, ()))
    return jsonify({"token": token, "count": len(items), "items": items})


if __name__ == "__main__":
    # Bind 0.0.0.0 so docker-compose can reach the collector. Port 5097
    # avoids conflict with the XSS lab (5099) and any common dev tool.
    app.run(host="0.0.0.0", port=5097, debug=False, threaded=True)
