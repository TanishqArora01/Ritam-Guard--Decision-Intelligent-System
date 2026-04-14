"""
main.py — Stage 3 Decision Optimization Engine.

Consumes from txn-stage2, runs argmin cost engine, publishes to decisions.
Also exposes synchronous POST /decide for direct integration.
"""
from __future__ import annotations

import json
import logging
import random
import threading
import time
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from prometheus_client import start_http_server, make_asgi_app

from config import config
from schemas import Stage3Request, Stage3Response, Action, ABVariant
from cost_engine import (
    decide, decide_with_ab, build_explanation,
    resolve_clv, effective_p_fraud, compute_all_costs,
)

logging.basicConfig(
    level=getattr(logging, config.log_level.upper(), logging.INFO),
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger("stage3.main")

try:
    from prometheus_client import Counter, Histogram
    DECISIONS_TOTAL = Counter("stage3_decisions_total", "Decisions", ["action","ab_variant"])
    LATENCY_MS      = Histogram("stage3_latency_ms", "Decision latency (ms)",
                                buckets=[1,2,5,10,20,50,100,200])
except Exception:
    class _N:
        def __init__(self,*a,**k): pass
        def labels(self,**k): return self
        def inc(self,v=1): pass
        def observe(self,v): pass
    DECISIONS_TOTAL = LATENCY_MS = _N()


# ---------------------------------------------------------------------------
# Core decision execution
# ---------------------------------------------------------------------------

def execute_decision(req: Stage3Request, rng: random.Random) -> Stage3Response:
    """Run the full decision pipeline and return a Stage3Response."""
    t0 = time.perf_counter()

    # A/B experiment assignment + cost-optimised decision
    action, variant, shadow_action, reason = decide_with_ab(req, rng)

    # Supporting values for explanation
    clv    = resolve_clv(req)
    p_eff  = effective_p_fraud(req.p_fraud, req.trust_score)
    costs  = compute_all_costs(p_eff, req.amount, clv)
    opt    = next((c for c in costs if c.is_optimal), costs[0])

    # Build explanation
    explanation = build_explanation(req, action, reason, clv, p_eff, costs)

    elapsed_ms = (time.perf_counter() - t0) * 1000
    DECISIONS_TOTAL.labels(action=action.value, ab_variant=variant.value).inc()
    LATENCY_MS.observe(elapsed_ms)

    return Stage3Response(
        txn_id           = req.txn_id,
        customer_id      = req.customer_id,
        amount           = req.amount,
        currency         = req.currency,
        action           = action,
        action_reason    = reason,
        optimal_cost     = opt.total_expected_cost,
        cost_breakdown   = costs,
        p_fraud          = req.p_fraud,
        uncertainty      = 1.0 - req.confidence,
        graph_risk_score = req.graph_risk_score,
        anomaly_score    = req.anomaly_score,
        confidence       = req.confidence,
        clv_used         = clv,
        trust_score      = req.trust_score,
        ab_experiment_id = config.ab_experiment_id if config.ab_enabled else "",
        ab_variant       = variant,
        ab_shadow_action = shadow_action,
        explanation      = explanation,
        pipeline_stage   = 3,
        decision_time_ms = round(elapsed_ms, 3),
        model_version    = config.service_version,
    )


# ---------------------------------------------------------------------------
# Kafka consumer thread
# ---------------------------------------------------------------------------

class KafkaConsumerThread(threading.Thread):

    def __init__(self, stop_event: threading.Event, rng: random.Random):
        super().__init__(name="stage3-kafka", daemon=True)
        self.stop_event = stop_event
        self.rng        = rng
        self._consumer  = None
        self._producer  = None

    def _connect(self) -> bool:
        try:
            from confluent_kafka import Consumer, Producer
            self._consumer = Consumer({
                "bootstrap.servers":  config.kafka_bootstrap_servers,
                "group.id":           config.kafka_consumer_group,
                "auto.offset.reset":  config.kafka_auto_offset_reset,
                "enable.auto.commit": False,
            })
            self._consumer.subscribe([config.kafka_topic_stage2])
            self._producer = Producer({
                "bootstrap.servers": config.kafka_bootstrap_servers,
                "acks": "1", "compression.type": "lz4", "linger.ms": "5",
            })
            logger.info("Kafka connected: %s → %s",
                        config.kafka_topic_stage2, config.kafka_topic_decisions)
            return True
        except Exception as e:
            logger.warning("Kafka unavailable (REST-only mode): %s", e); return False

    def run(self):
        if not config.kafka_enabled or not self._connect(): return
        while not self.stop_event.is_set():
            try:
                msg = self._consumer.poll(timeout=0.5)
                if msg is None or msg.error(): continue
                raw  = json.loads(msg.value().decode())
                req  = Stage3Request(**raw)
                resp = execute_decision(req, self.rng)
                self._producer.produce(
                    topic = config.kafka_topic_decisions,
                    key   = req.customer_id.encode(),
                    value = resp.model_dump_json().encode(),
                )
                # Also publish to A/B topic for experiment tracking
                if config.ab_enabled:
                    self._producer.produce(
                        topic = config.kafka_topic_ab,
                        key   = req.customer_id.encode(),
                        value = resp.model_dump_json().encode(),
                    )
                self._producer.poll(0)
                self._consumer.commit(msg, asynchronous=False)
            except Exception as e:
                logger.warning("Consumer error: %s", e); time.sleep(0.1)
        if self._consumer: self._consumer.close()
        if self._producer: self._producer.flush(10)


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("=" * 60)
    logger.info("Stage 3 — Decision Optimization Engine")
    logger.info("=" * 60)
    logger.info("  Cost review:     $%.2f", config.cost_manual_review)
    logger.info("  Cost step-up:    $%.2f", config.cost_stepup)
    logger.info("  CLV multiplier:  %.4f", config.clv_friction_multiplier)
    logger.info("  Hard block thr:  %.2f", config.hard_block_threshold)
    logger.info("  Hard approve thr:%.2f", config.hard_approve_threshold)
    logger.info("  A/B enabled:     %s (shadow=%s)",
                config.ab_enabled, config.ab_shadow_mode)

    rng = random.Random(42)
    app.state.rng = rng

    try:
        start_http_server(config.metrics_port)
        logger.info("Prometheus at http://0.0.0.0:%d/metrics", config.metrics_port)
    except Exception as e:
        logger.warning("Prometheus failed: %s", e)

    stop_event = threading.Event()
    kafka_thread = KafkaConsumerThread(stop_event, rng)
    kafka_thread.start()
    app.state.kafka_stop = stop_event

    logger.info("Stage 3 ready.")
    yield

    stop_event.set()
    kafka_thread.join(timeout=10)


app = FastAPI(
    title       = "Stage 3 — Decision Optimization Engine",
    description = "argmin E[cost] over {APPROVE, BLOCK, STEP_UP_AUTH, MANUAL_REVIEW} with A/B experimentation",
    version     = config.service_version,
    lifespan    = lifespan,
)
app.add_middleware(CORSMiddleware, allow_origins=["*"],
                   allow_methods=["GET","POST"], allow_headers=["*"])


def get_rng(request: Request) -> random.Random:
    return getattr(request.app.state, "rng", random.Random())


@app.post("/decide", response_model=Stage3Response,
          summary="Make a cost-optimised fraud decision")
async def decide_endpoint(req: Stage3Request, rng=Depends(get_rng)):
    try:
        return execute_decision(req, rng)
    except Exception as e:
        logger.exception("Decision failed for txn=%s: %s", req.txn_id, e)
        raise HTTPException(500, str(e))


@app.get("/health")
async def health():
    return {"status": "ok", "service": config.service_name}


@app.get("/ready")
async def ready():
    return {"ready": True, "ab_enabled": config.ab_enabled,
            "shadow_mode": config.ab_shadow_mode}


@app.get("/config")
async def get_config():
    return {
        "cost_manual_review":   config.cost_manual_review,
        "cost_stepup":          config.cost_stepup,
        "clv_friction_multiplier": config.clv_friction_multiplier,
        "hard_block_threshold": config.hard_block_threshold,
        "hard_approve_threshold": config.hard_approve_threshold,
        "ab_enabled":           config.ab_enabled,
        "ab_experiment_id":     config.ab_experiment_id,
        "ab_shadow_mode":       config.ab_shadow_mode,
    }


app.mount("/metrics", make_asgi_app())

if __name__ == "__main__":
    uvicorn.run("main:app", host=config.host, port=config.port,
                workers=1, log_level=config.log_level.lower())
