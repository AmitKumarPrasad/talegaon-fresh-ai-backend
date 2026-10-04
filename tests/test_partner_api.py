from app.partner_api import DELIVERY_TRANSITIONS
from app.partner_api import _delivery_otp_hash


def test_partner_delivery_lifecycle_is_monotonic():
    assert DELIVERY_TRANSITIONS["ASSIGNED"] == {"ACCEPTED"}
    assert DELIVERY_TRANSITIONS["ACCEPTED"] == {"PICKED_UP"}
    assert DELIVERY_TRANSITIONS["PICKED_UP"] == {"OUT_FOR_DELIVERY"}
    assert DELIVERY_TRANSITIONS["OUT_FOR_DELIVERY"] == {"DELIVERED"}


def test_delivery_otp_hash_is_not_plaintext():
    otp = "123456"
    assert _delivery_otp_hash(otp) != otp
    assert _delivery_otp_hash(otp) == _delivery_otp_hash(otp)
