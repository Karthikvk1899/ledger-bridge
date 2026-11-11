from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import fakeredis.aioredis
import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException

from app.api import create_app
from app.auth import OidcVerifier, configured_verifier
from app.domain import Event
from app.store import Store


def make_verifier():
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    verifier = OidcVerifier('https://issuer.example', 'ledger-api', 'https://issuer.example/keys')
    verifier.client.get_signing_key_from_jwt = lambda _: SimpleNamespace(key=private.public_key())
    return verifier, private


def token(private, audience='ledger-api', expired=False):
    now = datetime.now(timezone.utc)
    return jwt.encode({'iss': 'https://issuer.example', 'aud': audience, 'sub': 'user-1',
                       'iat': now, 'exp': now + timedelta(minutes=-5 if expired else 5)},
                      private, algorithm='RS256')


def test_oidc_verifies_signature_issuer_audience_and_expiry():
    verifier, private = make_verifier()
    assert verifier.verify(token(private))['sub'] == 'user-1'
    for invalid in (token(private, audience='wrong'), token(private, expired=True)):
        with pytest.raises(HTTPException) as error:
            verifier.verify(invalid)
        assert error.value.status_code == 401


def test_production_fails_closed(monkeypatch):
    monkeypatch.setenv('APP_ENV', 'production')
    for name in ('OIDC_ISSUER', 'OIDC_AUDIENCE', 'OIDC_JWKS_URL'):
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(RuntimeError, match='production requires'):
        configured_verifier()


@pytest.mark.asyncio
async def test_api_requires_token_and_exposes_metrics():
    redis = fakeredis.aioredis.FakeRedis()
    store = Store(redis)
    verifier, private = make_verifier()
    await store.ingest(Event(event_id='e', correlation_id='trade-1', source='actual', amount_minor=5, currency='USD'))
    app = create_app(store, verifier=verifier)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
        url = '/v1/reconciliations/trade-1'
        assert (await client.get(url)).status_code == 401
        assert (await client.get(url, headers={'Authorization': 'Bearer invalid'})).status_code == 401
        assert (await client.get(url, headers={'Authorization': f'Bearer {token(private)}'})).status_code == 200
        metrics = await client.get('/metrics')
        assert metrics.status_code == 200
        assert 'ledger_http_requests_total' in metrics.text
    await redis.aclose()
