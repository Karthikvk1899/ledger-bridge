"""Measure end-to-end reconciliation on a running local Compose stack.

Run: pip install -r service/requirements.txt && python scripts/benchmark.py --pairs 100
Results describe this machine and run only; they are not a production SLA.
"""
import argparse
import asyncio
import json
import statistics
import time
import uuid
from urllib.error import HTTPError
from urllib.request import urlopen

from aiokafka import AIOKafkaProducer


async def run(pairs: int, bootstrap: str, api: str, timeout: float) -> None:
    prefix = f"bench-{uuid.uuid4().hex[:12]}"
    producer = AIOKafkaProducer(bootstrap_servers=bootstrap)
    await producer.start()
    started = time.monotonic()
    sent_at: dict[str, float] = {}
    try:
        for number in range(pairs):
            correlation = f"{prefix}-{number}"
            for source in ("expected", "actual"):
                event = {
                    "event_id": f"{correlation}-{source}",
                    "correlation_id": correlation,
                    "source": source,
                    "amount_minor": number,
                    "currency": "USD",
                }
                await producer.send_and_wait("ledger.events", json.dumps(event).encode())
            sent_at[correlation] = time.monotonic()
    finally:
        await producer.stop()

    async def check(correlation: str) -> bool:
        def request() -> bool:
            try:
                with urlopen(f"{api.rstrip('/')}/v1/reconciliations/{correlation}", timeout=3) as response:
                    return json.load(response)["status"] == "matched"
            except HTTPError as exc:
                if exc.code == 404:
                    return False
                raise
        return await asyncio.to_thread(request)

    pending = set(sent_at)
    latency = []
    deadline = time.monotonic() + timeout
    while pending and time.monotonic() < deadline:
        batch = list(pending)
        results = await asyncio.gather(*(check(item) for item in batch))
        now = time.monotonic()
        completed = {item for item, matched in zip(batch, results) if matched}
        for item in completed:
            latency.append((now - sent_at[item]) * 1000)
        pending -= completed
        if pending:
            await asyncio.sleep(0.1)
    if pending:
        raise RuntimeError(f"{len(pending)} of {pairs} pairs did not reconcile before timeout")
    elapsed = time.monotonic() - started
    sorted_latency = sorted(latency)
    print(json.dumps({
        "pairs": pairs, "duration_seconds": round(elapsed, 3),
        "pairs_per_second": round(pairs / elapsed, 2),
        "observed_latency_ms_p50": round(statistics.median(sorted_latency), 2),
        "observed_latency_ms_p95": round(sorted_latency[min(pairs - 1, int(pairs * 0.95))], 2),
    }, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--pairs", type=int, default=100)
    parser.add_argument("--bootstrap", default="localhost:19092")
    parser.add_argument("--api", default="http://localhost:8000")
    parser.add_argument("--timeout", type=float, default=60)
    args = parser.parse_args()
    if args.pairs < 1:
        parser.error("--pairs must be positive")
    asyncio.run(run(args.pairs, args.bootstrap, args.api, args.timeout))
