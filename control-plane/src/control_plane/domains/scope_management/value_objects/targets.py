# SPDX-License-Identifier: AGPL-3.0-or-later

"""Scope-target value objects used by the JWT issuer.

Replaces the dataclasses originally living in ``control_plane.scope_jwt``; the
public field names + defaults match exactly so existing call sites continue to
work. Switching to :class:`~control_plane.core.shared.ValueObject` (a frozen
Pydantic model) buys us validation + structural equality + hashing for free.
"""

from __future__ import annotations

from pydantic import Field

from control_plane.core.shared import ValueObject


class ScopeTargets(ValueObject):
    """In-scope assets carried inside a scope JWT.

    Mirrors the buckets the policy engine recognises: domain wildcards, exact
    hostnames, IP/CIDR blocks, Android packages, iOS bundle IDs.
    """

    wildcards: tuple[str, ...] = Field(default_factory=tuple)
    exact_hosts: tuple[str, ...] = Field(default_factory=tuple)
    ips: tuple[str, ...] = Field(default_factory=tuple)
    android_packages: tuple[str, ...] = Field(default_factory=tuple)
    ios_bundles: tuple[str, ...] = Field(default_factory=tuple)


class ScopeExclusions(ValueObject):
    """Hostnames / paths the operator must not touch, plus free-form notes."""

    hostnames: tuple[str, ...] = Field(default_factory=tuple)
    paths: tuple[str, ...] = Field(default_factory=tuple)
    notes: str = ""


class RateLimits(ValueObject):
    """Per-host RPS budgets distributed alongside the scope JWT."""

    default_rps: int = 5
    relaxed_hosts: dict[str, int] = Field(default_factory=dict)


__all__ = ["RateLimits", "ScopeExclusions", "ScopeTargets"]
