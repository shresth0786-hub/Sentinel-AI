"""Unit tests: persistence layer (users, queries, feedback, transactions, review)."""

from __future__ import annotations

from app.database import get_user_db, get_query_db, db_backend
from app.database.events import get_transaction_store
from app.database.review import get_review_queue
from app.feedback import FeedbackStore
from app.database.verifications import verification_audit


# ------------------------------------------------------------------ users
def test_user_upsert_keeps_prior_fields():
    u = get_user_db()
    u.upsert_user("u1", {"payer_name": "Asha", "phone": "9990001111",
                         "amount_inr": 500, "merchant": "Store A",
                         "is_new_device": True},
                  outcome={"decision": "review",
                           "scores": {"investigator": 0.5},
                           "fraud_vector": "velocity", "event_id": "e1"})
    # a later event without the phone must not wipe it
    rec = u.upsert_user("u1", {"amount_inr": 700, "merchant": "Store B"})
    assert rec["name"] == "Asha"
    assert rec["phone"] == "9990001111"
    assert rec["amount_inr"] == 700
    assert rec["decision"] == "review"
    assert rec["scores"]["investigator"] == 0.5


def test_user_search_and_stats_and_delete():
    u = get_user_db()
    u.upsert_user("u2", {"payer_name": "Ravi", "phone": "888",
                         "merchant": "MegaMart"}, outcome={"decision": "block"})
    assert [r["user_id"] for r in u.search("ravi")] == ["u2"]
    assert [r["user_id"] for r in u.search("888")] == ["u2"]
    assert u.stats()["total_users"] == 1
    assert u.stats()["by_decision"].get("block") == 1
    removed = u.delete("u2")
    assert removed["user_id"] == "u2"
    assert u.get("u2") is None
    assert u.delete("u2") is None


def test_user_empty_id_is_noop():
    assert get_user_db().upsert_user("", {"amount_inr": 1}) == {}


# ------------------------------------------------------------------ queries
def test_query_lifecycle():
    q = get_query_db()
    rec = q.create_query("cust", "refund please", category="refund")
    qid = rec["query_id"]
    assert rec["status"] == "new"
    upd = q.update_query(qid, status="resolved", resolution="done")
    assert upd["status"] == "resolved"
    assert q.stats()["by_status"]["resolved"] == 1
    assert q.get(qid)["resolution"] == "done"


def test_query_invalid_category_falls_back():
    rec = get_query_db().create_query("x", "hi", category="not-a-category")
    assert rec["category"] == "other"


def test_query_invalid_status_raises():
    q = get_query_db()
    qid = q.create_query("x", "hi")["query_id"]
    try:
        q.update_query(qid, status="bogus")
        assert False, "expected ValueError"
    except ValueError:
        pass


# ------------------------------------------------------------------ feedback
def test_feedback_record_and_label():
    fs = FeedbackStore()
    fs.record("e10", {"user_id": "u"}, {"f": 1}, {"investigator": 0.7},
              "review", 0.66)
    rec = fs.get("e10")
    assert rec["label"] is None
    assert rec["p_corrected"] == 0.66
    # re-record keeps the (absent) label but refreshes scores
    fs.record("e10", {"user_id": "u"}, {"f": 2}, {"investigator": 0.8},
              "block", 0.81)
    assert fs.get("e10")["features"] == {"f": 2}
    fs.label("e10", 1, "manual", corrected=True)
    assert fs.get("e10")["label"] == 1
    st = fs.status()
    assert st["total_recorded"] == 1
    assert st["labelled"] == 1
    assert st["by_source"]["manual"] == 1
    assert st["corrected_manual"] == 1


def test_feedback_label_unknown_event_returns_none():
    assert FeedbackStore().label("does-not-exist", 0, "manual") is None


# ------------------------------------------------------------------ transactions
def test_transaction_save_and_recent():
    ts = get_transaction_store()
    ts.save({"user_id": "u5", "amount_inr": 1200, "merchant": "ShopZ",
             "card_last4": "4242", "device_id": "d1", "status": "captured"},
            {"event_id": "ev5", "decision": "review",
             "scores": {"investigator": 0.55}, "fraud_vector": "velocity"})
    ts.save({"user_id": "u6", "amount_inr": 80},
            {"event_id": "ev6", "decision": "approve",
             "scores": {"investigator": 0.02}})
    assert ts.count() == 2
    rec = ts.get("ev5")
    assert rec["user_id"] == "u5"
    assert rec["investigator_score"] == 0.55
    assert ts.stats()["by_decision"]["review"] == 1
    # upsert is idempotent by event_id
    ts.save({"user_id": "u5", "amount_inr": 1300},
            {"event_id": "ev5", "decision": "block", "scores": {}})
    assert ts.count() == 2
    assert ts.get("ev5")["decision"] == "block"


# ------------------------------------------------------------------ review queue
def test_review_enqueue_idempotent_and_resolve():
    q = get_review_queue()
    item = q.enqueue({"user_id": "u7", "amount_inr": 3000, "merchant": "CryptoX"},
                     {"event_id": "ev7", "decision": "review",
                      "scores": {"investigator": 0.62},
                      "evidence": [{"model": "ml_risk", "signal": "velocity"}]})
    assert item["status"] == "queued"
    assert len(item["indicators"]) == 1
    again = q.enqueue({"user_id": "u7"}, {"event_id": "ev7", "decision": "review"})
    assert again["review_id"] == item["review_id"]
    assert q.stats()["by_status"]["queued"] == 1
    resolved = q.resolve(item["review_id"], "block", reviewer="admin")
    assert resolved["status"] == "blocked"
    assert q.stats()["by_status"]["blocked"] == 1


def test_review_invalid_action_raises():
    q = get_review_queue()
    item = q.enqueue({"user_id": "u8"}, {"event_id": "ev8", "decision": "review"})
    try:
        q.resolve(item["review_id"], "maybe")
        assert False, "expected ValueError"
    except ValueError:
        pass


# ------------------------------------------------------------------ audit + backend
def test_verification_audit_roundtrip():
    a = verification_audit()
    a.save({"verification_id": "ver_x", "event_id": "ev", "status": "pending",
            "channel": "call", "amount_inr": 500, "call_script": ["hi"],
            "otp": "SECRET-SHOULD-NOT-PERSIST"})
    rec = a.get("ver_x")
    assert rec["status"] == "pending"
    assert rec["amount_inr"] == 500
    # the raw OTP must never be stored in the audit table
    assert "otp" not in rec


def test_db_backend_reports_sqlite():
    assert db_backend() == "sqlite"
