"""OIDC access-token verification for deployments that expose the read API."""
import os
from dataclasses import dataclass

import jwt
from fastapi import HTTPException
from jwt import PyJWKClient


@dataclass
class OidcVerifier:
    issuer: str
    audience: str
    jwks_url: str

    def __post_init__(self) -> None:
        if not self.issuer.startswith('https://') or not self.jwks_url.startswith('https://'):
            raise ValueError('OIDC issuer and JWKS URL must use HTTPS')
        self.client = PyJWKClient(self.jwks_url, cache_jwk_set=True, lifespan=300, timeout=5)

    def verify(self, token: str) -> dict:
        try:
            key = self.client.get_signing_key_from_jwt(token).key
            return jwt.decode(token, key, algorithms=['RS256'], audience=self.audience,
                              issuer=self.issuer, options={'require': ['exp', 'iat', 'iss', 'aud', 'sub']}, leeway=30)
        except (jwt.PyJWTError, OSError, ValueError) as exc:
            raise HTTPException(401, 'invalid access token', headers={'WWW-Authenticate': 'Bearer'}) from exc


def configured_verifier() -> OidcVerifier | None:
    issuer = os.getenv('OIDC_ISSUER')
    audience = os.getenv('OIDC_AUDIENCE')
    jwks_url = os.getenv('OIDC_JWKS_URL')
    present = (issuer, audience, jwks_url)
    if any(present) and not all(present):
        raise RuntimeError('OIDC_ISSUER, OIDC_AUDIENCE and OIDC_JWKS_URL must all be set')
    if os.getenv('APP_ENV') == 'production' and not all(present):
        raise RuntimeError('production requires OIDC configuration')
    return OidcVerifier(issuer, audience, jwks_url) if all(present) else None
