"""
processor.py
Per-transaction feature pipeline.

Orchestrates all 4 feature groups in the correct order:
  1. Parse raw Kafka event
  2. Velocity  (Redis ZSET, write-then-read)
  3. Geography (Redis KV + Set, read-then-write)
  4. Device/Network (Redis ZSET + Hash, read-then-write)
  5. Behavioral (Redis Hash, read-then-write)
  6. Assemble FeatureVector
  7. Publish to txn-enriched topic

Read-then-write ordering for Geography/Device/Behavioral ensures the
state BEFORE this transaction is used as the feature (not contaminated
by the current event). Velocity is write-then-read because count-after-
insert is the correct semantics for velocity (this txn is part of the window).
"""
from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from typing import Dict, Optional

from confluent_kafka import Producer, Consumer, KafkaException, KafkaError
from prometheus_client import Counter, Histogram, Gauge

from config import config
from features.registry import FeatureVector
from features.velocity import VelocityFeatures
from features.geography import GeographyFeatures
from features.device_network import DeviceNetworkFeatures
from features.behavioral import BehavioralFeatures
from store.redis_store import RedisStore

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Prometheus metrics
# ---------------------------------------------------------------------------
TXN_PROCESSED = Counter(
    "feature_engine_txn_processed_total",
    "Total transactions enriched",
)
TXN_ERRORS = Counter(
    "feature_engine_txn_errors_total",
    "Total processing errors",
    ["stage"],
)
FEATURE_LATENCY = Histogram(
    "feature_engine_latency_ms",
    "End-to-end feature computation latency in ms",
    buckets=[1, 2, 5, 10, 20, 50, 100, 200],
)
COLD_STARTS = Counter(
    "feature_engine_cold_starts_total",
    "Transactions with cold-start (no history)",
)
GEO_VELOCITY_HIGH = Counter(
    "feature_engine_geo_velocity_high_total",
    "Transactions with geo velocity exceeding threshold",
)


class FeatureProcessor:
    """
    Stateless processor: all state lives in Redis.
    Instantiate one per worker thread; each gets its own Kafka consumer.
    """

    def __init__(self, worker_id: int, redis_store: RedisStore):
        self.worker_id = worker_id
        self.store     = redis_store

        # Feature computers
        self.velocity  = VelocityFeatures(redis_store)
        self.geography = GeographyFeatures(redis_store)
        self.device_net= DeviceNetworkFeatures(redis_store)
        self.behavioral= BehavioralFeatures(redis_store)

        # Kafka consumer (one per worker, own partition assignment)
        self._consumer: Optional[Consumer] = None
        # Kafka producer (shared logic for publishing enriched events)
        self._producer: Optional[Producer] = None

    # -------------------------------------------------------------------------
    # Kafka connection
    # -------------------------------------------------------------------------

    def connect(self):
        self._consumer = Consumer({
            "bootstrap.servers":       config.kafka_bootstrap_servers,
            "group.id":                config.kafka_consumer_group,
            "auto.offset.reset":       config.kafka_auto_offset_reset,
            "enable.auto.commit":      False,   # manual commit after processing
            "max.poll.interval.ms":    300_000,
            "session.timeout.ms":      30_000,
            "fetch.max.bytes":         52_428_800,
            "max.partition.fetch.bytes": 1_048_576,
        })
        self._consumer.subscribe([config.kafka_topic_raw])

        self._producer = Producer({
            "bootstrap.servers":    config.kafka_bootstrap_servers,
            "acks":                 "1",
            "compression.type":     "lz4",
            "linger.ms":            "5",
            "batch.size":           "65536",
        })

        logger.info(
            "Worker %d connected | consumer-group=%s | input=%s | output=%s",
            self.worker_id, config.kafka_consumer_group,
            config.kafka_topic_raw, config.kafka_topic_enriched,
        )

    # -------------------------------------------------------------------------
    # Main consume loop
    # -------------------------------------------------------------------------

    def run(self, stop_event):
        """Blocking consume loop. Call from a thread."""
        logger.info("Worker %d starting consume loop", self.worker_id)
        batch: list[Message] = []

        try:
            while not stop_event.is_set():
                msg = self._consumer.poll(timeout=0.5)

                if msg is None:
                    if batch:
                        self._flush_batch(batch)
                        batch = []
                    continue

                if msg.error():
                    if msg.error().code() == KafkaError._PARTITION_EOF:
                        continue
                    logger.error("Consumer error: %s", msg.error())
                    TXN_ERRORS.labels(stage="consume").inc()
                    continue

                batch.append(msg)

                if len(batch) >= config.batch_size:
                    self._flush_batch(batch)
                    batch = []

        except Exception as e:
            logger.exception("Worker %d fatal error: %s", self.worker_id, e)
        finally:
            if batch:
                self._flush_batch(batch)
            self._consumer.close()
            logger.info("Worker %d stopped", self.worker_id)

    def _flush_batch(self, messages: list):
        """Process a batch of raw messages."""
        offsets = []
        for msg in messages:
            try:
                raw = json.loads(msg.value().decode("utf-8"))
                fv  = self.process_one(raw)
                self._publish_enriched(fv)
                offsets.append(msg)
                TXN_PROCESSED.inc()
            except Exception as e:
                TXN_ERRORS.labels(stage="process").inc()
                logger.warning("Worker %d failed to process message: %s", self.worker_id, e)

        # Commit the batch offset after all messages processed
        if offsets:
            self._consumer.commit(offsets[-1], asynchronous=False)
        self._producer.poll(0)

    # -------------------------------------------------------------------------
    # Single transaction feature pipeline
    # -------------------------------------------------------------------------

    def process_one(self, raw: Dict) -> FeatureVector:
        """
        Run the complete 4-group feature pipeline for one transaction.
        Returns an enriched FeatureVector.
        """
        t_start = time.perf_counter()

        # --- Parse raw event ---
        fv = FeatureVector.from_raw_event(raw)

        # Parse txn_ts to Unix float
        try:
            dt     = datetime.fromisoformat(fv.txn_ts.replace("Z", "+00:00"))
            txn_ts = dt.timestamp()
        except Exception:
            txn_ts = time.time()

        cold_start = False

        # --- Group 1: Velocity ---
        try:
            v_feats = self.velocity.compute(
                customer_id=fv.customer_id,
                amount=fv.amount,
                txn_ts=txn_ts,
            )
            fv.txn_count_1m   = v_feats.get("txn_count_1m",  1)
            fv.txn_count_5m   = v_feats.get("txn_count_5m",  1)
            fv.txn_count_1h   = v_feats.get("txn_count_1h",  1)
            fv.txn_count_24h  = v_feats.get("txn_count_24h", 1)
            fv.amount_sum_1m  = v_feats.get("amount_sum_1m",  fv.amount)
            fv.amount_sum_5m  = v_feats.get("amount_sum_5m",  fv.amount)
            fv.amount_sum_1h  = v_feats.get("amount_sum_1h",  fv.amount)
            fv.amount_sum_24h = v_feats.get("amount_sum_24h", fv.amount)
            if fv.txn_count_24h <= 1:
                cold_start = True
        except Exception as e:
            TXN_ERRORS.labels(stage="velocity").inc()
            cold_start = True

        # --- Group 2: Geography ---
        try:
            g_feats = self.geography.compute(
                customer_id=fv.customer_id,
                country_code=fv.country_code,
                lat=fv.lat,
                lng=fv.lng,
                txn_ts=txn_ts,
            )
            fv.geo_velocity_kmh     = g_feats.get("geo_velocity_kmh",     0.0)
            fv.is_new_country       = g_feats.get("is_new_country",       False)
            fv.unique_countries_24h = g_feats.get("unique_countries_24h", 1)

            if fv.geo_velocity_kmh > config.geo_impossible_speed_kmh:
                GEO_VELOCITY_HIGH.inc()
        except Exception as e:
            TXN_ERRORS.labels(stage="geography").inc()

        # --- Group 3: Device & Network ---
        try:
            d_feats = self.device_net.compute(
                customer_id=fv.customer_id,
                device_id=fv.device_id,
                ip_address=fv.ip_address,
                txn_id=fv.txn_id,
                txn_ts=txn_ts,
            )
            fv.device_trust_score = d_feats.get("device_trust_score", 0.5)
            fv.is_new_device      = d_feats.get("is_new_device",      False)
            fv.ip_txn_count_1h   = d_feats.get("ip_txn_count_1h",    0)
            fv.unique_devices_24h = d_feats.get("unique_devices_24h", 1)
        except Exception as e:
            TXN_ERRORS.labels(stage="device_network").inc()

        # --- Group 4: Behavioral ---
        try:
            # Use customer's declared avg from profile as cold-start fallback
            clv_avg = fv.clv / max(fv.account_age_days, 1) * 30
            b_feats = self.behavioral.compute(
                customer_id=fv.customer_id,
                amount=fv.amount,
                merchant_id=fv.merchant_id,
                txn_ts=txn_ts,
                customer_clv_avg=clv_avg,
            )
            fv.amount_vs_avg_ratio  = b_feats.get("amount_vs_avg_ratio",  1.0)
            fv.merchant_familiarity = b_feats.get("merchant_familiarity",  0.0)
            fv.hours_since_last_txn = b_feats.get("hours_since_last_txn", 24.0)
        except Exception as e:
            TXN_ERRORS.labels(stage="behavioral").inc()

        # --- Metadata ---
        elapsed_ms          = (time.perf_counter() - t_start) * 1000
        fv.feature_latency_ms = round(elapsed_ms, 3)
        fv.has_cold_start     = cold_start

        if cold_start:
            COLD_STARTS.inc()

        FEATURE_LATENCY.observe(elapsed_ms)
        return fv

    # -------------------------------------------------------------------------
    # Publish enriched event
    # -------------------------------------------------------------------------

    def _publish_enriched(self, fv: FeatureVector):
        try:
            self._producer.produce(
                topic   = config.kafka_topic_enriched,
                key     = fv.partition_key,
                value   = fv.to_kafka_bytes(),
            )
        except BufferError:
            self._producer.poll(0.1)
            self._producer.produce(
                topic   = config.kafka_topic_enriched,
                key     = fv.partition_key,
                value   = fv.to_kafka_bytes(),
            )
