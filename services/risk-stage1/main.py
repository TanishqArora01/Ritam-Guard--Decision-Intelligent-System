"""
main.py — Stage 1 Fast Risk Estimation service.

Startup sequence:
  1. Build predictor (train or load from MLflow + calibrate ICP)
  2. Start Kafka consumer thread (async scoring of txn-enriched stream)
  3. Start Prometheus metrics server
  4. Start FastAPI / uvicorn (synchronous REST path)

Shutdown:
  - Kafka consumer thread stops cleanly on SIGTERM/SIGINT
  - In-flight requests complete before shutdown
"""
from __future__ import annotations

import json
import logging
import signal
import threading
import time
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import start_http_server, make_asgi_app

from config import config
from model.predictor import build_predictor
from routes.predict import router as predict_router
from routes.health  import router as health_router
from schemas import PredictRequest

# ---------------------------------------------------------------------------
logging.basicConfig(
    level=getattr(logging, config.log_level.upper(), logging.INFO),
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("stage1.main")

# ---------------------------------------------------------------------------
# Kafka consumer (background thread)
# ---------------------------------------------------------------------------

class KafkaConsumerThread(threading.Thread):
    """
    Consumes from txn-enriched, runs Stage 1 inference,
    publishes scored results to txn-stage1.
    Fully independent of the REST path — failure here does not
    affect the synchronous /predict endpoint.
    """

    def __init__(self, predictor, stop_event: threading.Event):
        super().__init__(name="stage1-kafka-consumer", daemon=True)
        self.predictor   = predictor
        self.stop_event  = stop_event
        self._consumer   = None
        self._producer   = None

    def _connect(self):
        try:
            from confluent_kafka import Consumer, Producer
            self._consumer = Consumer({
                "bootstrap.servers":  config.kafka_bootstrap_servers,
                "group.id":           config.kafka_consumer_group,
                "auto.offset.reset":  config.kafka_auto_offset_reset,
                "enable.auto.commit": False,
                "session.timeout.ms": 30_000,
            })
            self._consumer.subscribe([config.kafka_topic_enriched])

            self._producer = Producer({
                "bootstrap.servers": config.kafka_bootstrap_servers,
                "acks":              "1",
                "compression.type":  "lz4",
                "linger.ms":         "5",
            })
            logger.info("Kafka consumer connected | group=%s | topic=%s",
                        config.kafka_consumer_group, config.kafka_topic_enriched)
            return True
        except Exception as e:
            logger.warning("Kafka connection failed (non-fatal): %s", e)
            return False

    def run(self):
        if not config.kafka_enabled or not self._connect():
            logger.info("Kafka consumer disabled or unavailable — REST only mode")
            return

        logger.info("Kafka consumer thread started")
        while not self.stop_event.is_set():
            try:
                msg = self._consumer.poll(timeout=0.5)
                if msg is None:
                    continue
                if msg.error():
                    logger.warning("Kafka error: %s", msg.error())
                    continue

                raw  = json.loads(msg.value().decode("utf-8"))
                req  = PredictRequest(**raw)
                resp = self.predictor.predict(req)

                # Publish to txn-stage1
                self._producer.produce(
                    topic = config.kafka_topic_stage1,
                    key   = req.customer_id.encode("utf-8"),
                    value = resp.model_dump_json().encode("utf-8"),
                )
                self._producer.poll(0)
                self._consumer.commit(msg, asynchronous=False)

            except Exception as e:
                logger.warning("Consumer loop error: %s", e)
                time.sleep(0.1)

        if self._consumer:
            self._consumer.close()
        if self._producer:
            self._producer.flush(10)
        logger.info("Kafka consumer thread stopped")


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup → yield → shutdown."""
    logger.info("=" * 60)
    logger.info("Stage 1 — Fast Risk Estimation Service")
    logger.info("=" * 60)
    logger.info("  Init strategy : %s", config.model_init_strategy)
    logger.info("  θ_low / θ_high: %.2f / %.2f", config.theta_low, config.theta_high)
    logger.info("  ICP alpha     : %.2f (%.0f%% coverage)",
                config.conformal_alpha, (1 - config.conformal_alpha) * 100)
    logger.info("  Kafka enabled : %s", config.kafka_enabled)

    # Build predictor (train or load)
    logger.info("Building predictor...")
    predictor = build_predictor()
    app.state.predictor = predictor

    # Start Prometheus
    try:
        start_http_server(config.metrics_port)
        logger.info("Prometheus metrics at http://0.0.0.0:%d/metrics", config.metrics_port)
    except Exception as e:
        logger.warning("Prometheus server failed to start: %s", e)

    # Start Kafka consumer thread
    stop_event = threading.Event()
    kafka_thread = KafkaConsumerThread(predictor, stop_event)
    kafka_thread.start()
    app.state.kafka_stop = stop_event

    logger.info("Stage 1 service ready.")
    yield

    # Shutdown
    logger.info("Shutting down...")
    stop_event.set()
    kafka_thread.join(timeout=10)


app = FastAPI(
    title       = "Stage 1 — Fast Risk Estimation",
    description = (
        "LightGBM-based fraud risk scorer with Inductive Conformal Prediction "
        "for uncertainty quantification. Implements early exit for low-risk "
        "transactions (<10ms), bypassing Stages 2 and 3."
    ),
    version     = config.service_version,
    lifespan    = lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

app.include_router(predict_router, tags=["Prediction"])
app.include_router(health_router,  tags=["Operations"])

# Prometheus ASGI metrics endpoint (in addition to the standalone server)
metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host    = config.host,
        port    = config.port,
        workers = 1,           # 1 worker so app.state is shared
        log_level = config.log_level.lower(),
    )
