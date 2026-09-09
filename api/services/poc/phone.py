from __future__ import annotations

import re


class InvalidCallerNumber(ValueError):
    pass


def normalize_indian_mobile(value: str | None) -> str:
    """Return the ten-digit Indian mobile number used by WFMS."""
    digits = re.sub(r"\D", "", value or "")
    if digits.startswith("0091"):
        digits = digits[4:]
    elif digits.startswith("91") and len(digits) == 12:
        digits = digits[2:]
    elif digits.startswith("0") and len(digits) == 11:
        digits = digits[1:]
    if len(digits) != 10 or digits[0] not in "6789":
        raise InvalidCallerNumber("Caller ID is not a valid Indian mobile number")
    return digits


def masked_mobile(value: str | None) -> str:
    try:
        normalized = normalize_indian_mobile(value)
    except InvalidCallerNumber:
        return "unknown"
    return f"******{normalized[-4:]}"
