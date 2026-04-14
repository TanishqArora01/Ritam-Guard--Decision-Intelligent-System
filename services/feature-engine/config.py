"""
config.py — Environment-driven configuration for the feature engineering service.
Every parameter overridable at runtime via env var.
"""
from __future__ import annotations
import os
from dataclasses import dataclass


@dataclass
class FeatureEngineConfig:

    # -------------------------------------------------------------------------
    # Kafka / Redpanda
    # -------------------------------------------------------------------------
    kafka_bootstrap_servers: str = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
    kafka_topic_raw:         str = os.getenv("KAFKA_TOPIC_RAW",      "txn-raw")
    kafka_topic_enriched:    str = os.getenv("KAFKA_TOPIC_ENRICHED", "txn-enriched")
    kafka_consumer_group:    str = os.getenv("KAFKA_CONSUMER_GROUP", "feature-engine-v1")
    kafka_auto_offset_reset: str = os.getenv("KAFKA_AUTO_OFFSET_RESET", "latest")
    kafka_max_poll_records:  int = int(os.getenv("KAFKA_MAX_POLL_RECORDS", "500"))

    # -------------------------------------------------------------------------
    # Redis — Online Feature Store
    # -------------------------------------------------------------------------
    redis_host:     str = os.getenv("REDIS_HOST", "localhost")
    redis_port:     int = int(os.getenv("REDIS_PORT", "6379"))
    redis_db:       int = int(os.getenv("REDIS_DB", "0"))
    redis_password: str = os.getenv("REDIS_PASSWORD", "")
    redis_pool_size: int = int(os.getenv("REDIS_POOL_SIZE", "20"))

    # Feature TTLs (seconds) — how long each key lives in Redis
    ttl_velocity_1m:   int = int(os.getenv("TTL_VELOCITY_1M",   "120"))     #  2 min
    ttl_velocity_5m:   int = int(os.getenv("TTL_VELOCITY_5M",   "600"))     # 10 min
    ttl_velocity_1h:   int = int(os.getenv("TTL_VELOCITY_1H",   "7200"))    #  2 hrs
    ttl_velocity_24h:  int = int(os.getenv("TTL_VELOCITY_24H",  "172800"))  # 48 hrs
    ttl_device_trust:  int = int(os.getenv("TTL_DEVICE_TRUST",  "86400"))   # 24 hrs
    ttl_behavioral:    int = int(os.getenv("TTL_BEHAVIORAL",    "604800"))  #  7 days
    ttl_geo_history:   int = int(os.getenv("TTL_GEO_HISTORY",   "86400"))   # 24 hrs

    # -------------------------------------------------------------------------
    # MinIO — Offline Feature Store
    # -------------------------------------------------------------------------
    minio_endpoint:        str = os.getenv("MINIO_ENDPOINT",   "http://localhost:9001")
    minio_access_key:      str = os.getenv("MINIO_ACCESS_KEY", "fraud_minio")
    minio_secret_key:      str = os.getenv("MINIO_SECRET_KEY", "fraud_minio_2024")
    minio_bucket_offline:  str = os.getenv("MINIO_BUCKET_OFFLINE",   "feast-offline")
    minio_bucket_snapshots:str = os.getenv("MINIO_BUCKET_SNAPSHOTS", "feature-snapshots")
    minio_secure:          bool = os.getenv("MINIO_SECURE", "false").lower() == "true"

    # Snapshot schedule (seconds between each MinIO write)
    snapshot_interval_sec: int = int(os.getenv("SNAPSHOT_INTERVAL_SEC", "3600"))  # 1 hour

    # -------------------------------------------------------------------------
    # Worker pool
    # -------------------------------------------------------------------------
    num_workers:    int = int(os.getenv("FEATURE_ENGINE_WORKERS", "4"))
    batch_size:     int = int(os.getenv("FEATURE_ENGINE_BATCH_SIZE", "100"))

    # -------------------------------------------------------------------------
    # Observability
    # -------------------------------------------------------------------------
    log_level:    str = os.getenv("LOG_LEVEL",    "INFO")
    metrics_port: int = int(os.getenv("METRICS_PORT", "9102"))

    # -------------------------------------------------------------------------
    # Feature window sizes (seconds) — used by velocity + geo computations
    # -------------------------------------------------------------------------
    window_1m:  int = 60
    window_5m:  int = 300
    window_1h:  int = 3600
    window_24h: int = 86400

    # Geo-impossibility threshold: min speed (km/h) to flag as suspicious
    geo_impossible_speed_kmh: float = float(
        os.getenv("GEO_IMPOSSIBLE_SPEED_KMH", "800.0")
    )

    # Device trust: number of past transactions before a device is "trusted"
    device_trusted_txn_threshold: int = int(
        os.getenv("DEVICE_TRUSTED_TXN_THRESHOLD", "5")
    )

    # Merchant familiarity: minimum past visits to consider "familiar"
    merchant_familiar_threshold: int = int(
        os.getenv("MERCHANT_FAMILIAR_THRESHOLD", "2")
    )


# Singleton
config = FeatureEngineConfig()
