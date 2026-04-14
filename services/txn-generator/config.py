"""
config.py — Environment-driven configuration for the synthetic transaction generator.
Every parameter is overridable at runtime via env var or .env file.
"""

import os
from dataclasses import dataclass, field
from typing import Dict


@dataclass
class GeneratorConfig:
    # -------------------------------------------------------------------------
    # Kafka / Redpanda
    # -------------------------------------------------------------------------
    kafka_bootstrap_servers: str = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
    kafka_topic_raw: str         = os.getenv("KAFKA_TOPIC_RAW", "txn-raw")
    kafka_batch_size: int        = int(os.getenv("KAFKA_BATCH_SIZE", "65536"))     # bytes
    kafka_linger_ms: int         = int(os.getenv("KAFKA_LINGER_MS", "5"))
    kafka_compression: str       = os.getenv("KAFKA_COMPRESSION", "lz4")
    kafka_acks: str              = os.getenv("KAFKA_ACKS", "1")                   # 1=leader only for speed

    # -------------------------------------------------------------------------
    # Throughput control
    # -------------------------------------------------------------------------
    # TPS: transactions per second. Set 0 = unlimited (max throughput test).
    tps: int     = int(os.getenv("GENERATOR_TPS", "500"))
    # How many producer worker threads
    workers: int = int(os.getenv("GENERATOR_WORKERS", "4"))
    # Total transactions to generate. 0 = run forever.
    total_txns: int = int(os.getenv("GENERATOR_TOTAL_TXNS", "0"))

    # -------------------------------------------------------------------------
    # Fraud injection rates
    # -------------------------------------------------------------------------
    # Overall fraud rate as a fraction (0.0–1.0)
    fraud_rate: float = float(os.getenv("FRAUD_RATE", "0.05"))   # default 5%

    # Within fraud transactions, weight per pattern (auto-normalised)
    fraud_pattern_weights: Dict[str, float] = field(default_factory=lambda: {
        "card_testing":       float(os.getenv("WEIGHT_CARD_TESTING",       "0.20")),
        "account_takeover":   float(os.getenv("WEIGHT_ACCOUNT_TAKEOVER",   "0.20")),
        "velocity_attack":    float(os.getenv("WEIGHT_VELOCITY_ATTACK",     "0.20")),
        "fraud_ring":         float(os.getenv("WEIGHT_FRAUD_RING",          "0.15")),
        "geo_impossibility":  float(os.getenv("WEIGHT_GEO_IMPOSSIBILITY",   "0.15")),
        "large_amount":       float(os.getenv("WEIGHT_LARGE_AMOUNT",        "0.10")),
    })

    # -------------------------------------------------------------------------
    # Customer / merchant pool sizes
    # -------------------------------------------------------------------------
    num_customers: int    = int(os.getenv("NUM_CUSTOMERS", "2000"))
    num_merchants: int    = int(os.getenv("NUM_MERCHANTS", "500"))
    num_devices: int      = int(os.getenv("NUM_DEVICES", "3000"))
    num_ips: int          = int(os.getenv("NUM_IPS", "4000"))

    # Premium customer fraction (affects CLV and trust score)
    premium_customer_fraction: float = float(os.getenv("PREMIUM_CUSTOMER_FRACTION", "0.10"))

    # -------------------------------------------------------------------------
    # Logging / metrics
    # -------------------------------------------------------------------------
    log_level: str         = os.getenv("LOG_LEVEL", "INFO")
    metrics_port: int      = int(os.getenv("METRICS_PORT", "9101"))  # Prometheus /metrics
    stats_interval_sec: int = int(os.getenv("STATS_INTERVAL_SEC", "10"))

    # -------------------------------------------------------------------------
    # Reproducibility
    # -------------------------------------------------------------------------
    random_seed: int = int(os.getenv("RANDOM_SEED", "42"))


# Singleton config instance
config = GeneratorConfig()
