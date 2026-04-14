"""
api-gateway/main.py
API Gateway — Single Entry Point for the Fraud Detection System

This is the ONLY service that external callers talk to.
It orchestrates the full 3-stage pipeline synchronously:

  POST /transaction
       ↓
  [Stage 1] LightGBM → P(fraud) + uncertainty
       │
       ├─ p < θ_low AND low uncertainty
       │    └─ EARLY EXIT → APPROVE  (<10ms)
       │
       └─ else → [Stage 2] XGBoost + MLP + Neo4j + Anomaly
                      └─ [Stage 3] argmin(cost) → final decision
                             └─ Response + publish to Kafka

Also exposes:
  POST /transaction/batch   — up to 100 transactions
  GET  /health              — liveness probe
  GET  /ready               — readiness (all upstream services healthy)
  GET  /stats               — real-time throughput and latency stats
  GET  /docs                — Swagger UI (auto-generated)
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx
import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from prometheus_client import Counter, Histogram, Gauge, start_http_server, make_asgi_app
from pydantic import BaseModel, Field

logging.basicConfig(
    level=getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO),
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger("api-gateway")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
STAGE1_URL   = os.getenv("STAGE1_URL",   "http://stage1-service:8100")
STAGE2_URL   = os.getenv("STAGE2_URL",   "http://stage2-service:8200")
STAGE3_URL   = os.getenv("STAGE3_URL",   "http://stage3-service:8300")
KAFKA_ENABLED = os.getenv("KAFKA_ENABLED", "true").lower() == "true"
KAFKA_BROKERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "redpanda:9092")
TIMEOUT_S1   = float(os.getenv("TIMEOUT_STAGE1",  "0.012"))  # 12ms budget
TIMEOUT_S2   = float(os.getenv("TIMEOUT_STAGE2",  "0.120"))  # 120ms budget
TIMEOUT_S3   = float(os.getenv("TIMEOUT_STAGE3",  "0.030"))  # 30ms budget
METRICS_PORT = int(os.getenv("METRICS_PORT", "9106"))

# ---------------------------------------------------------------------------
# Prometheus metrics
# ---------------------------------------------------------------------------
TXN_TOTAL     = Counter("gateway_txn",         "Total transactions received")
TXN_EARLY_EXIT= Counter("gateway_early_exit",   "Early exit approvals")
TXN_ERRORS    = Counter("gateway_errors",      "Gateway errors", ["stage"])
E2E_LATENCY   = Histogram("gateway_e2e_latency_ms", "End-to-end latency (ms)",
                           buckets=[5,10,20,50,100,200,500,1000])
STAGE_LATENCY = Histogram("gateway_stage_latency_ms", "Per-stage latency (ms)",
                           ["stage"], buckets=[1,2,5,10,20,50,100,200])
INFLIGHT      = Gauge("gateway_inflight_requests", "In-flight requests")

# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------

class TransactionRequest(BaseModel):
    """Raw transaction submitted by the bank / card network."""
    txn_id:          str
    customer_id:     str
    amount:          float = Field(gt=0)
    currency:        str   = "USD"
    channel:         str   = ""
    merchant_id:     str   = ""
    merchant_category: str = ""
    device_id:       str   = ""
    ip_address:      str   = ""
    is_new_device:   bool  = False
    is_new_ip:       bool  = False
    country_code:    str   = ""
    city:            str   = ""
    lat:             float = 0.0
    lng:             float = 0.0
    txn_ts:          str   = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    # Customer profile (provided by core banking)
    clv:             float = 0.0
    trust_score:     float = 0.5
    account_age_days:int   = 0
    customer_segment:str   = "standard"
    # Pre-computed features (from feature engine, optional)
    features:        Optional[Dict[str, float]] = None
    # Ground truth for evaluation (omit in production)
    is_fraud:        Optional[bool] = None
    fraud_pattern:   Optional[str]  = None


class DecisionResponse(BaseModel):
    """Final decision returned to the caller."""
    txn_id:          str
    customer_id:     str
    amount:          float
    currency:        str

    # THE DECISION
    action:          str    # APPROVE | BLOCK | STEP_UP_AUTH | MANUAL_REVIEW
    action_reason:   str

    # Risk signals
    p_fraud:         float
    confidence:      float
    graph_risk_score:float = 0.0
    anomaly_score:   float = 0.0

    # Cost optimisation
    optimal_cost_usd:float = 0.0

    # A/B experiment
    ab_experiment_id:str = ""
    ab_variant:      str = ""

    # Explanation (plain English)
    explanation:     Dict[str, str] = {}

    # Pipeline metadata
    pipeline_stage:  int    # 1 = early exit, 2 = full pipeline
    early_exit:      bool   = False
    e2e_latency_ms:  float
    stage1_ms:       float  = 0.0
    stage2_ms:       float  = 0.0
    stage3_ms:       float  = 0.0
    gateway_version: str    = "1.0.0"

# ---------------------------------------------------------------------------
# Running stats
# ---------------------------------------------------------------------------
@dataclass
class GatewayStats:
    total:       int   = 0
    early_exits: int   = 0
    errors:      int   = 0
    latency_sum: float = 0.0
    start_time:  float = field(default_factory=time.monotonic)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def record(self, latency_ms: float, early_exit: bool, error: bool = False):
        with self._lock:
            self.total       += 1
            self.latency_sum += latency_ms
            if early_exit: self.early_exits += 1
            if error:      self.errors      += 1

    def to_dict(self) -> dict:
        with self._lock:
            elapsed = max(time.monotonic() - self.start_time, 1)
            avg_lat = self.latency_sum / max(self.total, 1)
            return {
                "total_requests":    self.total,
                "early_exits":       self.early_exits,
                "early_exit_pct":    round(self.early_exits / max(self.total,1) * 100, 2),
                "errors":            self.errors,
                "avg_latency_ms":    round(avg_lat, 2),
                "tps":               round(self.total / elapsed, 2),
                "uptime_seconds":    round(elapsed, 1),
            }

stats = GatewayStats()

# ---------------------------------------------------------------------------
# HTTP clients (shared, connection-pooled)
# ---------------------------------------------------------------------------
_http_client: Optional[httpx.AsyncClient] = None

def get_http_client() -> httpx.AsyncClient:
    return _http_client

# ---------------------------------------------------------------------------
# Feature builder — maps TransactionRequest → Stage 1 feature dict
# ---------------------------------------------------------------------------

def build_feature_dict(req: TransactionRequest, pre_features: Optional[Dict] = None) -> dict:
    """
    Build the 18-feature payload for Stage 1/2 from a raw transaction.
    Uses pre-computed features if provided (from feature-engine),
    otherwise uses cold-start defaults.
    """
    f = pre_features or {}
    return {
        "txn_id":          req.txn_id,
        "customer_id":     req.customer_id,
        "amount":          req.amount,
        "currency":        req.currency,
        "channel":         req.channel,
        "merchant_id":     req.merchant_id,
        "merchant_category": req.merchant_category,
        "device_id":       req.device_id,
        "ip_address":      req.ip_address,
        "country_code":    req.country_code,
        "txn_ts":          req.txn_ts,
        "clv":             req.clv,
        "trust_score":     req.trust_score,
        "account_age_days":req.account_age_days,
        "customer_segment":req.customer_segment,
        "is_new_device":   req.is_new_device,
        # 18 computed features — from feature engine or cold-start defaults
        "txn_count_1m":    f.get("txn_count_1m",    1),
        "txn_count_5m":    f.get("txn_count_5m",    1),
        "txn_count_1h":    f.get("txn_count_1h",    1),
        "txn_count_24h":   f.get("txn_count_24h",   1),
        "amount_sum_1m":   f.get("amount_sum_1m",   req.amount),
        "amount_sum_5m":   f.get("amount_sum_5m",   req.amount),
        "amount_sum_1h":   f.get("amount_sum_1h",   req.amount),
        "amount_sum_24h":  f.get("amount_sum_24h",  req.amount),
        "geo_velocity_kmh":f.get("geo_velocity_kmh",0.0),
        "is_new_country":  f.get("is_new_country",  False),
        "unique_countries_24h": f.get("unique_countries_24h", 1),
        "device_trust_score":   f.get("device_trust_score",   0.5),
        "ip_txn_count_1h":      f.get("ip_txn_count_1h",      0),
        "unique_devices_24h":   f.get("unique_devices_24h",   1),
        "amount_vs_avg_ratio":  f.get("amount_vs_avg_ratio",  1.0),
        "merchant_familiarity": f.get("merchant_familiarity", 0.5),
        "hours_since_last_txn": f.get("hours_since_last_txn", 24.0),
        "has_cold_start":       pre_features is None,
        "is_fraud":             req.is_fraud,
        "fraud_pattern":        req.fraud_pattern,
    }

# ---------------------------------------------------------------------------
# Pipeline orchestration
# ---------------------------------------------------------------------------

async def run_pipeline(req: TransactionRequest) -> DecisionResponse:
    """
    Execute the full 3-stage pipeline (or early exit) for one transaction.
    """
    t0 = time.perf_counter()
    client = get_http_client()
    feature_dict = build_feature_dict(req, req.features)

    # ---- Stage 1: Fast Risk Estimation ----
    t1 = time.perf_counter()
    try:
        r1 = await client.post(
            f"{STAGE1_URL}/predict",
            json=feature_dict,
            timeout=TIMEOUT_S1,
        )
        r1.raise_for_status()
        s1 = r1.json()
    except Exception as e:
        TXN_ERRORS.labels(stage="stage1").inc()
        logger.warning("Stage 1 failed for %s: %s — using fallback", req.txn_id, e)
        # Fallback: send to Stage 2 as uncertain
        s1 = {"p_fraud": 0.5, "uncertainty": 1.0,
              "routing": "UNCERTAIN_ESCALATE", "inference_time_ms": 0}

    s1_ms = (time.perf_counter() - t1) * 1000
    STAGE_LATENCY.labels(stage="1").observe(s1_ms)

    p_fraud    = s1.get("p_fraud",    0.5)
    uncertainty= s1.get("uncertainty",0.5)
    routing    = s1.get("routing",    "PASS_TO_STAGE2")

    # ---- Early Exit path ----
    if routing == "EARLY_EXIT_APPROVE":
        e2e_ms = (time.perf_counter() - t0) * 1000
        TXN_EARLY_EXIT.inc()
        E2E_LATENCY.observe(e2e_ms)
        stats.record(e2e_ms, early_exit=True)
        await _publish_to_kafka(req, "APPROVE", p_fraud, "stage1_early_exit")
        return DecisionResponse(
            txn_id          = req.txn_id,
            customer_id     = req.customer_id,
            amount          = req.amount,
            currency        = req.currency,
            action          = "APPROVE",
            action_reason   = f"Stage 1 early exit: P(fraud)={p_fraud:.4f} below threshold",
            p_fraud         = p_fraud,
            confidence      = 1.0 - uncertainty,
            pipeline_stage  = 1,
            early_exit      = True,
            e2e_latency_ms  = round(e2e_ms, 3),
            stage1_ms       = round(s1_ms,  3),
            explanation     = {"stage1": f"Low risk — P(fraud)={p_fraud:.4f}"},
        )

    # ---- Stage 2: Deep Intelligence ----
    t2 = time.perf_counter()
    s2 = {}
    try:
        stage2_payload = {
            **feature_dict,
            "p_fraud_stage1":   p_fraud,
            "uncertainty_stage1": uncertainty,
            "stage1_routing":   routing,
        }
        r2 = await client.post(
            f"{STAGE2_URL}/predict",
            json=stage2_payload,
            timeout=TIMEOUT_S2,
        )
        r2.raise_for_status()
        s2 = r2.json()
    except Exception as e:
        TXN_ERRORS.labels(stage="stage2").inc()
        logger.warning("Stage 2 failed for %s: %s — using Stage 1 score", req.txn_id, e)
        s2 = {
            "p_fraud":         p_fraud,
            "confidence":      1.0 - uncertainty,
            "graph_risk_score":0.0,
            "anomaly_score":   0.0,
            "stage2_explanation": {},
        }

    s2_ms = (time.perf_counter() - t2) * 1000
    STAGE_LATENCY.labels(stage="2").observe(s2_ms)

    # ---- Stage 3: Decision Optimization ----
    t3 = time.perf_counter()
    s3 = {}
    try:
        stage3_payload = {
            "txn_id":           req.txn_id,
            "customer_id":      req.customer_id,
            "amount":           req.amount,
            "currency":         req.currency,
            "channel":          req.channel,
            "merchant_category":req.merchant_category,
            "country_code":     req.country_code,
            "txn_ts":           req.txn_ts,
            "clv":              req.clv,
            "trust_score":      req.trust_score,
            "account_age_days": req.account_age_days,
            "customer_segment": req.customer_segment,
            "p_fraud_stage1":   p_fraud,
            "uncertainty_stage1": uncertainty,
            "stage1_routing":   routing,
            "p_fraud":          s2.get("p_fraud",          p_fraud),
            "confidence":       s2.get("confidence",        0.5),
            "xgb_score":        s2.get("xgb_score",         0.5),
            "mlp_score":        s2.get("mlp_score",          0.5),
            "graph_risk_score": s2.get("graph_risk_score",  0.0),
            "fraud_ring_score": s2.get("fraud_ring_score",  0.0),
            "mule_account_score":s2.get("mule_account_score",0.0),
            "synthetic_identity_score":s2.get("synthetic_identity_score",0.0),
            "velocity_graph_score":s2.get("velocity_graph_score",0.0),
            "multi_hop_score":  s2.get("multi_hop_score",   0.0),
            "anomaly_score":    s2.get("anomaly_score",     0.0),
            "autoencoder_score":s2.get("autoencoder_score", 0.0),
            "isolation_forest_score":s2.get("isolation_forest_score",0.0),
            "is_anomaly":       s2.get("is_anomaly",        False),
            "neo4j_available":  s2.get("neo4j_available",   False),
            "stage2_explanation":s2.get("explanation",      {}),
            "top_features":     s2.get("top_features",      {}),
            "is_fraud":         req.is_fraud,
            "fraud_pattern":    req.fraud_pattern,
        }
        r3 = await client.post(
            f"{STAGE3_URL}/decide",
            json=stage3_payload,
            timeout=TIMEOUT_S3,
        )
        r3.raise_for_status()
        s3 = r3.json()
    except Exception as e:
        TXN_ERRORS.labels(stage="stage3").inc()
        logger.warning("Stage 3 failed for %s: %s — using safe default MANUAL_REVIEW", req.txn_id, e)
        s3 = {
            "action":       "MANUAL_REVIEW",
            "action_reason":"Stage 3 unavailable — conservative fallback",
            "optimal_cost": 15.0,
            "explanation":  {"fallback": "Stage 3 service unavailable"},
            "ab_variant":   "control",
        }

    s3_ms  = (time.perf_counter() - t3) * 1000
    e2e_ms = (time.perf_counter() - t0) * 1000
    STAGE_LATENCY.labels(stage="3").observe(s3_ms)
    E2E_LATENCY.observe(e2e_ms)
    stats.record(e2e_ms, early_exit=False)

    action = s3.get("action", "MANUAL_REVIEW")
    await _publish_to_kafka(req, action, s2.get("p_fraud", p_fraud), "full_pipeline")

    return DecisionResponse(
        txn_id           = req.txn_id,
        customer_id      = req.customer_id,
        amount           = req.amount,
        currency         = req.currency,
        action           = action,
        action_reason    = s3.get("action_reason", ""),
        p_fraud          = s2.get("p_fraud",          p_fraud),
        confidence       = s2.get("confidence",        0.5),
        graph_risk_score = s2.get("graph_risk_score",  0.0),
        anomaly_score    = s2.get("anomaly_score",     0.0),
        optimal_cost_usd = s3.get("optimal_cost",      0.0),
        ab_experiment_id = s3.get("ab_experiment_id",  ""),
        ab_variant       = s3.get("ab_variant",        "control"),
        explanation      = s3.get("explanation",       {}),
        pipeline_stage   = 3,
        early_exit       = False,
        e2e_latency_ms   = round(e2e_ms, 3),
        stage1_ms        = round(s1_ms,  3),
        stage2_ms        = round(s2_ms,  3),
        stage3_ms        = round(s3_ms,  3),
    )


async def _publish_to_kafka(req: TransactionRequest, action: str,
                             p_fraud: float, path: str):
    """Fire-and-forget Kafka publish — never blocks the response."""
    if not KAFKA_ENABLED:
        return
    try:
        from confluent_kafka import Producer
        producer = Producer({"bootstrap.servers": KAFKA_BROKERS, "acks": "0"})
        producer.produce(
            topic = "decisions",
            key   = req.customer_id.encode(),
            value = json.dumps({
                "txn_id":     req.txn_id,
                "action":     action,
                "p_fraud":    p_fraud,
                "path":       path,
                "gateway_ts": datetime.now(timezone.utc).isoformat(),
            }).encode(),
        )
        producer.poll(0)
    except Exception:
        pass   # non-fatal

# ---------------------------------------------------------------------------
# FastAPI application
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    global _http_client
    logger.info("API Gateway starting up...")
    logger.info("  Stage 1: %s", STAGE1_URL)
    logger.info("  Stage 2: %s", STAGE2_URL)
    logger.info("  Stage 3: %s", STAGE3_URL)

    _http_client = httpx.AsyncClient(
        limits=httpx.Limits(max_connections=200, max_keepalive_connections=50),
        timeout=httpx.Timeout(1.0),
    )

    try:
        start_http_server(METRICS_PORT)
        logger.info("Prometheus at http://0.0.0.0:%d/metrics", METRICS_PORT)
    except Exception as e:
        logger.warning("Prometheus failed: %s", e)

    logger.info("API Gateway ready.")
    yield

    await _http_client.aclose()
    logger.info("API Gateway shutdown.")


app = FastAPI(
    title       = "Fraud Detection — API Gateway",
    description = (
        "Single entry point for real-time fraud scoring. "
        "Orchestrates Stage 1 (LightGBM fast risk), "
        "Stage 2 (XGBoost + MLP + Neo4j graph + Anomaly detection), "
        "and Stage 3 (argmin cost decision engine)."
    ),
    version     = "1.0.0",
    lifespan    = lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins  = ["*"],
    allow_methods  = ["GET", "POST"],
    allow_headers  = ["*"],
)


@app.post(
    "/transaction",
    response_model  = DecisionResponse,
    summary         = "Score a single transaction",
    description     = (
        "Submit a transaction for real-time fraud scoring. "
        "Returns a decision (APPROVE / BLOCK / STEP_UP_AUTH / MANUAL_REVIEW) "
        "with explanation and cost breakdown. "
        "Low-risk transactions exit after Stage 1 in <10ms."
    ),
)
async def score_transaction(req: TransactionRequest) -> DecisionResponse:
    TXN_TOTAL.inc()
    INFLIGHT.inc()
    try:
        return await run_pipeline(req)
    except Exception as e:
        stats.record(0, early_exit=False, error=True)
        logger.exception("Pipeline failed for %s: %s", req.txn_id, e)
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        INFLIGHT.dec()


@app.post(
    "/transaction/batch",
    response_model  = List[DecisionResponse],
    summary         = "Score up to 100 transactions in one call",
)
async def score_batch(reqs: List[TransactionRequest]) -> List[DecisionResponse]:
    if len(reqs) > 100:
        raise HTTPException(422, "Batch size exceeds limit of 100")
    import asyncio
    TXN_TOTAL.inc(len(reqs))
    results = await asyncio.gather(
        *[run_pipeline(req) for req in reqs],
        return_exceptions=True,
    )
    responses = []
    for r in results:
        if isinstance(r, Exception):
            logger.warning("Batch item failed: %s", r)
        else:
            responses.append(r)
    return responses


@app.get("/", summary="Gateway root")
async def root():
    return {
        "service": "api-gateway",
        "status": "ok",
        "docs": "/docs",
        "health": "/health",
        "score_endpoint": "/transaction",
    }


@app.get("/health", summary="Liveness probe")
async def health():
    return {"status": "ok", "service": "api-gateway", "version": "1.0.0"}


@app.get("/ready", summary="Readiness — checks all upstream services")
async def ready():
    client  = get_http_client()
    checks  = {}
    overall = True
    for name, url in [("stage1", STAGE1_URL), ("stage2", STAGE2_URL), ("stage3", STAGE3_URL)]:
        try:
            r = await client.get(f"{url}/health", timeout=2.0)
            checks[name] = r.status_code == 200
        except Exception:
            checks[name] = False
        if not checks[name]:
            overall = False
    status_code = 200 if overall else 503
    return JSONResponse(
        status_code = status_code,
        content     = {"ready": overall, "services": checks},
    )


@app.get("/stats", summary="Real-time gateway statistics")
async def gateway_stats():
    return stats.to_dict()


app.mount("/metrics", make_asgi_app())


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run(
        app,
        host      = os.getenv("HOST", "0.0.0.0"),
        port      = port,
        workers   = int(os.getenv("UVICORN_WORKERS", "2")),
        log_level = os.getenv("LOG_LEVEL", "info").lower(),
    )
