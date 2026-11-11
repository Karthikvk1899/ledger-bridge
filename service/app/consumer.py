import asyncio
import logging
import os
import signal

from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
from aiokafka.structs import OffsetAndMetadata
from pydantic import ValidationError
from prometheus_client import Counter, start_http_server
from redis.asyncio import Redis

from .domain import Conflict, Event
from .store import Store

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
log = logging.getLogger(__name__)
EVENTS = Counter('ledger_events_total', 'Kafka events handled', ['outcome'])


async def run() -> None:
    bootstrap = os.getenv("KAFKA_BOOTSTRAP", "localhost:9092")
    topic = os.getenv("KAFKA_TOPIC", "ledger.events")
    consumer = AIOKafkaConsumer(topic, bootstrap_servers=bootstrap, group_id="ledger-bridge-v1", enable_auto_commit=False, auto_offset_reset="earliest")
    producer = AIOKafkaProducer(bootstrap_servers=bootstrap, acks="all")
    redis = Redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/0"))
    store = Store(redis)
    if os.getenv('METRICS_PORT'):
        start_http_server(int(os.environ['METRICS_PORT']), addr='0.0.0.0')
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stop.set)
    await consumer.start()
    await producer.start()
    try:
        while not stop.is_set():
            batches = await consumer.getmany(timeout_ms=1000, max_records=100)
            for partition, messages in batches.items():
                for msg in messages:
                    try:
                        event = Event.model_validate_json(msg.value)
                        record, changed = await store.ingest(event)
                        if changed:
                            EVENTS.labels(record.status).inc()
                            log.info("reconciled correlation_id=%s status=%s", record.correlation_id, record.status)
                        else:
                            EVENTS.labels('duplicate').inc()
                    except (ValidationError, Conflict) as exc:
                        # Poison messages are durably sent before acknowledging input.
                        await producer.send_and_wait(f"{topic}.dlq", key=msg.key, value=msg.value,
                                                     headers=[("error", str(exc).encode()[:512])])
                        log.warning("sent invalid event to DLQ: %s", exc)
                        EVENTS.labels('dead_letter').inc()
                    # Any infrastructure failure propagates and leaves the offset uncommitted.
                    await consumer.commit({partition: OffsetAndMetadata(msg.offset + 1, "")})
                if stop.is_set():
                    break
    finally:
        await consumer.stop()
        await producer.stop()
        await redis.aclose()


if __name__ == "__main__":
    asyncio.run(run())
