import pytest
from app.domain import Conflict, Event, Record, apply


def event(source, amount=100, event_id=None, currency="USD"):
    return Event(event_id=event_id or source, correlation_id="trade-1", source=source, amount_minor=amount, currency=currency)


def test_match_and_duplicate():
    pending, changed = apply(Record(correlation_id="trade-1"), event("expected"))
    assert changed and pending.status == "pending"
    matched, changed = apply(pending, event("actual"))
    assert changed and matched.status == "matched"
    assert apply(matched, event("actual")) == (matched, False)


@pytest.mark.parametrize("amount,currency", [(101, "USD"), (100, "EUR")])
def test_mismatch(amount, currency):
    pending, _ = apply(Record(correlation_id="trade-1"), event("expected"))
    result, _ = apply(pending, event("actual", amount=amount, currency=currency))
    assert result.status == "mismatched"


def test_conflicting_side_rejected():
    pending, _ = apply(Record(correlation_id="trade-1"), event("expected"))
    with pytest.raises(Conflict):
        apply(pending, event("expected", event_id="another"))


def test_contract_rejects_invalid_currency():
    with pytest.raises(ValueError):
        event("actual", currency="usd")
