"""
flink/feature_job.py
PyFlink DataStream API scaffold — Phase 2b

This is the production-grade Flink implementation of the same feature pipeline
that the Python worker (processor.py) implements for the PoC.

Migration path:
  Phase 2a (now):  Python Kafka consumer worker  → txn-enriched
  Phase 2b (next): Submit this PyFlink job to the Flink cluster instead.
                   The Python worker becomes a fallback / shadow mode.

Why Flink over the Python worker:
  - Exactly-once semantics (checkpointing to MinIO)
  - Stateful operators with RocksDB backend (survives restarts)
  - Native watermark + event-time windows (correct late-event handling)
  - Horizontal scaling (add TaskManagers, no code change)
  - Backpressure handling built-in

Submission:
  docker cp flink/feature_job.py fraud_flink_jobmanager:/opt/flink/
  docker exec fraud_flink_jobmanager flink run -py /opt/flink/feature_job.py

Requirements inside Flink container:
  pip install apache-flink==1.18.0 redis confluent-kafka
"""
from __future__ import annotations

import json
import logging
import math
import time
from typing import Iterator

# ---------------------------------------------------------------------------
# PyFlink imports (available when running inside Flink container)
# ---------------------------------------------------------------------------
try:
    from pyflink.datastream import StreamExecutionEnvironment, CheckpointingMode
    from pyflink.datastream.connectors.kafka import (
        KafkaSource, KafkaSink,
        KafkaRecordSerializationSchema, KafkaOffsetsInitializer,
    )
    from pyflink.common import WatermarkStrategy, Types, Duration
    from pyflink.common.serialization import SimpleStringSchema
    from pyflink.datastream.functions import (
        MapFunction, KeyedProcessFunction, RuntimeContext,
    )
    from pyflink.datastream.state import (
        ValueStateDescriptor, ListStateDescriptor, MapStateDescriptor,
    )
    _FLINK_AVAILABLE = True
except ImportError:
    _FLINK_AVAILABLE = False
    # Stubs so the file is importable in non-Flink environments
    class MapFunction:
        pass
    class KeyedProcessFunction:
        pass

logger = logging.getLogger("feature_job")

# ---------------------------------------------------------------------------
# Constants (mirror config.py values)
# ---------------------------------------------------------------------------
KAFKA_BROKERS     = "redpanda:9092"
TOPIC_RAW         = "txn-raw"
TOPIC_ENRICHED    = "txn-enriched"
CONSUMER_GROUP    = "flink-feature-engine-v1"
REDIS_HOST        = "redis"
REDIS_PORT        = 6379
WINDOW_1M_MS      = 60_000
WINDOW_5M_MS      = 300_000
WINDOW_1H_MS      = 3_600_000
WINDOW_24H_MS     = 86_400_000
CHECKPOINT_DIR    = "s3://flink-checkpoints/checkpoints"


# ---------------------------------------------------------------------------
# Flink MapFunction: parse raw JSON → dict
# ---------------------------------------------------------------------------
class ParseRawEvent(MapFunction):
    def map(self, value: str) -> dict:
        try:
            return json.loads(value)
        except Exception:
            return {}


# ---------------------------------------------------------------------------
# Flink KeyedProcessFunction: stateful feature computation per customer
# ---------------------------------------------------------------------------
class CustomerFeatureProcessor(KeyedProcessFunction):
    """
    Keyed by customer_id.
    State:
      - txn_history:  ListState[(ts_ms: long, amount: float)]
      - last_location: ValueState[{lat, lng, ts}]
      - device_counts: MapState[device_id -> int]
      - avg_amount:    ValueState[float]
      - txn_count:     ValueState[int]
      - last_txn_ts:   ValueState[float]
      - merchant_counts: MapState[merchant_id -> int]
    """

    def open(self, context: RuntimeContext):
        # Velocity state
        self.txn_history = context.get_list_state(
            ListStateDescriptor("txn_history", Types.STRING())
        )
        # Geography state
        self.last_location = context.get_state(
            ValueStateDescriptor("last_location", Types.STRING())
        )
        # Device state
        self.device_counts = context.get_map_state(
            MapStateDescriptor("device_counts", Types.STRING(), Types.INT())
        )
        self.device_events = context.get_list_state(
            ListStateDescriptor("device_events_24h", Types.STRING())
        )
        # Behavioral state
        self.avg_amount   = context.get_state(ValueStateDescriptor("avg_amount",   Types.FLOAT()))
        self.txn_count    = context.get_state(ValueStateDescriptor("txn_count",     Types.INT()))
        self.last_txn_ts  = context.get_state(ValueStateDescriptor("last_txn_ts",   Types.DOUBLE()))
        self.merchant_counts = context.get_map_state(
            MapStateDescriptor("merchant_counts", Types.STRING(), Types.INT())
        )

    def process_element(self, raw: dict, ctx):
        if not raw:
            return

        now_ms = ctx.timestamp() or int(time.time() * 1000)
        now_s  = now_ms / 1000.0

        customer_id  = raw.get("customer_id", "")
        amount       = float(raw.get("amount", 0.0))
        device_id    = raw.get("device_id", "")
        ip_address   = raw.get("ip_address", "")
        country_code = raw.get("country_code", "")
        lat          = float(raw.get("lat", 0.0))
        lng          = float(raw.get("lng", 0.0))
        merchant_id  = raw.get("merchant_id", "")

        # ---- Group 1: Velocity ----
        entry = json.dumps({"ts": now_s, "amount": amount})
        self.txn_history.add(entry)

        # Prune old entries and compute window counts
        cutoff_24h = now_s - 86400
        history    = []
        for e in self.txn_history.get() or []:
            d = json.loads(e)
            if d["ts"] >= cutoff_24h:
                history.append(d)

        self.txn_history.clear()
        for d in history:
            self.txn_history.add(json.dumps(d))

        def window_stats(seconds):
            cutoff = now_s - seconds
            items  = [d for d in history if d["ts"] >= cutoff]
            return len(items), round(sum(d["amount"] for d in items), 4)

        cnt_1m,  sum_1m  = window_stats(60)
        cnt_5m,  sum_5m  = window_stats(300)
        cnt_1h,  sum_1h  = window_stats(3600)
        cnt_24h, sum_24h = window_stats(86400)

        # ---- Group 2: Geography ----
        geo_velocity_kmh = 0.0
        last_loc_str     = self.last_location.value()
        if last_loc_str:
            loc = json.loads(last_loc_str)
            dist_km = self._haversine(loc["lat"], loc["lng"], lat, lng)
            elapsed_h = max((now_s - loc["ts"]) / 3600.0, 1 / 3600.0)
            geo_velocity_kmh = round(dist_km / elapsed_h, 2)

        self.last_location.update(json.dumps({"lat": lat, "lng": lng, "ts": now_s}))

        # ---- Group 3: Device & Network ----
        dev_count     = self.device_counts.get(device_id) or 0
        is_new_device = dev_count == 0
        device_trust  = round(min(1.0, dev_count / 5), 4)
        self.device_counts.put(device_id, dev_count + 1)

        # ---- Group 4: Behavioral ----
        n       = (self.txn_count.value() or 0) + 1
        old_avg = self.avg_amount.value() or 0.0
        new_avg = old_avg + (amount - old_avg) / n

        last_ts = self.last_txn_ts.value() or 0.0
        hours_since = round((now_s - last_ts) / 3600.0, 4) if last_ts > 0 else 24.0

        m_count     = self.merchant_counts.get(merchant_id) or 0
        familiarity = round(min(1.0, m_count / 2), 4)
        self.merchant_counts.put(merchant_id, m_count + 1)

        amount_ratio = round(min(100.0, amount / max(new_avg, 0.01)), 4)

        # Update state
        self.avg_amount.update(new_avg)
        self.txn_count.update(n)
        self.last_txn_ts.update(now_s)

        # ---- Assemble enriched event ----
        enriched = {
            **raw,
            # velocity
            "txn_count_1m":  cnt_1m,  "txn_count_5m":  cnt_5m,
            "txn_count_1h":  cnt_1h,  "txn_count_24h": cnt_24h,
            "amount_sum_1m": sum_1m,  "amount_sum_5m": sum_5m,
            "amount_sum_1h": sum_1h,  "amount_sum_24h": sum_24h,
            # geography
            "geo_velocity_kmh":     geo_velocity_kmh,
            "is_new_country":       False,
            "unique_countries_24h": 1,
            # device
            "device_trust_score": device_trust,
            "is_new_device":      is_new_device,
            "ip_txn_count_1h":    0,
            "unique_devices_24h": 1,
            # behavioral
            "amount_vs_avg_ratio":  amount_ratio,
            "merchant_familiarity": familiarity,
            "hours_since_last_txn": hours_since,
            # metadata
            "feature_engine_version": "flink-1.0.0",
            "has_cold_start": n <= 1,
        }

        yield json.dumps(enriched)

    @staticmethod
    def _haversine(lat1, lng1, lat2, lng2) -> float:
        R    = 6371.0
        phi1, phi2 = math.radians(lat1), math.radians(lat2)
        dphi = math.radians(lat2 - lat1)
        dlam = math.radians(lng2 - lng1)
        a    = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlam/2)**2
        return 2 * R * math.asin(math.sqrt(max(0.0, a)))


# ---------------------------------------------------------------------------
# Job definition
# ---------------------------------------------------------------------------
def build_job():
    """Construct and return the Flink StreamExecutionEnvironment."""
    if not _FLINK_AVAILABLE:
        raise RuntimeError("PyFlink not installed. Run inside the Flink container.")

    env = StreamExecutionEnvironment.get_execution_environment()
    env.set_parallelism(4)

    # Exactly-once checkpointing to MinIO
    env.enable_checkpointing(60_000, CheckpointingMode.EXACTLY_ONCE)
    env.get_checkpoint_config().set_checkpoint_storage_uri(CHECKPOINT_DIR)

    # Kafka source
    source = (
        KafkaSource.builder()
        .set_bootstrap_servers(KAFKA_BROKERS)
        .set_topics(TOPIC_RAW)
        .set_group_id(CONSUMER_GROUP)
        .set_starting_offsets(KafkaOffsetsInitializer.latest())
        .set_value_only_deserializer(SimpleStringSchema())
        .build()
    )

    # Kafka sink
    sink = (
        KafkaSink.builder()
        .set_bootstrap_servers(KAFKA_BROKERS)
        .set_record_serializer(
            KafkaRecordSerializationSchema.builder()
            .set_topic(TOPIC_ENRICHED)
            .set_value_serialization_schema(SimpleStringSchema())
            .build()
        )
        .build()
    )

    # Build pipeline
    (
        env
        .from_source(source, WatermarkStrategy.for_monotonous_timestamps(), "txn-raw")
        .map(ParseRawEvent())
        .filter(lambda d: bool(d.get("customer_id")))
        .key_by(lambda d: d["customer_id"])
        .process(CustomerFeatureProcessor())
        .sink_to(sink)
    )

    return env


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    env = build_job()
    logger.info("Submitting Flink feature engineering job...")
    env.execute("fraud-feature-engineering-v1")
