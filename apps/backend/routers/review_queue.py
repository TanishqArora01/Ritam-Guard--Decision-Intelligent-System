"""routers/review_queue.py — Analyst review queue case management."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select, and_, desc, func
from sqlalchemy.ext.asyncio import AsyncSession

from auth.rbac import get_current_user, require_analyst, require_any
from db.postgres import (
    CaseStatus, CaseVerdict, ReviewCase, User, UserRole, get_db,
)

router = APIRouter(prefix="/review-queue", tags=["Review Queue"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class CaseOut(BaseModel):
    id:              str
    txn_id:          str
    customer_id:     str
    amount:          float
    currency:        str
    channel:         str
    country_code:    str
    p_fraud:         float
    confidence:      float
    graph_risk_score:float
    anomaly_score:   float
    model_action:    str
    model_version:   str
    explanation:     dict
    status:          str
    priority:        int
    assigned_to:     Optional[str]
    verdict:         Optional[str]
    analyst_notes:   str
    created_at:      str
    updated_at:      str

    @classmethod
    def from_orm(cls, c: ReviewCase) -> "CaseOut":
        try:
            expl = json.loads(c.explanation) if isinstance(c.explanation, str) else (c.explanation or {})
        except Exception:
            expl = {}
        return cls(
            id=c.id, txn_id=c.txn_id, customer_id=c.customer_id,
            amount=c.amount, currency=c.currency or "USD",
            channel=c.channel or "", country_code=c.country_code or "",
            p_fraud=c.p_fraud or 0.0, confidence=c.confidence or 0.0,
            graph_risk_score=c.graph_risk_score or 0.0,
            anomaly_score=c.anomaly_score or 0.0,
            model_action=c.model_action or "MANUAL_REVIEW",
            model_version=c.model_version or "",
            explanation=expl,
            status=c.status.value if hasattr(c.status, "value") else str(c.status),
            priority=c.priority or 2,
            assigned_to=c.assigned_to,
            verdict=c.verdict.value if c.verdict and hasattr(c.verdict, "value") else (str(c.verdict) if c.verdict else None),
            analyst_notes=c.analyst_notes or "",
            created_at=c.created_at.isoformat() if c.created_at else "",
            updated_at=c.updated_at.isoformat() if c.updated_at else "",
        )


class AssignRequest(BaseModel):
    assigned_to: Optional[str] = None   # user_id, None = unassign


class ResolveRequest(BaseModel):
    verdict:       CaseVerdict
    analyst_notes: str = ""


class UpdatePriorityRequest(BaseModel):
    priority: int   # 1=HIGH 2=MEDIUM 3=LOW


class UpdateStatusRequest(BaseModel):
    status: CaseStatus


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("", response_model=dict)
async def list_cases(
    status_filter:   Optional[str] = Query(None, alias="status"),
    assigned_to_me:  bool          = Query(False),
    priority:        Optional[int] = Query(None),
    page:            int           = Query(1, ge=1),
    page_size:       int           = Query(20, ge=1, le=100),
    current_user:    User          = Depends(require_analyst),
    db:              AsyncSession  = Depends(get_db),
):
    """List review cases with optional filters."""
    conditions = []

    if status_filter:
        try:
            conditions.append(ReviewCase.status == CaseStatus(status_filter.upper()))
        except ValueError:
            pass
    else:
        # Default: show open + in-review
        conditions.append(ReviewCase.status.in_([CaseStatus.OPEN, CaseStatus.IN_REVIEW]))

    if assigned_to_me:
        conditions.append(ReviewCase.assigned_to == current_user.id)
    if priority:
        conditions.append(ReviewCase.priority == priority)

    # Count
    count_q = select(func.count()).select_from(ReviewCase)
    if conditions:
        count_q = count_q.where(and_(*conditions))
    total = (await db.execute(count_q)).scalar() or 0

    # Data
    data_q = select(ReviewCase).order_by(
        ReviewCase.priority.asc(), ReviewCase.created_at.desc()
    ).offset((page - 1) * page_size).limit(page_size)
    if conditions:
        data_q = data_q.where(and_(*conditions))

    rows = (await db.execute(data_q)).scalars().all()

    return {
        "items":     [CaseOut.from_orm(r) for r in rows],
        "total":     total,
        "page":      page,
        "page_size": page_size,
        "pages":     max(1, -(-total // page_size)),
        "open_count":    (await db.execute(select(func.count()).select_from(ReviewCase).where(ReviewCase.status == CaseStatus.OPEN))).scalar() or 0,
        "in_review_count":(await db.execute(select(func.count()).select_from(ReviewCase).where(ReviewCase.status == CaseStatus.IN_REVIEW))).scalar() or 0,
    }


@router.get("/{case_id}", response_model=CaseOut)
async def get_case(
    case_id:      str,
    current_user: User         = Depends(require_analyst),
    db:           AsyncSession = Depends(get_db),
):
    result = await db.execute(select(ReviewCase).where(ReviewCase.id == case_id))
    case   = result.scalar_one_or_none()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    return CaseOut.from_orm(case)


@router.patch("/{case_id}/assign", response_model=CaseOut)
async def assign_case(
    case_id:      str,
    req:          AssignRequest,
    current_user: User         = Depends(require_analyst),
    db:           AsyncSession = Depends(get_db),
):
    result = await db.execute(select(ReviewCase).where(ReviewCase.id == case_id))
    case   = result.scalar_one_or_none()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    case.assigned_to = req.assigned_to or current_user.id
    case.status      = CaseStatus.IN_REVIEW
    case.updated_at  = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(case)
    return CaseOut.from_orm(case)


@router.patch("/{case_id}/resolve", response_model=CaseOut)
async def resolve_case(
    case_id:      str,
    req:          ResolveRequest,
    current_user: User         = Depends(require_analyst),
    db:           AsyncSession = Depends(get_db),
):
    result = await db.execute(select(ReviewCase).where(ReviewCase.id == case_id))
    case   = result.scalar_one_or_none()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    case.verdict       = req.verdict
    case.analyst_notes = req.analyst_notes
    case.status        = CaseStatus.RESOLVED
    case.resolved_at   = datetime.now(timezone.utc)
    case.updated_at    = datetime.now(timezone.utc)
    if not case.assigned_to:
        case.assigned_to = current_user.id
    await db.commit()
    await db.refresh(case)
    return CaseOut.from_orm(case)


@router.patch("/{case_id}/priority", response_model=CaseOut)
async def update_priority(
    case_id:      str,
    req:          UpdatePriorityRequest,
    current_user: User         = Depends(require_analyst),
    db:           AsyncSession = Depends(get_db),
):
    result = await db.execute(select(ReviewCase).where(ReviewCase.id == case_id))
    case   = result.scalar_one_or_none()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    case.priority   = max(1, min(3, req.priority))
    case.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(case)
    return CaseOut.from_orm(case)


@router.patch("/{case_id}/status", response_model=CaseOut)
async def update_status(
    case_id:      str,
    req:          UpdateStatusRequest,
    current_user: User         = Depends(require_analyst),
    db:           AsyncSession = Depends(get_db),
):
    result = await db.execute(select(ReviewCase).where(ReviewCase.id == case_id))
    case   = result.scalar_one_or_none()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    case.status = req.status
    if req.status == CaseStatus.IN_REVIEW and not case.assigned_to:
        case.assigned_to = current_user.id
    if req.status == CaseStatus.RESOLVED and not case.resolved_at:
        case.resolved_at = datetime.now(timezone.utc)
    if req.status != CaseStatus.RESOLVED:
        case.resolved_at = None

    case.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(case)
    return CaseOut.from_orm(case)


@router.post("/sync-from-decisions")
async def sync_from_decisions(
    current_user: User         = Depends(require_analyst),
    db:           AsyncSession = Depends(get_db),
):
    """
    Pull MANUAL_REVIEW decisions from decisions.records that
    don't yet have a ReviewCase and create cases for them.
    Called periodically by the frontend or a cron job.
    """
    from sqlalchemy import text
    try:
        result = await db.execute(text("""
            SELECT txn_id, customer_id, amount, currency, p_fraud, uncertainty,
                   graph_risk_score, anomaly_score, model_version, explanation, decided_at
            FROM decisions.records
            WHERE action = 'MANUAL_REVIEW'
              AND txn_id NOT IN (SELECT txn_id FROM app.app_review_cases)
            ORDER BY decided_at DESC
            LIMIT 100
        """))
        rows = result.mappings().all()
    except Exception:
        rows = []

    created = 0
    for r in rows:
        try:
            expl = r.get("explanation", "{}")
            case = ReviewCase(
                txn_id           = r["txn_id"],
                customer_id      = r["customer_id"],
                amount           = float(r.get("amount", 0)),
                currency         = r.get("currency", "USD"),
                p_fraud          = float(r.get("p_fraud", 0)),
                confidence       = float(1 - (r.get("uncertainty") or 0)),
                graph_risk_score = float(r.get("graph_risk_score", 0)),
                anomaly_score    = float(r.get("anomaly_score", 0)),
                model_version    = r.get("model_version", ""),
                explanation      = expl if isinstance(expl, str) else json.dumps(expl),
                priority         = 1 if float(r.get("p_fraud", 0)) > 0.7 else 2,
            )
            db.add(case)
            created += 1
        except Exception:
            pass

    if created:
        await db.commit()

    return {"synced": created}
