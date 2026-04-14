"""
routes/health.py
Operational endpoints: health, readiness, model info.
"""
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from schemas import ModelInfoResponse
from config import config

router = APIRouter()


@router.get("/health", summary="Liveness probe")
async def health():
    return {"status": "ok", "service": config.service_name}


@router.get("/ready", summary="Readiness probe — fails if model not loaded")
async def ready(request: Request):
    predictor = getattr(request.app.state, "predictor", None)
    if predictor is None:
        return JSONResponse(status_code=503, content={"ready": False, "reason": "model not loaded"})
    return {"ready": True, "model_version": predictor.artifact.model_version}


@router.get(
    "/model-info",
    response_model=ModelInfoResponse,
    summary="Current model metadata and calibration parameters",
)
async def model_info(request: Request):
    predictor = getattr(request.app.state, "predictor", None)
    if predictor is None:
        return JSONResponse(status_code=503, content={"error": "model not loaded"})

    art = predictor.artifact
    cp  = predictor.conformal
    metrics = art.val_metrics

    return ModelInfoResponse(
        model_name      = config.mlflow_model_name,
        model_version   = art.model_version,
        model_stage     = config.mlflow_model_stage,
        n_features      = len(config.feature_names),
        feature_names   = config.feature_names,
        theta_low       = config.theta_low,
        theta_high      = config.theta_high,
        conformal_alpha = config.conformal_alpha,
        train_samples   = config.train_samples,
        val_auc         = metrics.get("val_auc"),
        val_precision   = metrics.get("val_precision"),
        val_recall      = metrics.get("val_recall"),
        loaded_at       = art.trained_at,
    )
