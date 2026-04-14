from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.auth import require_auth
from app.models import OverrideRequest
from app.simulator import transactions

router = APIRouter(prefix="/api/decision", tags=["decision"])


@router.get("/{txn_id}")
async def get_decision(txn_id: str):
    for txn in transactions:
        if txn.id == txn_id:
            return {
                "transaction_id": txn.id,
                "risk_score": txn.risk_score.model_dump(),
                "graph": txn.graph,
                "status": txn.status,
            }
    raise HTTPException(status_code=404, detail="Transaction not found")


@router.post("/{txn_id}/override")
async def override_decision(
    txn_id: str,
    body: OverrideRequest,
    current_user: dict = Depends(require_auth),
):
    """Analyst override – requires authentication."""
    for txn in transactions:
        if txn.id == txn_id:
            status_map = {"APPROVE": "approved", "REVIEW": "under_review", "BLOCK": "blocked"}
            new_status = status_map.get(body.decision)
            if new_status is None:
                raise HTTPException(status_code=400, detail="Invalid decision value")
            # Pydantic models are immutable by default; rebuild with updated status
            updated = txn.model_copy(update={"status": new_status})
            # Replace in deque
            idx = list(transactions).index(txn)
            txn_list = list(transactions)
            txn_list[idx] = updated
            transactions.clear()
            transactions.extendleft(reversed(txn_list))
            return {
                "transaction_id": txn_id,
                "new_status": new_status,
                "overridden_by": current_user["username"],
                "reason": body.reason,
            }
    raise HTTPException(status_code=404, detail="Transaction not found")
