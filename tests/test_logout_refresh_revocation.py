"""Logout must revoke both existing access tokens and refresh credentials."""

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import auth, pin_auth
from app.db import Base
from app.models import CustomerModel


@pytest.fixture
def sessions(monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False)
    monkeypatch.setattr(auth, "SessionLocal", factory)
    monkeypatch.setattr(pin_auth, "SessionLocal", factory)
    monkeypatch.setenv("JWT_SECRET", "logout-regression-test-secret")
    yield factory
    engine.dispose()


def test_logout_revokes_all_customer_sessions_and_preserves_other_customer(sessions):
    device = "logout-regression-device-one"
    second_device = "logout-regression-device-two"
    first = pin_auth.register("9999999999", "First", "123456", device)
    second = pin_auth.login("9999999999", "123456", second_device)
    unrelated = pin_auth.register("9999999998", "Other", "123456", device)

    customer = auth.current_customer("Bearer " + first["access_token"])
    auth.logout_customer(customer)

    for tokens, session_device in ((first, device), (second, second_device)):
        with pytest.raises(HTTPException) as access_error:
            auth.current_customer("Bearer " + tokens["access_token"])
        assert access_error.value.status_code == 401
        with pytest.raises(HTTPException) as refresh_error:
            pin_auth.refresh(tokens["refresh_token"], session_device)
        assert refresh_error.value.status_code == 401

    with sessions() as db:
        revoked = db.query(pin_auth.CustomerSessionModel).filter_by(
            customer_id="9999999999"
        ).all()
        assert len(revoked) == 2
        assert all(session.revoked_at is not None for session in revoked)
        assert db.get(CustomerModel, "9999999999").auth_version == 2

    # Logout remains customer-scoped and does not prevent a fresh PIN login.
    other = pin_auth.refresh(unrelated["refresh_token"], device)
    assert auth.current_customer("Bearer " + other["access_token"]).phone == "9999999998"
    fresh = pin_auth.login("9999999999", "123456", device)
    assert auth.current_customer("Bearer " + fresh["access_token"]).phone == "9999999999"


def test_device_logout_revokes_its_access_token_and_preserves_other_devices(sessions):
    device = "logout-regression-device-one"
    other_device = "logout-regression-device-two"
    first = pin_auth.register("9999999999", "First", "123456", device)
    other = pin_auth.login("9999999999", "123456", other_device)
    pin_auth.revoke(first["refresh_token"])

    with pytest.raises(HTTPException) as error:
        auth.current_customer("Bearer " + first["access_token"])
    assert error.value.status_code == 401
    with pytest.raises(HTTPException):
        pin_auth.refresh(first["refresh_token"], device)

    assert auth.current_customer("Bearer " + other["access_token"]).phone == "9999999999"
    refreshed = pin_auth.refresh(other["refresh_token"], other_device)
    assert auth.current_customer("Bearer " + refreshed["access_token"]).phone == "9999999999"


def test_pin_account_cannot_use_old_unbound_access_token_after_device_logout(sessions):
    tokens = pin_auth.register("9999999999", "First", "123456", "logout-regression-device")
    old_access = auth.create_token("9999999999", "First")
    pin_auth.revoke(tokens["refresh_token"])
    with pytest.raises(HTTPException) as error:
        auth.current_customer("Bearer " + old_access)
    assert error.value.status_code == 401


def test_refresh_rotates_access_session_and_rejects_expired_session(sessions):
    from datetime import datetime, timedelta, timezone

    device = "logout-regression-device"
    first = pin_auth.register("9999999999", "First", "123456", device)
    refreshed = pin_auth.refresh(first["refresh_token"], device)
    with pytest.raises(HTTPException):
        auth.current_customer("Bearer " + first["access_token"])
    assert auth.current_customer("Bearer " + refreshed["access_token"]).phone == "9999999999"
    with sessions() as db:
        row = db.query(pin_auth.CustomerSessionModel).filter_by(
            refresh_token_hash=pin_auth._refresh_hash(refreshed["refresh_token"])
        ).one()
        row.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        db.commit()
    with pytest.raises(HTTPException) as error:
        auth.current_customer("Bearer " + refreshed["access_token"])
    assert error.value.status_code == 401
