"""
config.py — Stage 1 Fast Risk Estimation service configuration.
All parameters overridable at runtime via environment variables.
"""
from __future__ import annotations
import os
from dataclasses import dataclass, field
from typing import List


@dataclass
class Stage1Config:

    # -------------------------------------------------------------------------
    # Service identity
    # -------------------------------------------------------------------------
    service_name:    str = "stage1-fast-risk"
    service_version: str = "1.0.0"
    host:            str = os.getenv("HOST", "0.0.0.0")
    port:            int = int(os.getenv("PORT", "8100"))
    workers:         int = int(os.getenv("UVICORN_WORKERS", "2"))

    # -------------------------------------------------------------------------
    # Kafka
    # -------------------------------------------------------------------------
    kafka_bootstrap_servers: str = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
    kafka_topic_enriched:    str = os.getenv("KAFKA_TOPIC_ENRICHED",  "txn-enriched")
    kafka_topic_stage1:      str = os.getenv("KAFKA_TOPIC_STAGE1",    "txn-stage1")
    kafka_consumer_group:    str = os.getenv("KAFKA_CONSUMER_GROUP",  "stage1-service-v1")
    kafka_auto_offset_reset: str = os.getenv("KAFKA_AUTO_OFFSET_RESET", "latest")
    kafka_enabled:           bool = os.getenv("KAFKA_ENABLED", "true").lower() == "true"

    # -------------------------------------------------------------------------
    # MLflow — model registry
    # -------------------------------------------------------------------------
    mlflow_tracking_uri:  str = os.getenv("MLFLOW_TRACKING_URI", "http://localhost:5000")
    mlflow_experiment:    str = os.getenv("MLFLOW_EXPERIMENT",   "fraud_detection_v1")
    mlflow_model_name:    str = os.getenv("MLFLOW_MODEL_NAME",   "stage1_lgbm")
    mlflow_model_stage:   str = os.getenv("MLFLOW_MODEL_STAGE",  "Production")

    # -------------------------------------------------------------------------
    # MinIO — artifact store (used when MLflow artifact root is S3)
    # -------------------------------------------------------------------------
    minio_endpoint:   str = os.getenv("MINIO_ENDPOINT",   "http://localhost:9001")
    minio_access_key: str = os.getenv("MINIO_ACCESS_KEY", "fraud_minio")
    minio_secret_key: str = os.getenv("MINIO_SECRET_KEY", "fraud_minio_2024")

    # -------------------------------------------------------------------------
    # Model initialisation strategy
    # -------------------------------------------------------------------------
    # "train"  → always retrain from synthetic data
    # "load"   → always load from MLflow (fails if no model registered)
    # "auto"   → load from MLflow if available, else train from scratch
    model_init_strategy: str = os.getenv("MODEL_INIT_STRATEGY", "auto")

    # -------------------------------------------------------------------------
    # LightGBM training hyperparameters
    # -------------------------------------------------------------------------
    lgbm_n_estimators:    int   = int(os.getenv("LGBM_N_ESTIMATORS",   "300"))
    lgbm_learning_rate:   float = float(os.getenv("LGBM_LEARNING_RATE", "0.05"))
    lgbm_num_leaves:      int   = int(os.getenv("LGBM_NUM_LEAVES",     "63"))
    lgbm_max_depth:       int   = int(os.getenv("LGBM_MAX_DEPTH",      "6"))
    lgbm_min_child_samples: int = int(os.getenv("LGBM_MIN_CHILD",      "20"))
    lgbm_scale_pos_weight: float = float(os.getenv("LGBM_SCALE_POS",   "19.0"))
    lgbm_n_jobs:          int   = int(os.getenv("LGBM_N_JOBS",         "2"))

    # Training data — synthetic samples to generate
    train_samples:        int   = int(os.getenv("TRAIN_SAMPLES",        "50000"))
    train_fraud_rate:     float = float(os.getenv("TRAIN_FRAUD_RATE",   "0.05"))
    train_val_split:      float = float(os.getenv("TRAIN_VAL_SPLIT",    "0.2"))
    random_seed:          int   = int(os.getenv("RANDOM_SEED",          "42"))

    # -------------------------------------------------------------------------
    # Conformal Prediction calibration
    # -------------------------------------------------------------------------
    # Significance level α — P(true label NOT in prediction set) ≤ α
    # α=0.05 → 95% coverage guarantee
    conformal_alpha:       float = float(os.getenv("CONFORMAL_ALPHA",      "0.05"))
    conformal_cal_samples: int   = int(os.getenv("CONFORMAL_CAL_SAMPLES",  "5000"))

    # -------------------------------------------------------------------------
    # Decision thresholds (Stage 1 gating)
    # -------------------------------------------------------------------------
    # p_fraud < theta_low  → EARLY EXIT → Approve (bypass Stage 2+3)
    # p_fraud > theta_high → pass to Stage 2 as HIGH RISK
    # theta_low ≤ p ≤ theta_high → pass to Stage 2 as UNCERTAIN
    theta_low:  float = float(os.getenv("THETA_LOW",  "0.10"))
    theta_high: float = float(os.getenv("THETA_HIGH", "0.70"))

    # Uncertainty threshold: if uncertainty > this, escalate regardless of p_fraud
    uncertainty_escalate: float = float(os.getenv("UNCERTAINTY_ESCALATE", "0.30"))

    # -------------------------------------------------------------------------
    # Feature names (canonical order — must match FeatureVector.to_feature_array)
    # -------------------------------------------------------------------------
    feature_names: List[str] = field(default_factory=lambda: [
        # Velocity (8)
        "txn_count_1m", "txn_count_5m", "txn_count_1h", "txn_count_24h",
        "amount_sum_1m", "amount_sum_5m", "amount_sum_1h", "amount_sum_24h",
        # Geography (3)
        "geo_velocity_kmh", "is_new_country", "unique_countries_24h",
        # Device & Network (4)
        "device_trust_score", "is_new_device", "ip_txn_count_1h", "unique_devices_24h",
        # Behavioral (3)
        "amount_vs_avg_ratio", "merchant_familiarity", "hours_since_last_txn",
    ])

    # -------------------------------------------------------------------------
    # Observability
    # -------------------------------------------------------------------------
    log_level:    str = os.getenv("LOG_LEVEL",    "INFO")
    metrics_port: int = int(os.getenv("METRICS_PORT", "9103"))


config = Stage1Config()
