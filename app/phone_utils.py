"""Shared phone number normalization for outbound SMS/WhatsApp delivery."""
DEFAULT_COUNTRY_CODE = "91"


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
