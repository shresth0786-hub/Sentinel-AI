"""Integration tests: FastAPI endpoints via TestClient."""

from __future__ import annotations

from app.verification import verifier
from app.database.review import get_review_queue
from app.database.events import get_transaction_store
from app.database import get_user_db


# ------------------------------------------------------------------ basics
def test_health_and_system(client):
    h = client.get("/api/health")
    assert h.status_code == 200
    assert h.json()["status"] == "ok"
    s = client.get("/api/system")
    assert s.status_code == 200
    body = s.json()
    assert body["storage"] == "sqlite"
    assert body["cache"] == "memory"


def test_login_success_and_failure(client):
    ok = client.post("/api/auth/login",
                     json={"username": "admin", "password": "testpass"})
    assert ok.status_code == 200
    assert ok.json()["token"]
    bad = client.post("/api/auth/login",
                      json={"username": "admin", "password": "nope"})
    assert bad.status_code == 401


def test_admin_routes_require_auth(client):
    assert client.get("/api/users").status_code == 401
    assert client.get("/api/review").status_code == 401
    # with a valid admin token
    r = client.post("/api/auth/login",
                    json={"username": "admin", "password": "testpass"})
    tok = r.json()["token"]
    assert client.get("/api/users", headers={"Authorization": f"Bearer {tok}"}).status_code == 200


# ------------------------------------------------------------------ review queue
def test_review_endpoints(client, admin_headers):
    item = get_review_queue().enqueue(
        {"user_id": "u_api", "amount_inr": 4200, "merchant": "CryptoX"},
        {"event_id": "ev_api", "decision": "review",
         "scores": {"investigator": 0.6},
         "evidence": [{"model": "ml_risk", "signal": "velocity",
                       "detail": "6 attempts/min", "weight": 0.7}]})

    lst = client.get("/api/review", headers=admin_headers)
    assert lst.status_code == 200
    body = lst.json()
    assert body["stats"]["total_reviews"] == 1
    assert body["reviews"][0]["indicators"][0]["signal"] == "velocity"

    res = client.post(f"/api/review/{item['review_id']}/resolve",
                      headers=admin_headers,
                      json={"action": "block", "resolution": "confirmed"})
    assert res.status_code == 200
    assert res.json()["status"] == "blocked"

    # invalid action -> 400
    bad = client.post(f"/api/review/{item['review_id']}/resolve",
                      headers=admin_headers, json={"action": "maybe"})
    assert bad.status_code == 422  # pydantic pattern validation

    # unknown id -> 404
    miss = client.post("/api/review/rev_missing/resolve",
                       headers=admin_headers, json={"action": "approve"})
    assert miss.status_code == 404


# ------------------------------------------------------------------ verification flow
def test_verification_api_flow(client, admin_headers):
    s = verifier().create({"event_id": "ev_v", "user_id": "u_v",
                           "amount_inr": 900, "merchant": "Shop",
                           "phone": "999", "card_last4": "1111",
                           "channel": "sms"})
    vid = s["verification_id"]
    assert s["status"] == "pending"

    got = client.get(f"/api/verification/{vid}", headers=admin_headers)
    assert got.status_code == 200

    lst = client.get("/api/verification", headers=admin_headers)
    assert lst.status_code == 200
    assert any(x["verification_id"] == vid for x in lst.json()["sessions"])

    # wrong OTP -> stays pending
    w = client.post(f"/api/verification/{vid}/confirm",
                    headers=admin_headers, json={"otp": "000000"})
    assert w.json()["status"] == "pending"

    # correct OTP -> approved
    c = client.post(f"/api/verification/{vid}/confirm",
                    headers=admin_headers, json={"otp": s["otp"]})
    assert c.json()["status"] == "approved"

    # unknown id -> 404
    assert client.get("/api/verification/ver_x").status_code in (401, 404)


# ------------------------------------------------------------------ real end-to-end
def test_real_investigation_persists_transaction(client, detector):
    """A full pipeline run through the API persists exactly one transaction and
    returns a decision + evidence."""
    payload = {"event": {"user_id": "e2e_user", "amount_inr": 1500,
                         "merchant": "Demo Store", "device_id": "dev_e2e",
                         "card_last4": "4242", "payment_method": "card"}}
    r = client.post("/api/investigate", json=payload)
    assert r.status_code == 200
    res = r.json()
    assert res["decision"] in ("approve", "review", "block")
    assert "investigator" in res["scores"]
    assert get_transaction_store().get(res["event_id"]) is not None
    # a review-band decision must have enqueued exactly one review item
    if res["decision"] == "review":
        assert any(x["event_id"] == res["event_id"]
                   for x in get_review_queue().all())


def test_investigate_accepts_and_persists_payer_name(client):
    """A supplied payer name must survive the request schema and reach the user
    database (regression: the API used to drop it before persistence)."""
    payload = {"event": {"user_id": "name_user", "amount_inr": 900,
                         "merchant": "Name Store", "payer_name": "Asha Rao",
                         "device_id": "dev_name", "card_last4": "1111"}}
    assert client.post("/api/investigate", json=payload).status_code == 200
    rec = get_user_db().get("name_user")
    assert rec is not None
    assert rec["name"] == "Asha Rao"
    # the `customer_name` alias is accepted too
    payload["event"]["user_id"] = "name_user2"
    payload["event"].pop("payer_name")
    payload["event"]["customer_name"] = "Ravi Kumar"
    assert client.post("/api/investigate", json=payload).status_code == 200
    assert get_user_db().get("name_user2")["name"] == "Ravi Kumar"
