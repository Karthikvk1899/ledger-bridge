from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, Field, StrictInt


class Event(BaseModel):
    event_id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_.:-]+$")
    correlation_id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_.:-]+$")
    source: Literal["expected", "actual"]
    amount_minor: StrictInt
    currency: str = Field(pattern=r"^[A-Z]{3}$")

class Side(BaseModel):
    event_id: str
    amount_minor: int
    currency: str


class Record(BaseModel):
    correlation_id: str
    expected: Side | None = None
    actual: Side | None = None
    status: Literal["pending", "matched", "mismatched"] = "pending"


def reconcile(record: Record) -> Record:
    if record.expected and record.actual:
        record.status = (
            "matched"
            if (record.expected.amount_minor, record.expected.currency)
            == (record.actual.amount_minor, record.actual.currency)
            else "mismatched"
        )
    else:
        record.status = "pending"
    return record


def apply(record: Record, event: Event) -> tuple[Record, bool]:
    existing = getattr(record, event.source)
    if existing:
        if existing.event_id == event.event_id:
            return record, False
        raise Conflict(f"{event.source} already received for {event.correlation_id}")
    updated = record.model_copy(deep=True)
    setattr(updated, event.source, Side(event_id=event.event_id, amount_minor=event.amount_minor, currency=event.currency))
    return reconcile(updated), True


@dataclass
class Conflict(Exception):
    detail: str
