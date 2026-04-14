# RitamGuard — Decision-Intelligent Fraud Detection System

> **Enterprise-grade, real-time fraud detection platform** powered by a multi-stage ML pipeline, WebSocket live feeds, D3.js visualisations, and an analyst case-management workflow.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│                     Monorepo Layout                      │
│                                                         │
│  apps/                                                  │
│    backend/      FastAPI · JWT auth · WebSocket         │
│    frontend/     Next.js 14 · Zustand · D3.js           │
│                                                         │
│  services/                                              │
│    stream-simulator/   Standalone transaction generator │
│    scoring-engine/     Standalone ML microservice       │
│                                                         │
│  infra/                                                 │
│    docker-compose.yml  Full-stack orchestration         │
└─────────────────────────────────────────────────────────┘
```

### Decision Pipeline (3-stage)

```
Transaction ──► Stage 1: Rule Engine ──► Stage 2: Behavioral ML ──► Ensemble Decision
                  (velocity, IP                (user baseline,          APPROVE / REVIEW / BLOCK
                   blacklist, amounts)          geo-anomaly, device)     + SHAP-like explanations
```

---

## Quick Start

### Option A — Docker Compose (recommended)

```bash
cd infra
docker compose up --build
```

| Service | URL |
|---------|-----|
| Frontend | http://localhost:3000 |
| Backend API | http://localhost:8000 |
| API Docs | http://localhost:8000/docs |
| Scoring Engine | http://localhost:8002 |

### Option B — Local development

#### Backend

```bash
cd apps/backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

#### Frontend

```bash
cd apps/frontend
cp .env.local.example .env.local   # adjust URLs if needed
npm install
npm run dev
```

Open http://localhost:3000.

#### Services (optional standalone)

```bash
# Stream simulator
cd services/stream-simulator
pip install -r requirements.txt
python simulator.py --mode server --port 8001

# Scoring engine
cd services/scoring-engine
pip install -r requirements.txt
python scorer.py --port 8002
```

---

## Authentication

| Username | Password | Role |
|----------|----------|------|
| `analyst` | `analyst123` | analyst |
| `admin` | `admin123` | admin |

All read endpoints are public. Decision overrides require a valid JWT (obtained via `POST /api/auth/token`).

---

## API Reference

### Transactions
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/transactions` | List recent transactions (`limit`, `offset`, `status`) |
| GET | `/api/transactions/{id}` | Single transaction detail |
| GET | `/api/transactions/stream` | SSE live feed |

### Decisions
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/decision/{id}` | Full decision with graph data |
| POST | `/api/decision/{id}/override` | Analyst override (**auth required**) |

### Cases
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/cases` | List cases (filter by status, priority) |
| POST | `/api/cases` | Create case from transaction |
| PUT | `/api/cases/{id}` | Update case (notes, status, resolution) |

### Metrics
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/metrics` | Current snapshot |
| GET | `/api/metrics/history` | Last 60 snapshots (time-series) |

### WebSocket
| Channel | URL | Description |
|---------|-----|-------------|
| Transactions | `ws://localhost:8000/ws/transactions` | New transaction per message |
| Metrics | `ws://localhost:8000/ws/metrics` | Metrics snapshot every ~10 txns |

---

## Frontend Pages

| Route | Description |
|-------|-------------|
| `/` | Dashboard — metrics cards + live stream + decision flow |
| `/transactions` | Sortable table + decision flow + explainability + graph |
| `/cases` | Analyst case management (kanban-style cards) |
| `/models` | ML pipeline overview + feature importance + score history |

---

## Key Components

| Component | Description |
|-----------|-------------|
| `MetricsDashboard` | 4 metric cards with D3 sparklines, auto-refreshes every 2 s |
| `TransactionStream` | Live WebSocket feed with animated rows, green pulsing dot |
| `DecisionFlow` | 3-stage pipeline visualisation with score bars |
| `ExplainabilityPanel` | SHAP-like D3 bar chart of feature contributions |
| `GraphViewer` | D3 force-directed entity graph (user/device/IP/merchant) |
| `TransactionTable` | Filterable, sortable table with status badges |
| `Sidebar` | Navigation with active state + WebSocket health indicator |

---

## Environment Variables

### Backend
| Variable | Default | Description |
|----------|---------|-------------|
| `JWT_SECRET` | `ritamguard-secret-key-change-in-prod` | JWT signing secret |

### Frontend (`.env.local`)
| Variable | Default | Description |
|----------|---------|-------------|
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000` | Backend REST URL |
| `NEXT_PUBLIC_WS_URL` | `ws://localhost:8000` | Backend WebSocket URL |

---

## Project Structure

```
apps/
  backend/
    main.py                   # FastAPI app entry point
    requirements.txt
    Dockerfile
    app/
      auth.py                 # JWT auth + /api/auth/token
      models.py               # Pydantic models
      simulator.py            # Background transaction generator
      scoring.py              # 3-stage ML scoring pipeline
      graph.py                # Entity graph generator
      routes/
        transactions.py
        decisions.py
        cases.py
        metrics.py
      websocket/
        stream.py             # WS connection manager

  frontend/
    src/
      app/                    # Next.js App Router pages
        layout.tsx
        page.tsx              # Dashboard
        transactions/page.tsx
        cases/page.tsx
        models/page.tsx
      components/             # React components
      lib/
        api.ts                # Typed API client
        websocket.ts          # Auto-reconnect WS client
      store/
        transactionStore.ts   # Zustand store
        metricsStore.ts
      types/index.ts          # TypeScript interfaces

services/
  stream-simulator/
    simulator.py              # Standalone generator (poster or server mode)
  scoring-engine/
    scorer.py                 # Standalone scoring microservice

infra/
  docker-compose.yml
```

---

## Fraud Patterns Simulated

- **Velocity attacks** — many small transactions in quick succession
- **Card testing** — tiny amounts (< $1) to verify card validity
- **Large suspicious transfers** — amounts > $9,500 near reporting thresholds
- **Blacklisted IPs** — known bad actor IP addresses
- **High-risk merchants** — crypto exchanges, gambling, wire transfers
- **Geo anomalies** — transactions from unusual locations for a user
- **Shared-device fraud** — multiple user accounts sharing one device

---

## Development Notes

- The backend stores the last **1,000 transactions** in a `collections.deque` (in-memory).
- All routes work **without authentication** for ease of development; auth is enforced only on decision overrides.
- The scoring pipeline runs **synchronously inside an async endpoint** — each score takes < 1 ms.
- WebSocket auto-reconnect uses **exponential backoff** (max 30 s).

---

## License

MIT
Real-time Fraud Detection Decision Intelligence System with multi-stage ML, streaming architecture, graph intelligence, and explainable risk-based decisioning.
