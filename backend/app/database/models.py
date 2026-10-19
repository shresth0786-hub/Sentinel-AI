"""
DATABASE MODELS — ORM tables for every persisted store
------------------------------------------------------
Maps the previously file-backed stores (users, queries, feedback, verification
log) and adds first-class tables for **transactions** and the **human review
queue**. Works on SQLite (local/demo/tests) and PostgreSQL (production) — JSON
columns degrade gracefully on both.
"""

from __future__ import annotations

import time

from sqlalchemy import JSON, Boolean, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database.db import Base


class User(Base):
    """A payer whose payment was investigated (formerly database/db/users.json)."""
    __tablename__ = "users"

    user_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(64), nullable=True)
    card_last4: Mapped[str | None] = mapped_column(String(8), nullable=True)
    device_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    merchant: Mapped[str | None] = mapped_column(String(256), nullable=True)
    payment_method: Mapped[str | None] = mapped_column(String(32), nullable=True)
    amount_inr: Mapped[float | None] = mapped_column(Float, nullable=True)
    attempt_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_new_device: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    decision: Mapped[str | None] = mapped_column(String(16), nullable=True)
    fraud_vector: Mapped[str | None] = mapped_column(String(64), nullable=True)
    event_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    scores: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    first_seen_at: Mapped[float] = mapped_column(Float, default=time.time)
    updated_at: Mapped[float] = mapped_column(Float, default=time.time)

    def to_dict(self) -> dict:
        return {
            "user_id": self.user_id,
            "name": self.name,
            "phone": self.phone,
            "card_last4": self.card_last4,
            "device_id": self.device_id,
            "merchant": self.merchant,
            "payment_method": self.payment_method,
            "amount_inr": self.amount_inr,
            "attempt_count": self.attempt_count,
            "is_new_device": bool(self.is_new_device) if self.is_new_device is not None else None,
            "status": self.status,
            "decision": self.decision,
            "fraud_vector": self.fraud_vector,
            "event_id": self.event_id,
            "scores": self.scores or {},
            "first_seen_at": self.first_seen_at,
            "updated_at": self.updated_at,
        }


class Query(Base):
    """A customer-care / support query (formerly database/db/queries.json)."""
    __tablename__ = "queries"

    query_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    author: Mapped[str] = mapped_column(String(256), default="unknown")
    category: Mapped[str] = mapped_column(String(32), default="other")
    message: Mapped[str] = mapped_column(Text, default="")
    contact: Mapped[str] = mapped_column(String(256), default="")
    status: Mapped[str] = mapped_column(String(32), default="new")
    assigned_to: Mapped[str] = mapped_column(String(128), default="")
    resolution: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[float] = mapped_column(Float, default=time.time)
    updated_at: Mapped[float] = mapped_column(Float, default=time.time)

    def to_dict(self) -> dict:
        return {
            "query_id": self.query_id,
            "author": self.author,
            "category": self.category,
            "message": self.message,
            "contact": self.contact,
            "status": self.status,
            "assigned_to": self.assigned_to,
            "resolution": self.resolution,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class FeedbackRecord(Base):
    """A scored transaction + optional confirmed label (continual learning)."""
    __tablename__ = "feedback"

    event_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    event: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    features: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    scores: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    decision: Mapped[str | None] = mapped_column(String(16), nullable=True)
    p_corrected: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[float] = mapped_column(Float, default=time.time)
    label: Mapped[int | None] = mapped_column(Integer, nullable=True)
    label_source: Mapped[str | None] = mapped_column(String(32), nullable=True)
    corrected: Mapped[bool] = mapped_column(Boolean, default=False)
    labelled_at: Mapped[float | None] = mapped_column(Float, nullable=True)

    def to_dict(self) -> dict:
        return {
            "event_id": self.event_id,
            "event": self.event or {},
            "features": self.features or {},
            "scores": self.scores or {},
            "decision": self.decision,
            "p_corrected": self.p_corrected,
            "created_at": self.created_at,
            "label": self.label,
            "label_source": self.label_source,
            "corrected": bool(self.corrected),
            "labelled_at": self.labelled_at,
        }


class VerificationRecord(Base):
    """Persisted verification / OTP audit record (the 'recorded call' log)."""
    __tablename__ = "verifications"

    verification_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    event_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    user_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    merchant: Mapped[str | None] = mapped_column(String(256), nullable=True)
    amount_inr: Mapped[float | None] = mapped_column(Float, nullable=True)
    phone: Mapped[str | None] = mapped_column(String(64), nullable=True)
    card_last4: Mapped[str | None] = mapped_column(String(8), nullable=True)
    channel: Mapped[str | None] = mapped_column(String(16), nullable=True)
    otp_expires_at: Mapped[float | None] = mapped_column(Float, nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3)
    status: Mapped[str | None] = mapped_column(String(16), nullable=True)
    created_at: Mapped[float] = mapped_column(Float, default=time.time)
    resolved_at: Mapped[float | None] = mapped_column(Float, nullable=True)
    final_action: Mapped[str | None] = mapped_column(String(16), nullable=True)
    reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    delivered: Mapped[str | None] = mapped_column(String(64), nullable=True)
    delivery_sid: Mapped[str | None] = mapped_column(String(128), nullable=True)
    message: Mapped[str | None] = mapped_column(String(32), nullable=True)
    recording_available: Mapped[bool] = mapped_column(Boolean, default=False)
    call_script: Mapped[list | None] = mapped_column(JSON, nullable=True)

    def to_dict(self) -> dict:
        return {
            "verification_id": self.verification_id,
            "event_id": self.event_id,
            "user_id": self.user_id,
            "merchant": self.merchant,
            "amount_inr": self.amount_inr,
            "phone": self.phone,
            "card_last4": self.card_last4,
            "channel": self.channel,
            "otp_expires_at": self.otp_expires_at,
            "attempts": self.attempts,
            "max_attempts": self.max_attempts,
            "status": self.status,
            "created_at": self.created_at,
            "resolved_at": self.resolved_at,
            "final_action": self.final_action,
            "reason": self.reason,
            "delivered": self.delivered,
            "delivery_sid": self.delivery_sid,
            "message": self.message,
            "recording_available": bool(self.recording_available),
            "call_script": self.call_script or [],
        }


class Transaction(Base):
    """A persisted scored payment/transaction (ingestion record)."""
    __tablename__ = "transactions"

    event_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    user_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    merchant: Mapped[str | None] = mapped_column(String(256), nullable=True)
    amount_inr: Mapped[float | None] = mapped_column(Float, nullable=True)
    payment_method: Mapped[str | None] = mapped_column(String(32), nullable=True)
    card_last4: Mapped[str | None] = mapped_column(String(8), nullable=True)
    device_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    decision: Mapped[str | None] = mapped_column(String(16), nullable=True)
    fraud_vector: Mapped[str | None] = mapped_column(String(64), nullable=True)
    investigator_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    scores: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    raw: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[float] = mapped_column(Float, default=time.time)

    def to_dict(self) -> dict:
        return {
            "event_id": self.event_id,
            "user_id": self.user_id,
            "merchant": self.merchant,
            "amount_inr": self.amount_inr,
            "payment_method": self.payment_method,
            "card_last4": self.card_last4,
            "device_id": self.device_id,
            "status": self.status,
            "decision": self.decision,
            "fraud_vector": self.fraud_vector,
            "investigator_score": self.investigator_score,
            "scores": self.scores or {},
            "created_at": self.created_at,
        }


class ReviewItem(Base):
    """Human review queue entry (review band) with explainable risk indicators."""
    __tablename__ = "review_queue"

    review_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    event_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    user_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    amount_inr: Mapped[float | None] = mapped_column(Float, nullable=True)
    merchant: Mapped[str | None] = mapped_column(String(256), nullable=True)
    investigator_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    indicators: Mapped[list | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="queued")  # queued|approved|blocked
    reviewer: Mapped[str | None] = mapped_column(String(128), nullable=True)
    resolution: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[float] = mapped_column(Float, default=time.time)
    resolved_at: Mapped[float | None] = mapped_column(Float, nullable=True)

    def to_dict(self) -> dict:
        return {
            "review_id": self.review_id,
            "event_id": self.event_id,
            "user_id": self.user_id,
            "amount_inr": self.amount_inr,
            "merchant": self.merchant,
            "investigator_score": self.investigator_score,
            "indicators": self.indicators or [],
            "status": self.status,
            "reviewer": self.reviewer,
            "resolution": self.resolution,
            "created_at": self.created_at,
            "resolved_at": self.resolved_at,
        }
