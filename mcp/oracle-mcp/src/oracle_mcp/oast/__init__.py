"""OAST (Out-of-band Application Security Testing) helpers.

Single concrete client today: a simplified Interactsh stub
(see ``interactsh.py``).  Full RSA-AES Interactsh protocol can be
swapped in later without changing oracle call sites — they only use
``register_token``, ``poll_interactions``, and ``deregister``.
"""

from .interactsh import (
    Interaction,
    InteractshClient,
    InteractshToken,
    get_default_client,
)

__all__ = [
    "Interaction",
    "InteractshClient",
    "InteractshToken",
    "get_default_client",
]
