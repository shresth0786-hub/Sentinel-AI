"""
REVIEW QUEUE — durable human-in-the-loop queue
----------------------------------------------
Every payment that lands in the *review* band is enqueued here with its
**explainable risk indicators** (the per-model evidence the investigator
produced) so a human analyst can audit and resolve it. The queue is persisted
(SQLite locally, PostgreSQL in production) and survives restarts.

Resolving an item feeds the continual-learning loop (approve -> clean label,
block -> fraud label), so human decisions improve future scoring.
"""

from __future__ import annotations

import time
import uuid

from sqlalchemy import func, select

from app.database.db import get_session, init_db
from app.database.models import ReviewItem

VALID_ACTIONS = {"approve", "block"}


class ReviewQueue:
    def __init__(self) -> None:
        init_db()

    # ---------------------------------------------------------------- enqueue
    def enqueue(self, event: dict, result: dict) -> dict:
        """Add a review-band payment to the queue with its risk indicators.
        Idempotent by event_id while an item is still queued."""
        event = event or {}
        result = result or {}
        event_id = str(result.get("event_id") or event.get("event_id") or "")
        if not event_id:
            return {}
        with get_session() as s:
            existing = s.execute(
                select(ReviewItem).where(
                    ReviewItem.event_id == event_id,
                    ReviewItem.status == "queued")
            ).scalars().first()
            if existing is not None:
                return existing.to_dict()

            scores = result.get("scores") or {}
            try:
                inv = float(scores.get("investigator")) if scores.get("investigator") is not None else None
            except (TypeError, ValueError):
                inv = None
            try:
                amount = float(event.get("amount_inr")) if event.get("amount_inr") is not None else None
            except (TypeError, ValueError):
                amount = None

            rec = ReviewItem(
                review_id="rev_" + uuid.uuid4().hex[:12],
                event_id=event_id,
                user_id=event.get("user_id"),
                amount_inr=amount,
                merchant=event.get("merchant"),
                investigator_score=inv,
                indicators=list(result.get("evidence") or []),
                status="queued",
                created_at=time.time(),
            )
            s.add(rec)
            s.flush()
            return rec.to_dict()

    # ------------------------------------------------------------------ read
    def all(self, status: str | None = None) -> list[dict]:
        with get_session() as s:
            stmt = select(ReviewItem).order_by(ReviewItem.created_at.desc())
            if status:
                stmt = stmt.where(ReviewItem.status == status)
            rows = s.execute(stmt).scalars().all()
            return [r.to_dict() for r in rows]

    def get(self, review_id: str) -> dict | None:
        with get_session() as s:
            rec = s.get(ReviewItem, review_id)
            return rec.to_dict() if rec else None

    # --------------------------------------------------------------- resolve
    def resolve(self, review_id: str, action: str, reviewer: str = "admin",
                resolution: str = "") -> dict | None:
        """Resolve a queued item (approve | block) and feed the label back into
        the continual-learning loop."""
        action = (action or "").lower()
        if action not in VALID_ACTIONS:
            raise ValueError(f"invalid action: {action}")
        with get_session() as s:
            rec = s.get(ReviewItem, review_id)
            if rec is None:
                return None
            if rec.status != "queued":
                return rec.to_dict()
            rec.status = "approved" if action == "approve" else "blocked"
            rec.reviewer = reviewer
            rec.resolution = resolution or action
            rec.resolved_at = time.time()
            out = rec.to_dict()
        # continual learning: human verdict is ground truth
        try:
            from app.feedback import get_controller
            label = 0 if action == "approve" else 1
            get_controller().label(str(out.get("event_id")), label, "manual",
                                   corrected=True)
        except Exception:  # pragma: no cover - learning must not break review
            pass
        return out

    def stats(self) -> dict:
        with get_session() as s:
            total = int(s.execute(
                select(func.count()).select_from(ReviewItem)).scalar() or 0)
            rows = s.execute(
                select(ReviewItem.status, func.count()).group_by(ReviewItem.status)
            ).all()
        return {"total_reviews": total,
                "by_status": {(st or "queued"): int(c) for st, c in rows}}


_queue: ReviewQueue | None = None


def get_review_queue() -> ReviewQueue:
    global _queue
    if _queue is None:
        _queue = ReviewQueue()
    return _queue
