# Ritam-Guard — Decision Intelligent System

Real-time fraud detection platform with multi-stage ML decisioning, explainability, analyst workflow, and streaming architecture.

## Pre-Deployment Checklist

### 1) Folder structure

This repository is now organized as:

```text
apps/
  frontend/
  backend/
```

### 2) Run backend locally

```bash
cd apps/backend
uvicorn main:app --reload
```

Open:

- http://localhost:8000/docs

If `/docs` does not load locally, deployment will fail.

### 3) Backend dependencies

`requirements.txt` is present at:

- `apps/backend/requirements.txt`

If you need to regenerate:

```bash
cd apps/backend
pip freeze > requirements.txt
```

### 4) CORS

CORS middleware is enabled in backend and supports deployment configuration via `CORS_ORIGINS`.
Current default is permissive for bootstrap deployment.

## Deploy Backend on Render

### 5) Create Render service

1. Go to Render
2. New -> Web Service
3. Connect GitHub repo
4. Set root directory to `apps/backend`

### 6) Configure build/start

- Build Command: `pip install -r requirements.txt`
- Start Command: `uvicorn main:app --host 0.0.0.0 --port 10000`

### 7) Deploy

After deploy, Render will provide:

- `https://your-backend.onrender.com`

### 8) Verify

Open:

- `https://your-backend.onrender.com/docs`

If docs load, backend is live.

## Frontend Deployment (Recommended)

Deploy frontend separately (Vercel preferred):

- Root directory: `apps/frontend`
- Environment variables:
  - `NEXT_PUBLIC_API_URL=/api/backend`
  - `BACKEND_URL=https://your-backend.onrender.com`

## Quick Local Smoke Test

Backend:

```bash
cd apps/backend
uvicorn main:app --reload --port 8000
```

Frontend:

```bash
cd apps/frontend
npm install
npm run dev
```

Open:

- Frontend: http://localhost:3001
- Backend docs: http://localhost:8000/docs
