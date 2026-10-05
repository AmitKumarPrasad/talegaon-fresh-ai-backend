from datetime import datetime, timedelta, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.models import DeliveryPartnerModel, DeliveryPayoutLedgerModel, OrderModel
from app import partner_api


@pytest.fixture
def delivery_client(monkeypatch):
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    monkeypatch.setattr(partner_api, "SessionLocal", factory)
    monkeypatch.setattr("app.order_status.SessionLocal", factory)
    monkeypatch.setenv("JWT_SECRET", "partner-delivery-test-secret")
    partner = DeliveryPartnerModel(phone="9876543210", name="Test Partner", active=True)
    with factory() as db:
        db.add(OrderModel(
            id=1, customer_id="test-customer", status="OUT_FOR_DELIVERY",
            delivery_status="OUT_FOR_DELIVERY", delivery_person_phone=partner.phone,
            payment_method="COD", total=100, address="Test address",
            delivery_otp_hash=partner_api._delivery_otp_hash("123456"),
            delivery_otp_expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
            delivery_otp_attempts=0,
        ))
        db.commit()
    app = FastAPI()
    app.include_router(partner_api.router)
    app.dependency_overrides[partner_api.current_partner] = lambda: partner
    with TestClient(app) as client:
        yield client, factory
    engine.dispose()


def test_incorrect_delivery_otp_is_a_validation_error_not_session_expiry(delivery_client):
    client, factory = delivery_client
    response = client.post(
        "/partner/orders/1/complete", json={"otp": "000000", "cod_collected": True}
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid delivery OTP"
    with factory() as db:
        order = db.get(OrderModel, 1)
        assert order.delivery_otp_attempts == 1
        assert order.status == "OUT_FOR_DELIVERY"


def test_incorrect_delivery_otp_still_locks_after_five_attempts(delivery_client):
    client, _ = delivery_client
    for _ in range(5):
        response = client.post(
            "/partner/orders/1/complete", json={"otp": "000000", "cod_collected": True}
        )
        assert response.status_code == 400
    response = client.post(
        "/partner/orders/1/complete", json={"otp": "123456", "cod_collected": True}
    )
    assert response.status_code == 429


def test_corrected_otp_completes_delivery_and_records_one_payout(delivery_client):
    client, factory = delivery_client
    response = client.post(
        "/partner/orders/1/complete", json={"otp": "000000", "cod_collected": True}
    )
    assert response.status_code == 400
    response = client.post(
        "/partner/orders/1/complete", json={"otp": "123456", "cod_collected": True}
    )
    assert response.status_code == 200
    assert response.json()["status"] == "DELIVERED"
    with factory() as db:
        order = db.get(OrderModel, 1)
        assert order.delivery_otp_hash is None
        assert order.delivery_otp_attempts == 0
        payout = db.query(DeliveryPayoutLedgerModel).one()
        assert payout.order_id == 1
        assert payout.cod_amount == 100
