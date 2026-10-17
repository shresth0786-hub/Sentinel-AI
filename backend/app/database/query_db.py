"""
SENTINEL AI — customer-care QUERY database
------------------------------------------
Persistence store for the queries that customers / partners raise to customer
care. Deliberately isolated from the user database and the payment datasets.

Backed by SQLAlchemy (SQLite locally, PostgreSQL in production). The ``queries``
table keeps a query a first-class support record, separate from payments and
payer identities.

Each record:
  * query_id, author (customer name/contact), category, message
  * status  : new -> in_progress -> resolved
  * created_at, updated_at, assigned_to, resolution (admin/care note)
"""

from __future__ import annotations

import time
import uuid

from sqlalchemy import func, select

from app.database.db import db_backend, get_session, init_db
from app.database.models import Query

VALID_STATUS = {"new", "in_progress", "resolved"}
VALID_CATEGORIES = {
    "payment", "refund", "account", "fraud_report", "verification", "other",
}


def _log(msg: str) -> None:
    print(f"[query_db] {msg}")


class QueryDatabase:
    def __init__(self, path: str | None = None):  # path kept for backwards-compat
        init_db()

    # ------------------------------------------------------------------ write
    def create_query(self, author: str, message: str, category: str = "other",
                     contact: str = "") -> dict:
        """Open a new support ticket in the query database."""
        category = category if category in VALID_CATEGORIES else "other"
        query_id = "qry_" + uuid.uuid4().hex[:12]
        now = time.time()
        with get_session() as s:
            rec = Query(
                query_id=query_id,
                author=(author or "unknown").strip() or "unknown",
                category=category,
                message=(message or "").strip(),
                contact=contact or "",
                status="new",
                assigned_to="",
                resolution="",
                created_at=now,
                updated_at=now,
            )
            s.add(rec)
            s.flush()
            return rec.to_dict()

    def update_query(self, query_id: str, *, status: str | None = None,
                     assigned_to: str | None = None,
                     resolution: str | None = None) -> dict | None:
        with get_session() as s:
            rec = s.get(Query, query_id)
            if rec is None:
                return None
            if status is not None:
                if status not in VALID_STATUS:
                    raise ValueError(f"invalid status: {status}")
                rec.status = status
            if assigned_to is not None:
                rec.assigned_to = assigned_to
            if resolution is not None:
                rec.resolution = resolution
            rec.updated_at = time.time()
            s.flush()
            return rec.to_dict()

    # ------------------------------------------------------------------ read
    def all(self) -> list[dict]:
        with get_session() as s:
            rows = s.execute(select(Query).order_by(Query.created_at.desc())).scalars().all()
            return [r.to_dict() for r in rows]

    def get(self, query_id: str) -> dict | None:
        with get_session() as s:
            rec = s.get(Query, query_id)
            return rec.to_dict() if rec else None

    def stats(self) -> dict:
        with get_session() as s:
            total = int(s.execute(select(func.count()).select_from(Query)).scalar() or 0)
            rows = s.execute(select(Query.status, func.count()).group_by(Query.status)).all()
        by_status = {(st or "new"): int(c) for st, c in rows}
        return {"total_queries": total, "by_status": by_status,
                "backend": db_backend()}


_db: QueryDatabase | None = None


def get_query_db() -> QueryDatabase:
    global _db
    if _db is None:
        _db = QueryDatabase()
    return _db
