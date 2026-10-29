"""Strict, side-effect-free EZVIZ device video encryption state parsing."""
from __future__ import annotations


def parse_encryption_state(info: dict) -> bool | None:
    """Return True (encrypted), False (clear), or None (unknown).

    Never interpret missing or malformed cloud fields as unencrypted.
    """
    value = info.get("isEncrypt") if isinstance(info, dict) else None
    if value in (0, "0") and not isinstance(value, bool):
        return False
    if value in (1, "1") and not isinstance(value, bool):
        return True
    return None
