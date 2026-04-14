"""routes/predict.py — Stage 2 REST endpoints."""
from __future__ import annotations
import logging
from typing import List
from fastapi import APIRouter, Depends, HTTPException, Request
from schemas import Stage2Request, Stage2Response

logger = logging.getLogger(__name__)
router = APIRouter()


def get_engine(request: Request):
    engine = getattr(request.app.state, "engine", None)
    if engine is None:
        raise HTTPException(status_code=503, detail="Stage 2 engine not ready")
    return engine


@router.post("/predict", response_model=Stage2Response,
             summary="Deep intelligence scoring for a single transaction")
async def predict(req: Stage2Request, engine=Depends(get_engine)) -> Stage2Response:
    try:
        return engine.score(req)
    except Exception as e:
        logger.exception("Stage 2 scoring failed for txn=%s: %s", req.txn_id, e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/predict/batch", response_model=List[Stage2Response])
async def predict_batch(reqs: List[Stage2Request], engine=Depends(get_engine)):
    if len(reqs) > 50:
        raise HTTPException(status_code=422, detail="Batch limit is 50")
    return [engine.score(r) for r in reqs]
