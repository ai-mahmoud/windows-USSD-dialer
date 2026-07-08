"""
core/reply_parser.py
────────────────────
Pure functions for interpreting raw modem text after an ATD command.

Design recipe:
  Purpose  : raw modem string + failure keywords → ModemResponse
  Input    : str (everything the modem sent), list[str] keywords
  Output   : ModemResponse (frozen, no side-effects)
  Side-effects: none

The modem can send multiple lines. We look for:
  +CUSD: <n>,"<message>",<dcs>   ← operator USSD reply
  OK                              ← command accepted
  NO CARRIER                      ← call not connected
  ERROR                           ← modem-level error
"""

import re
from core.types import ModemResponse


# ── Patterns ─────────────────────────────────────────────────────────────────

_CUSD_PATTERN = re.compile(r'\+CUSD:\s*\d+,"([^"]*)"', re.IGNORECASE)


# ── Public API ───────────────────────────────────────────────────────────────

def parse_modem_reply(raw: str, failure_keywords: list[str]) -> ModemResponse:
    """
    Interpret everything the modem wrote after one ATD command.

    Success criteria (all must hold):
      1. "NO CARRIER" and "ERROR" are absent.
      2. If a +CUSD line is present, none of the failure_keywords appear
         in the USSD message (case-insensitive).

    Returns a ModemResponse with:
      success   : bool
      raw_reply : the original raw string (for logging)
      cusd_text : extracted USSD message, or None
    """
    cusd_text = _extract_cusd(raw)
    failed_by_carrier = _contains_no_carrier(raw)
    failed_by_error   = _contains_error(raw)
    failed_by_keyword = _keyword_hit(cusd_text, failure_keywords)

    success = not (failed_by_carrier or failed_by_error or failed_by_keyword)

    return ModemResponse(
        success=success,
        raw_reply=raw,
        cusd_text=cusd_text,
    )


def extract_cusd_text(raw: str) -> str | None:
    """Public convenience — extract USSD message text from modem output."""
    return _extract_cusd(raw)


# ── Private helpers ──────────────────────────────────────────────────────────

def _extract_cusd(raw: str) -> str | None:
    match = _CUSD_PATTERN.search(raw)
    return match.group(1).strip() if match else None


def _contains_no_carrier(raw: str) -> bool:
    return "NO CARRIER" in raw.upper()


def _contains_error(raw: str) -> bool:
    # "ERROR" but not inside "+CUSD" text — check top-level modem codes only
    for line in raw.splitlines():
        stripped = line.strip().upper()
        if stripped == "ERROR" or stripped.startswith("+CME ERROR") or stripped.startswith("+CMS ERROR"):
            return True
    return False


def _keyword_hit(cusd_text: str | None, keywords: list[str]) -> bool:
    if cusd_text is None or not keywords:
        return False
    lower = cusd_text.lower()
    return any(kw.lower() in lower for kw in keywords if kw.strip())
