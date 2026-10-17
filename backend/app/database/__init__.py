# Database package (app.database)
#
# A single, configurable persistence layer built on SQLAlchemy. SQLite is the
# local/demo/test default; PostgreSQL is used in production via DATABASE_URL.
# Sub-modules:
#   db.py        -> engine / session factory / Base / init_db()
#   models.py    -> ORM tables (users, queries, feedback, verifications,
#                   transactions, review_queue)
#   user_db.py   -> user / payer store (users table); exposed to the RAG pipeline
#   query_db.py  -> customer-care query store (queries table)
#
# Re-exported here so the rest of the backend can simply do:
#   from app.database import get_user_db, get_query_db
from app.database.db import db_backend, get_session, init_db
from app.database.query_db import get_query_db
from app.database.user_db import get_user_db

__all__ = ["get_user_db", "get_query_db", "init_db", "get_session", "db_backend"]
