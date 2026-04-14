"""
predictor.py
Stage 2 inference orchestrator.

Execution order per transaction:
  1. Parse Stage2Request → feature array
  2. XGBoost inference   (always)
  3. MLP inference       (always)
  4. Neo4j graph queries (if available, parallel-friendly)
  5. Anomaly detection   (autoencoder + isolation forest)
  6. Ensemble fusion     (weighted average of all 4 components)
  7. Build explanation
  8. Return Stage2Response

Target latency: <100ms (dominated by Neo4j round-trip ~20-50ms)
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Dict, Optional

import numpy as np

from config import config
from schemas import (
    Stage2Request, Stage2Response,
    GraphRiskResult, AnomalyResult,
)
from ensemble.fusion import EnsembleFusion
from graph.queries import run_all_graph_queries
from anomaly.detectors import AnomalyDetector

logger = logging.getLogger(__name__)

try:
    from prometheus_client import Counter, Histogram, Gauge
    PRED_TOTAL   = Counter("stage2_predictions_total", "Total Stage 2 predictions")
    PRED_LATENCY = Histogram("stage2_latency_ms", "Stage 2 latency (ms)",
                             buckets=[5,10,20,50,100,200,500])
    NEO4J_CALLS  = Counter("stage2_neo4j_calls_total", "Neo4j graph query calls")
    ANOMALY_HIGH = Counter("stage2_anomaly_high_total", "Anomaly score > 0.6 count")
except Exception:
    class _NoOp:
        def inc(self,v=1): pass
        def observe(self,v): pass
        def set(self,v): pass
        def labels(self,**k): return self
    PRED_TOTAL = PRED_LATENCY = NEO4J_CALLS = ANOMALY_HIGH = _NoOp()


class Stage2Predictor:
    """
    Stateless inference engine — safe to call from multiple threads.
    All components are read-only after initialisation.
    """

    def __init__(
        self,
        xgb_artifact,
        mlp_artifact,
        anomaly_detector: AnomalyDetector,
        neo4j_client,
    ):
        self.xgb      = xgb_artifact
        self.mlp      = mlp_artifact
        self.anomaly  = anomaly_detector
        self.neo4j    = neo4j_client
        self.fusion   = EnsembleFusion()

        logger.info(
            "Stage2Predictor ready | xgb=%s mlp=%s neo4j=%s",
            xgb_artifact.version,
            mlp_artifact.version,
            "available" if neo4j_client.available else "unavailable",
        )

    def predict(self, req: Stage2Request) -> Stage2Response:
        t_start = time.perf_counter()

        X = np.array([req.to_feature_array()], dtype=np.float32)

        # ---- 1. ML Ensemble ----
        xgb_score = float(self.xgb.predict_proba(X)[0])
        mlp_score = float(self.mlp.predict_proba(X)[0])

        # ---- 2. Graph Intelligence ----
        graph_dict = {}
        if self.neo4j.available:
            NEO4J_CALLS.inc()
            graph_dict = run_all_graph_queries(
                self.neo4j,
                customer_id      = req.customer_id,
                device_id        = req.device_id,
                account_age_days = req.account_age_days,
            )

        graph_risk = GraphRiskResult(
            graph_risk_score          = graph_dict.get("graph_risk_score",         0.0),
            fraud_ring_score          = graph_dict.get("fraud_ring_score",          0.0),
            mule_account_score        = graph_dict.get("mule_account_score",        0.0),
            synthetic_identity_score  = graph_dict.get("synthetic_identity_score",  0.0),
            velocity_graph_score      = graph_dict.get("velocity_graph_score",      0.0),
            multi_hop_score           = graph_dict.get("multi_hop_score",           0.0),
            shared_devices            = graph_dict.get("shared_devices",            []),
            shared_ips                = graph_dict.get("shared_ips",                []),
            connected_customers       = graph_dict.get("connected_customers",       []),
            hop_path_summary          = graph_dict.get("hop_path_summary",          ""),
            neo4j_available           = self.neo4j.available,
        )

        # ---- 3. Anomaly Detection ----
        combined_a, ae_s, if_s = self.anomaly.score(X)
        anomaly = AnomalyResult(
            anomaly_score          = combined_a,
            autoencoder_score      = ae_s,
            isolation_forest_score = if_s,
            is_anomaly             = combined_a > 0.6,
        )
        if anomaly.is_anomaly:
            ANOMALY_HIGH.inc()

        # ---- 4. Ensemble Fusion ----
        p_fraud, confidence, component_scores = self.fusion.fuse(
            xgb_score     = xgb_score,
            mlp_score     = mlp_score,
            anomaly_score = combined_a,
            graph_score   = graph_risk.graph_risk_score,
            graph_available = self.neo4j.available,
        )

        # ---- 5. Explanation ----
        top_features = self._top_features(xgb_score, mlp_score)
        explanation  = self.fusion.build_explanation(
            p_fraud       = p_fraud,
            xgb_score     = xgb_score,
            mlp_score     = mlp_score,
            anomaly_score = combined_a,
            graph_risk    = graph_risk,
            top_features  = top_features,
        )

        elapsed_ms = (time.perf_counter() - t_start) * 1000
        PRED_TOTAL.inc()
        PRED_LATENCY.observe(elapsed_ms)

        return Stage2Response(
            txn_id          = req.txn_id,
            customer_id     = req.customer_id,
            amount          = req.amount,
            p_fraud         = round(p_fraud,    6),
            confidence      = round(confidence, 6),
            xgb_score       = round(xgb_score,  6),
            mlp_score       = round(mlp_score,   6),
            graph_risk      = graph_risk,
            anomaly         = anomaly,
            p_fraud_stage1  = req.p_fraud_stage1,
            explanation     = explanation,
            top_features    = top_features,
            model_versions  = {
                "xgb": self.xgb.version,
                "mlp": self.mlp.version,
            },
            inference_time_ms = round(elapsed_ms, 3),
            pipeline_stage    = 2,
        )

    def _top_features(self, xgb_score: float, mlp_score: float) -> Dict[str, float]:
        """Simple gain-based feature importance from XGBoost."""
        try:
            imp   = self.xgb.booster.get_score(importance_type="gain")
            total = max(sum(imp.values()), 1.0)
            pairs = sorted(imp.items(), key=lambda x: x[1], reverse=True)[:3]
            return {k: round(v / total, 5) for k, v in pairs}
        except Exception:
            return {}


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def build_predictor(neo4j_client) -> Stage2Predictor:
    """
    Build Stage2Predictor:
      - Train XGBoost + MLP + Anomaly detectors (or load from MLflow)
      - Attach Neo4j client
    """
    from ensemble.xgboost_model import XGBoostTrainer, load_xgb_from_mlflow
    from ensemble.mlp_model     import MLPTrainer,     load_mlp_from_mlflow
    from anomaly.detectors      import AnomalyTrainer

    strategy = config.model_init_strategy

    # --- Generate shared training data once ---
    logger.info("Generating training data (n=%d)...", config.train_samples)
    rng = np.random.RandomState(config.random_seed)

    # Import the same generator as Stage 1 — shared feature schema
    import sys, os
    stage1_path = os.path.join(os.path.dirname(__file__), "..", "stage1-service")
    if os.path.exists(stage1_path) and stage1_path not in sys.path:
        sys.path.insert(0, stage1_path)

    try:
        from model.trainer import SyntheticDataGenerator
        gen   = SyntheticDataGenerator(rng)
        X, y  = gen.generate(config.train_samples, config.train_fraud_rate)
    except ImportError:
        # Fallback: generate simple synthetic data inline
        X = rng.randn(config.train_samples, 18).astype(np.float32)
        y = (rng.rand(config.train_samples) < config.train_fraud_rate).astype(float)

    X_legit = X[y == 0]

    # --- XGBoost ---
    xgb_artifact = None
    if strategy in ("auto", "load"):
        xgb_artifact = load_xgb_from_mlflow()
    if xgb_artifact is None:
        xgb_artifact = XGBoostTrainer().train(X, y)

    # --- MLP ---
    mlp_artifact = None
    if strategy in ("auto", "load"):
        mlp_artifact = load_mlp_from_mlflow()
    if mlp_artifact is None:
        mlp_artifact = MLPTrainer().train(X, y)

    # --- Anomaly detectors (train on legitimate data only) ---
    logger.info("Training anomaly detectors on %d legitimate samples...", len(X_legit))
    ae_artifact, if_artifact = AnomalyTrainer().train(X_legit)
    anomaly_detector = AnomalyDetector(ae_artifact, if_artifact)

    return Stage2Predictor(xgb_artifact, mlp_artifact, anomaly_detector, neo4j_client)
