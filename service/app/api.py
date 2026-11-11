import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from redis.asyncio import Redis

from .domain import Record
from .store import Store


class Health(BaseModel):
    status: str


def create_app(store: Store | None = None) -> FastAPI:
    owned = store is None
    if store is None:
        store = Store(Redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/0")))

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        yield
        if owned:
            await store.redis.aclose()

    app = FastAPI(title="Ledger Bridge", version="1.0.0", lifespan=lifespan)

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

    @app.get("/v1/reconciliations/{correlation_id}", response_model=Record)
    async def fetch(correlation_id: str):
        if not 1 <= len(correlation_id) <= 128 or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_.:-" for c in correlation_id):
            raise HTTPException(422, "invalid correlation_id")
        record = await store.get(correlation_id)
        if record is None:
            raise HTTPException(404, "not found")
        return record

    return app


app = create_app()
