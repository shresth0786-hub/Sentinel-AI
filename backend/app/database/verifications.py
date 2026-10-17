"""
VERIFICATION AUDIT STORE — durable 'recorded call' log
------------------------------------------------------
Mirrors each phone-verification session into the ``verifications`` table
(SQLite locally, PostgreSQL in production) so the call log survives restarts and
is visible to the dashboard/RAG.

Security note: the live OTP is held ONLY in the cache (Redis, TTL-scoped). This
audit store never persists the raw OTP — it keeps the transaction metadata,
state transitions and audit trail.
"""

from __future__ import annotations

from sqlalchemy import select

from app.database.db import get_session, init_db
from app.database.models import VerificationRecord

_FIELDS = (
    "event_id", "user_id", "merchant", "amount_inr", "phone", "card_last4",
    "channel", "otp_expires_at", "attempts", "max_attempts", "status",
    "created_at", "resolved_at", "final_action", "reason", "delivered",
    "delivery_sid", "message", "recording_available", "call_script",
)


class VerificationAudit:
    def __init__(self) -> None:
        init_db()

    def save(self, ver: dict) -> dict:
        vid = ver.get("verification_id")
        if not vid:
            return {}
        with get_session() as s:
            rec = s.get(VerificationRecord, vid)
            if rec is None:
                rec = VerificationRecord(verification_id=vid)
                s.add(rec)
            for f in _FIELDS:
                if f in ver:
                    setattr(rec, f, ver.get(f))
            if rec.amount_inr is not None:
                try:
                    rec.amount_inr = float(rec.amount_inr)
                except (TypeError, ValueError):
                    rec.amount_inr = None
            s.flush()
            return rec.to_dict()

    def get(self, verification_id: str) -> dict | None:
        with get_session() as s:
            rec = s.get(VerificationRecord, verification_id)
            return rec.to_dict() if rec else None

    def all(self) -> list[dict]:
        with get_session() as s:
            rows = s.execute(
                select(VerificationRecord).order_by(VerificationRecord.created_at.desc())
            ).scalars().all()
            return [r.to_dict() for r in rows]


_audit: VerificationAudit | None = None


def verification_audit() -> VerificationAudit:
    global _audit
    if _audit is None:
        _audit = VerificationAudit()
    return _audit
