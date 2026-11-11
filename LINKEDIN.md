I built Ledger Bridge, an open-source event reconciliation service for teams whose systems report the same transaction at different times.

When an expected event and an actual event arrive out of order—or Kafka redelivers one—it should still be easy to answer: did they match, and why?

Ledger Bridge uses a Python Kafka consumer and atomic Redis state updates to pair events by correlation ID. It compares integer minor currency units, sends invalid or conflicting events to a dead-letter topic, exposes a read-only FastAPI endpoint, and includes a React + TypeScript investigation console. Docker Compose and automated Python/TypeScript tests make it straightforward to run locally.

The project is intentionally scoped to one event per side and documents its seven-day idempotency window and at-least-once delivery semantics.

Explore the code, try the quick start, and open an issue or PR with feedback: https://github.com/Karthikvk1899/ledger-bridge

#OpenSource #Kafka #FastAPI #Redis #React #TypeScript #DistributedSystems
