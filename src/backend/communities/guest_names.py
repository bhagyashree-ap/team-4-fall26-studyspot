"""Stable display aliases for local demos. Session keys remain private."""

import hashlib

from django.conf import settings

_FIRST = [
    "Maya",
    "Leo",
    "Iris",
    "Alex",
    "Nora",
    "Theo",
    "Clara",
    "Lucas",
    "Naomi",
    "Evan",
    "Sofia",
    "Amir",
    "Leila",
    "Miles",
    "Owen",
    "Ada",
]
_LAST = [
    "Chen",
    "Brooks",
    "Park",
    "Miller",
    "Torres",
    "Bennett",
    "Patel",
    "Rivera",
    "Wilson",
    "Reed",
    "Morgan",
    "Hayes",
    "Shah",
    "Kim",
    "Lewis",
    "Scott",
]


def guest_name(identity: str) -> str:
    digest = hashlib.sha256(identity.encode()).digest()
    if settings.DEBUG:
        return f"{_FIRST[digest[0] % len(_FIRST)]} {_LAST[digest[1] % len(_LAST)]}"
    return f"Guest {digest.hex()[:6]}"
