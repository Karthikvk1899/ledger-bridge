from redis.asyncio import Redis

from .domain import Conflict, Event, Record, apply

class Store:
    def __init__(self, redis: Redis, ttl_seconds: int = 604800):
        self.redis = redis
        self.ttl_seconds = ttl_seconds

    @staticmethod
    def key(correlation_id: str) -> str:
        return f"reconcile:record:{correlation_id}"

    async def get(self, correlation_id: str) -> Record | None:
        raw = await self.redis.get(self.key(correlation_id))
        return Record.model_validate_json(raw) if raw else None

    async def ingest(self, event: Event) -> tuple[Record, bool]:
        key = self.key(event.correlation_id)
        marker = f"reconcile:event:{event.event_id}"
        # WATCH protects the read/derive/write boundary. An event ID used with a
        # different correlation ID remains a contract violation within retention.
        from redis.exceptions import WatchError
        for _ in range(20):
            async with self.redis.pipeline() as pipe:
                try:
                    await pipe.watch(key, marker)
                    raw, seen = await pipe.get(key), await pipe.get(marker)
                    if seen:
                        if seen.decode() != event.correlation_id:
                            raise Conflict("event_id reused for another correlation_id")
                        record = Record.model_validate_json(raw) if raw else None
                        if record is None:
                            raise Conflict("event marker exists without record")
                        return record, False
                    record = Record.model_validate_json(raw) if raw else Record(correlation_id=event.correlation_id)
                    updated, changed = apply(record, event)
                    if not changed:
                        return record, False
                    pipe.multi()
                    pipe.set(key, updated.model_dump_json(), ex=self.ttl_seconds)
                    pipe.set(marker, event.correlation_id, ex=self.ttl_seconds)
                    await pipe.execute()
                    return updated, True
                except WatchError:
                    continue
        raise RuntimeError("concurrent update retry budget exhausted")
