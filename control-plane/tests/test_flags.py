# SPDX-License-Identifier: AGPL-3.0-or-later

"""Unit tests for control_plane.core.flags.

Covers: in-memory enabled/disabled, tier-enterprise default-False, fail-closed on
error, UnleashProvider boolean contract (mocked client), TLS rejection, malformed
response fail-closed, untrusted-context safety, community default.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from control_plane.core.flags import client as flags_client
from control_plane.core.flags import configure_flags, is_enabled
from control_plane.core.flags.provider import UnleashProvider
from openfeature.flag_evaluation import Reason


@pytest.fixture(autouse=True)
def _reset_to_inmemory():
    # Arrange: each test starts from the community in-memory default.
    configure_flags()
    yield


# --- in-memory client ---


def test_inmemory_flag_enabled_when_set_true():
    # Arrange
    configure_flags({"some-feature": True})
    # Act
    result = is_enabled("some-feature")
    # Assert
    assert result is True


def test_inmemory_unset_flag_returns_default_false():
    # Act / Assert
    assert is_enabled("does-not-exist") is False


def test_tier_enterprise_defaults_false_community():
    # community in-memory ships tier-enterprise=False (AC-9)
    assert is_enabled("tier-enterprise") is False


# --- fail closed ---


def test_is_enabled_fails_closed_on_client_error(monkeypatch):
    # Arrange: force the OpenFeature client to raise
    broken = MagicMock()
    broken.get_boolean_value.side_effect = RuntimeError("provider down")
    monkeypatch.setattr(flags_client, "get_client", lambda: broken)
    # Act
    result = is_enabled("tier-enterprise", default=False)
    # Assert — returns default, no exception escapes
    assert result is False


def test_caller_context_cannot_flip_gate_on_its_own():
    # AC-9: untrusted context. Community default tier-enterprise=False; a caller
    # passing context tier=enterprise must NOT by itself enable the gate.
    result = is_enabled("tier-enterprise", default=False, context={"tier": "enterprise"})
    assert result is False


# --- UnleashProvider contract (mocked client) ---


def _provider_with_mock(mock_client) -> UnleashProvider:
    p = UnleashProvider("https://unleash.example", "bountystrike", "tok")
    p._client = mock_client  # inject mock, skip real initialize
    return p


def test_unleash_provider_subclasses_abstract():
    from openfeature.provider import AbstractProvider

    assert issubclass(UnleashProvider, AbstractProvider)


def test_unleash_resolve_boolean_true():
    mock = MagicMock()
    mock.is_enabled.return_value = True
    p = _provider_with_mock(mock)
    details = p.resolve_boolean_details("tier-enterprise", False)
    assert details.value is True


def test_unleash_resolve_boolean_fails_closed_on_error():
    mock = MagicMock()
    mock.is_enabled.side_effect = RuntimeError("unleash unreachable")
    p = _provider_with_mock(mock)
    details = p.resolve_boolean_details("tier-enterprise", False)
    assert details.value is False
    assert details.reason == Reason.ERROR


def test_unleash_resolve_boolean_fails_closed_on_malformed():
    # AC-8: a non-bool ("true" string, spoof, etc.) is NOT trusted as enabled
    mock = MagicMock()
    mock.is_enabled.return_value = "true"
    p = _provider_with_mock(mock)
    details = p.resolve_boolean_details("tier-enterprise", False)
    assert details.value is False
    assert details.reason == Reason.ERROR


def test_unleash_rejects_insecure_url():
    # AC-8: http:// without allow_insecure must raise
    with pytest.raises(ValueError):
        UnleashProvider("http://unleash.example", "bountystrike", "tok")


def test_unleash_allows_insecure_url_in_dev():
    p = UnleashProvider("http://localhost:4242", "bountystrike", "tok", allow_insecure=True)
    assert p is not None


def test_unleash_requires_token():
    with pytest.raises(ValueError):
        UnleashProvider("https://unleash.example", "bountystrike", "")
