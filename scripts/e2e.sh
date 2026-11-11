#!/usr/bin/env bash
set -euo pipefail

# Runs against the local Compose stack. CI starts and removes the stack.
for attempt in $(seq 1 60); do
  if docker compose exec -T kafka rpk topic list >/dev/null 2>&1; then break; fi
  if [ "$attempt" -eq 60 ]; then echo 'Kafka was not ready' >&2; exit 1; fi
  sleep 2
done
docker compose exec -T kafka rpk topic create ledger.events >/dev/null 2>&1 || true
docker compose exec -T kafka rpk topic create ledger.events.dlq >/dev/null 2>&1 || true
docker compose exec -T kafka rpk topic describe ledger.events >/dev/null
docker compose exec -T kafka rpk topic describe ledger.events.dlq >/dev/null
python - <<'PY'
from urllib.request import urlopen
with urlopen('http://localhost:5173/', timeout=10) as response:
    assert b'Ledger Bridge' in response.read()
PY

publish() {
  printf '%s\n' "$1" | docker compose exec -T kafka rpk topic produce ledger.events >/dev/null
}

publish '{"event_id":"e2","correlation_id":"smoke-match","source":"actual","amount_minor":12500,"currency":"USD"}'
publish '{"event_id":"e1","correlation_id":"smoke-match","source":"expected","amount_minor":12500,"currency":"USD"}'
# Re-delivery must not alter the matched record.
publish '{"event_id":"e1","correlation_id":"smoke-match","source":"expected","amount_minor":12500,"currency":"USD"}'
publish '{"event_id":"e3","correlation_id":"smoke-mismatch","source":"expected","amount_minor":12500,"currency":"USD"}'
publish '{"event_id":"e4","correlation_id":"smoke-mismatch","source":"actual","amount_minor":12501,"currency":"USD"}'
publish '{"event_id":"e1","correlation_id":"smoke-match","source":"expected","amount_minor":1,"currency":"USD"}'
publish '{"event_id":"invalid-amount","correlation_id":"smoke-invalid","source":"actual","amount_minor":"12500","currency":"USD"}'

python - <<'PY'
import json
import time
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

for correlation, expected_status in [('smoke-match', 'matched'), ('smoke-mismatch', 'mismatched')]:
    for attempt in range(60):
        try:
            with urlopen(f'http://localhost:8000/v1/reconciliations/{correlation}', timeout=2) as response:
                record = json.load(response)
            if record['status'] == expected_status:
                assert record['expected'] is not None and record['actual'] is not None
                print(f'{correlation}: {expected_status}')
                break
        except (HTTPError, URLError):
            pass
        time.sleep(2)
    else:
        raise SystemExit(f'{correlation} never reached {expected_status}')
PY

# Both a changed duplicate and an invalid contract must reach the dead-letter topic.
docker compose exec -T worker python - <<'PY'
import asyncio
import json
from aiokafka import AIOKafkaConsumer

async def verify():
    consumer = AIOKafkaConsumer('ledger.events.dlq', bootstrap_servers='kafka:9092',
                                auto_offset_reset='earliest', enable_auto_commit=False)
    await consumer.start()
    seen = set()
    try:
        while len(seen) < 2:
            message = await asyncio.wait_for(consumer.getone(), timeout=30)
            assert any(k == 'error' for k, _ in message.headers)
            seen.add(json.loads(message.value)['event_id'])
        assert seen == {'e1', 'invalid-amount'}, seen
        print('dead-letter events:', sorted(seen))
    finally:
        await consumer.stop()

asyncio.run(verify())
PY

python - <<'PY'
from urllib.request import urlopen
with urlopen('http://localhost:8000/metrics', timeout=5) as response:
    assert b'ledger_http_requests_total' in response.read()
PY
docker compose exec -T worker python - <<'PY'
from urllib.request import urlopen
with urlopen('http://localhost:9100/metrics', timeout=5) as response:
    assert b'ledger_events_total' in response.read()
PY

# Restart the consumer, then verify that fresh events are still processed.
docker compose restart worker >/dev/null
publish '{"event_id":"restart-e1","correlation_id":"smoke-restart","source":"expected","amount_minor":7,"currency":"USD"}'
publish '{"event_id":"restart-e2","correlation_id":"smoke-restart","source":"actual","amount_minor":7,"currency":"USD"}'
python - <<'PY'
import json
import time
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

for _ in range(60):
    try:
        with urlopen('http://localhost:8000/v1/reconciliations/smoke-restart', timeout=2) as response:
            if json.load(response)['status'] == 'matched':
                print('worker restart: matched')
                break
    except (HTTPError, URLError):
        pass
    time.sleep(2)
else:
    raise SystemExit('worker did not recover after restart')
PY

# Exercise a bounded batch through the actual broker, worker, Redis and API.
docker compose exec -T worker python - --bootstrap kafka:9092 --api http://api:8000 --pairs 30 < scripts/benchmark.py
