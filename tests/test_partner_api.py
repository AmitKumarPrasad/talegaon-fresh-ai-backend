from app.partner_api import DELIVERY_TRANSITIONS, DELIVERY_STATUSES


def test_partner_delivery_lifecycle_is_monotonic():
    assert DELIVERY_TRANSITIONS["ASSIGNED"] == {"ACCEPTED"}
    assert DELIVERY_TRANSITIONS["ACCEPTED"] == {"PICKED_UP"}
    assert DELIVERY_TRANSITIONS["PICKED_UP"] == {"OUT_FOR_DELIVERY"}
    assert DELIVERY_TRANSITIONS["OUT_FOR_DELIVERY"] == {"DELIVERED"}
    assert "CANCELLED" not in DELIVERY_STATUSES
