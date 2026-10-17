"""Unit tests: phone-call payment verification (OTP flow)."""

from __future__ import annotations

import time

import pytest

from app.verification import PhoneVerifier


def _event(**kw):
    base = {"event_id": "ev1", "user_id": "u1", "amount_inr": 2500,
            "merchant": "Store", "phone": "9990001111", "card_last4": "4242",
            "channel": "call"}
    base.update(kw)
    return base


def test_create_builds_pending_session_with_script():
    v = PhoneVerifier()
    s = v.create(_event())
    assert s["status"] == "pending"
    assert len(s["otp"]) == 6
    assert s["delivered"] == "simulated"
    assert s["channel"] == "call"
    assert isinstance(s["call_script"], list) and len(s["call_script"]) == 3


def test_correct_otp_approves():
    v = PhoneVerifier()
    s = v.create(_event())
    out = v.confirm(s["verification_id"], s["otp"])
    assert out["status"] == "approved"
    assert out["final_action"] == "approve"


def test_wrong_otp_three_times_blocks():
    v = PhoneVerifier()
    s = v.create(_event())
    vid = s["verification_id"]
    for _ in range(2):
        r = v.confirm(vid, "000000")
        assert r["status"] == "pending"
    r = v.confirm(vid, "000000")
    assert r["status"] == "blocked"
    assert r["reason"] == "too_many_failed_otp"


def test_deny_blocks():
    v = PhoneVerifier()
    s = v.create(_event())
    out = v.deny(s["verification_id"])
    assert out["status"] == "blocked"
    assert out["reason"] == "caller_denied_ownership"


def test_resend_regenerates_otp_and_resets():
    v = PhoneVerifier()
    s = v.create(_event())
    old = s["otp"]
    r = v.resend(s["verification_id"])
    assert r["status"] == "pending"
    assert r["otp"] != old
    assert v.confirm(s["verification_id"], r["otp"])["status"] == "approved"


def test_expired_otp_is_reported_expired():
    v = PhoneVerifier()
    s = v.create(_event())
    vid = s["verification_id"]
    # force the session to be past its OTP window (still within cache grace)
    live = v._cache.get(vid)
    live["otp_expires_at"] = time.time() - 1
    v._cache.set(vid, live, ttl=60)
    out = v.confirm(vid, s["otp"])
    assert out["status"] == "expired"


def test_unknown_verification_raises():
    v = PhoneVerifier()
    with pytest.raises(KeyError):
        v.confirm("ver_missing", "123456")


def test_list_and_status():
    v = PhoneVerifier()
    v.create(_event(event_id="a"))
    v.create(_event(event_id="b"))
    assert len(v.list()) == 2
    st = v.status()
    assert st["active"] == 2
    assert st["cache_backend"] == "memory"
    assert st["mode"] == "simulated"  # Twilio blanked in tests
