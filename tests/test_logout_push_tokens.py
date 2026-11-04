from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app import auth, partner_api


def test_customer_logout_clears_push_token():
    customer = SimpleNamespace(phone="9000000000")
    stored_customer = SimpleNamespace(phone=customer.phone, auth_version=1, fcm_token="device-token")
    db = MagicMock()
    db.get.return_value = stored_customer

    with patch.object(auth, "SessionLocal", return_value=db):
        auth.logout_customer(customer)

    assert stored_customer.auth_version == 2
    assert stored_customer.fcm_token is None
    db.commit.assert_called_once()


def test_partner_logout_clears_push_token():
    partner = SimpleNamespace(phone="9000000001", fcm_token="partner-device-token")
    session = SimpleNamespace(device_id="partner-device-0001")
    db = MagicMock()
    db.get.return_value = partner
    payload = partner_api.PartnerLogoutRequest(device_id=session.device_id)

    with (
        patch.object(partner_api, "SessionLocal", return_value=db),
        patch.object(partner_api, "_decode", return_value={"sub": partner.phone}),
        patch.object(partner_api, "current_partner", return_value=partner),
        patch.object(partner_api, "_active_partner_session", return_value=session),
    ):
        result = partner_api.partner_logout(payload, "Bearer signed-token")

    assert result == {"revoked_sessions": 0}
    assert partner.fcm_token is None
    db.commit.assert_called_once()

def test_customer_refresh_logout_clears_push_token():
    customer = SimpleNamespace(phone="9000000002", fcm_token="refresh-device-token")
    session = SimpleNamespace(customer_id=customer.phone, device_id="customer-device-123", refresh_token_hash="hashed-refresh-token", revoked_at=None, rotated_to_hash=None)
    db = MagicMock()
    db.query.return_value.filter.return_value.with_for_update.return_value.first.return_value = session
    db.get.return_value = customer

    with (
        patch("app.pin_auth.SessionLocal", return_value=db),
        patch("app.pin_auth._refresh_hash", return_value="hashed-refresh-token"),
    ):
        from app.pin_auth import revoke
        revoke("refresh-token", "customer-device-123")

    assert session.revoked_at is not None
    assert customer.fcm_token is None
    db.commit.assert_called_once()
