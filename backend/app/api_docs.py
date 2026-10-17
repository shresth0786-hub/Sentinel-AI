"""
CURATED API DOCUMENTATION
-------------------------
Adds production-grade, human-curated OpenAPI metadata to the FastAPI app so the
interactive docs (/docs, /redoc) are grouped, described and searchable, and so an
exported spec (see ``export_openapi.py``) reads like real API reference docs.

We enrich the schema centrally (by path prefix) instead of tagging every route
by hand, which keeps endpoint code clean and the docs consistent.
"""

from __future__ import annotations

from fastapi.openapi.utils import get_openapi

TITLE = "Sentinel AI API — Razorpay Fraud Guardian"
VERSION = "1.0.0"

DESCRIPTION = """
**Sentinel AI** is a production-grade, defense-only payment-fraud detection and
explainability platform for Razorpay-scale payments.

It turns each payment into a decision through a three-model ensemble plus an
investigator, and never auto-approves a suspicious payment — it escalates to a
human review queue and a phone/OTP verification instead.

### Pipeline
`payment event -> feature engineering -> ML Risk + Behaviour AI + Graph Engine`
`-> Investigator ensemble -> decision (approve | review | block) + evidence`

### Persistence & infrastructure
* **Storage** — SQLAlchemy. SQLite for local/demo, **PostgreSQL** in production
  (`DATABASE_URL`): users, queries, feedback, transactions, verifications,
  review queue.
* **Cache** — OTP/verification sessions live in **Redis** (`REDIS_URL`) with a
  TTL so secrets expire on their own; falls back to an in-memory store locally.
* **Human review queue** — review-band payments are enqueued with explainable
  risk indicators and resolved by an analyst (feeds continual learning).
* **Phone verification** — OTP over call / SMS / WhatsApp (Twilio optional);
  simulated fully offline otherwise.

### Auth
Bearer token from `POST /api/auth/login`. Admin-only routes are marked
`Authorization: Bearer <token>`; a single **admin** role exists.
"""

# OpenAPI tag groups shown in the docs sidebar (order matters).
TAGS = [
    {"name": "system", "description": "Health, infrastructure self-report and demo fixtures."},
    {"name": "auth", "description": "Login and session identity."},
    {"name": "scoring", "description": "Payment ingestion, model summary, live investigation and evidence."},
    {"name": "review-queue", "description": "Human review queue for medium-risk (review-band) payments with explainable indicators."},
    {"name": "verification", "description": "Phone-call / OTP payment confirmation (call, SMS, WhatsApp)."},
    {"name": "user-database", "description": "Persisted payer / transaction details (admin integrity: search + delete)."},
    {"name": "customer-care", "description": "Customer-care support query store."},
    {"name": "learning", "description": "Continual-learning feedback and on-demand retrain."},
    {"name": "senbot", "description": "SENbot — the grounded admin assistant over the runbook + live data."},
    {"name": "razorpay", "description": "Razorpay test-mode integration: orders + webhook ingestion."},
]

_PREFIX_TAGS = [
    ("/api/auth", "auth"),
    ("/api/health", "system"),
    ("/api/system", "system"),
    ("/api/demo", "scoring"),
    ("/api/users", "user-database"),
    ("/api/queries", "customer-care"),
    ("/api/verification", "verification"),
    ("/api/verify", "verification"),
    ("/api/review", "review-queue"),
    ("/api/feedback", "learning"),
    ("/api/learning", "learning"),
    ("/api/rag", "senbot"),
    ("/api/senbot", "senbot"),
    ("/api/summary", "scoring"),
    ("/api/events", "scoring"),
    ("/api/vectors", "scoring"),
    ("/api/test-metrics", "scoring"),
    ("/api/investigate", "scoring"),
    ("/api/rzp", "razorpay"),
]

# (METHOD, path) -> short curated summary.
_SUMMARIES = {
    ("GET", "/api/health"): "Liveness probe.",
    ("GET", "/api/system"): "Report active storage / cache / verification backends.",
    ("GET", "/api/auth/roles"): "List demo accounts + role labels (drives the login page).",
    ("POST", "/api/auth/login"): "Exchange username/password for a bearer token.",
    ("GET", "/api/auth/me"): "Return the current session identity.",
    ("GET", "/api/summary"): "Dataset + model summary with decision metrics.",
    ("GET", "/api/test-metrics"): "Held-out evaluation metrics (precision / recall / AUC, cost).",
    ("GET", "/api/events"): "Recent scored payment events (filter by risk).",
    ("GET", "/api/events/{event_id}"): "Full investigation report + evidence for one event.",
    ("GET", "/api/vectors"): "Fraud-vector distribution across the dataset.",
    ("POST", "/api/investigate"): "Score a live payment (optional velocity history) and return decision + evidence.",
    ("GET", "/api/demo/fraud"): "Ready-made card-testing burst body for /api/investigate.",
    ("GET", "/api/demo/clean"): "Ready-made benign payment body for /api/investigate.",
    ("GET", "/api/review"): "List the human review queue (filter by status) with risk indicators.",
    ("GET", "/api/review/stats"): "Review-queue counts by status.",
    ("POST", "/api/review/{review_id}/resolve"): "Resolve a queued review item (approve | block); feeds continual learning.",
    ("GET", "/api/verification"): "All phone-verification sessions (active + resolved).",
    ("GET", "/api/verification/{verification_id}"): "One verification session with call script + state.",
    ("POST", "/api/verification/{verification_id}/confirm"): "Confirm with the caller's OTP (correct -> approve, wrong x3 -> block).",
    ("POST", "/api/verification/{verification_id}/deny"): "Caller denied ownership -> escalate to block.",
    ("POST", "/api/verification/{verification_id}/resend"): "Regenerate + re-deliver the OTP.",
    ("POST", "/api/verify/event"): "Score an event and return a phone-verification handle when it lands in the review band.",
    ("GET", "/api/users"): "List stored payer/transaction details (admin).",
    ("GET", "/api/users/stats"): "User-database counts by decision (admin).",
    ("GET", "/api/users/search"): "Read-only search across the user database.",
    ("GET", "/api/users/{user_id}"): "Fetch one stored payer (admin).",
    ("DELETE", "/api/users/{user_id}"): "Admin integrity action: delete a payer + their data.",
    ("GET", "/api/queries"): "List customer-care support queries (admin).",
    ("GET", "/api/queries/stats"): "Customer-care query counts by status (admin).",
    ("POST", "/api/queries"): "Open a new customer-care query (admin).",
    ("PATCH", "/api/queries/{query_id}"): "Update a query (status / assignee / resolution) (admin).",
    ("GET", "/api/feedback"): "Continual-learning feedback store status + records (admin).",
    ("POST", "/api/feedback/{event_id}/correct"): "Attach a confirmed label / manual correction to a scored event (admin).",
    ("POST", "/api/learning/retrain"): "Retrain the supervised models on the base data + confirmed feedback (admin).",
    ("POST", "/api/rag/ask"): "Ask SENbot a grounded question over the runbook + live data (admin).",
    ("GET", "/api/rag/status"): "SENbot index + live-source status (admin).",
    ("GET", "/api/rag/knowledge"): "List the static runbook entries SENbot indexes (admin).",
    ("GET", "/api/rzp/status"): "Razorpay integration status (keys present?).",
    ("POST", "/api/rzp/create-order"): "Create a Razorpay test-mode order.",
    ("POST", "/api/rzp/webhook"): "Ingest a Razorpay payment.captured / order.paid webhook and score it.",
    ("GET", "/api/rzp/demo-payment"): "Demo card-testing payload for Razorpay test mode.",
}


def _tag_for(path: str) -> str:
    for prefix, tag in _PREFIX_TAGS:
        if path.startswith(prefix):
            return tag
    return "misc"


def install(app) -> None:
    """Replace ``app.openapi`` with a curated-schema generator."""

    def custom_openapi():
        if app.openapi_schema:
            return app.openapi_schema
        schema = get_openapi(
            title=TITLE,
            version=VERSION,
            description=DESCRIPTION,
            routes=app.routes,
            tags=TAGS,
        )
        for path, ops in schema.get("paths", {}).items():
            tag = _tag_for(path)
            for method, op in ops.items():
                op["tags"] = [tag]
                s = _SUMMARIES.get((method.upper(), path))
                if s:
                    op["summary"] = s
        schema.setdefault("info", {})
        schema["info"]["contact"] = {
            "name": "Sentinel AI — Razorpay AI Buildathon (Track 02)",
            "url": "https://github.com/shresth0786-hub/Sentinel-AI",
        }
        schema["info"]["license"] = {"name": "MIT"}
        schema["servers"] = [{"url": "/", "description": "current server"}]
        app.openapi_schema = schema
        return schema

    app.openapi = custom_openapi
