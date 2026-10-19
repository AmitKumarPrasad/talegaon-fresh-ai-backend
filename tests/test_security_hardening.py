from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException
from app import pin_auth, partner_api, rate_limiter


def test_existing_customer_without_pin_cannot_register_or_get_session():
    db = MagicMock()
    db.get.return_value = SimpleNamespace(phone='9000000000', name='Existing')
    with patch.object(pin_auth, 'SessionLocal', return_value=db), patch.object(pin_auth, '_issue') as issue:
        with pytest.raises(HTTPException) as error:
            pin_auth.register('9000000000', 'Other', '123456', 'local-audit-device')
        assert error.value.status_code == 409
        issue.assert_not_called()
        db.add.assert_not_called()


def test_partner_pin_change_invalidates_old_access_token(monkeypatch):
    monkeypatch.setenv('JWT_SECRET', 'local-test-key-that-is-long-enough-for-tests')
    partner = SimpleNamespace(phone='9000000000', name='Partner', active=True, pin_hash='old-hash')
    token = partner_api._token(partner, 1)
    partner.pin_hash = 'new-hash'
    from datetime import datetime, timedelta, timezone
    session = SimpleNamespace(partner_phone=partner.phone, revoked_at=None, expires_at=datetime.now(timezone.utc) + timedelta(days=1))
    db = MagicMock()
    db.get.side_effect = lambda model, key: partner if model is partner_api.DeliveryPartnerModel else session
    with patch.object(partner_api, 'SessionLocal', return_value=db):
        with pytest.raises(HTTPException) as error:
            partner_api.current_partner('Bearer ' + token)
        assert error.value.status_code == 401
        new_token = partner_api._token(partner, 1)
        assert partner_api.current_partner('Bearer ' + new_token) is partner


def test_partner_pin_reset_revokes_refresh_sessions():
    partner = SimpleNamespace(phone='9000000000', name='Partner', active=True, pin_hash='old')
    db = MagicMock(); db.get.return_value = partner
    payload = partner_api.PartnerProvisionRequest(phone=partner.phone, name=partner.name, pin='123456')
    with patch.object(partner_api, 'SessionLocal', return_value=db), patch.object(partner_api, '_admin_authorized', return_value=True):
        partner_api.provision_partner(payload, MagicMock())
    db.query.return_value.filter.return_value.update.assert_called_once()
    assert partner.pin_hash != 'old'


def test_partner_routes_are_rate_limited():
    assert rate_limiter.rule_for('/partner/auth/login') == (10, 60)
    assert rate_limiter.rule_for('/partner/auth/refresh') == (30, 60)
    assert rate_limiter.rule_for('/partner/admin/partners') == (60, 60)
    assert rate_limiter.rule_for('/partner/ai/assistant') == (20, 60)


def test_render_runtime_counts_as_production(monkeypatch):
    monkeypatch.setenv('RENDER', 'true'); monkeypatch.delenv('ENVIRONMENT', raising=False)
    assert rate_limiter._environment() == 'production'


def test_render_limiter_fails_closed_on_redis_error(monkeypatch):
    import asyncio
    monkeypatch.setenv('RENDER', 'true'); monkeypatch.delenv('ENVIRONMENT', raising=False)
    request = SimpleNamespace(url=SimpleNamespace(path='/partner/auth/login'), headers={}, client=SimpleNamespace(host='127.0.0.1'))
    with patch.object(rate_limiter, '_client', side_effect=RuntimeError('offline')):
        response = asyncio.run(rate_limiter.enforce_rate_limit(request))
    assert response.status_code == 503


def test_partner_login_checks_account_limit_after_ip_limit():
    import asyncio
    from unittest.mock import AsyncMock
    request = SimpleNamespace(url=SimpleNamespace(path='/partner/auth/login'), headers={}, client=SimpleNamespace(host='127.0.0.1'), json=AsyncMock(return_value={'phone':'9000000000'}))
    redis = MagicMock(); redis.eval = AsyncMock(side_effect=[[1,9,60],[0,0,900]])
    with patch.object(rate_limiter, '_client', return_value=redis):
        response = asyncio.run(rate_limiter.enforce_rate_limit(request))
    assert response.status_code == 429
    assert redis.eval.await_count == 2
    assert '9000000000' not in redis.eval.call_args.args[2]


def test_account_limit_preserves_request_body_for_login_handler():
    from fastapi import FastAPI, Request
    from fastapi.testclient import TestClient
    from unittest.mock import AsyncMock
    app = FastAPI()
    @app.middleware('http')
    async def limiter(request, call_next):
        response = await rate_limiter.enforce_rate_limit(request)
        return response if response is not None else await call_next(request)
    @app.post('/partner/auth/login')
    async def login(request: Request):
        return await request.json()
    redis = MagicMock(); redis.eval = AsyncMock(return_value=[1,4,900])
    with patch.object(rate_limiter, '_client', return_value=redis):
        response = TestClient(app).post('/partner/auth/login', json={'phone':'9000000000','pin':'123456'})
    assert response.status_code == 200
    assert response.json()['phone'] == '9000000000'
    assert redis.eval.await_count == 2

