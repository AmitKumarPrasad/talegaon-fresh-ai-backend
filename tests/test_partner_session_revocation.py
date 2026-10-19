from datetime import datetime, timedelta, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import partner_api
from app.db import Base
from app.models import DeliveryPartnerModel, DeliveryPartnerSessionModel

DEVICE_A = "test-partner-device-a"
DEVICE_B = "test-partner-device-b"


@pytest.fixture
def sessions_client(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    monkeypatch.setattr(partner_api, "SessionLocal", factory)
    monkeypatch.setenv("JWT_SECRET", "partner-session-revocation-test-key")
    with factory() as db:
        for phone in ["9876543210", "9876543211"]:
            db.add(DeliveryPartnerModel(phone=phone, name="Partner", active=True, pin_hash=partner_api._pin_hash("123456")))
        db.commit()
    app = FastAPI()
    app.include_router(partner_api.router)
    with TestClient(app) as client:
        yield client, factory
    engine.dispose()


def login(client, device=DEVICE_A, phone="9876543210"):
    response = client.post("/partner/auth/login", json={"phone": phone, "pin": "123456", "device_id": device})
    assert response.status_code == 200
    return response.json()


def headers(tokens):
    return {"Authorization": "Bearer " + tokens["access_token"]}


def refresh(client, tokens, device=DEVICE_A):
    return client.post("/partner/auth/refresh", json={"refresh_token": tokens["refresh_token"], "device_id": device})


def test_logout_revokes_access_and_refresh_but_preserves_other_sessions(sessions_client):
    client, _ = sessions_client
    a = login(client)
    same_device = login(client)
    b = login(client, DEVICE_B)
    other = login(client, DEVICE_A, "9876543211")
    assert client.get("/partner/me", headers=headers(a)).status_code == 200
    response = client.post("/partner/auth/logout", json={"device_id": DEVICE_A}, headers=headers(a))
    assert response.status_code == 200
    assert response.json()["revoked_sessions"] == 2
    for tokens in [a, same_device]:
        assert client.get("/partner/me", headers=headers(tokens)).status_code == 401
        assert refresh(client, tokens).status_code == 401
    assert client.get("/partner/me", headers=headers(b)).status_code == 200
    assert refresh(client, b, DEVICE_B).status_code == 200
    assert client.get("/partner/me", headers=headers(other)).status_code == 200
    assert refresh(client, other).status_code == 200
    fresh = login(client)
    assert client.get("/partner/me", headers=headers(fresh)).status_code == 200


def test_refresh_rotation_invalidates_old_access_and_logout_revokes_new_pair(sessions_client):
    client, _ = sessions_client
    old = login(client)
    response = refresh(client, old)
    assert response.status_code == 200
    new = response.json()
    assert new["access_token"] != old["access_token"]
    assert client.get("/partner/me", headers=headers(old)).status_code == 401
    assert refresh(client, old).status_code == 401
    assert client.get("/partner/me", headers=headers(new)).status_code == 200
    assert client.post("/partner/auth/logout", json={"device_id": DEVICE_A}, headers=headers(new)).status_code == 200
    assert client.get("/partner/me", headers=headers(new)).status_code == 401
    assert refresh(client, new).status_code == 401


def test_wrong_device_cannot_logout_another_device(sessions_client):
    client, _ = sessions_client
    a = login(client)
    b = login(client, DEVICE_B)
    assert client.post("/partner/auth/logout", json={"device_id": DEVICE_B}, headers=headers(a)).status_code == 401
    assert client.get("/partner/me", headers=headers(a)).status_code == 200
    assert client.get("/partner/me", headers=headers(b)).status_code == 200


def test_expired_session_rejects_access_even_when_jwt_not_expired(sessions_client):
    client, factory = sessions_client
    tokens = login(client)
    with factory() as db:
        row = db.get(DeliveryPartnerSessionModel, partner_api._decode(tokens["access_token"])["sid"])
        row.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        db.commit()
    assert client.get("/partner/me", headers=headers(tokens)).status_code == 401
    assert refresh(client, tokens).status_code == 401


def test_legacy_access_requires_refresh_but_existing_refresh_can_upgrade(sessions_client):
    import hashlib
    import hmac
    import json

    client, _ = sessions_client
    tokens = login(client)
    header, _, _ = tokens["access_token"].split(".")
    claims = partner_api._decode(tokens["access_token"])
    del claims["sid"]
    payload = partner_api._b64(json.dumps(claims).encode())
    signature = hmac.new(partner_api._secret().encode(), f"{header}.{payload}".encode(), hashlib.sha256).digest()
    legacy = {"access_token": f"{header}.{payload}.{partner_api._b64(signature)}"}
    assert client.get("/partner/me", headers=headers(legacy)).status_code == 401
    upgraded = refresh(client, tokens)
    assert upgraded.status_code == 200
    assert client.get("/partner/me", headers=headers(upgraded.json())).status_code == 200


def test_expired_access_can_refresh_then_logout(sessions_client, monkeypatch):
    client, _ = sessions_client
    monkeypatch.setattr(partner_api, "ACCESS_TOKEN_MINUTES", -1)
    old = login(client)
    assert client.post("/partner/auth/logout", json={"device_id": DEVICE_A}, headers=headers(old)).status_code == 401
    monkeypatch.setattr(partner_api, "ACCESS_TOKEN_MINUTES", 30)
    response = refresh(client, old)
    assert response.status_code == 200
    new = response.json()
    assert client.post("/partner/auth/logout", json={"device_id": DEVICE_A}, headers=headers(new)).status_code == 200
    assert client.get("/partner/me", headers=headers(new)).status_code == 401


def test_session_binding_rejects_another_partners_session_id(sessions_client):
    client, factory = sessions_client
    other = login(client, phone="9876543211")
    other_sid = partner_api._decode(other["access_token"])["sid"]
    with factory() as db:
        partner = db.get(DeliveryPartnerModel, "9876543210")
        mismatched = {"access_token": partner_api._token(partner, other_sid)}
    assert client.get("/partner/me", headers=headers(mismatched)).status_code == 401
