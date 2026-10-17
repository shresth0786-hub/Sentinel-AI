"""
USER DATABASE — persisted user / transaction details
-----------------------------------------------------
Stores the **name and other details** of every user whose payment is run
through the live investigation flow (e.g. the "Live fraud check" / a payment
that lands in the review band).

Persistence is now a real database (SQLAlchemy): SQLite by default for local /
demo / tests, PostgreSQL in production via ``DATABASE_URL``. Records survive a
backend restart because they live in the ``users`` table, never on GitHub.

Each record is keyed by `user_id` and keeps the latest values of that user's
most recent investigated payment:
  * identity : user_id, name (payer_name/customer_name if supplied), phone,
               card_last4, device_id
  * context  : merchant, payment_method, amount_inr, attempt_count,
               is_new_device, status
  * outcome  : decision, model scores (ml_risk / behaviour_ai / graph_engine /
               investigator), fraud_vector, and the event_id + timestamp
"""

from __future__ import annotations

from sqlalchemy import func, select

from app.database.db import db_backend, get_session, init_db
from app.database.models import User


def _log(msg: str) -> None:
    print(f"[user_db] {msg}")


_UPSERT_FIELDS = (
    "name", "phone", "card_last4", "device_id", "merchant", "payment_method",
    "amount_inr", "attempt_count", "is_new_device", "status",
)


class UserDatabase:
    def __init__(self, path: str | None = None):  # path kept for backwards-compat
        init_db()

    # ------------------------------------------------------------------ write
    def upsert_user(self, user_id: str, event: dict, outcome: dict | None = None,
                    replace: bool = False) -> dict:
        """Persist (or refresh) a user from an investigated payment event and its
        investigation outcome. `replace=False` keeps earlier user fields that a
        later event does not set (e.g. a phone number seen only once)."""
        if not user_id:
            return {}
        event = event or {}
        with get_session() as s:
            rec = s.get(User, user_id)
            if rec is None:
                rec = User(user_id=user_id, first_seen_at=None)  # type: ignore[arg-type]
                s.add(rec)

            def _keep(attr, value):
                if value is None:
                    return
                if replace or getattr(rec, attr) in (None, "", 0) or value:
                    setattr(rec, attr, value)

            _keep("name", event.get("payer_name") or event.get("customer_name")
                           or event.get("name"))
            _keep("phone", event.get("phone") or event.get("payer_phone"))
            for attr in ("card_last4", "device_id", "merchant", "payment_method",
                         "amount_inr", "attempt_count", "is_new_device", "status"):
                if event.get(attr) is not None:
                    _keep(attr, event.get(attr))

            if outcome:
                if outcome.get("decision"):
                    rec.decision = outcome.get("decision")
                if outcome.get("scores"):
                    rec.scores = outcome.get("scores")
                if outcome.get("fraud_vector"):
                    rec.fraud_vector = outcome.get("fraud_vector")
                if outcome.get("event_id"):
                    rec.event_id = outcome.get("event_id")

            import time
            rec.updated_at = time.time()
            if not rec.first_seen_at:
                rec.first_seen_at = rec.updated_at
            s.flush()
            return rec.to_dict()

    def touch(self, user_id: str, event: dict) -> dict:
        """Record a user whose payment was investigated but keep prior values."""
        return self.upsert_user(user_id, event, None, replace=False)

    # ------------------------------------------------------------------ read
    def all(self) -> list[dict]:
        with get_session() as s:
            rows = s.execute(select(User).order_by(User.updated_at.desc())).scalars().all()
            return [r.to_dict() for r in rows]

    def get(self, user_id: str) -> dict | None:
        with get_session() as s:
            rec = s.get(User, user_id)
            return rec.to_dict() if rec else None

    def search(self, query: str) -> list[dict]:
        """Read-only search over users by phone, user id, name, card, merchant or
        device. Matching is case-insensitive substring (SQL, works on SQLite and
        PostgreSQL)."""
        q = (query or "").strip().lower()
        if not q:
            return self.all()
        like = f"%{q}%"
        cols = (User.user_id, User.name, User.phone, User.card_last4, User.merchant,
                User.device_id, User.decision, User.fraud_vector)
        with get_session() as s:
            conds = [func.lower(func.coalesce(c, "")).like(like) for c in cols]
            from sqlalchemy import or_
            rows = s.execute(
                select(User).where(or_(*conds)).order_by(User.updated_at.desc())
            ).scalars().all()
            return [r.to_dict() for r in rows]

    def delete(self, user_id: str) -> dict | None:
        """ADMIN integrity action: remove a payer permanently from the store.
        Returns the removed record (or None if it did not exist)."""
        with get_session() as s:
            rec = s.get(User, user_id)
            if rec is None:
                return None
            data = rec.to_dict()
            s.delete(rec)
            return data

    def count(self) -> int:
        with get_session() as s:
            return int(s.execute(select(func.count()).select_from(User)).scalar() or 0)

    def stats(self) -> dict:
        with get_session() as s:
            total = int(s.execute(select(func.count()).select_from(User)).scalar() or 0)
            rows = s.execute(select(User.decision, func.count()).group_by(User.decision)).all()
        decisions = {(d or "unknown"): int(c) for d, c in rows}
        return {"total_users": total, "by_decision": decisions,
                "backend": db_backend()}


_db: UserDatabase | None = None


def get_user_db() -> UserDatabase:
    global _db
    if _db is None:
        _db = UserDatabase()
    return _db
