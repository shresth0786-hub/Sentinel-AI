"""
DATABASE — SQLAlchemy engine / session layer
--------------------------------------------
A single, configurable persistence layer used by every store (users, queries,
feedback, verification log, review queue, transactions).

* Local / demo / tests  : defaults to SQLite (no server required) so the app and
  the test-suite run anywhere out of the box.
* Production            : set ``DATABASE_URL`` to a PostgreSQL DSN, e.g.
  ``postgresql+psycopg2://sentinel:secret@db:5432/sentinel``.

Nothing here stores secrets or data inside the image — the DSN is injected at
runtime (env / secret manager) and all rows live in the database, never in the
Dockerfile.
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

# ------------------------------------------------------------------ config
# Default: a file-backed SQLite DB under backend/database/ (gitignored).
_DEFAULT_SQLITE = os.path.join(
    Path(__file__).resolve().parent.parent.parent, "database", "sentinel.db"
)
DATABASE_URL = os.environ.get("DATABASE_URL") or f"sqlite:///{_DEFAULT_SQLITE}"

_is_sqlite = DATABASE_URL.startswith("sqlite")

_engine_kwargs: dict = {"future": True, "pool_pre_ping": True}
if _is_sqlite:
    # FastAPI runs sync endpoints in a threadpool -> allow cross-thread use.
    _engine_kwargs["connect_args"] = {"check_same_thread": False}

engine = create_engine(DATABASE_URL, **_engine_kwargs)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False,
                            future=True)


class Base(DeclarativeBase):
    """Declarative base for every ORM model."""


def init_db() -> None:
    """Create all tables. Safe to call repeatedly."""
    from app.database import models  # noqa: F401  (register models on Base)
    if _is_sqlite:
        os.makedirs(os.path.dirname(_DEFAULT_SQLITE), exist_ok=True)
    Base.metadata.create_all(bind=engine)


@contextmanager
def get_session():
    """Yield a session, committing on success and always closing it."""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def db_backend() -> str:
    """Human-readable backend name for status endpoints."""
    if _is_sqlite:
        return "sqlite"
    if DATABASE_URL.startswith("postgresql"):
        return "postgresql"
    return DATABASE_URL.split(":", 1)[0]
