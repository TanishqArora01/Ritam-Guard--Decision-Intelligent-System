"""
config.py — Stage 2 Deep Intelligence service configuration.
All parameters overridable at runtime via environment variables.
"""
from __future__ import annotations
import os
from dataclasses import dataclass, field
from typing import List


@dataclass
class Stage2Config:

    service_name:    str = "stage2-deep-intelligence"
    service_version: str = "1.0.0"
    host:            str = os.getenv("HOST", "0.0.0.0")
    port:            int = int(os.getenv("PORT", "8200"))

    # Kafka
    kafka_bootstrap_servers: str  = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
    kafka_topic_stage1:      str  = os.getenv("KAFKA_TOPIC_STAGE1",   "txn-stage1")
    kafka_topic_stage2:      str  = os.getenv("KAFKA_TOPIC_STAGE2",   "txn-stage2")
    kafka_consumer_group:    str  = os.getenv("KAFKA_CONSUMER_GROUP", "stage2-service-v1")
    kafka_auto_offset_reset: str  = os.getenv("KAFKA_AUTO_OFFSET_RESET", "latest")
    kafka_enabled:           bool = os.getenv("KAFKA_ENABLED", "true").lower() == "true"

    # MLflow
    mlflow_tracking_uri: str = os.getenv("MLFLOW_TRACKING_URI", "http://localhost:5000")
    mlflow_experiment:   str = os.getenv("MLFLOW_EXPERIMENT",   "fraud_detection_v1")
    mlflow_xgb_name:     str = os.getenv("MLFLOW_XGB_NAME",     "stage2_xgboost")
    mlflow_mlp_name:     str = os.getenv("MLFLOW_MLP_NAME",     "stage2_mlp")
    mlflow_ae_name:      str = os.getenv("MLFLOW_AE_NAME",      "stage2_autoencoder")
    mlflow_model_stage:  str = os.getenv("MLFLOW_MODEL_STAGE",  "Production")
    model_init_strategy: str = os.getenv("MODEL_INIT_STRATEGY", "auto")

    # Neo4j
    neo4j_uri:      str  = os.getenv("NEO4J_URI",      "bolt://localhost:7687")
    neo4j_user:     str  = os.getenv("NEO4J_USER",     "neo4j")
    neo4j_password: str  = os.getenv("NEO4J_PASSWORD", "fraud_neo4j_2024")
    neo4j_database: str  = os.getenv("NEO4J_DATABASE", "neo4j")
    neo4j_timeout:  int  = int(os.getenv("NEO4J_TIMEOUT", "5"))
    neo4j_enabled:  bool = os.getenv("NEO4J_ENABLED", "true").lower() == "true"

    # Graph thresholds
    fraud_ring_min_shared:    int = int(os.getenv("FRAUD_RING_MIN_SHARED",   "2"))
    mule_indegree_threshold:  int = int(os.getenv("MULE_INDEGREE_THRESHOLD", "10"))
    synthetic_id_age_days:    int = int(os.getenv("SYNTHETIC_ID_AGE_DAYS",   "30"))
    velocity_burst_window_min:int = int(os.getenv("VELOCITY_BURST_WINDOW",   "5"))
    velocity_burst_threshold: int = int(os.getenv("VELOCITY_BURST_THRESHOLD","5"))
    multi_hop_max_depth:      int = int(os.getenv("MULTI_HOP_MAX_DEPTH",     "3"))

    # XGBoost
    xgb_n_estimators:     int   = int(os.getenv("XGB_N_ESTIMATORS",  "400"))
    xgb_learning_rate:    float = float(os.getenv("XGB_LR",          "0.05"))
    xgb_max_depth:        int   = int(os.getenv("XGB_MAX_DEPTH",     "6"))
    xgb_subsample:        float = float(os.getenv("XGB_SUBSAMPLE",   "0.8"))
    xgb_colsample:        float = float(os.getenv("XGB_COLSAMPLE",   "0.8"))
    xgb_scale_pos_weight: float = float(os.getenv("XGB_SCALE_POS",  "19.0"))
    xgb_n_jobs:           int   = int(os.getenv("XGB_N_JOBS",        "2"))

    # PyTorch MLP
    mlp_hidden_dims: List[int] = field(default_factory=lambda: [128, 64, 32])
    mlp_dropout:     float     = float(os.getenv("MLP_DROPOUT",  "0.3"))
    mlp_lr:          float     = float(os.getenv("MLP_LR",       "0.001"))
    mlp_epochs:      int       = int(os.getenv("MLP_EPOCHS",     "30"))
    mlp_batch_size:  int       = int(os.getenv("MLP_BATCH_SIZE", "512"))

    # Autoencoder
    ae_encoding_dims: List[int] = field(default_factory=lambda: [18, 12, 6, 12, 18])
    ae_lr:            float     = float(os.getenv("AE_LR",         "0.001"))
    ae_epochs:        int       = int(os.getenv("AE_EPOCHS",       "30"))
    ae_batch_size:    int       = int(os.getenv("AE_BATCH_SIZE",   "256"))
    ae_contamination: float     = float(os.getenv("AE_CONTAMINATION","0.05"))

    # Isolation Forest
    if_n_estimators:  int   = int(os.getenv("IF_N_ESTIMATORS",    "200"))
    if_contamination: float = float(os.getenv("IF_CONTAMINATION", "0.05"))
    if_n_jobs:        int   = int(os.getenv("IF_N_JOBS",          "2"))

    # Anomaly combiner weights
    anomaly_ae_weight: float = float(os.getenv("ANOMALY_AE_WEIGHT", "0.6"))
    anomaly_if_weight: float = float(os.getenv("ANOMALY_IF_WEIGHT", "0.4"))

    # Ensemble fusion weights — must sum to 1.0
    ensemble_xgb_weight:     float = float(os.getenv("ENSEMBLE_XGB_WEIGHT",    "0.40"))
    ensemble_mlp_weight:     float = float(os.getenv("ENSEMBLE_MLP_WEIGHT",    "0.35"))
    ensemble_anomaly_weight: float = float(os.getenv("ENSEMBLE_ANOMALY_WEIGHT","0.15"))
    ensemble_graph_weight:   float = float(os.getenv("ENSEMBLE_GRAPH_WEIGHT",  "0.10"))

    # Training
    train_samples:    int   = int(os.getenv("TRAIN_SAMPLES",    "60000"))
    train_fraud_rate: float = float(os.getenv("TRAIN_FRAUD_RATE","0.05"))
    random_seed:      int   = int(os.getenv("RANDOM_SEED",      "42"))

    # Feature names — canonical 18, same order as Stage 1
    feature_names: List[str] = field(default_factory=lambda: [
        "txn_count_1m","txn_count_5m","txn_count_1h","txn_count_24h",
        "amount_sum_1m","amount_sum_5m","amount_sum_1h","amount_sum_24h",
        "geo_velocity_kmh","is_new_country","unique_countries_24h",
        "device_trust_score","is_new_device","ip_txn_count_1h","unique_devices_24h",
        "amount_vs_avg_ratio","merchant_familiarity","hours_since_last_txn",
    ])

    log_level:    str = os.getenv("LOG_LEVEL",    "INFO")
    metrics_port: int = int(os.getenv("METRICS_PORT", "9104"))


config = Stage2Config()
