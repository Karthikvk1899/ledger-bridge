import fakeredis.aioredis
import httpx
import pytest
from app.api import create_app
from app.domain import Event
from app.store import Store


@pytest.mark.asyncio
async def test_api_lookup_and_validation():
    redis = fakeredis.aioredis.FakeRedis()
    store = Store(redis)
    app = create_app(store)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        assert (await client.get("/v1/reconciliations/missing")).status_code == 404
        assert (await client.get("/v1/reconciliations/bad!id")).status_code == 422
        await store.ingest(Event(event_id="e", correlation_id="c", source="expected", amount_minor=0, currency="USD"))
        response = await client.get("/v1/reconciliations/c")
        assert response.status_code == 200
        assert response.json()["expected"]["amount_minor"] == 0
    await redis.aclose()
