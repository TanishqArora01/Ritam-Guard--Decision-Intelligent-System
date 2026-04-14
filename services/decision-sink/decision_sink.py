"""
sinks/decision_sink.py
Consumes the decisions Kafka topic and writes to:
  1. PostgreSQL  decisions.records  — operational audit trail
  2. ClickHouse  fraud_analytics.decisions — OLAP analytics

Runs as a standalone microservice (decisions → dual-write sink).
Fault-tolerant: if one store is unavailable, the other still receives writes.
Uses batched inserts (configurable batch_size) for throughput.
"""
from __future__ import annotations

import json
import logging
import os
import signal
import sys
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
@dataclass
class SinkConfig:
    kafka_bootstrap_servers: str = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
    kafka_topic_decisions:   str = os.getenv("KAFKA_TOPIC_DECISIONS",   "decisions")
    kafka_consumer_group:    str = os.getenv("KAFKA_CONSUMER_GROUP",    "decision-sink-v1")
    kafka_auto_offset_reset: str = os.getenv("KAFKA_AUTO_OFFSET_RESET", "earliest")

    # PostgreSQL
    pg_dsn: str = os.getenv("POSTGRES_DSN",
        "postgresql://fraud_admin:fraud_secret_2024@localhost:5432/fraud_db")
    pg_enabled: bool = os.getenv("PG_ENABLED", "true").lower() == "true"

    # ClickHouse
    ch_host:     str = os.getenv("CLICKHOUSE_HOST",     "localhost")
    ch_port:     int = int(os.getenv("CLICKHOUSE_PORT", "9000"))
    ch_user:     str = os.getenv("CLICKHOUSE_USER",     "default")
    ch_password: str = os.getenv("CLICKHOUSE_PASSWORD", "")
    ch_database: str = os.getenv("CLICKHOUSE_DB",       "fraud_analytics")
    ch_enabled:  bool = os.getenv("CH_ENABLED", "true").lower() == "true"

    batch_size:    int = int(os.getenv("SINK_BATCH_SIZE",    "100"))
    batch_timeout: float = float(os.getenv("SINK_BATCH_TIMEOUT", "2.0"))
    log_level: str = os.getenv("LOG_LEVEL", "INFO")


config = SinkConfig()


# ---------------------------------------------------------------------------
# PostgreSQL writer
# ---------------------------------------------------------------------------

class PostgresWriter:

    def __init__(self):
        self._conn = None

    def connect(self):
        try:
            import psycopg2
            self._conn = psycopg2.connect(config.pg_dsn)
            self._conn.autocommit = False
            logger.info("PostgreSQL connected")
        except Exception as e:
            logger.warning("PostgreSQL unavailable: %s", e)

    def write_batch(self, decisions: List[Dict]) -> int:
        if not self._conn: return 0
        sql = """
        INSERT INTO decisions.records (
            txn_id, pipeline_stage, action, p_fraud, uncertainty,
            graph_risk_score, anomaly_score, clv_at_decision, trust_score,
            expected_loss, expected_friction, expected_review_cost,
            explanation, model_version, ab_experiment_id, ab_variant,
            latency_ms, decided_at
        ) VALUES (
            %(txn_id)s, %(pipeline_stage)s, %(action)s, %(p_fraud)s, %(uncertainty)s,
            %(graph_risk_score)s, %(anomaly_score)s, %(clv_at_decision)s, %(trust_score)s,
            %(expected_loss)s, %(expected_friction)s, %(expected_review_cost)s,
            %(explanation)s::jsonb, %(model_version)s, %(ab_experiment_id)s, %(ab_variant)s,
            %(latency_ms)s, %(decided_at)s
        ) ON CONFLICT DO NOTHING
        """
        try:
            import psycopg2.extras
            cur = self._conn.cursor()
            psycopg2.extras.execute_batch(cur, sql, decisions, page_size=50)
            self._conn.commit()
            return len(decisions)
        except Exception as e:
            logger.error("PostgreSQL write failed: %s", e)
            try: self._conn.rollback()
            except Exception: pass
            return 0

    def close(self):
        if self._conn:
            try: self._conn.close()
            except Exception: pass


# ---------------------------------------------------------------------------
# ClickHouse writer
# ---------------------------------------------------------------------------

class ClickHouseWriter:

    def __init__(self):
        self._client = None

    def connect(self):
        try:
            from clickhouse_driver import Client
            self._client = Client(
                host=config.ch_host, port=config.ch_port,
                user=config.ch_user, password=config.ch_password,
                database=config.ch_database,
                connect_timeout=5, send_receive_timeout=30,
            )
            self._client.execute("SELECT 1")
            logger.info("ClickHouse connected at %s:%d", config.ch_host, config.ch_port)
        except Exception as e:
            logger.warning("ClickHouse unavailable: %s", e)

    def write_batch(self, decisions: List[Dict]) -> int:
        if not self._client: return 0

        rows = []
        for d in decisions:
            try:
                rows.append((
                    datetime.fromisoformat(d.get("decided_at", datetime.now(timezone.utc).isoformat()).replace("Z","+00:00")),
                    d.get("txn_id",     ""),
                    d.get("txn_id",     ""),           # decision_id = txn_id for simplicity
                    d.get("customer_id",""),
                    int(d.get("pipeline_stage", 3)),
                    d.get("action",     ""),
                    float(d.get("p_fraud",          0.0)),
                    float(d.get("uncertainty",      0.0)),
                    float(d.get("graph_risk_score", 0.0)),
                    float(d.get("anomaly_score",    0.0)),
                    float(d.get("amount",           0.0)),
                    d.get("currency",   "USD"),
                    d.get("channel",    ""),
                    d.get("merchant_category", ""),
                    d.get("country_code", ""),
                    float(d.get("clv_used",     0.0)),
                    float(d.get("trust_score",  0.5)),
                    float(d.get("optimal_cost", 0.0)),   # expected_loss
                    0.0,                                  # expected_friction
                    0.0,                                  # expected_review_cost
                    float(d.get("decision_time_ms", 0.0)),
                    d.get("model_version", ""),
                    d.get("ab_experiment_id", ""),
                    d.get("ab_variant", "control"),
                    json.dumps(d.get("explanation", {})),
                ))
            except Exception as e:
                logger.debug("ClickHouse row prep error: %s", e)

        if not rows: return 0

        sql = """INSERT INTO fraud_analytics.decisions (
            decided_at, txn_id, decision_id, customer_id, pipeline_stage,
            action, p_fraud, uncertainty, graph_risk_score, anomaly_score,
            amount, currency, channel, merchant_category, country_code,
            clv_at_decision, trust_score, expected_loss, expected_friction,
            expected_review_cost, latency_ms, model_version,
            ab_experiment_id, ab_variant, explanation
        ) VALUES"""

        try:
            self._client.execute(sql, rows)
            return len(rows)
        except Exception as e:
            logger.error("ClickHouse write failed: %s", e)
            return 0


# ---------------------------------------------------------------------------
# Transform Kafka message → DB row dict
# ---------------------------------------------------------------------------

def parse_decision(raw: Dict) -> Dict:
    """Flatten Stage3Response JSON into a flat dict suitable for DB insert."""
    # Extract optimal_cost components from cost_breakdown
    cost_breakdown = raw.get("cost_breakdown", [])
    optimal = next((c for c in cost_breakdown if c.get("is_optimal")), {})

    return {
        "txn_id":           raw.get("txn_id",           ""),
        "customer_id":      raw.get("customer_id",       ""),
        "pipeline_stage":   raw.get("pipeline_stage",    3),
        "action":           raw.get("action",            ""),
        "p_fraud":          float(raw.get("p_fraud",     0.0)),
        "uncertainty":      float(raw.get("uncertainty", 0.0)),
        "graph_risk_score": float(raw.get("graph_risk_score", 0.0)),
        "anomaly_score":    float(raw.get("anomaly_score",    0.0)),
        "clv_at_decision":  float(raw.get("clv_used",         0.0)),
        "trust_score":      float(raw.get("trust_score",       0.5)),
        "amount":           float(raw.get("amount",            0.0)),
        "currency":         raw.get("currency", "USD"),
        "channel":          raw.get("channel",  ""),
        "country_code":     raw.get("country_code", ""),
        "merchant_category":raw.get("merchant_category", ""),
        "expected_loss":    float(optimal.get("expected_loss",     0.0)),
        "expected_friction":float(optimal.get("expected_friction",  0.0)),
        "expected_review_cost": float(optimal.get("expected_review", 0.0)),
        "optimal_cost":     float(raw.get("optimal_cost", 0.0)),
        "explanation":      json.dumps(raw.get("explanation", {})),
        "model_version":    raw.get("model_version",    ""),
        "ab_experiment_id": raw.get("ab_experiment_id", ""),
        "ab_variant":       raw.get("ab_variant",       "control"),
        "latency_ms":       float(raw.get("decision_time_ms", 0.0)),
        "decided_at":       datetime.now(timezone.utc).isoformat(),
    }


# ---------------------------------------------------------------------------
# Main sink loop
# ---------------------------------------------------------------------------

class DecisionSink:

    def __init__(self):
        self.pg = PostgresWriter() if config.pg_enabled else None
        self.ch = ClickHouseWriter() if config.ch_enabled else None
        self._stop = threading.Event()

    def connect(self):
        if self.pg: self.pg.connect()
        if self.ch: self.ch.connect()

    def run(self):
        try:
            from confluent_kafka import Consumer, KafkaError
        except ImportError:
            logger.error("confluent-kafka not installed"); return

        consumer = Consumer({
            "bootstrap.servers":  config.kafka_bootstrap_servers,
            "group.id":           config.kafka_consumer_group,
            "auto.offset.reset":  config.kafka_auto_offset_reset,
            "enable.auto.commit": False,
        })
        consumer.subscribe([config.kafka_topic_decisions])
        logger.info("Decision sink started — consuming from %s", config.kafka_topic_decisions)

        batch: List[Dict] = []
        last_flush = time.monotonic()

        while not self._stop.is_set():
            msg = consumer.poll(timeout=0.5)

            if msg is not None and not msg.error():
                try:
                    raw  = json.loads(msg.value().decode())
                    row  = parse_decision(raw)
                    batch.append(row)
                except Exception as e:
                    logger.warning("Parse error: %s", e)

            elapsed = time.monotonic() - last_flush
            if len(batch) >= config.batch_size or (batch and elapsed >= config.batch_timeout):
                self._flush(batch, consumer)
                batch = []
                last_flush = time.monotonic()

        if batch:
            self._flush(batch, consumer)
        consumer.close()
        logger.info("Decision sink stopped")

    def _flush(self, batch: List[Dict], consumer):
        n_pg = self.pg.write_batch(batch) if self.pg else 0
        n_ch = self.ch.write_batch(batch) if self.ch else 0
        logger.info("Flushed %d decisions → pg=%d ch=%d", len(batch), n_pg, n_ch)
        consumer.commit(asynchronous=False)

    def stop(self):
        self._stop.set()


if __name__ == "__main__":
    logging.basicConfig(
        level=getattr(logging, config.log_level.upper(), logging.INFO),
        format="%(asctime)s | %(levelname)-8s | %(message)s",
    )
    sink = DecisionSink()
    sink.connect()

    def _shutdown(s, f):
        logger.info("Shutdown signal received"); sink.stop()

    signal.signal(signal.SIGINT,  _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)
    sink.run()
