"""
model/trainer.py
LightGBM training pipeline for Stage 1 Fast Risk Estimation.

Generates synthetic training data using the same 18-feature schema
as the feature engineering service, trains a binary classifier,
calibrates conformal prediction, and registers the model in MLflow.

Feature engineering is intentionally embedded here so training can
run at container startup without needing the full feature pipeline.
"""
from __future__ import annotations

import logging
import os
import pickle
import time
from datetime import datetime, timezone
from typing import Dict, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Lazy imports — only required for training, not inference
# ---------------------------------------------------------------------------
try:
    import lightgbm as lgb
    from sklearn.model_selection import train_test_split
    from sklearn.metrics import roc_auc_score, precision_score, recall_score, f1_score
    _LGBM_AVAILABLE = True
except ImportError:
    _LGBM_AVAILABLE = False
    logger.error("lightgbm or scikit-learn not installed — training unavailable")

try:
    import mlflow
    import mlflow.lightgbm
    _MLFLOW_AVAILABLE = True
except ImportError:
    _MLFLOW_AVAILABLE = False
    logger.warning("mlflow not installed — model won't be registered")

from config import config


# ---------------------------------------------------------------------------
# Synthetic feature data generator
# ---------------------------------------------------------------------------

class SyntheticDataGenerator:
    """
    Generates realistic synthetic training data for the 18-feature schema.

    Each fraud pattern produces a distinctive feature signature that
    matches what the feature engineering service computes on real transactions.
    """

    def __init__(self, rng: np.random.RandomState):
        self.rng = rng

    def generate(
        self, n_samples: int, fraud_rate: float
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        Returns:
            X: (n_samples, 18) feature matrix
            y: (n_samples,) binary labels  (1=fraud, 0=legit)
        """
        n_fraud = int(n_samples * fraud_rate)
        n_legit = n_samples - n_fraud

        X_legit = self._generate_legitimate(n_legit)
        X_fraud = self._generate_fraud(n_fraud)

        X = np.vstack([X_legit, X_fraud])
        y = np.concatenate([np.zeros(n_legit), np.ones(n_fraud)])

        # Shuffle
        idx = self.rng.permutation(len(y))
        return X[idx], y[idx]

    def _generate_legitimate(self, n: int) -> np.ndarray:
        r = self.rng
        rows = []
        for _ in range(n):
            # Velocity: low counts, moderate amounts
            txn_c1m  = r.poisson(0.3)
            txn_c5m  = txn_c1m  + r.poisson(0.8)
            txn_c1h  = txn_c5m  + r.poisson(2.0)
            txn_c24h = txn_c1h  + r.poisson(5.0)
            base_amt = r.lognormal(4.5, 0.8)  # ~$90 median
            rows.append([
                # velocity
                txn_c1m, txn_c5m, txn_c1h, txn_c24h,
                base_amt * txn_c1m,
                base_amt * txn_c5m,
                base_amt * txn_c1h,
                base_amt * txn_c24h,
                # geography
                r.exponential(15),        # geo_velocity_kmh (short distances)
                float(r.random() < 0.03), # is_new_country (rarely)
                1 + r.poisson(0.1),       # unique_countries
                # device
                r.uniform(0.5, 1.0),      # device_trust_score (trusted)
                float(r.random() < 0.05), # is_new_device
                r.poisson(2),             # ip_txn_count_1h (low)
                1 + r.poisson(0.3),       # unique_devices_24h
                # behavioral
                r.lognormal(0.0, 0.4),    # amount_vs_avg_ratio (near 1.0)
                r.uniform(0.4, 1.0),      # merchant_familiarity (known merchants)
                r.exponential(12),        # hours_since_last_txn
            ])
        return np.array(rows, dtype=np.float32)

    def _generate_fraud(self, n: int) -> np.ndarray:
        r = self.rng
        rows = []
        patterns = [
            "card_testing", "account_takeover", "velocity_attack",
            "fraud_ring", "geo_impossibility", "large_amount",
        ]
        weights = [0.20, 0.20, 0.20, 0.15, 0.15, 0.10]
        pattern_idx = r.choice(len(patterns), size=n, p=weights)

        for i in range(n):
            pattern = patterns[pattern_idx[i]]
            rows.append(self._fraud_pattern(pattern))
        return np.array(rows, dtype=np.float32)

    def _fraud_pattern(self, pattern: str) -> list:
        r = self.rng

        if pattern == "card_testing":
            # Many tiny txns very fast
            cnt = r.randint(5, 15)
            return [
                cnt, cnt, cnt + r.randint(0, 3), cnt + r.randint(2, 8),
                cnt * r.uniform(0.5, 4.0),   # micro amounts
                cnt * r.uniform(0.5, 4.0),
                cnt * r.uniform(0.5, 4.0),
                cnt * r.uniform(1.0, 8.0),
                r.uniform(0, 50),             # same location
                float(r.random() < 0.3),
                1 + r.poisson(0.2),
                0.0,                          # new device → trust=0
                True,
                r.poisson(15),               # high IP count
                1,
                r.uniform(0.01, 0.1),        # tiny ratio
                0.0,                          # unknown merchant
                r.uniform(0, 2),
            ]

        elif pattern == "account_takeover":
            return [
                r.poisson(0.5), r.poisson(1), r.poisson(2), r.poisson(6),
                0, r.uniform(100, 500), r.uniform(500, 2000), r.uniform(1000, 5000),
                r.uniform(3000, 15000),       # geo-velocity: flew in from far
                True,                         # new country
                r.randint(2, 4),
                0.0,                          # brand new device
                True,
                r.poisson(3),
                1,
                r.uniform(5, 20),             # much higher than avg
                0.0,                          # unknown merchant
                r.uniform(1, 168),
            ]

        elif pattern == "velocity_attack":
            cnt = r.randint(8, 25)
            avg = r.uniform(100, 500)
            return [
                cnt, cnt + r.randint(2, 5), cnt + r.randint(5, 10), cnt + r.randint(10, 20),
                cnt * avg, cnt * avg, cnt * avg, cnt * avg * 1.2,
                r.uniform(0, 30),
                float(r.random() < 0.2),
                1 + r.poisson(0.3),
                r.uniform(0.0, 0.4),          # low trust
                float(r.random() < 0.5),
                r.poisson(20),               # many from same IP
                1 + r.poisson(0.5),
                r.uniform(2, 6),
                0.0,
                r.uniform(0, 1),
            ]

        elif pattern == "fraud_ring":
            return [
                r.poisson(1), r.poisson(2), r.poisson(4), r.poisson(8),
                r.uniform(50, 300), r.uniform(100, 600), r.uniform(300, 1500), r.uniform(500, 3000),
                r.uniform(0, 100),
                float(r.random() < 0.2),
                1 + r.poisson(0.5),
                0.0, True,
                r.randint(30, 100),           # very high IP count (many accounts)
                1,
                r.uniform(0.8, 3.0),
                0.0,
                r.uniform(0, 48),
            ]

        elif pattern == "geo_impossibility":
            return [
                r.poisson(0.5), r.poisson(1), r.poisson(2), r.poisson(5),
                0, r.uniform(50, 200), r.uniform(200, 1000), r.uniform(500, 2000),
                r.uniform(1000, 20000),        # impossible speed
                True,                          # definitely new country
                r.randint(2, 5),
                0.0, True,
                r.poisson(5),
                1 + r.poisson(0.3),
                r.uniform(2, 10),
                0.0,
                r.uniform(0.1, 2),
            ]

        else:  # large_amount
            return [
                r.poisson(0.3), r.poisson(0.8), r.poisson(2), r.poisson(5),
                0, r.uniform(100, 500), r.uniform(500, 2000), r.uniform(1000, 5000),
                r.uniform(0, 200),
                float(r.random() < 0.1),
                1 + r.poisson(0.1),
                r.uniform(0.0, 0.6),
                float(r.random() < 0.4),
                r.poisson(3),
                1 + r.poisson(0.2),
                r.uniform(10, 50),             # huge ratio
                r.uniform(0, 0.2),
                r.uniform(1, 720),
            ]


# ---------------------------------------------------------------------------
# Model artifact — wraps LightGBM + metadata
# ---------------------------------------------------------------------------

class ModelArtifact:
    """Everything needed for inference: model + feature names + metrics."""

    def __init__(
        self,
        booster,
        feature_names: list,
        val_metrics:   Dict[str, float],
        model_version: str = "local",
        trained_at:    str = "",
    ):
        self.booster       = booster
        self.feature_names = feature_names
        self.val_metrics   = val_metrics
        self.model_version = model_version
        self.trained_at    = trained_at or datetime.now(timezone.utc).isoformat()

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        """Return P(fraud) for each row in X."""
        return self.booster.predict(X)

    def save(self, path: str):
        with open(path, "wb") as f:
            pickle.dump(self, f)

    @classmethod
    def load(cls, path: str) -> "ModelArtifact":
        with open(path, "rb") as f:
            return pickle.load(f)


# ---------------------------------------------------------------------------
# Trainer
# ---------------------------------------------------------------------------

class Stage1Trainer:

    def __init__(self):
        if not _LGBM_AVAILABLE:
            raise RuntimeError("lightgbm and scikit-learn are required for training")

    def train(self) -> ModelArtifact:
        """
        Full training pipeline:
          1. Generate synthetic data
          2. Train LightGBM
          3. Evaluate on validation set
          4. Register in MLflow
          5. Return ModelArtifact
        """
        logger.info("Starting Stage 1 LightGBM training...")
        logger.info("  Samples: %d | Fraud rate: %.1f%%",
                    config.train_samples, config.train_fraud_rate * 100)

        rng = np.random.RandomState(config.random_seed)

        # --- 1. Generate data ---
        t0 = time.perf_counter()
        gen = SyntheticDataGenerator(rng)
        X, y = gen.generate(config.train_samples, config.train_fraud_rate)
        logger.info("  Generated %d samples in %.1fs", len(y), time.perf_counter() - t0)

        # --- 2. Train / val split ---
        X_train, X_val, y_train, y_val = train_test_split(
            X, y,
            test_size=config.train_val_split,
            random_state=config.random_seed,
            stratify=y,
        )
        logger.info(
            "  Train: %d (%d fraud) | Val: %d (%d fraud)",
            len(y_train), int(y_train.sum()),
            len(y_val),   int(y_val.sum()),
        )

        # --- 3. LightGBM training ---
        lgb_params = {
            "objective":         "binary",
            "metric":            ["binary_logloss", "auc"],
            "learning_rate":     config.lgbm_learning_rate,
            "num_leaves":        config.lgbm_num_leaves,
            "max_depth":         config.lgbm_max_depth,
            "min_child_samples": config.lgbm_min_child_samples,
            "scale_pos_weight":  config.lgbm_scale_pos_weight,
            "n_jobs":            config.lgbm_n_jobs,
            "verbose":           -1,
            "random_state":      config.random_seed,
            "feature_name":      config.feature_names,
        }

        dtrain = lgb.Dataset(X_train, label=y_train,
                             feature_name=config.feature_names)
        dval   = lgb.Dataset(X_val,   label=y_val,
                             feature_name=config.feature_names,
                             reference=dtrain)

        callbacks = [
            lgb.early_stopping(stopping_rounds=30, verbose=False),
            lgb.log_evaluation(period=50),
        ]

        t1 = time.perf_counter()
        booster = lgb.train(
            params           = lgb_params,
            train_set        = dtrain,
            num_boost_round  = config.lgbm_n_estimators,
            valid_sets       = [dval],
            callbacks        = callbacks,
        )
        train_time = time.perf_counter() - t1
        logger.info("  LightGBM trained in %.1fs | best_iter=%d",
                    train_time, booster.best_iteration)

        # --- 4. Evaluate ---
        y_prob = booster.predict(X_val)
        y_pred = (y_prob >= 0.5).astype(int)

        val_metrics = {
            "val_auc":       float(roc_auc_score(y_val, y_prob)),
            "val_precision": float(precision_score(y_val, y_pred, zero_division=0)),
            "val_recall":    float(recall_score(y_val, y_pred, zero_division=0)),
            "val_f1":        float(f1_score(y_val, y_pred, zero_division=0)),
            "train_samples": config.train_samples,
            "best_iteration": booster.best_iteration,
        }
        logger.info(
            "  Val metrics: AUC=%.4f  Prec=%.4f  Rec=%.4f  F1=%.4f",
            val_metrics["val_auc"],
            val_metrics["val_precision"],
            val_metrics["val_recall"],
            val_metrics["val_f1"],
        )

        # --- 5. MLflow registration ---
        model_version = self._register_mlflow(booster, val_metrics, X_train, y_train)

        artifact = ModelArtifact(
            booster       = booster,
            feature_names = config.feature_names,
            val_metrics   = val_metrics,
            model_version = model_version,
        )
        logger.info("Training complete. Model version: %s", model_version)
        return artifact

    def _register_mlflow(
        self, booster, metrics: dict, X_train, y_train
    ) -> str:
        """Register the trained model in MLflow. Returns version string."""
        if not _MLFLOW_AVAILABLE:
            return "local-no-mlflow"

        try:
            mlflow.set_tracking_uri(config.mlflow_tracking_uri)
            mlflow.set_experiment(config.mlflow_experiment)

            with mlflow.start_run(run_name=f"stage1-lgbm-{int(time.time())}") as run:
                # Log hyperparameters
                mlflow.log_params({
                    "n_estimators":    config.lgbm_n_estimators,
                    "learning_rate":   config.lgbm_learning_rate,
                    "num_leaves":      config.lgbm_num_leaves,
                    "max_depth":       config.lgbm_max_depth,
                    "scale_pos_weight":config.lgbm_scale_pos_weight,
                    "train_samples":   config.train_samples,
                    "fraud_rate":      config.train_fraud_rate,
                })
                # Log metrics
                mlflow.log_metrics(metrics)

                # Log model
                mlflow.lightgbm.log_model(
                    lgb_model         = booster,
                    artifact_path     = "model",
                    registered_model_name = config.mlflow_model_name,
                )

                version = run.info.run_id[:8]
                logger.info("MLflow run logged: %s", run.info.run_id)
                return version

        except Exception as e:
            logger.warning("MLflow registration failed (non-fatal): %s", e)
            return "local-mlflow-failed"


def load_from_mlflow() -> Optional[ModelArtifact]:
    """
    Attempt to load the latest Production model from MLflow.
    Returns None if no model is registered or MLflow is unavailable.
    """
    if not _MLFLOW_AVAILABLE:
        return None

    try:
        mlflow.set_tracking_uri(config.mlflow_tracking_uri)
        client = mlflow.tracking.MlflowClient()

        # Try to get latest Production version
        versions = client.get_latest_versions(
            config.mlflow_model_name, stages=[config.mlflow_model_stage]
        )
        if not versions:
            logger.info("No %s model in MLflow stage: %s",
                        config.mlflow_model_name, config.mlflow_model_stage)
            return None

        mv = versions[0]
        logger.info("Loading MLflow model: %s v%s", mv.name, mv.version)

        model_uri = f"models:/{config.mlflow_model_name}/{config.mlflow_model_stage}"
        booster   = mlflow.lightgbm.load_model(model_uri)

        return ModelArtifact(
            booster       = booster,
            feature_names = config.feature_names,
            val_metrics   = {},
            model_version = f"mlflow-v{mv.version}",
        )

    except Exception as e:
        logger.warning("Failed to load from MLflow: %s", e)
        return None
