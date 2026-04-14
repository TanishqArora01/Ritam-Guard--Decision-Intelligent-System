"""
routes/predict.py
FastAPI prediction endpoint.

POST /predict
  → synchronous inference path (REST)
  → returns PredictResponse immediately
  → target latency: <10ms for early exits, <20ms for Stage 2 pass-through

POST /predict/batch
  → batch inference (up to 100 transactions per call)
"""
from __future__ import annotations

import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from schemas import PredictRequest, PredictResponse

logger = logging.getLogger(__name__)
router = APIRouter()


def get_predictor(request: Request):
    """Dependency: retrieve the shared predictor from app state."""
    predictor = getattr(request.app.state, "predictor", None)
    if predictor is None:
        raise HTTPException(status_code=503, detail="Model not loaded")
    return predictor


@router.post(
    "/predict",
    response_model=PredictResponse,
    summary="Score a single enriched transaction",
    description=(
        "Accepts a FeatureVector (18 computed features + transaction metadata). "
        "Returns P(fraud), uncertainty, conformal prediction set, and routing decision. "
        "Early exits (low risk) resolve in <10ms without touching Stage 2."
    ),
)
async def predict(
    req:       PredictRequest,
    predictor = Depends(get_predictor),
) -> PredictResponse:
    try:
        return predictor.predict(req)
    except Exception as e:
        logger.exception("Prediction failed for txn=%s: %s", req.txn_id, e)
        raise HTTPException(status_code=500, detail=f"Inference error: {e}")


@router.post(
    "/predict/batch",
    response_model=List[PredictResponse],
    summary="Score a batch of transactions",
)
async def predict_batch(
    reqs:      List[PredictRequest],
    predictor = Depends(get_predictor),
) -> List[PredictResponse]:
    if len(reqs) > 100:
        raise HTTPException(
            status_code=422,
            detail="Batch size exceeds limit of 100 transactions per call",
        )
    results = []
    for req in reqs:
        try:
            results.append(predictor.predict(req))
        except Exception as e:
            logger.warning("Batch item failed txn=%s: %s", req.txn_id, e)
    return results
