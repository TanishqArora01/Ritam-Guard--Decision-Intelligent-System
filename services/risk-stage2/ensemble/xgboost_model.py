"""
ensemble/xgboost_model.py
XGBoost binary classifier for Stage 2 deep intelligence.
Train on synthetic data, register in MLflow, expose predict_proba().
"""
from __future__ import annotations
import logging, time
from typing import Dict, Optional
import numpy as np
logger = logging.getLogger(__name__)

try:
    import xgboost as xgb
    from sklearn.model_selection import train_test_split
    from sklearn.metrics import roc_auc_score, precision_score, recall_score, f1_score
    _XGB = True
except ImportError:
    _XGB = False

try:
    import mlflow, mlflow.xgboost
    _MLFLOW = True
except ImportError:
    _MLFLOW = False

from config import config


class XGBoostArtifact:
    def __init__(self, booster, val_metrics: dict, version: str = "local"):
        self.booster = booster
        self.val_metrics = val_metrics
        self.version = version

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        dmat = xgb.DMatrix(X, feature_names=config.feature_names)
        return self.booster.predict(dmat)


class XGBoostTrainer:
    def __init__(self):
        if not _XGB:
            raise RuntimeError("xgboost not installed")

    def train(self, X: np.ndarray, y: np.ndarray) -> XGBoostArtifact:
        X_tr, X_val, y_tr, y_val = train_test_split(
            X, y, test_size=0.2, random_state=config.random_seed, stratify=y
        )
        dtrain = xgb.DMatrix(X_tr,  label=y_tr,  feature_names=config.feature_names)
        dval   = xgb.DMatrix(X_val, label=y_val, feature_names=config.feature_names)
        params = {
            "objective": "binary:logistic", "eval_metric": ["logloss", "auc"],
            "learning_rate": config.xgb_learning_rate, "max_depth": config.xgb_max_depth,
            "subsample": config.xgb_subsample, "colsample_bytree": config.xgb_colsample,
            "scale_pos_weight": config.xgb_scale_pos_weight,
            "nthread": config.xgb_n_jobs, "seed": config.random_seed, "verbosity": 0,
        }
        cbs = [xgb.callback.EarlyStopping(rounds=30, save_best=True)]
        logger.info("Training XGBoost n=%d fraud=%.1f%%...", len(y), y.mean()*100)
        t0 = time.perf_counter()
        booster = xgb.train(params, dtrain, num_boost_round=config.xgb_n_estimators,
                            evals=[(dval,"val")], callbacks=cbs, verbose_eval=False)
        logger.info("XGBoost done in %.1fs", time.perf_counter()-t0)
        y_prob = booster.predict(dval)
        y_pred = (y_prob >= 0.5).astype(int)
        metrics = {
            "val_auc":       float(roc_auc_score(y_val, y_prob)),
            "val_precision": float(precision_score(y_val, y_pred, zero_division=0)),
            "val_recall":    float(recall_score(y_val, y_pred, zero_division=0)),
            "val_f1":        float(f1_score(y_val, y_pred, zero_division=0)),
        }
        logger.info("XGBoost val: AUC=%.4f P=%.3f R=%.3f", metrics["val_auc"], metrics["val_precision"], metrics["val_recall"])
        version = self._register(booster, metrics)
        return XGBoostArtifact(booster, metrics, version)

    def _register(self, booster, metrics) -> str:
        if not _MLFLOW: return "local-no-mlflow"
        try:
            mlflow.set_tracking_uri(config.mlflow_tracking_uri)
            mlflow.set_experiment(config.mlflow_experiment)
            with mlflow.start_run(run_name=f"stage2-xgb-{int(time.time())}") as r:
                mlflow.log_metrics(metrics)
                mlflow.xgboost.log_model(booster, "xgb_model", registered_model_name=config.mlflow_xgb_name)
                return r.info.run_id[:8]
        except Exception as e:
            logger.warning("XGBoost MLflow failed: %s", e); return "local-mlflow-failed"


def load_xgb_from_mlflow() -> Optional[XGBoostArtifact]:
    if not _MLFLOW or not _XGB: return None
    try:
        mlflow.set_tracking_uri(config.mlflow_tracking_uri)
        client = mlflow.tracking.MlflowClient()
        vs = client.get_latest_versions(config.mlflow_xgb_name, stages=[config.mlflow_model_stage])
        if not vs: return None
        booster = mlflow.xgboost.load_model(f"models:/{config.mlflow_xgb_name}/{config.mlflow_model_stage}")
        return XGBoostArtifact(booster, {}, f"mlflow-v{vs[0].version}")
    except Exception as e:
        logger.warning("XGBoost MLflow load failed: %s", e); return None
