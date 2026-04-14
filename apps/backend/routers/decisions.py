"""routers/decisions.py — Decision stream (SSE) + audit trail search."""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select, and_, or_, desc, func, text
from sqlalchemy.ext.asyncio import AsyncSession

from auth.rbac import get_current_user, require_any
from db.postgres import User, UserRole, get_db

router = APIRouter(prefix="/decisions", tags=["Decisions"])


class DecisionRecord(BaseModel):
    txn_id:          str
    customer_id:     str
    amount:          float
    currency:        str
    action:          str
    p_fraud:         float
    confidence:      float
    graph_risk_score:float
    anomaly_score:   float
    optimal_cost:    float
    model_version:   str
    ab_variant:      str
    latency_ms:      float
    decided_at:      str
    explanation:     dict


# ---------------------------------------------------------------------------
# Audit trail — paginated search from PostgreSQL
# ---------------------------------------------------------------------------

@router.get("", response_model=dict)
async def list_decisions(
    txn_id:       Optional[str] = Query(None),
    customer_id:  Optional[str] = Query(None),
    action:       Optional[str] = Query(None),
    p_fraud_min:  Optional[float] = Query(None, ge=0, le=1),
    p_fraud_max:  Optional[float] = Query(None, ge=0, le=1),
    date_from:    Optional[str]   = Query(None, description="ISO date, e.g. 2024-01-01"),
    date_to:      Optional[str]   = Query(None),
    page:         int = Query(1, ge=1),
    page_size:    int = Query(50, ge=1, le=200),
    current_user: User = Depends(require_any),
    db:           AsyncSession = Depends(get_db),
):
    """
    Paginated audit trail search.
    BANK_PARTNER role is scoped to their org_id only (via customer_id prefix convention).
    """
    # Build raw SQL against decisions.records (already has data from decision-sink)
    conditions = ["1=1"]
    params: dict = {}

    if txn_id:
        conditions.append("txn_id ILIKE :txn_id")
        params["txn_id"] = f"%{txn_id}%"
    if customer_id:
        conditions.append("customer_id ILIKE :customer_id")
        params["customer_id"] = f"%{customer_id}%"
    if action:
        conditions.append("action = :action")
        params["action"] = action.upper()
    if p_fraud_min is not None:
        conditions.append("p_fraud >= :p_fraud_min")
        params["p_fraud_min"] = p_fraud_min
    if p_fraud_max is not None:
        conditions.append("p_fraud <= :p_fraud_max")
        params["p_fraud_max"] = p_fraud_max
    if date_from:
        conditions.append("decided_at >= :date_from")
        params["date_from"] = date_from
    if date_to:
        conditions.append("decided_at <= :date_to")
        params["date_to"] = date_to

    # BANK_PARTNER: scope to their org_id as customer prefix
    if current_user.role == UserRole.BANK_PARTNER and current_user.org_id:
        conditions.append("customer_id LIKE :org_prefix")
        params["org_prefix"] = f"{current_user.org_id}%"

    where = " AND ".join(conditions)
    offset = (page - 1) * page_size

    count_sql = text(f"SELECT COUNT(*) FROM decisions.records WHERE {where}")
    data_sql  = text(f"""
        SELECT txn_id, customer_id, amount, currency, action,
               p_fraud, uncertainty, graph_risk_score, anomaly_score,
               clv_at_decision, trust_score, expected_loss, latency_ms,
               model_version, ab_variant, decided_at, explanation
        FROM decisions.records
        WHERE {where}
        ORDER BY decided_at DESC
        LIMIT :limit OFFSET :offset
    """)

    try:
        total_row = await db.execute(count_sql, params)
        total     = total_row.scalar() or 0
        rows_res  = await db.execute(data_sql, {**params, "limit": page_size, "offset": offset})
        rows      = rows_res.mappings().all()
        items = []
        for r in rows:
            expl = r.get("explanation", "{}")
            try:
                expl = json.loads(expl) if isinstance(expl, str) else expl
            except Exception:
                expl = {}
            items.append({
                "txn_id":          r["txn_id"],
                "customer_id":     r["customer_id"],
                "amount":          float(r.get("amount", 0)),
                "currency":        r.get("currency", "USD"),
                "action":          r.get("action", ""),
                "p_fraud":         float(r.get("p_fraud", 0)),
                "confidence":      float(1 - (r.get("uncertainty") or 0)),
                "graph_risk_score":float(r.get("graph_risk_score", 0)),
                "anomaly_score":   float(r.get("anomaly_score", 0)),
                "optimal_cost":    float(r.get("expected_loss", 0)),
                "model_version":   r.get("model_version", ""),
                "ab_variant":      r.get("ab_variant", ""),
                "latency_ms":      float(r.get("latency_ms", 0)),
                "decided_at":      str(r.get("decided_at", "")),
                "explanation":     expl,
            })
    except Exception as e:
        # decisions.records may not exist yet in dev
        items, total = [], 0

    return {
        "items":     items,
        "total":     total,
        "page":      page,
        "page_size": page_size,
        "pages":     max(1, -(-total // page_size)),
    }


# ---------------------------------------------------------------------------
# SSE live feed — streams recent decisions in real-time
# ---------------------------------------------------------------------------

@router.get("/stream")
async def stream_decisions(
    current_user: User = Depends(require_any),
):
    """
    Server-Sent Events stream of recent decisions.
    Polls PostgreSQL every 2 seconds and emits new rows.
    """
    from config import config

    async def event_generator():
        last_ts = datetime.now(timezone.utc) - timedelta(seconds=10)

        yield f"data: {json.dumps({'type': 'connected', 'user': current_user.username})}\n\n"

        while True:
            try:
                async with AsyncSession(bind=None) as db:
                    pass
            except Exception:
                pass

            # Emit keepalive + poll via a fresh raw connection
            await asyncio.sleep(2)

            try:
                from db.postgres import AsyncSessionLocal
                async with AsyncSessionLocal() as db:
                    result = await db.execute(text("""
                        SELECT txn_id, customer_id, amount, currency, action,
                               p_fraud, graph_risk_score, anomaly_score,
                               latency_ms, decided_at
                        FROM decisions.records
                        WHERE decided_at > :last_ts
                        ORDER BY decided_at DESC
                        LIMIT 20
                    """), {"last_ts": last_ts})
                    rows = result.mappings().all()

                for r in reversed(list(rows)):
                    event = {
                        "type":           "decision",
                        "txn_id":         r["txn_id"],
                        "customer_id":    r["customer_id"],
                        "amount":         float(r.get("amount", 0)),
                        "currency":       r.get("currency", "USD"),
                        "action":         r.get("action", ""),
                        "p_fraud":        float(r.get("p_fraud", 0)),
                        "graph_risk":     float(r.get("graph_risk_score", 0)),
                        "anomaly":        float(r.get("anomaly_score", 0)),
                        "latency_ms":     float(r.get("latency_ms", 0)),
                        "decided_at":     str(r.get("decided_at", "")),
                    }
                    yield f"data: {json.dumps(event)}\n\n"
                    last_ts = max(last_ts,
                                  datetime.fromisoformat(str(r["decided_at"]).replace("Z", "+00:00")))

            except Exception:
                yield f"data: {json.dumps({'type': 'keepalive'})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
