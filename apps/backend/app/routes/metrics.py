from __future__ import annotations

import random
import time

from fastapi import APIRouter

from app.simulator import (
    _compute_metrics,  # noqa: WPS450
    metrics_history,
    transactions,
    _transaction_count,
)

router = APIRouter(prefix="/api/metrics", tags=["metrics"])


@router.get("")
async def get_metrics():
    return _compute_metrics()


@router.get("/history")
async def get_metrics_history():
    history = list(metrics_history)
    # ensure at least a few data points so the frontend can render charts
    if len(history) < 2:
        snap = _compute_metrics()
        history = [snap] * max(2, len(history))
    return {"history": history, "count": len(history)}
