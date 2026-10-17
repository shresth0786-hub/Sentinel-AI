# Sentinel AI API — Razorpay Fraud Guardian

**Version:** 1.0.0

> Generated from the live OpenAPI schema (`python export_openapi.py`).
> Interactive docs: `/docs` (Swagger UI) and `/redoc`.

## Tag groups

- **system** — Health, infrastructure self-report and demo fixtures.
- **auth** — Login and session identity.
- **scoring** — Payment ingestion, model summary, live investigation and evidence.
- **review-queue** — Human review queue for medium-risk (review-band) payments with explainable indicators.
- **verification** — Phone-call / OTP payment confirmation (call, SMS, WhatsApp).
- **user-database** — Persisted payer / transaction details (admin integrity: search + delete).
- **customer-care** — Customer-care support query store.
- **learning** — Continual-learning feedback and on-demand retrain.
- **senbot** — SENbot — the grounded admin assistant over the runbook + live data.
- **razorpay** — Razorpay test-mode integration: orders + webhook ingestion.

## system

### `GET /api/health`

Liveness probe.

### `GET /api/system`

Report active storage / cache / verification backends.


## auth

### `POST /api/auth/login`

Exchange username/password for a bearer token.

### `GET /api/auth/me`

Return the current session identity.

| param | in | required | description |
| --- | --- | --- | --- |
| `authorization` | header | no |  |

### `GET /api/auth/roles`

List demo accounts + role labels (drives the login page).


## scoring

### `GET /api/demo/clean`

Ready-made benign payment body for /api/investigate.

### `GET /api/demo/fraud`

Ready-made card-testing burst body for /api/investigate.

### `GET /api/events`

Recent scored payment events (filter by risk).

| param | in | required | description |
| --- | --- | --- | --- |
| `limit` | query | no |  |
| `risk` | query | no |  |

### `GET /api/events/{event_id}`

Full investigation report + evidence for one event.

| param | in | required | description |
| --- | --- | --- | --- |
| `event_id` | path | yes |  |

### `POST /api/investigate`

Score a live payment (optional velocity history) and return decision + evidence.

### `GET /api/summary`

Dataset + model summary with decision metrics.

### `GET /api/test-metrics`

Held-out evaluation metrics (precision / recall / AUC, cost).

### `GET /api/vectors`

Fraud-vector distribution across the dataset.


## review-queue

### `GET /api/review`

List the human review queue (filter by status) with risk indicators.

| param | in | required | description |
| --- | --- | --- | --- |
| `status` | query | no |  |
| `authorization` | header | no |  |

### `GET /api/review/stats`

Review-queue counts by status.

| param | in | required | description |
| --- | --- | --- | --- |
| `authorization` | header | no |  |

### `POST /api/review/{review_id}/resolve`

Resolve a queued review item (approve | block); feeds continual learning.

| param | in | required | description |
| --- | --- | --- | --- |
| `review_id` | path | yes |  |
| `authorization` | header | no |  |


## verification

### `GET /api/verification`

All phone-verification sessions (active + resolved).

### `GET /api/verification/{verification_id}`

One verification session with call script + state.

| param | in | required | description |
| --- | --- | --- | --- |
| `verification_id` | path | yes |  |

### `POST /api/verification/{verification_id}/confirm`

Confirm with the caller's OTP (correct -> approve, wrong x3 -> block).

| param | in | required | description |
| --- | --- | --- | --- |
| `verification_id` | path | yes |  |

### `POST /api/verification/{verification_id}/deny`

Caller denied ownership -> escalate to block.

| param | in | required | description |
| --- | --- | --- | --- |
| `verification_id` | path | yes |  |

### `POST /api/verification/{verification_id}/resend`

Regenerate + re-deliver the OTP.

| param | in | required | description |
| --- | --- | --- | --- |
| `verification_id` | path | yes |  |

### `POST /api/verify/event`

Score an event and return a phone-verification handle when it lands in the review band.


## user-database

### `GET /api/users`

List stored payer/transaction details (admin).

| param | in | required | description |
| --- | --- | --- | --- |
| `risk` | query | no |  |
| `authorization` | header | no |  |

### `GET /api/users/search`

Read-only search across the user database.

| param | in | required | description |
| --- | --- | --- | --- |
| `q` | query | no |  |
| `authorization` | header | no |  |

### `GET /api/users/stats`

User-database counts by decision (admin).

| param | in | required | description |
| --- | --- | --- | --- |
| `authorization` | header | no |  |

### `DELETE /api/users/{user_id}`

Admin integrity action: delete a payer + their data.

| param | in | required | description |
| --- | --- | --- | --- |
| `user_id` | path | yes |  |
| `authorization` | header | no |  |

### `GET /api/users/{user_id}`

Fetch one stored payer (admin).

| param | in | required | description |
| --- | --- | --- | --- |
| `user_id` | path | yes |  |
| `authorization` | header | no |  |


## customer-care

### `GET /api/queries`

List customer-care support queries (admin).

| param | in | required | description |
| --- | --- | --- | --- |
| `authorization` | header | no |  |

### `POST /api/queries`

Open a new customer-care query (admin).

| param | in | required | description |
| --- | --- | --- | --- |
| `authorization` | header | no |  |

### `GET /api/queries/stats`

Customer-care query counts by status (admin).

| param | in | required | description |
| --- | --- | --- | --- |
| `authorization` | header | no |  |

### `PATCH /api/queries/{query_id}`

Update a query (status / assignee / resolution) (admin).

| param | in | required | description |
| --- | --- | --- | --- |
| `query_id` | path | yes |  |
| `authorization` | header | no |  |


## learning

### `GET /api/feedback`

Continual-learning feedback store status + records (admin).

### `POST /api/feedback/{event_id}/correct`

Attach a confirmed label / manual correction to a scored event (admin).

| param | in | required | description |
| --- | --- | --- | --- |
| `event_id` | path | yes |  |

### `POST /api/learning/retrain`

Retrain the supervised models on the base data + confirmed feedback (admin).

| param | in | required | description |
| --- | --- | --- | --- |
| `seed` | query | no |  |


## senbot

### `POST /api/rag/ask`

Ask SENbot a grounded question over the runbook + live data (admin).

| param | in | required | description |
| --- | --- | --- | --- |
| `authorization` | header | no |  |

### `GET /api/rag/knowledge`

List the static runbook entries SENbot indexes (admin).

| param | in | required | description |
| --- | --- | --- | --- |
| `authorization` | header | no |  |

### `GET /api/rag/status`

SENbot index + live-source status (admin).

| param | in | required | description |
| --- | --- | --- | --- |
| `authorization` | header | no |  |


## razorpay

### `POST /api/rzp/create-order`

Create a Razorpay test-mode order.

| param | in | required | description |
| --- | --- | --- | --- |
| `amount_inr` | query | no |  |

### `GET /api/rzp/demo-payment`

Demo card-testing payload for Razorpay test mode.

### `GET /api/rzp/status`

Razorpay integration status (keys present?).

### `POST /api/rzp/webhook`

Ingest a Razorpay payment.captured / order.paid webhook and score it.


## misc

### `GET /`

 Serve Root

### `GET /{path}`

 Serve Spa

| param | in | required | description |
| --- | --- | --- | --- |
| `path` | path | yes |  |

