"""routes/health.py — Liveness and readiness probes."""
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from config import config

router = APIRouter()

@router.get("/health")
async def health():
    return {"status": "ok", "service": config.service_name}

@router.get("/ready")
async def ready(request: Request):
    engine = getattr(request.app.state, "engine", None)
    if engine is None:
        return JSONResponse(status_code=503, content={"ready": False})
    return {"ready": True, "graph_available": engine.graph_scorer.client.available}

@router.get("/model-info")
async def model_info(request: Request):
    engine = getattr(request.app.state, "engine", None)
    if engine is None:
        return JSONResponse(status_code=503, content={"error": "not loaded"})
    return {
        "xgb_version":    engine.xgb.model_version,
        "mlp_version":    engine.mlp.model_version,
        "ae_version":     engine.anomaly_scorer.ae.model_version,
        "iforest_version":engine.anomaly_scorer.iforest.model_version,
        "graph_available":engine.graph_scorer.client.available,
        "neo4j_uri":      config.neo4j_uri,
        "feature_count":  len(config.feature_names),
    }
