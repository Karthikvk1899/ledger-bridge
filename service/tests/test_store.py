import fakeredis.aioredis
import pytest
from app.domain import Conflict, Event
from app.store import Store


@pytest.mark.asyncio
async def test_atomic_ingestion_and_cross_key_idempotency():
    redis = fakeredis.aioredis.FakeRedis()
    store = Store(redis)
    first = Event(event_id="same", correlation_id="a", source="actual", amount_minor=12, currency="USD")
    result, changed = await store.ingest(first)
    assert changed and result.status == "pending"
    _, changed = await store.ingest(first)
    assert not changed
    with pytest.raises(Conflict):
        await store.ingest(first.model_copy(update={"correlation_id": "b"}))
    result, changed = await store.ingest(Event(event_id="two", correlation_id="a", source="expected", amount_minor=12, currency="USD"))
    assert changed and result.status == "matched"
    assert (await store.get("a")) == result
    await redis.aclose()


@pytest.mark.asyncio
async def test_concurrent_opposing_sides():
    import asyncio
    redis = fakeredis.aioredis.FakeRedis()
    store = Store(redis)
    events = [Event(event_id=s, correlation_id="c", source=s, amount_minor=5, currency="USD") for s in ("actual", "expected")]
    await asyncio.gather(*(store.ingest(e) for e in events))
    assert (await store.get("c")).status == "matched"
    await redis.aclose()
