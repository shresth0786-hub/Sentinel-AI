"""Unit tests: auth tokens + role gating."""

from __future__ import annotations

import time

import pytest
from fastapi import HTTPException

from app import auth


def test_token_roundtrip():
    tok = auth.create_token("admin")
    ctx = auth.verify_token(tok)
    assert ctx["username"] == "admin"
    assert ctx["role"] == "admin"


def test_token_tamper_rejected():
    tok = auth.create_token("admin")
    bad = tok[:-1] + ("0" if tok[-1] != "0" else "1")
    with pytest.raises(HTTPException) as ei:
        auth.verify_token(bad)
    assert ei.value.status_code == 401


def test_malformed_token_rejected():
    with pytest.raises(HTTPException):
        auth.verify_token("not-a-token")


def test_expired_token_rejected(monkeypatch):
    # issue a token that expires immediately
    monkeypatch.setattr(auth, "_TOKEN_TTL", -1)
    tok = auth.create_token("admin")
    # ensure clock has moved past expiry
    time.sleep(0.01)
    with pytest.raises(HTTPException) as ei:
        auth.verify_token(tok)
    assert "expired" in str(ei.value.detail)


def test_unknown_user_rejected():
    # sign a token for a user that does not exist
    tok = auth.create_token("ghost")
    with pytest.raises(HTTPException):
        auth.verify_token(tok)


def test_require_role_allows_and_denies():
    admin = {"username": "admin", "role": "admin", "name": "Demo Admin"}
    dep = auth.require_role("admin")
    assert dep(user=admin)["role"] == "admin"

    dep_ops = auth.require_role("ops")
    with pytest.raises(HTTPException) as ei:
        dep_ops(user=admin)
    assert ei.value.status_code == 403


def test_get_current_user_header_parsing():
    tok = auth.create_token("admin")
    ctx = auth.get_current_user(authorization=f"Bearer {tok}")
    assert ctx["username"] == "admin"
    with pytest.raises(HTTPException):
        auth.get_current_user(authorization="Token abc")
    with pytest.raises(HTTPException):
        auth.get_current_user(authorization=None)
