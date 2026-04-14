"""dataset-pipeline/config.py — Dataset export configuration."""
from __future__ import annotations
import os
from dataclasses import dataclass, field
from typing import List


@dataclass
class DatasetConfig:
    # PostgreSQL
    postgres_dsn: str = os.getenv(
        "POSTGRES_DSN",
        "postgresql://fraud_admin:fraud_secret_2024@postgres:5432/fraud_db"
    )

    # ClickHouse
    clickhouse_host:     str = os.getenv("CLICKHOUSE_HOST",     "clickhouse")
    clickhouse_port:     int = int(os.getenv("CLICKHOUSE_PORT", "9000"))
    clickhouse_user:     str = os.getenv("CLICKHOUSE_USER",     "default")
    clickhouse_password: str = os.getenv("CLICKHOUSE_PASSWORD", "")
    clickhouse_db:       str = os.getenv("CLICKHOUSE_DB",       "fraud_analytics")

    # MinIO — dataset output bucket
    minio_endpoint:      str = os.getenv("MINIO_ENDPOINT",      "http://minio:9000")
    minio_access_key:    str = os.getenv("MINIO_ACCESS_KEY",    "fraud_minio")
    minio_secret_key:    str = os.getenv("MINIO_SECRET_KEY",    "fraud_minio_2024")
    minio_bucket:        str = os.getenv("MINIO_DATASET_BUCKET","datasets")

    # Output paths (local working dir inside container)
    output_dir:          str = os.getenv("OUTPUT_DIR", "/tmp/dataset_export")

    # Anonymisation
    anon_salt:           str = os.getenv("ANON_SALT", "fraud-anon-salt-2024")
    anon_ip_mask_octets: int = int(os.getenv("ANON_IP_MASK", "2"))  # mask last N octets

    # Synthetic dataset
    synthetic_rows:      int   = int(os.getenv("SYNTHETIC_ROWS",   "100000"))
    synthetic_fraud_rate:float = float(os.getenv("SYNTHETIC_FRAUD_RATE", "0.05"))
    synthetic_seed:      int   = int(os.getenv("SYNTHETIC_SEED",   "42"))

    # Real export — how many days back
    real_export_days:    int = int(os.getenv("REAL_EXPORT_DAYS", "30"))
    real_max_rows:       int = int(os.getenv("REAL_MAX_ROWS",    "500000"))

    # Dataset version (semver, incremented per release)
    dataset_version:     str = os.getenv("DATASET_VERSION", "1.0.0")

    # Feature names canonical order (18 features)
    feature_names: List[str] = field(default_factory=lambda: [
        "txn_count_1m","txn_count_5m","txn_count_1h","txn_count_24h",
        "amount_sum_1m","amount_sum_5m","amount_sum_1h","amount_sum_24h",
        "geo_velocity_kmh","is_new_country","unique_countries_24h",
        "device_trust_score","is_new_device","ip_txn_count_1h","unique_devices_24h",
        "amount_vs_avg_ratio","merchant_familiarity","hours_since_last_txn",
    ])

    log_level: str = os.getenv("LOG_LEVEL", "INFO")


config = DatasetConfig()
