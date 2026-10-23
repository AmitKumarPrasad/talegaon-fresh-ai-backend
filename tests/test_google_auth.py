import pytest
from fastapi import HTTPException

from app import google_auth


def test_google_id_token_uses_configured_audience_and_returns_verified_identity(monkeypatch):
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_ID", "web-client-id")
    calls = {}

    def verify(token, request, audience):
        calls.update(token=token, audience=audience)
        return {
            "sub": "google-subject-123",
            "email": "Customer@Example.com",
            "email_verified": True,
            "name": "Fresh Customer",
            "iss": "https://accounts.google.com",
        }

    monkeypatch.setattr(google_auth.id_token, "verify_oauth2_token", verify)

    identity = google_auth.verify_google_id_token("signed-id-token")

    assert calls == {"token": "signed-id-token", "audience": "web-client-id"}
    assert identity == {
        "subject": "google-subject-123",
        "email": "customer@example.com",
        "name": "Fresh Customer",
    }


def test_google_id_token_rejects_unverified_email(monkeypatch):
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_ID", "web-client-id")
    monkeypatch.setattr(
        google_auth.id_token,
        "verify_oauth2_token",
        lambda *_args: {
            "sub": "google-subject-123",
            "email": "customer@example.com",
            "email_verified": False,
        },
    )

    with pytest.raises(HTTPException) as error:
        google_auth.verify_google_id_token("signed-id-token")

    assert error.value.status_code == 401


def test_google_id_token_fails_closed_without_oauth_client_id(monkeypatch):
    monkeypatch.delenv("GOOGLE_OAUTH_CLIENT_ID", raising=False)

    with pytest.raises(HTTPException) as error:
        google_auth.verify_google_id_token("signed-id-token")

    assert error.value.status_code == 503


def test_google_id_token_rejects_invalid_provider_token(monkeypatch):
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_ID", "web-client-id")

    def invalid(*_args):
        raise ValueError("not a valid token")

    monkeypatch.setattr(google_auth.id_token, "verify_oauth2_token", invalid)

    with pytest.raises(HTTPException) as error:
        google_auth.verify_google_id_token("invalid")

    assert error.value.status_code == 401
