# Sentinel AI — How to Run & Understand the Program

> A practical guide for running the project and understanding how it works.

---

## Part 1 — Run the code (step by step)

### Option 0 — One file, one command (simplest)

```powershell
cd "C:\Users\SHRESTH\OneDrive\Desktop\razorpay-fraud-detector"
C:\Python313\python.exe execute.py
```

`execute.py` is a single self-contained launcher (standard library only — nothing to
install). It:

1. starts Docker Desktop if it is not already running,
2. brings up the **app + PostgreSQL + Redis** stack,
3. waits until the API is healthy,
4. opens the dashboard in your browser (<http://localhost:8100>).

Useful flags:

| Command | What it does |
|---------|--------------|
| `python execute.py` | Auto: Docker stack if available, otherwise local dev servers |
| `python execute.py --mode docker` | Force the full Docker stack |
| `python execute.py --mode local` | Force local dev (backend + Vite frontend) |
| `python execute.py --no-browser` | Do not open the browser automatically |
| `python execute.py --build` | Rebuild the Docker image before starting |
| `python execute.py --stop` | Stop the Docker stack |

### Option A — Docker (recommended: full stack = app + PostgreSQL + Redis)

```powershell
cd "C:\Users\SHRESTH\OneDrive\Desktop\razorpay-fraud-detector"
```

**Step 1 — set required secrets.** `docker-compose.yml` has no defaults and refuses to
start without these:

```powershell
$env:POSTGRES_PASSWORD      = "sentinel-db-pw-2026"
$env:SENTINEL_AUTH_SECRET   = "00000000000000000000000000000000000000000000000000000000000000ff"
$env:SENTINEL_ADMIN_PASSWORD= "SentinelAdmin!2026"
```

**Step 2 — build and start:**

```powershell
docker compose up --build -d
```

**Step 3 — open the app:** <http://localhost:8100>

**Login:** `admin` / `SentinelAdmin!2026` (whichever password you set in Step 1).

**Step 4 — stop later:**

```powershell
docker compose down        # add -v to also wipe the database volumes
```

> These env vars only live in that PowerShell window. To skip them every time, save them
> into a `.env` file next to `docker-compose.yml` and run
> `docker compose --env-file .env up -d`.

### Option B — Local dev (backend + Vite frontend, SQLite, no Docker)

Open **two** PowerShell windows.

**Window 1 — backend (API on port 8100):**

```powershell
cd "C:\Users\SHRESTH\OneDrive\Desktop\razorpay-fraud-detector\backend"
C:\Python313\python.exe -m uvicorn app.main:app --port 8100
```

Wait for `Application startup complete`.

**Window 2 — frontend (dashboard on port 5173):**

```powershell
cd "C:\Users\SHRESTH\OneDrive\Desktop\razorpay-fraud-detector\frontend\app"
npm run dev
```

**Open:** <http://localhost:5173> — login `admin` / `admin123` (the local default).

> Faster: run `.\start.ps1` from the project root to start both at once. Or in VS Code
> press **Ctrl+Shift+B** (`execute` task), which also opens the browser.

### Option C — VS Code one-click

Open the `razorpay-fraud-detector` folder in VS Code, then **Ctrl+Shift+B**
(Run Build Task) → the `execute` task starts the backend (:8100) and frontend (:5173)
and opens the app in your browser.

---

## Part 2 — Understand the program

### What it is

**Sentinel AI** is a payment-fraud detection platform (Razorpay-style). It scores a live
payment in real time and returns **approve / review / block** with the evidence behind the
decision. It is **strictly defense-only** — it only detects fraud; it cannot generate or
execute any.

### The big picture (what happens when you submit a payment)

```
payment event (JSON)
   |
   v
POST /api/investigate  ->  main.py:investigate()
   |
   +-> features.py          FeatureEngineer.build()   -> 46 engineered features
   +-> models/ml_risk       MLRiskModel               -> p_ml      (supervised)
   +-> models/behaviour_ai  BehaviourAutoencoder      -> p_behav   (anomaly)
   +-> models/graph_engine  GraphEngine               -> p_graph   (entity links)
   |
   v
pipeline.py: FraudDetector.investigate_event()
   |   combines the 3 scores -> investigator.py (Investigator) -> final probability
   |   + explains WHY (evidence, fraud_vector) and picks the decision band
   v
decision bands:  < 0.44 approve  |  0.44 - 0.80 review  |  > 0.80 block
   |
   +-> persist: database/{events,users}.py   (PostgreSQL or SQLite)
   +-> if review -> verification.py   OTP phone confirmation (Twilio or simulated)
   +-> if review -> database/review.py human review queue
```

### The ML ensemble (3 models + 1 boss)

| File | Class | Role |
|------|-------|------|
| `app/models/ml_risk.py` | `MLRiskModel` | Supervised classifier trained on labelled history |
| `app/models/behaviour_ai.py` | `BehaviourAutoencoder` | Unsupervised anomaly detector (reconstruction error) |
| `app/models/graph_engine.py` | `GraphEngine` | Graph/entity features (collusion rings, shared devices/cards) |
| `app/investigator.py` | `Investigator` | The ensemble — blends the 3 scores + rules into a final score and explanation |

- `app/data_generator.py` synthesises a realistic dataset (seed 42) with **9 fraud
  vectors**: `CARD_TESTING, VELOCITY_BURST, BOT_AUTOMATION, COLLUSION_RING,
  STOLEN_CARD, UPI_P2P, ACCOUNT_TAKEOVER, REFUND_ABUSE, MERCHANT_BIN`.
- `app/features.py` builds 46 features (velocity windows, device/card links, geography
  mismatch, typing speed, 3-DS, and more).
- `backend/train.py` trains everything and writes the model artifacts.

### The review band (the clever part)

Medium-risk payments are **not** auto-declined. They are held for **phone / SMS /
WhatsApp OTP payment confirmation** (`app/verification.py`) so a real customer can prove
they own the card. Sessions live in **Redis** (fast, expiring) and a durable audit row
goes to **PostgreSQL**. Humans can also resolve them via the review queue.

### Persistence (survives restarts)

Six tables in `app/database/models.py`: **users, queries, feedback, verifications,
transactions, review_queue**. SQLite by default; **PostgreSQL** in Docker (via
`DATABASE_URL`). **Redis** stores OTP sessions (via `REDIS_URL`).

### File map

| File | What it does |
|------|--------------|
| `backend/app/main.py` | **The entry point** — all API routes (`app.main:app`) |
| `backend/app/pipeline.py` | `FraudDetector` — ties the whole scoring pipeline together |
| `backend/app/investigator.py` | Ensemble scoring + human-readable explanation |
| `backend/app/features.py` | Feature engineering |
| `backend/app/data_generator.py` | Synthetic dataset + the 9 fraud vectors |
| `backend/app/database/*` | Stores (users, events, feedback, review queue, audit) |
| `backend/app/verification.py` | OTP phone-confirmation flow |
| `backend/app/cache.py` | Redis / in-memory session store |
| `backend/train.py` | Trains the models and writes artifacts |
| `frontend/app/src/App.jsx` | The dashboard UI |
| `execute.py` | **One-file launcher** — starts everything and opens the app |
| `execute.json` / `.vscode/tasks.json` | One-shot "run everything" task (VS Code) |
| `docker-compose.yml` | App + PostgreSQL + Redis in one command |

### Key API endpoints

Login first (`POST /api/auth/login` with `username` + `password`, **not** email) and send
the returned token as `Authorization: Bearer <token>`.

| Endpoint | Purpose |
|----------|---------|
| `POST /api/investigate` | **Score a live payment** -> decision + scores + evidence |
| `GET /api/events` | Recent payments with scores and decisions |
| `GET /api/test-metrics` | Honest held-out precision / recall / cost |
| `GET /api/users` | Everyone who has been investigated (admin) |
| `GET /api/review` + `POST /api/review/{id}/resolve` | Human review queue |
| `POST /api/learning/retrain` | Retrain on confirmed feedback |
| `GET /docs` | Interactive Swagger UI |

### Tests and honest metrics (held-out test set, seed 42)

- **46 tests pass**: `cd backend; C:\Python313\python.exe -m pytest`
- **Precision 1.000** (zero false positives — a legitimate customer is never wrongly
  blocked), **Recall 0.984** (182 / 185 fraud blocked), **F1 0.992**, **AUC 1.000**.
  The 3 misses were flagged `review`, never `approve`.
- **About Rs 304,781** of fraud prevented versus doing nothing.
- Full write-up: `TEST_METRICS.md`.

---

## Suggested order to explore

1. Run Option A and open <http://localhost:8100>.
2. In the dashboard, try **Live fraud check** and the *Borderline — phone verify* mode.
3. Then read `backend/app/pipeline.py` and `backend/app/investigator.py` to see how the
   decision is made and explained.
