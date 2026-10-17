"""
Pytest bootstrap for the Sentinel AI backend.

CRITICAL: environment is configured *before* any ``app`` module is imported, so
the storage/cache/auth singletons pick up the test configuration:

  * a throwaway SQLite database (never the demo/dev DB)
  * the in-memory session cache (no Redis required)
  * Twilio disabled -> verification runs fully in SIMULATED mode
  * a known auth secret + admin password for the API tests
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_TEST_DB = _HERE / "database" / "test_sentinel.db"

# ---- environment FIRST (before importing app.*) ----
os.environ["DATABASE_URL"] = f"sqlite:///{_TEST_DB.as_posix()}"
os.environ["REDIS_URL"] = ""                     # falsy -> in-memory cache
os.environ["SENTINEL_AUTH_SECRET"] = "test-secret-please-ignore"
os.environ["SENTINEL_ADMIN_PASSWORD"] = "testpass"
os.environ["SENTINEL_REDACT_OTP"] = "0"          # show OTP so tests can read it
# Disable real telephony even if backend/.env defines Twilio keys (setdefault
# in razorpay_client.load_dotenv() will NOT override these explicit values).
os.environ["TWILIO_ACCOUNT_SID"] = ""
os.environ["TWILIO_AUTH_TOKEN"] = ""
os.environ["TWILIO_PHONE_NUMBER"] = ""

sys.path.insert(0, str(_HERE))

import pytest  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _clean_db_file():
    """Remove any leftover test DB before and after the session."""
    _TEST_DB.parent.mkdir(parents=True, exist_ok=True)
    if _TEST_DB.exists():
        _TEST_DB.unlink()
    yield
    try:
        from app.database.db import engine
        engine.dispose()
    except Exception:  # pragma: no cover
        pass
    _TEST_DB.unlink(missing_ok=True)


@pytest.fixture(autouse=True)
def _fresh_schema():
    """Give every test a clean database (drop + recreate all tables) and a clean
    session cache (drop any cached OTP sessions)."""
    from app.database.db import Base, engine, init_db
    from app.database import models  # noqa: F401  (register models)
    Base.metadata.drop_all(bind=engine)
    init_db()
    from app.cache import get_session_cache
    get_session_cache().clear()
    yield


@pytest.fixture()
def client():
    from fastapi.testclient import TestClient
    import app.main as main
    return TestClient(main.app)


@pytest.fixture()
def admin_headers(client):
    r = client.post("/api/auth/login",
                    json={"username": "admin", "password": "testpass"})
    assert r.status_code == 200, r.text
    token = r.json()["token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="session")
def detector():
    """The real, trained detector (loaded once). Skips if artifacts are absent."""
    from app.pipeline import FraudDetector
    try:
        det = FraudDetector.load()
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"model artifacts unavailable: {exc}")
    # reuse the same instance in the API so artifacts load only once
    import app.main as main
    main._detector = det
    return det
