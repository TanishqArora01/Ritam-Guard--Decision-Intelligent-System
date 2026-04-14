from __future__ import annotations

import asyncio
import logging

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from app.auth import router as auth_router
from app.routes.transactions import router as txn_router
from app.routes.decisions import router as decision_router
from app.routes.cases import router as cases_router
from app.routes.metrics import router as metrics_router
from app.websocket.stream import manager
import app.simulator as simulator

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="RitamGuard – Fraud Detection API",
    version="1.0.0",
    description="Decision-Intelligent System for real-time fraud detection",
)

# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------
app.include_router(auth_router)
app.include_router(txn_router)
app.include_router(decision_router)
app.include_router(cases_router)
app.include_router(metrics_router)


# ---------------------------------------------------------------------------
# WebSocket endpoints
# ---------------------------------------------------------------------------
@app.websocket("/ws/transactions")
async def ws_transactions(websocket: WebSocket):
    await manager.connect("transactions", websocket)
    try:
        while True:
            # Keep connection alive; all data is pushed via broadcast
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect("transactions", websocket)


@app.websocket("/ws/metrics")
async def ws_metrics(websocket: WebSocket):
    await manager.connect("metrics", websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect("metrics", websocket)


# ---------------------------------------------------------------------------
# Startup: wire up simulator broadcast and launch background task
# ---------------------------------------------------------------------------
@app.on_event("startup")
async def startup_event():
    simulator.set_broadcast_callback(manager.broadcast)
    asyncio.create_task(simulator.run_simulator())
    logger.info("RitamGuard backend started – transaction simulator running")


@app.get("/health")
async def health():
    return {"status": "ok", "service": "ritamguard-backend"}
