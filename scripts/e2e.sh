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

publish() {
  printf '%s\n' "$1" | docker compose exec -T kafka rpk topic produce ledger.events >/dev/null
}

publish '{"event_id":"e2","correlation_id":"smoke-match","source":"actual","amount_minor":12500,"currency":"USD"}'
publish '{"event_id":"e1","correlation_id":"smoke-match","source":"expected","amount_minor":12500,"currency":"USD"}'
# Re-delivery must not alter the matched record.
publish '{"event_id":"e1","correlation_id":"smoke-match","source":"expected","amount_minor":12500,"currency":"USD"}'
publish '{"event_id":"e3","correlation_id":"smoke-mismatch","source":"expected","amount_minor":12500,"currency":"USD"}'
publish '{"event_id":"e4","correlation_id":"smoke-mismatch","source":"actual","amount_minor":12501,"currency":"USD"}'

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
