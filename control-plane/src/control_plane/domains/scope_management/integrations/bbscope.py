# SPDX-License-Identifier: AGPL-3.0-or-later

"""Federation L1 client — ``bbscope`` v2 (authenticated).

bbscope v2 (sw33tLie) replaced the v1 per-platform subcommands
(``bbscope h1 -t ...``) with a two-step model: ``poll`` refreshes a local
DB from every configured platform using your credentials, and ``db`` queries
that local DB. We drive both and parse the JSON output into the shared
:class:`~..integrations.arkadiyt.FederationProgram` shape so the existing
upsert path (``_ingest_federation_program`` -> ``_normalize_federation``)
handles normalization and diffing.

This is the authenticated depth over the arkadiyt baseline: per-program
scopes plus Intigriti *out-of-scope* entries (fetched with ``--oos``), whose
``in_scope=False`` rows prevent out-of-scope submissions downstream.

Credentials are read from the environment (BYOK — never hardcoded), mirroring
``.env.example``:

* ``H1_API_TOKEN`` / ``H1_USERNAME``
* ``BUGCROWD_SESSION_COOKIE`` — the ``_bugcrowd_session`` cookie value (trap #10)
* ``INTIGRITI_PAT``
* ``YESWEHACK_BEARER``

.. note::
   The bbscope binary is installed by plan 01-08; the exact ``poll`` / ``db``
   flag names must be confirmed against ``bbscope --help`` at install time.
   The argv builders (:meth:`BbscopeClient._poll_argv` /
   :meth:`BbscopeClient._db_argv`) are isolated so reconciliation is a one-line
   change, and all JSON parsing is covered by canned-output tests that inject a
   ``runner`` and therefore never touch the real binary.
"""

from __future__ import annotations

import asyncio
import json
import os
from collections.abc import Awaitable, Callable, Sequence
from typing import Any

from pydantic import BaseModel, ConfigDict

from ..value_objects.platform import Platform
from .arkadiyt import FederationProgram

# bbscope authenticates against these four platforms (immunefi is not covered).
BBSCOPE_PLATFORMS: tuple[Platform, ...] = (
    "hackerone",
    "bugcrowd",
    "intigriti",
    "yeswehack",
)

# Per-platform key names so a bare bbscope target string is shaped into the
# dict the matching normalizer in ``_normalize_federation`` expects, plus the
# default asset-type when bbscope does not classify the target.
_PLATFORM_TARGET_KEY: dict[Platform, str] = {
    "hackerone": "asset_identifier",
    "bugcrowd": "target",
    "intigriti": "endpoint",
    "yeswehack": "target",
}
_PLATFORM_TYPE_KEY: dict[Platform, tuple[str, str]] = {
    "hackerone": ("asset_type", "URL"),
    "bugcrowd": ("category", "website"),
    "intigriti": ("type", "url"),
    "yeswehack": ("type", "web-application"),
}

# A subprocess runner: argv -> stdout text. Injectable so tests bypass the binary.
Runner = Callable[[Sequence[str]], Awaitable[str]]


class BbscopeError(RuntimeError):
    """Raised when a bbscope subprocess exits non-zero."""


async def _default_runner(argv: Sequence[str], *, env: dict[str, str]) -> str:
    """Run ``argv`` via ``asyncio.create_subprocess_exec`` (never blocking)."""
    proc = await asyncio.create_subprocess_exec(
        *argv,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        raise BbscopeError(
            f"{' '.join(argv)} exited {proc.returncode}: {stderr.decode('utf-8', 'replace')[:500]}"
        )
    return stdout.decode("utf-8", "replace")


class BbscopeScopeRow(BaseModel):
    """One scope entry emitted by ``bbscope db -o json``.

    The exact field names depend on the installed binary; extra keys are
    ignored and only ``platform``/``handle``/``target`` are required.
    """

    model_config = ConfigDict(extra="ignore")

    platform: Platform
    handle: str
    name: str | None = None
    url: str | None = None
    target: str
    category: str | None = None
    in_scope: bool = True


class BbscopeClient:
    """Async wrapper over the bbscope v2 CLI (``poll`` + ``db``)."""

    def __init__(
        self,
        *,
        binary: str = "bbscope",
        env: dict[str, str] | None = None,
        runner: Runner | None = None,
    ) -> None:
        self._binary = binary
        self._env = dict(env if env is not None else os.environ)
        if runner is None:
            runner = lambda argv: _default_runner(argv, env=self._env)  # noqa: E731
        self._runner = runner

    # ------------------------------------------------------------------
    # argv builders — confirm flag names against `bbscope --help` (plan 01-08)
    # ------------------------------------------------------------------

    def _poll_argv(self) -> list[str]:
        """``poll`` refreshes the local bbscope DB from configured platforms."""
        return [self._binary, "poll"]

    def _db_argv(self, platform: Platform, *, oos: bool = False) -> list[str]:
        """``db`` queries the local DB for one platform; ``--oos`` = exclusions."""
        argv = [self._binary, "db", "-p", platform, "-o", "json"]
        if oos:
            argv.append("--oos")
        return argv

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def poll(self) -> None:
        """Refresh the local bbscope DB (authenticated fetch from platforms)."""
        await self._runner(self._poll_argv())

    async def fetch_platform(
        self, platform: Platform, *, oos: bool = False
    ) -> list[BbscopeScopeRow]:
        """Query one platform's scopes from the local DB."""
        raw = await self._runner(self._db_argv(platform, oos=oos))
        return _parse_db_output(platform, raw, oos=oos)

    async def fetch_all(self, *, poll: bool = True) -> dict[Platform, list[FederationProgram]]:
        """Poll, then read every platform; group into FederationProgram lists.

        For Intigriti we additionally query ``--oos`` and merge the exclusion
        rows (``in_scope=False``) — trap: OOS entries gate out-of-scope
        submissions, so they must be persisted, not dropped.
        """
        if poll:
            await self.poll()

        out: dict[Platform, list[FederationProgram]] = {}
        for platform in BBSCOPE_PLATFORMS:
            rows = await self.fetch_platform(platform)
            if platform == "intigriti":
                rows = rows + await self.fetch_platform(platform, oos=True)
            out[platform] = _rows_to_programs(platform, rows)
        return out


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


def _parse_db_output(platform: Platform, raw: str, *, oos: bool) -> list[BbscopeScopeRow]:
    """Parse ``bbscope db`` output (JSON array, ``{scopes:[...]}``, or JSON-lines)."""
    raw = raw.strip()
    if not raw:
        return []

    records: list[Any]
    try:
        data = json.loads(raw)
        if isinstance(data, list):
            records = data
        elif isinstance(data, dict):
            records = data.get("scopes") or data.get("results") or data.get("data") or []
        else:
            records = []
    except json.JSONDecodeError:
        # Fall back to JSON-lines (one record per line).
        records = []
        for line in raw.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    rows: list[BbscopeScopeRow] = []
    for rec in records:
        if not isinstance(rec, dict):
            continue
        rec.setdefault("platform", platform)
        if oos:
            rec["in_scope"] = False
        try:
            rows.append(BbscopeScopeRow.model_validate(rec))
        except (ValueError, TypeError):
            continue
    return rows


def _rows_to_programs(platform: Platform, rows: list[BbscopeScopeRow]) -> list[FederationProgram]:
    """Group scope rows by program handle into FederationProgram objects.

    Each target is shaped into the dict the platform's normalizer expects so
    the shared ``_normalize_federation`` path produces CanonicalScope rows.
    """
    target_key = _PLATFORM_TARGET_KEY[platform]
    type_key, default_type = _PLATFORM_TYPE_KEY[platform]

    by_handle: dict[str, FederationProgram] = {}
    for r in rows:
        if not r.handle or not r.target:
            continue
        fp = by_handle.get(r.handle)
        if fp is None:
            fp = FederationProgram(
                platform=platform,
                handle=r.handle,
                name=r.name or r.handle,
                url=r.url,
                offers_bounties=None,
                raw={"source": "bbscope"},
            )
            by_handle[r.handle] = fp
        target_dict: dict[str, Any] = {
            target_key: r.target,
            type_key: r.category or default_type,
        }
        if r.in_scope:
            fp.targets_in_scope.append(target_dict)
        else:
            fp.targets_out_of_scope.append(target_dict)
    return list(by_handle.values())


__all__ = [
    "BBSCOPE_PLATFORMS",
    "BbscopeClient",
    "BbscopeError",
    "BbscopeScopeRow",
    "FederationProgram",
]
