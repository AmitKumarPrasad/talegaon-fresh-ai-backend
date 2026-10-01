"""Shared phone number validation and normalization helpers."""
import re

DEFAULT_COUNTRY_CODE = "91"
INDIAN_MOBILE_RE = re.compile(r"^[6-9]\d{9}$")


def is_valid_indian_mobile(phone: str) -> bool:
    """Accept only a bare Indian ten-digit mobile number."""
    return bool(INDIAN_MOBILE_RE.fullmatch("".join(ch for ch in phone if ch.isdigit())))


def to_e164_digits(phone: str) -> str:
    """Return digits-only international number (country code + number, no '+').

    Assumes DEFAULT_COUNTRY_CODE for bare 10-digit local numbers.
    """
    digits = "".join(ch for ch in phone if ch.isdigit())
    if len(digits) == 10:
        return DEFAULT_COUNTRY_CODE + digits
    return digits


def to_e164(phone: str) -> str:
    """Return '+'-prefixed international number for providers that require it."""
    return "+" + to_e164_digits(phone)
