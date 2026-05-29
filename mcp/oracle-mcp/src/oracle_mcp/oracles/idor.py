# SPDX-License-Identifier: AGPL-3.0-or-later

"""IDOR oracle via cross-account resource access matrix.

Verifies Insecure Direct Object Reference by confirming that account B
(``accessor_session``) can successfully access a resource owned by account A
(``owner_session``).  IDOR is confirmed when:

1. The owner's request succeeds with the expected status.
2. The accessor's request also returns 200.
3. The response bodies share substantial content (Jaccard ≥ 0.3 on word sets).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx
import structlog

from oracle_mcp.result import OracleResult
from oracle_mcp.security import reject_destructive_payload

log = structlog.get_logger("oracle_mcp.oracles")


@dataclass(frozen=True)
class SessionCredentials:
    """HTTP credentials for one account in the IDOR cross-account test."""

    headers: dict[str, str]   # e.g. {"Authorization": "Bearer token_b"}
    cookies: dict[str, str]   # e.g. {"session": "sess_b"}


def _jaccard_similarity(text_a: str, text_b: str) -> float:
    """Return Jaccard similarity between word sets of *text_a* and *text_b*.

    Returns 0.0 if either set is empty (no meaningful overlap can be measured).
    """
    words_a = set(text_a.split())
    words_b = set(text_b.split())
    union = words_a | words_b
    if not union:
        return 0.0
    return len(words_a & words_b) / len(union)


async def oracle_idor(
    resource_url: str,
    owner_session: SessionCredentials,
    accessor_session: SessionCredentials,
    expected_owner_status: int = 200,
    timeout_seconds: float = 10.0,
) -> OracleResult:
    """Verify IDOR by comparing access between two distinct account sessions.

    Args:
        resource_url: URL of account A's resource (e.g. ``/api/users/42/profile``).
        owner_session: Account A's credentials — the legitimate owner; expected
            to succeed.
        accessor_session: Account B's credentials — should be denied in a
            correctly authorised system.
        expected_owner_status: HTTP status that the owner's request must return
            for the test to proceed (default 200).
        timeout_seconds: Per-request HTTP timeout in seconds.

    Returns:
        :class:`~oracle_mcp.result.OracleResult` with one of the following verdicts:

        - ``validated`` — IDOR confirmed; accessor received owner's resource.
        - ``unreproducible`` — accessor was correctly denied (401 / 403 / 404).
        - ``inconclusive`` — owner request failed, or accessor returned 200 but
          body similarity was too low to be conclusive.
    """
    reject_destructive_payload(resource_url)

    log.info(
        "idor.oracle.start",
        resource_url=resource_url,
        expected_owner_status=expected_owner_status,
    )

    async with httpx.AsyncClient(timeout=timeout_seconds) as client:
        owner_response = await client.get(
            resource_url,
            headers=owner_session.headers,
            cookies=owner_session.cookies,
        )
        owner_status = owner_response.status_code
        owner_body = owner_response.text

        log.debug("idor.owner_response", status=owner_status)

        if owner_status != expected_owner_status:
            reason = (
                f"owner session did not produce expected status "
                f"{expected_owner_status}, got {owner_status}"
            )
            log.info("idor.oracle.done", verdict="inconclusive", reason=reason)
            return OracleResult(
                verdict="inconclusive",
                oracle_method="idor_cross_account",
                evidence={
                    "resource_url": resource_url,
                    "owner_status": owner_status,
                    "expected_owner_status": expected_owner_status,
                },
                reason=reason,
            )

        accessor_response = await client.get(
            resource_url,
            headers=accessor_session.headers,
            cookies=accessor_session.cookies,
        )
        accessor_status = accessor_response.status_code
        accessor_body = accessor_response.text

        log.debug("idor.accessor_response", status=accessor_status)

    evidence: dict[str, Any] = {
        "resource_url": resource_url,
        "owner_status": owner_status,
        "accessor_status": accessor_status,
    }

    if accessor_status == 200:
        similarity = _jaccard_similarity(owner_body, accessor_body)
        evidence["jaccard_similarity"] = similarity

        log.info(
            "idor.oracle.similarity",
            accessor_status=accessor_status,
            jaccard_similarity=similarity,
        )

        if similarity >= 0.3:
            log.info("idor.oracle.done", verdict="validated")
            return OracleResult(
                verdict="validated",
                oracle_method="idor_cross_account",
                evidence=evidence,
            )

        # 200 response but bodies too dissimilar to confirm IDOR.
        reason = (
            f"accessor returned 200 but body similarity {similarity:.3f} < 0.3"
        )
        log.info("idor.oracle.done", verdict="inconclusive", reason=reason)
        return OracleResult(
            verdict="inconclusive",
            oracle_method="idor_cross_account",
            evidence=evidence,
            reason=reason,
        )

    if accessor_status in (401, 403, 404):
        reason = "accessor correctly denied"
        log.info(
            "idor.oracle.done",
            verdict="unreproducible",
            accessor_status=accessor_status,
        )
        return OracleResult(
            verdict="unreproducible",
            oracle_method="idor_cross_account",
            evidence=evidence,
            reason=reason,
        )

    # Any other status (e.g. 500, 302 without resolution, etc.).
    reason = f"accessor returned unexpected status {accessor_status}"
    log.info("idor.oracle.done", verdict="inconclusive", reason=reason)
    return OracleResult(
        verdict="inconclusive",
        oracle_method="idor_cross_account",
        evidence=evidence,
        reason=reason,
    )
