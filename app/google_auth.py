"""Google ID-token verification for customer sign-in."""
import os

from fastapi import HTTPException
from google.auth.transport.requests import Request
from google.oauth2 import id_token


def verify_google_id_token(token: str) -> dict[str, str]:
    """Verify a Google OIDC ID token and return only trusted identity claims."""
    client_id = os.getenv("GOOGLE_OAUTH_CLIENT_ID", "").strip()
    if not client_id:
        raise HTTPException(
            status_code=503,
            detail="Google sign-in is not configured on the server.",
        )
    if not token or len(token) > 8192:
        raise HTTPException(status_code=401, detail="Invalid Google sign-in token.")

    try:
        claims = id_token.verify_oauth2_token(token, Request(), client_id)
    except Exception as exc:
        # Never include the token or provider response in the API error.
        raise HTTPException(
            status_code=401,
            detail="Google sign-in could not be verified. Please try again.",
        ) from exc

    subject = claims.get("sub")
    email = claims.get("email")
    verified = claims.get("email_verified") is True or claims.get("email_verified") == "true"
    if not isinstance(subject, str) or not subject or not isinstance(email, str) or not verified:
        raise HTTPException(
            status_code=401,
            detail="Use a Google account with a verified email address.",
        )

    return {
        "subject": subject,
        "email": email.strip().lower(),
        "name": str(claims.get("name") or "").strip()[:100],
    }
