"""
main.py — Stage 2 Deep Intelligence service.

Three parallel scoring layers run per transaction:
  1. ML Ensemble    (XGBoost + PyTorch MLP)
  2. Graph Intel    (5 Neo4j Cypher queries, concurrent)
  3. Anomaly Detect (Autoencoder + IsolationForest combined)

All three scores are fused into combined_risk_score → Stage 3.
If Neo4j/PyTorch is unavailable, the service degrades gracefully
and continues scoring with available components.
"""
from __future__ import annotations
import json
import logging
import signal
import threading
import time
from contextlib import asynccontextmanager

import numpy as np
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import Counter, Histogram, start_http_server

from config import config
from schemas import Stage2Request, Stage2Response
from ensemble.xgboost_model import XGBoostModel
from ensemble.mlp_model import MLPModel
from ensemble.fusion import fuse_ensemble, fuse_all, build_explanation
from graph.neo4j_client import Neo4jClient
from graph.graph_scorer import GraphScorer
from anomaly.anomaly_scorer import build_anomaly_scorer, AnomalyScorer
from routes.predict import router as predict_router
from routes.health  import router as health_router

logging.basicConfig(
    level=getattr(logging, config.log_level.upper(), logging.INFO),
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger("stage2.main")

# Prometheus
SCORED_TOTAL   = Counter("stage2_scored_total", "Total transactions scored", ["routing"])
SCORE_LATENCY  = Histogram("stage2_latency_ms", "Stage 2 inference latency",
                            buckets=[5,10,20,50,100,200,500])


# ---------------------------------------------------------------------------
# Core scoring engine
# ---------------------------------------------------------------------------

class Stage2Engine:
    """Thread-safe. All state is read-only after startup."""

    def __init__(self, xgb: XGBoostModel, mlp: MLPModel,
                 graph_scorer: GraphScorer, anomaly_scorer: AnomalyScorer):
        self.xgb           = xgb
        self.mlp           = mlp
        self.graph_scorer  = graph_scorer
        self.anomaly_scorer= anomaly_scorer

    def score(self, req: Stage2Request) -> Stage2Response:
        t0 = time.perf_counter()
        X  = np.array([req.to_feature_array()], dtype=np.float32)

        # --- Layer 1: ML Ensemble ---
        xgb_p = float(self.xgb.predict_proba(X)[0])
        mlp_p = float(self.mlp.predict_proba(X)[0])
        refined_p, confidence = fuse_ensemble(
            xgb_p, mlp_p, config.ensemble_weight_xgb, config.ensemble_weight_mlp
        )

        # --- Layer 2: Graph Intelligence (non-blocking) ---
        graph_signals = self.graph_scorer.score(req)

        # --- Layer 3: Anomaly Detection ---
        anomaly_signals = self.anomaly_scorer.score(X)

        # --- Final fusion ---
        combined = fuse_all(
            ensemble_score = refined_p,
            graph_risk     = graph_signals.graph_risk_score,
            anomaly_score  = anomaly_signals.combined_anomaly_score,
        )

        # --- SHAP top features ---
        top_features = self.xgb.top_shap_features(X, top_n=3)

        # --- Explanation ---
        explanation = build_explanation(
            xgb_p, mlp_p, graph_signals.graph_risk_score,
            anomaly_signals.combined_anomaly_score, top_features,
        )

        elapsed_ms = (time.perf_counter() - t0) * 1000
        SCORE_LATENCY.observe(elapsed_ms)
        SCORED_TOTAL.labels(routing=req.stage1_routing).inc()

        return Stage2Response(
            txn_id               = req.txn_id,
            customer_id          = req.customer_id,
            amount               = req.amount,
            refined_p_fraud      = round(refined_p,  6),
            xgb_p_fraud          = round(xgb_p,      6),
            mlp_p_fraud          = round(mlp_p,       6),
            ensemble_confidence  = round(confidence,  4),
            graph                = graph_signals,
            anomaly              = anomaly_signals,
            combined_risk_score  = round(combined,    6),
            top_features         = top_features,
            explanation          = explanation,
            model_versions       = {
                "xgb":     self.xgb.model_version,
                "mlp":     self.mlp.model_version,
                "ae":      self.anomaly_scorer.ae.model_version,
                "iforest": self.anomaly_scorer.iforest.model_version,
            },
            inference_time_ms = round(elapsed_ms, 2),
            pipeline_stage    = 2,
        )


# ---------------------------------------------------------------------------
# Kafka consumer thread
# ---------------------------------------------------------------------------

class KafkaConsumerThread(threading.Thread):
    def __init__(self, engine: Stage2Engine, stop_event: threading.Event):
        super().__init__(name="stage2-kafka", daemon=True)
        self.engine     = engine
        self.stop_event = stop_event
        self._consumer  = None
        self._producer  = None

    def _connect(self):
        try:
            from confluent_kafka import Consumer, Producer
            self._consumer = Consumer({
                "bootstrap.servers":  config.kafka_bootstrap_servers,
                "group.id":           config.kafka_consumer_group,
                "auto.offset.reset":  config.kafka_auto_offset_reset,
                "enable.auto.commit": False,
            })
            self._consumer.subscribe([config.kafka_topic_stage1])
            self._producer = Producer({
                "bootstrap.servers": config.kafka_bootstrap_servers,
                "acks": "1", "linger.ms": "5",
            })
            logger.info("Stage 2 Kafka consumer started | group=%s",
                        config.kafka_consumer_group)
            return True
        except Exception as e:
            logger.warning("Kafka unavailable (non-fatal): %s", e)
            return False

    def run(self):
        if not config.kafka_enabled or not self._connect():
            return
        while not self.stop_event.is_set():
            try:
                msg = self._consumer.poll(timeout=0.5)
                if msg is None or msg.error():
                    continue
                raw  = json.loads(msg.value().decode())
                req  = Stage2Request(**raw)
                resp = self.engine.score(req)
                self._producer.produce(
                    topic=config.kafka_topic_stage2,
                    key=req.customer_id.encode(),
                    value=json.dumps(resp.__dict__).encode(),
                )
                self._producer.poll(0)
                self._consumer.commit(msg, asynchronous=False)
            except Exception as e:
                logger.warning("Stage 2 Kafka loop error: %s", e)
        if self._consumer: self._consumer.close()
        if self._producer: self._producer.flush(5)


# ---------------------------------------------------------------------------
# FastAPI lifespan
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("=" * 60)
    logger.info("Stage 2 — Deep Intelligence Service")
    logger.info("=" * 60)

    # 1. Train or load models
    from ensemble.trainer import build_models, SyntheticDataGenerator
    xgb_model, mlp_model = build_models()

    # 2. Train anomaly detectors on same synthetic data
    rng = np.random.RandomState(config.random_seed + 2)
    gen = SyntheticDataGenerator(rng)
    X_all, y_all = gen.generate(config.train_samples, config.train_fraud_rate)
    anomaly_scorer = build_anomaly_scorer(X_all, y_all)

    # 3. Neo4j graph scorer
    neo4j = Neo4jClient()
    neo4j.connect()
    graph_scorer = GraphScorer(neo4j)

    # 4. Assemble engine
    engine = Stage2Engine(xgb_model, mlp_model, graph_scorer, anomaly_scorer)
    app.state.engine = engine

    # 5. Prometheus
    try:
        start_http_server(config.metrics_port)
        logger.info("Prometheus metrics at http://0.0.0.0:%d/metrics", config.metrics_port)
    except Exception:
        pass

    # 6. Kafka consumer
    stop_event = threading.Event()
    kafka_thread = KafkaConsumerThread(engine, stop_event)
    kafka_thread.start()
    app.state.kafka_stop = stop_event

    logger.info("Stage 2 engine ready.")
    yield

    stop_event.set()
    kafka_thread.join(timeout=10)
    neo4j.close()


app = FastAPI(
    title    = "Stage 2 — Deep Intelligence",
    version  = config.service_version,
    lifespan = lifespan,
)
app.add_middleware(CORSMiddleware, allow_origins=["*"],
                   allow_methods=["GET","POST"], allow_headers=["*"])
app.include_router(predict_router, tags=["Prediction"])
app.include_router(health_router,  tags=["Operations"])


if __name__ == "__main__":
    uvicorn.run("main:app", host=config.host, port=config.port,
                workers=1, log_level=config.log_level.lower())
