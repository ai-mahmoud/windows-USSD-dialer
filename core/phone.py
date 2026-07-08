"""
core/phone.py
─────────────
Pure functions for parsing and normalising Egyptian phone numbers.

Design recipe: function design.
  Purpose  : take raw cell value → PhoneNumber or error string
  Input    : any raw value from an Excel cell (str, int, float, None)
  Output   : PhoneNumber (success) | str describing why it failed
  Side-effects: none
"""

from typing import Union
from core.types import PhoneNumber


# ── Constants ────────────────────────────────────────────────────────────────

_VALID_PREFIXES = ("010", "011", "012", "015")   # Egyptian operators


# ── Public API ───────────────────────────────────────────────────────────────

def parse_phone(raw: object) -> Union[PhoneNumber, str]:
    """
    Parse any raw Excel cell value into a PhoneNumber.

    Returns a PhoneNumber on success.
    Returns a plain str (the reason) on failure — never raises.

    Handles:
      - int / float stored as number in Excel  (e.g. 1012345678 → "01012345678")
      - strings with country code              (+201012345678, 201012345678)
      - strings with spaces / dashes           (010-123 456 78)
      - leading zeros already present          (01012345678)
    """
    if raw is None:
        return "empty cell"

    normalised = _normalise_raw(raw)

    if normalised is None:
        return f"cannot convert {raw!r} to digits"

    if len(normalised) not in (10, 11, 12, 13):
        return f"unexpected length {len(normalised)} for {normalised!r}"

    local = _to_local_format(normalised)

    if local is None:
        return f"unrecognised format: {normalised!r}"

    if not _has_valid_prefix(local):
        return f"unknown operator prefix in {local!r}"

    try:
        return PhoneNumber(local)
    except ValueError as exc:
        return str(exc)


def is_valid_phone(raw: object) -> bool:
    """Convenience predicate — True if parse_phone would succeed."""
    return isinstance(parse_phone(raw), PhoneNumber)


# ── Private helpers ──────────────────────────────────────────────────────────

def _normalise_raw(raw: object) -> Union[str, None]:
    """Strip to digits only. Handles numeric Excel values."""
    if isinstance(raw, float):
        if not raw.is_integer():
            return None
        raw = int(raw)
    if isinstance(raw, int):
        raw = str(raw)
    if not isinstance(raw, str):
        return None
    digits = "".join(ch for ch in raw if ch.isdigit())
    return digits if digits else None


def _to_local_format(digits: str) -> Union[str, None]:
    """
    Convert digit string to 11-digit local format (01xxxxxxxxx).

    +201xxxxxxxxx → 12 digits after removing +, starts with 20
    201xxxxxxxxx  → 12 digits, starts with 20
    01xxxxxxxxx   → 11 digits, starts with 0
    1xxxxxxxxx    → 10 digits (missing leading 0)
    """
    if len(digits) == 13 and digits.startswith("200"):
        # rare: 200 prefix misread — not valid
        return None
    if len(digits) == 12 and digits.startswith("20"):
        return "0" + digits[2:]
    if len(digits) == 11 and digits.startswith("0"):
        return digits
    if len(digits) == 10 and digits.startswith("1"):
        return "0" + digits
    return None


def _has_valid_prefix(local: str) -> bool:
    return any(local.startswith(p) for p in _VALID_PREFIXES)
