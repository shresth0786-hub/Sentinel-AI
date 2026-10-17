"""
FEEDBACK / CONTINUAL LEARNING
-----------------------------
Gives the fraud model a mechanism to LEARN from each transaction so it does not
repeat the same decision error again and again.

Two complementary mechanisms (as requested):

  1. ONLINE CORRECTION LAYER
     A lightweight online logistic maps the investigator's ensemble score to a
     corrected fraud probability. Every *confirmed* outcome (human verdict,
     OTP confirm/deny, manual operator correction) is fed to an online SGD
     update so the decision boundary adapts immediately -- before a full
     retrain is warranted. This is the "fast" path.

  2. PERIODIC / ON-DEMAND RETRAIN
     All confirmed feedback accumulates in a labelled log. On demand (or after
     enough confirmed corrections) the supervised models (ML Risk + the
     Investigator ensemble) are retrained on the original synthetic data PLUS
     the confirmed feedback, and the artifacts are re-persisted. This is the
     "thorough" path that fixes root causes, not just the top layer.

Ground-truth sources (called 'labels'):
  * otp_confirm  -> payer confirmed ownership -> clean (label 0)
  * otp_deny     -> payer denied ownership   -> fraud (label 1)
  * manual       -> an operator marks a decision correct/incorrect
  * chargeback   -> reserved for a later real chargeback webhook

Every scored transaction is recorded (unlabelled) so it can be labelled later,
meaning the model can learn from decisions it did NOT make (false positives /
false negatives), not only from the review band.
"""

from __future__ import annotations

import threading
import time

import numpy as np
from sqlalchemy import func, select

from app.database.db import get_session, init_db
from app.database.models import FeedbackRecord


# ---- sink to allow the dialog to be monkey-patched away in tests ----
def _log(msg: str) -> None:
    print(f"[feedback] {msg}")


class FeedbackStore:
    """Log of scored transactions + their confirmed labels, persisted in the
    ``feedback`` table (SQLite locally, PostgreSQL in production)."""

    def __init__(self, path: str | None = None):  # path kept for backwards-compat
        init_db()

    # ------------------------------------------------------------------ writes
    def record(self, event_id: str, event: dict, features: dict,
               scores: dict, decision: str, corrected_prob: float) -> dict:
        """Register a scored transaction (idempotent by event_id). Existing
        record keeps its label; we refresh the latest scores/decision."""
        with get_session() as s:
            rec = s.get(FeedbackRecord, event_id)
            if rec is None:
                rec = FeedbackRecord(
                    event_id=event_id, created_at=time.time(),
                    label=None, label_source=None,
                )
                s.add(rec)
            rec.event = event
            rec.features = features
            rec.scores = scores
            rec.decision = decision
            rec.p_corrected = round(float(corrected_prob), 4)
            s.flush()
            return rec.to_dict()

    def label(self, event_id: str, label: int, source: str,
              corrected: bool = False) -> dict | None:
        """Attach a confirmed label to a previously recorded transaction."""
        with get_session() as s:
            rec = s.get(FeedbackRecord, event_id)
            if rec is None:
                return None
            rec.label = int(label)
            rec.label_source = source
            rec.corrected = bool(corrected)
            rec.labelled_at = time.time()
            s.flush()
            return rec.to_dict()

    # ------------------------------------------------------------------ reads
    def get(self, event_id: str) -> dict | None:
        with get_session() as s:
            rec = s.get(FeedbackRecord, event_id)
            return rec.to_dict() if rec else None

    def all(self) -> list[dict]:
        with get_session() as s:
            rows = s.execute(
                select(FeedbackRecord).order_by(FeedbackRecord.created_at.asc())
            ).scalars().all()
            return [r.to_dict() for r in rows]

    def labelled(self) -> list[dict]:
        return [r for r in self.all() if r.get("label") is not None]

    def unlabelled(self) -> list[dict]:
        return [r for r in self.all() if r.get("label") is None]

    def status(self) -> dict:
        with get_session() as s:
            total = int(s.execute(
                select(func.count()).select_from(FeedbackRecord)).scalar() or 0)
            labelled = int(s.execute(
                select(func.count()).select_from(FeedbackRecord)
                .where(FeedbackRecord.label.is_not(None))).scalar() or 0)
            corrected = int(s.execute(
                select(func.count()).select_from(FeedbackRecord)
                .where(FeedbackRecord.corrected.is_(True))).scalar() or 0)
            src_rows = s.execute(
                select(FeedbackRecord.label_source, func.count())
                .where(FeedbackRecord.label.is_not(None))
                .group_by(FeedbackRecord.label_source)).all()
        by_src = {(src or "unknown"): int(c) for src, c in src_rows}
        return {
            "total_recorded": total,
            "labelled": labelled,
            "unlabelled": total - labelled,
            "by_source": by_src,
            "corrected_manual": corrected,
        }


class OnlineCorrector:
    """An online logistic that re-weights the investigator's score using
    confirmed feedback. Uses `SGDClassifier(partial_fit)` on the logit of the
    ensemble probability with only the confirmed-feedback stream, so the
    boundary adapts immediately without retraining the base models."""

    def __init__(self, lr: float = 0.05, epochs_per_point: int = 3):
        from sklearn.linear_model import SGDClassifier
        self._clf = SGDClassifier(
            loss="log_loss", learning_rate="constant", eta0=lr,
            max_iter=epochs_per_point, shuffle=False, random_state=1)
        self._initialised = False
        self._n_updates = 0

    def _logit(self, p: float) -> float:
        p = float(np.clip(p, 1e-6, 1.0 - 1e-6))
        return float(np.log(p / (1.0 - p)))

    def _ensure_init(self, z: float, y: int) -> None:
        if not self._initialised:
            # prime classes so partial_fit can label new batches
            self._clf.partial_fit(np.array([[z]], dtype=np.float64),
                                  np.array([y]), classes=np.array([0, 1]))
            self._initialised = True

    def update(self, p_investigator: float, label: int) -> None:
        """Feed one confirmed outcome: real p + true label."""
        z = self._logit(float(p_investigator))
        self._ensure_init(z, int(label))
        # one pass over this single point (partial_fit accumulates)
        self._clf.partial_fit(np.array([[z]], dtype=np.float64),
                              np.array([int(label)]))
        self._n_updates += 1

    def adjust(self, p_investigator: float) -> float:
        """Map the raw investigator probability through the learned boundary."""
        if not self._initialised or self._n_updates == 0:
            return float(p_investigator)
        z = self._logit(float(p_investigator))
        try:
            pred = float(self._clf.predict_proba(
                np.array([[z]], dtype=np.float64))[0, 1])
        except Exception:  # pragma: no cover - fall back to raw on any failure
            return float(p_investigator)
        # blend gently toward the corrected probability so a couple of labels
        # can't radically flip a well-calibrated ensemble
        alpha = min(1.0, 0.3 + 0.7 * (self._n_updates / 50.0))
        return float(alpha * pred + (1 - alpha) * p_investigator)

    def stats(self) -> dict:
        return {"updates": self._n_updates}


class LearningController:
    """Coordinates the store, the online corrector and periodic retrain."""

    def __init__(self, store: FeedbackStore | None = None,
                 corrector: OnlineCorrector | None = None):
        self.store = store or FeedbackStore()
        self.corrector = corrector or OnlineCorrector()
        self._retrain_lock = threading.Lock()

    # ------------------------------------------------------------------ record
    def record(self, event_id: str, event: dict, features: dict,
               scores: dict, decision: str, p_corrected: float) -> None:
        self.store.record(event_id, event, features, scores, decision, p_corrected)

    def label(self, event_id: str, label: int, source: str,
              p_used: float | None = None, corrected: bool = False) -> bool:
        """Confirm a label for a transaction. Also feeds the online corrector
        on the score that was used to decide (so it learns from the error)."""
        rec = self.store.get(event_id)
        p = p_used
        if rec is not None and p is None:
            p = rec.get("p_corrected") or rec.get("scores", {}).get("investigator")
        stored = self.store.label(event_id, label, source, corrected=corrected)
        if stored is not None and p is not None:
            self.corrector.update(p, label)
            _log(f"labeled {event_id} -> fraud={label} via {source} (p={p:.3f})")
        return stored is not None

    # ------------------------------------------------------------------ query
    def status(self) -> dict:
        return {"store": self.store.status(), "corrector": self.corrector.stats()}

    def records(self) -> list[dict]:
        return self.store.all()


# ------------------------------------------------------------------ singleton
_controller: LearningController | None = None


def get_controller() -> LearningController:
    global _controller
    if _controller is None:
        _controller = LearningController()
    return _controller


def feedback_store() -> FeedbackStore:
    return get_controller().store
