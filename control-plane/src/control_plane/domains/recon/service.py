"""Recon orchestrator — the only thing :file:`scripts/orchestrator.py`
should need to invoke for a recon run.

Step sequence (matches ``.claude/agents/recon.md``):

1. Mark scan_job ``running``.
2. ``subfinder`` for each wildcard apex.
3. Add exact_hosts as-is.
4. Filter all hosts through :class:`ScopeFilter`.
5. ``httpx`` to find live URLs and tech.
6. ``katana`` to discover endpoints inside the scope regex.
7. Filter endpoints, classify into hypothesis-finding rows, persist.
8. Mark scan_job ``recon_complete``.

Every external network/binary call goes through :class:`BinaryRunner`,
so unit tests can swap in a fake without touching subprocesses.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from urllib.parse import parse_qs, urlparse

import structlog

from .persistence import HypothesisFinding, ScanPersistence
from .scope_filter import ScopeFilter
from .tool_runner import BinaryRunner, KatanaEndpoint

log = structlog.get_logger("recon.service")


# Heuristic CWE mapping. Validator-agent refines per-finding; this is just
# the first-pass discriminator used to pick which oracle to run later.
# Keeping this table local to recon keeps domain coupling minimal.
_PARAM_CWE_HINTS: tuple[tuple[tuple[str, ...], str], ...] = (
    (("url", "uri", "redirect", "next", "return", "dest"), "open-redirect-candidate"),
    (("target", "fetch", "callback", "webhook", "image_url"), "ssrf-candidate"),
    (("id", "user_id", "account_id", "doc_id"), "idor-candidate"),
    (("cmd", "exec", "command", "shell"), "rce-candidate"),
    (("template", "render", "view"), "ssti-candidate"),
)


def _classify_parameter(name: str) -> str:
    """Map a query/form parameter name → likely CWE candidate."""
    n = name.lower()
    for keywords, cwe in _PARAM_CWE_HINTS:
        if any(k in n for k in keywords):
            return cwe
    # Default fallthrough: most common bug class is reflected XSS / SQLi;
    # validator runs both oracles when CWE is `xss-candidate` (cheap).
    return "xss-candidate"


@dataclass(frozen=True, slots=True)
class ReconResult:
    """Summary returned by :meth:`ReconService.run`."""

    hosts_found: int
    endpoints_found: int
    findings_inserted: int


class ReconService:
    """Composition root for a single recon run."""

    def __init__(
        self,
        runner: BinaryRunner,
        persistence: ScanPersistence,
        scope_filter: ScopeFilter,
    ) -> None:
        self.runner = runner
        self.persistence = persistence
        self.scope_filter = scope_filter

    async def run(
        self,
        conn,
        job_id: uuid.UUID | str,
        program_handle: str,
        platform: str,
    ) -> ReconResult:
        log.info(
            "recon.start",
            job_id=str(job_id),
            program_handle=program_handle,
            platform=platform,
            wildcards=self.scope_filter.wildcards,
            exact_hosts=self.scope_filter.exact_hosts,
        )
        try:
            await self.persistence.mark_running(conn, job_id)

            hosts = await self._enumerate_hosts()
            if not hosts:
                log.warning("recon.no_hosts")
                await self.persistence.mark_complete(conn, job_id, 0, 0)
                return ReconResult(0, 0, 0)

            probes = await self._fingerprint(hosts)
            live_urls = [p.url for p in probes if 200 <= p.status_code < 400 and p.url]

            endpoints = await self._discover_endpoints(live_urls)
            findings = self._classify_findings(endpoints)

            inserted = await self.persistence.insert_findings(
                conn,
                job_id,
                program_handle,
                platform,
                findings,
            )

            await self.persistence.mark_complete(
                conn, job_id, len(hosts), len(endpoints)
            )
            log.info(
                "recon.complete",
                hosts=len(hosts),
                endpoints=len(endpoints),
                findings=inserted,
            )
            return ReconResult(len(hosts), len(endpoints), inserted)
        except Exception as exc:  # pragma: no cover - propagated after marker
            log.exception("recon.failed", error=str(exc))
            await self.persistence.mark_failed(conn, job_id, str(exc))
            raise

    # ------------------------------------------------------------------
    # Steps
    # ------------------------------------------------------------------

    async def _enumerate_hosts(self) -> list[str]:
        seen: set[str] = set()
        rps = self.scope_filter.default_rps
        for domain in self.scope_filter.domains_for_subfinder():
            try:
                hosts = await self.runner.subfinder(domain, rps)
            except Exception as exc:
                log.warning("recon.subfinder.failed", domain=domain, error=str(exc))
                continue
            for h in hosts:
                if self.scope_filter.allows_host(h):
                    seen.add(h.lower())
        for h in self.scope_filter.exact_hosts:
            if self.scope_filter.allows_host(h):
                seen.add(h.lower())
        return sorted(seen)

    async def _fingerprint(self, hosts: list[str]):
        rps = self.scope_filter.default_rps
        return await self.runner.httpx(hosts, rps)

    async def _discover_endpoints(self, live_urls: list[str]) -> list[KatanaEndpoint]:
        if not live_urls:
            return []
        rps = self.scope_filter.default_rps
        scope_regex = self.scope_filter.katana_scope_regex()
        if not scope_regex:
            log.warning("recon.katana.empty_scope_regex.skip")
            return []
        endpoints = await self.runner.katana(live_urls, rps, scope_regex)
        # Defence-in-depth: katana respects -scope but we re-filter just in case.
        return [e for e in endpoints if self.scope_filter.allows_url(e.url)]

    def _classify_findings(
        self, endpoints: list[KatanaEndpoint]
    ) -> list[HypothesisFinding]:
        findings: list[HypothesisFinding] = []
        seen_keys: set[tuple[str, str]] = set()
        for endpoint in endpoints:
            params = list(endpoint.parameters)
            # Also harvest URL query params — katana's struct already includes
            # them in the URL, but we want one finding per parameter.
            parsed = urlparse(endpoint.url)
            for qparam in parse_qs(parsed.query, keep_blank_values=True):
                if qparam not in params:
                    params.append(qparam)
            for param in params:
                key = (endpoint.url, param)
                if key in seen_keys:
                    continue
                seen_keys.add(key)
                findings.append(
                    HypothesisFinding(
                        url=endpoint.url,
                        parameter=param,
                        cwe=_classify_parameter(param),
                    )
                )
        return findings


__all__ = ["ReconResult", "ReconService"]
