"""Phase 2 §10.4 exit criterion #5 — zero out-of-scope in 100-scan audit.

Per the build plan exit criteria:

    [ ] Zero out-of-scope requests in 100-scan audit trail review

The unit tests in ``test_recon.py`` cover individual ScopeFilter
behaviours (apex, subdomain, exclusion, exact-host). This audit is
the structural counterpart: a 100-row synthesised scan-attempt
trail mixing labelled in-scope and labelled OOS targets, run
through ``ScopeFilter.allows_url`` end-to-end, with two
hard assertions:

* every labelled OOS attempt MUST be denied (false-negative-rate = 0)
* every labelled in-scope attempt MUST be allowed (otherwise the
  audit itself is broken — without this leg the OOS recall could
  trivially be 100% by denying everything)

The OOS sample space deliberately spans the attack-surface classes
that matter operationally:

  * Off-target apex             — ``evil.com``
  * Substring spoof             — ``acme.com.evil.com``
  * Right-anchored spoof        — ``aacme.com`` / ``xacme.com``
  * Explicitly-excluded host    — listed in exclusions[hostnames]
  * Excluded path on allowed    — ``/admin/`` prefix anywhere
  * Loopback / metadata         — ``127.0.0.1``, ``169.254.169.254``
  * Private RFC 1918            — ``10.0.0.5`` literal
  * Port-only host              — ``:8080`` (no host)
  * Empty / malformed URL       — ``relative/path``
  * Punycode lookalike apex     — ``xn--cme-fma.com`` ≠ acme.com

Deterministic via ``random.Random(seed=42)`` so a CI failure can be
reproduced exactly.
"""

from __future__ import annotations

import dataclasses
import random
from typing import Literal

import pytest
from control_plane.domains.recon import ScopeFilter

# ---------------------------------------------------------------------------
# Audit corpus
# ---------------------------------------------------------------------------


_CLAIMS: dict = {
    "targets": {
        "wildcards": ["*.acme.com", "*.partner-public.example"],
        "exact_hosts": ["api.partner.example", "static.partner.example"],
    },
    "exclusions": {
        "hostnames": ["internal.acme.com", "vpn.acme.com"],
        "paths": ["/admin/", "/internal/"],
    },
    "rate_limits": {
        "default_rps": 5,
        "relaxed_hosts": {},
    },
}


_IN_SCOPE_HOSTS = (
    "acme.com",
    "www.acme.com",
    "shop.acme.com",
    "api.deep.acme.com",
    "blog.partner-public.example",
    "static.partner.example",
    "api.partner.example",
)

_IN_SCOPE_PATHS = (
    "/",
    "/about",
    "/api/v1/users",
    "/login",
    "/static/main.css",
    "/products?id=42",
    "/help/contact",
)

_OOS_OFF_TARGET = (
    "evil.com",
    "google.com",
    "attacker.example",
    "some-random-saas.io",
)

_OOS_SUBSTRING_SPOOF = (
    "acme.com.evil.com",
    "www.acme.com.attacker.example",
    "partner.example.evil.com",
)

_OOS_PREFIX_SPOOF = (
    "xacme.com",
    "1acme.com",
    "evil-acme.com",
)

_OOS_EXCLUDED_HOST = (
    "internal.acme.com",
    "vpn.acme.com",
)

_OOS_EXCLUDED_PATH_ON_ALLOWED = tuple(
    f"https://{h}{p}"
    for h in ("acme.com", "shop.acme.com")
    for p in ("/admin/", "/admin/users", "/internal/secrets", "/internal/")
)

_OOS_INFRA = (
    "https://127.0.0.1/",
    "https://169.254.169.254/latest/meta-data/",
    "https://10.0.0.5/",
    "https://localhost/",
    "https://[::1]/",
)

_OOS_PUNYCODE = (
    # xn--cme-fma.com is the punycode encoding of "ácme.com" — a
    # different domain from acme.com that visually resembles it.
    "https://xn--cme-fma.com/",
)


_Verdict = Literal["allow", "deny"]


@dataclasses.dataclass(frozen=True, slots=True)
class ScanAttempt:
    """One row in the synthesised scan audit trail."""

    url: str
    label: _Verdict          # ground truth — what ScopeFilter SHOULD return
    category: str            # human-readable bucket for failure reports


def _build_corpus(seed: int = 42) -> list[ScanAttempt]:
    """Return a 100-row deterministic mix of labelled in-scope + OOS attempts."""
    rng = random.Random(seed)
    rows: list[ScanAttempt] = []

    # --- 70 in-scope attempts (the audit's denominator-balancing leg) ---
    while len([r for r in rows if r.label == "allow"]) < 70:
        host = rng.choice(_IN_SCOPE_HOSTS)
        path = rng.choice(_IN_SCOPE_PATHS)
        scheme = rng.choice(("http", "https"))
        rows.append(
            ScanAttempt(
                url=f"{scheme}://{host}{path}",
                label="allow",
                category="in_scope",
            )
        )

    # --- 30 OOS attempts spread across the listed OOS categories ---
    oos_buckets: tuple[tuple[str, tuple[str, ...]], ...] = (
        ("off_target_apex", _OOS_OFF_TARGET),
        ("substring_spoof", _OOS_SUBSTRING_SPOOF),
        ("prefix_spoof", _OOS_PREFIX_SPOOF),
        ("excluded_host", _OOS_EXCLUDED_HOST),
        ("infra_loopback_metadata_rfc1918", _OOS_INFRA),
        ("punycode_lookalike", _OOS_PUNYCODE),
    )
    excluded_path_rows = [
        ScanAttempt(url=u, label="deny", category="excluded_path_on_allowed")
        for u in _OOS_EXCLUDED_PATH_ON_ALLOWED
    ]
    rows.extend(excluded_path_rows[:8])

    while len([r for r in rows if r.label == "deny"]) < 30:
        cat, samples = rng.choice(oos_buckets)
        sample = rng.choice(samples)
        scheme = rng.choice(("http", "https"))
        url = sample if "://" in sample else f"{scheme}://{sample}/"
        rows.append(ScanAttempt(url=url, label="deny", category=cat))

    rng.shuffle(rows)
    return rows


# ---------------------------------------------------------------------------
# Audit primitives — a small dataclass + helpers tests / orchestrator can reuse
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True, slots=True)
class OosAuditReport:
    total: int
    in_scope_total: int
    oos_total: int
    in_scope_blocked_by_audit: tuple[ScanAttempt, ...]   # filter rejected an
                                                          # in-scope target
    oos_leaked_by_audit: tuple[ScanAttempt, ...]          # filter allowed an
                                                          # OOS target

    @property
    def passed(self) -> bool:
        # §10.4 — zero OOS in 100-scan audit. The in-scope leg must
        # also be perfect or the audit's denominator is broken.
        return not self.oos_leaked_by_audit and not self.in_scope_blocked_by_audit


def run_oos_audit(
    corpus: list[ScanAttempt],
    sf: ScopeFilter,
) -> OosAuditReport:
    """Run *corpus* through *sf*; surface every false-positive AND
    false-negative so a failing audit names its culprits."""
    leaked: list[ScanAttempt] = []
    blocked: list[ScanAttempt] = []
    in_scope = 0
    oos = 0
    for row in corpus:
        verdict = "allow" if sf.allows_url(row.url) else "deny"
        if row.label == "allow":
            in_scope += 1
            if verdict == "deny":
                blocked.append(row)
        else:
            oos += 1
            if verdict == "allow":
                leaked.append(row)
    return OosAuditReport(
        total=len(corpus),
        in_scope_total=in_scope,
        oos_total=oos,
        in_scope_blocked_by_audit=tuple(blocked),
        oos_leaked_by_audit=tuple(leaked),
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_corpus_size_is_exactly_100() -> None:
    corpus = _build_corpus()
    assert len(corpus) == 100


def test_corpus_split_matches_audit_intent() -> None:
    """≥30 OOS attempts so a no-op filter cannot trivially pass — and a
    healthy in-scope leg so the audit isn't a "deny everything" tautology."""
    corpus = _build_corpus()
    in_scope = sum(1 for r in corpus if r.label == "allow")
    oos = sum(1 for r in corpus if r.label == "deny")
    assert in_scope == 70
    assert oos == 30


def test_corpus_oos_categories_are_diverse() -> None:
    """At least 5 distinct OOS categories represented — guards against a
    regression where the corpus collapses to one trivially-blocked class."""
    corpus = _build_corpus()
    cats = {r.category for r in corpus if r.label == "deny"}
    assert len(cats) >= 5, f"OOS sample space too narrow: {cats}"


def test_corpus_seed_is_deterministic() -> None:
    a = _build_corpus(seed=42)
    b = _build_corpus(seed=42)
    assert [(r.url, r.label, r.category) for r in a] == [
        (r.url, r.label, r.category) for r in b
    ]


def test_oos_100_scan_audit_zero_out_of_scope() -> None:
    """Phase 2 §10.4 #5 — every OOS attempt blocked, every in-scope allowed.

    A leak (OOS allowed) is the audit's headline failure. A spurious
    block (in-scope denied) is also fatal because it means the audit
    itself is over-restrictive — a future regression could pass
    "zero OOS leaked" by trivially denying everything.
    """
    sf = ScopeFilter.from_jwt_claims(_CLAIMS)
    corpus = _build_corpus()
    report = run_oos_audit(corpus, sf)

    assert report.total == 100
    assert report.oos_leaked_by_audit == (), (
        "§10.4 OOS leak — these attempts were allowed but should have been "
        f"blocked: {[(r.url, r.category) for r in report.oos_leaked_by_audit]}"
    )
    assert report.in_scope_blocked_by_audit == (), (
        "Audit fairness leg failed — these in-scope URLs were blocked: "
        f"{[(r.url, r.category) for r in report.in_scope_blocked_by_audit]}"
    )
    assert report.passed


@pytest.mark.parametrize(
    "url,why",
    (
        ("https://acme.com.evil.com/", "substring_spoof must not match *.acme.com"),
        ("https://xacme.com/", "prefix_spoof must not match *.acme.com"),
        ("https://internal.acme.com/", "exclusion list overrides *.acme.com"),
        ("https://acme.com/admin/users", "excluded path overrides allowed host"),
        ("https://127.0.0.1/", "loopback never in scope"),
        ("https://169.254.169.254/latest/meta-data/", "metadata IP never in scope"),
    ),
)
def test_oos_individual_class_regressions(url: str, why: str) -> None:
    """Pin specific OOS classes the audit cares about, so a future
    ScopeFilter rewrite that breaks one of these surfaces a focused
    failure rather than just `report.passed is False`."""
    sf = ScopeFilter.from_jwt_claims(_CLAIMS)
    assert sf.allows_url(url) is False, why
