import os
import asyncio
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Request
from pydantic import BaseModel
from prometheus_client import CONTENT_TYPE_LATEST, Counter, generate_latest
from redis.asyncio import Redis
from fastapi.responses import Response

from .auth import OidcVerifier, configured_verifier
from .domain import Record
from .store import Store

HTTP_REQUESTS = Counter('ledger_http_requests_total', 'HTTP requests', ['method', 'status'])

class Health(BaseModel):
    status: str


def create_app(store: Store | None = None, verifier: OidcVerifier | None = None) -> FastAPI:
    owned = store is None
    verifier = verifier or configured_verifier()
    if store is None:
        store = Store(Redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/0")))

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        yield
        if owned:
            await store.redis.aclose()

    app = FastAPI(title="Ledger Bridge", version="1.0.0", lifespan=lifespan)

    @app.middleware('http')
    async def count_requests(request: Request, call_next):
        response = await call_next(request)
        HTTP_REQUESTS.labels(request.method, str(response.status_code)).inc()
        return response

    async def require_identity(request: Request) -> None:
        if verifier is None:
            return
        authorization = request.headers.get('Authorization', '')
        scheme, _, token = authorization.partition(' ')
        if scheme.lower() != 'bearer' or not token:
            raise HTTPException(401, 'bearer token required', headers={'WWW-Authenticate': 'Bearer'})
        await asyncio.to_thread(verifier.verify, token)

    @app.get("/health/live", response_model=Health)
    async def live():
        return Health(status="ok")

    @app.get("/health/ready", response_model=Health)
    async def ready():
        try:
            await store.redis.ping()
        except Exception as exc:
            raise HTTPException(503, "Redis unavailable") from exc
        return Health(status="ok")

    @app.get('/metrics', include_in_schema=False)
    async def metrics():
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

    @app.get("/v1/reconciliations/{correlation_id}", response_model=Record, dependencies=[Depends(require_identity)])
    async def fetch(correlation_id: str):
        if not 1 <= len(correlation_id) <= 128 or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_.:-" for c in correlation_id):
            raise HTTPException(422, "invalid correlation_id")
        record = await store.get(correlation_id)
        if record is None:
            raise HTTPException(404, "not found")
        return record

    return app


app = create_app()
