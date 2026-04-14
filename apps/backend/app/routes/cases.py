from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from app.models import Case, CaseCreateRequest, CaseUpdateRequest
from app.simulator import cases, transactions

router = APIRouter(prefix="/api/cases", tags=["cases"])


@router.get("")
async def list_cases(
    status: Optional[str] = Query(None),
    priority: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
):
    result = list(cases.values())
    if status:
        result = [c for c in result if c["status"] == status]
    if priority:
        result = [c for c in result if c["priority"] == priority]
    result.sort(key=lambda c: c["created_at"], reverse=True)
    return {"total": len(result), "cases": result[:limit]}


@router.get("/{case_id}")
async def get_case(case_id: str):
    case = cases.get(case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    return case


@router.post("", status_code=201)
async def create_case(body: CaseCreateRequest):
    # Verify transaction exists
    txn = next((t for t in transactions if t.id == body.transaction_id), None)
    if not txn:
        raise HTTPException(status_code=404, detail="Transaction not found")

    # Determine priority from risk score if not provided
    priority = body.priority or _auto_priority(txn.risk_score.final_score)

    case_id = f"CASE_{uuid.uuid4().hex[:8].upper()}"
    now = datetime.now(timezone.utc).isoformat()
    case = {
        "id": case_id,
        "transaction_id": body.transaction_id,
        "assigned_to": body.assigned_to,
        "status": "open",
        "priority": priority,
        "created_at": now,
        "updated_at": now,
        "notes": body.notes,
        "resolution": None,
    }
    cases[case_id] = case
    return case


@router.put("/{case_id}")
async def update_case(case_id: str, body: CaseUpdateRequest):
    case = cases.get(case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    if body.status is not None:
        case["status"] = body.status
    if body.assigned_to is not None:
        case["assigned_to"] = body.assigned_to
    if body.priority is not None:
        case["priority"] = body.priority
    if body.notes is not None:
        case["notes"] = case.get("notes", []) + body.notes
    if body.resolution is not None:
        case["resolution"] = body.resolution

    case["updated_at"] = datetime.now(timezone.utc).isoformat()
    cases[case_id] = case
    return case


def _auto_priority(score: float) -> str:
    if score >= 0.8:
        return "critical"
    if score >= 0.6:
        return "high"
    if score >= 0.4:
        return "medium"
    return "low"
