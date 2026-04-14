from __future__ import annotations

import asyncio
from typing import Optional

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse

from app.simulator import transactions

router = APIRouter(prefix="/api/transactions", tags=["transactions"])


@router.get("")
async def list_transactions(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    status: Optional[str] = Query(None),
):
    txn_list = list(transactions)
    if status:
        txn_list = [t for t in txn_list if t.status == status]
    page = txn_list[offset : offset + limit]
    return {
        "total": len(txn_list),
        "transactions": [t.model_dump() for t in page],
    }


@router.get("/stream")
async def sse_stream():
    """Server-Sent Events alternative to WebSocket."""

    async def event_generator():
        last_seen: Optional[str] = None
        while True:
            if transactions:
                latest = transactions[0]
                if latest.id != last_seen:
                    last_seen = latest.id
                    yield f"data: {latest.model_dump_json()}\n\n"
            await asyncio.sleep(0.5)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.get("/{txn_id}")
async def get_transaction(txn_id: str):
    for txn in transactions:
        if txn.id == txn_id:
            return txn.model_dump()
    from fastapi import HTTPException
    raise HTTPException(status_code=404, detail="Transaction not found")
