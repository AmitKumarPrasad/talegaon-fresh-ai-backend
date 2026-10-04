from app.partner_api import DELIVERY_TRANSITIONS
from app.partner_api import _delivery_otp_hash
from app.partner_api import _settle_payout_entry

from types import SimpleNamespace


def test_partner_delivery_lifecycle_is_monotonic():
    assert DELIVERY_TRANSITIONS["ASSIGNED"] == {"ACCEPTED"}
    assert DELIVERY_TRANSITIONS["ACCEPTED"] == {"PICKED_UP"}
    assert DELIVERY_TRANSITIONS["PICKED_UP"] == {"OUT_FOR_DELIVERY"}
    assert DELIVERY_TRANSITIONS["OUT_FOR_DELIVERY"] == {"DELIVERED"}


def test_delivery_otp_hash_is_not_plaintext():
    otp = "123456"
    assert _delivery_otp_hash(otp) != otp
    assert _delivery_otp_hash(otp) == _delivery_otp_hash(otp)


def test_payout_settlement_is_idempotent_and_sets_paid_at():
    entry = SimpleNamespace(status="PENDING", paid_at=None)
    assert _settle_payout_entry(entry) is True
    assert entry.status == "PAID"
    assert entry.paid_at is not None
    assert _settle_payout_entry(entry) is False
