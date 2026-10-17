"""
TRANSACTION STORE — persisted scored payment events
---------------------------------------------------
Every payment that flows through the live investigation is persisted into the
``transactions`` table (SQLite locally, PostgreSQL in production). This gives the
dashboard, the RAG pipeline and audit an authoritative, durable event log rather
than a process-local cache.
"""

from __future__ import annotations

import time

from sqlalchemy import func, select

from app.database.db import get_session, init_db
from app.database.models import Transaction


class TransactionStore:
    def __init__(self) -> None:
        init_db()

    def save(self, event: dict, result: dict) -> dict:
        """Persist (upsert) a scored transaction from the raw event + pipeline
        result. Idempotent by event_id."""
        event = event or {}
        result = result or {}
        event_id = str(result.get("event_id") or event.get("event_id") or "")
        if not event_id:
            return {}
        scores = result.get("scores") or {}
        with get_session() as s:
            rec = s.get(Transaction, event_id)
            if rec is None:
                rec = Transaction(event_id=event_id, created_at=time.time())
                s.add(rec)
            rec.user_id = event.get("user_id")
            rec.merchant = event.get("merchant")
            try:
                rec.amount_inr = float(event.get("amount_inr")) if event.get("amount_inr") is not None else None
            except (TypeError, ValueError):
                rec.amount_inr = None
            rec.payment_method = event.get("payment_method")
            rec.card_last4 = str(event.get("card_last4")) if event.get("card_last4") is not None else None
            rec.device_id = event.get("device_id")
            rec.status = event.get("status")
            rec.decision = result.get("decision")
            rec.fraud_vector = result.get("fraud_vector")
            try:
                rec.investigator_score = float(scores.get("investigator")) if scores.get("investigator") is not None else None
            except (TypeError, ValueError):
                rec.investigator_score = None
            rec.scores = scores
            rec.raw = {k: v for k, v in event.items() if k not in ("features",)}
            s.flush()
            return rec.to_dict()

    def get(self, event_id: str) -> dict | None:
        with get_session() as s:
            rec = s.get(Transaction, event_id)
            return rec.to_dict() if rec else None

    def recent(self, limit: int = 50) -> list[dict]:
        with get_session() as s:
            rows = s.execute(
                select(Transaction).order_by(Transaction.created_at.desc()).limit(limit)
            ).scalars().all()
            return [r.to_dict() for r in rows]

    def count(self) -> int:
        with get_session() as s:
            return int(s.execute(select(func.count()).select_from(Transaction)).scalar() or 0)

    def stats(self) -> dict:
        with get_session() as s:
            total = int(s.execute(select(func.count()).select_from(Transaction)).scalar() or 0)
            rows = s.execute(select(Transaction.decision, func.count()).group_by(Transaction.decision)).all()
        return {"total_transactions": total,
                "by_decision": {(d or "unknown"): int(c) for d, c in rows}}


_store: TransactionStore | None = None


def get_transaction_store() -> TransactionStore:
    global _store
    if _store is None:
        _store = TransactionStore()
    return _store
