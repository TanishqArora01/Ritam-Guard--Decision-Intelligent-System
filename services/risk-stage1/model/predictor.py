"""
model/predictor.py
Stage 1 inference engine.

Responsibilities:
  1. Accept a PredictRequest (18 features)
  2. Run LightGBM → P(fraud)
  3. Run Conformal Predictor → uncertainty
  4. Apply early exit logic → routing decision
  5. Compute SHAP top-3 feature attributions
  6. Return PredictResponse

Early Exit Logic:
  ┌─────────────────────────────────────────────────────┐
  │  p_fraud < θ_low  (default 0.10)                    │
  │  AND uncertainty < uncertainty_escalate (0.30)      │
  │  AND NOT has_cold_start                             │
  │  → EARLY_EXIT_APPROVE  (skip Stage 2 + 3, <10ms)   │
  ├─────────────────────────────────────────────────────┤
  │  uncertainty > uncertainty_escalate                 │
  │  → UNCERTAIN_ESCALATE (pass to Stage 2 regardless) │
  ├─────────────────────────────────────────────────────┤
  │  p_fraud > θ_high (default 0.70)                   │
  │  → HIGH_RISK_STAGE2                                 │
  ├─────────────────────────────────────────────────────┤
  │  θ_low ≤ p_fraud ≤ θ_high                          │
  │  → PASS_TO_STAGE2 (normal path)                     │
  └─────────────────────────────────────────────────────┘
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, Optional

import numpy as np

from config import config
from schemas import PredictRequest, PredictResponse, Stage1Routing
from model.conformal import ConformalPredictor

logger = logging.getLogger(__name__)

try:
    import shap
    _SHAP_AVAILABLE = True
except ImportError:
    _SHAP_AVAILABLE = False
    logger.warning("shap not installed — top features will use gain-based importance")


# ---------------------------------------------------------------------------
# Prometheus metrics (lazy init — safe if prometheus_client not installed)
# ---------------------------------------------------------------------------
try:
    from prometheus_client import Counter, Histogram, Gauge
    _PROM = True
except ImportError:
    _PROM = False
    class _NoOp:
        def __init__(self, *a, **k): pass
        def labels(self, **k): return self
        def inc(self, v=1): pass
        def observe(self, v): pass
        def set(self, v): pass
    Counter = Histogram = Gauge = _NoOp

PRED_TOTAL    = Counter("stage1_predictions_total", "Total predictions", ["routing"])
PRED_LATENCY  = Histogram("stage1_latency_ms", "Inference latency (ms)",
                           buckets=[1,2,3,5,8,10,15,20,50,100])
EARLY_EXIT    = Counter("stage1_early_exit_total", "Early exit approvals")
P_FRAUD_GAUGE = Gauge("stage1_p_fraud_latest", "Latest P(fraud) score")


# ---------------------------------------------------------------------------
# Predictor
# ---------------------------------------------------------------------------

class Stage1Predictor:
    """
    Thread-safe inference engine.
    Wraps the LightGBM booster + ConformalPredictor.
    All public methods are stateless — safe to call from multiple threads.
    """

    def __init__(self, model_artifact, conformal: ConformalPredictor):
        self.artifact    = model_artifact
        self.conformal   = conformal
        self._shap_explainer = None
        self._feature_importances: Dict[str, float] = {}

        # Pre-compute fallback feature importances (gain-based)
        try:
            imp = model_artifact.booster.feature_importance(importance_type="gain")
            names = config.feature_names
            total = max(imp.sum(), 1.0)
            self._feature_importances = {
                names[i]: float(imp[i] / total)
                for i in range(min(len(imp), len(names)))
            }
        except Exception:
            pass

        logger.info(
            "Stage1Predictor ready | model=%s | conformal=%s | θ_low=%.2f θ_high=%.2f",
            model_artifact.model_version,
            "calibrated" if conformal.is_calibrated else "uncalibrated",
            config.theta_low,
            config.theta_high,
        )

    # -------------------------------------------------------------------------
    # Main inference entry point
    # -------------------------------------------------------------------------

    def predict(self, req: PredictRequest) -> PredictResponse:
        """
        Full inference pipeline for one transaction.
        Target latency: <10ms for early exit path, <20ms otherwise.
        """
        t_start = time.perf_counter()

        # 1. Feature vector
        X = np.array([req.to_feature_array()], dtype=np.float32)

        # 2. LightGBM score
        p_fraud = float(self.artifact.predict_proba(X)[0])
        p_fraud = max(0.0, min(1.0, p_fraud))   # clamp to [0,1]
        P_FRAUD_GAUGE.set(p_fraud)

        # 3. Conformal uncertainty
        includes_fraud, uncertainty, pv_fraud, pv_legit = \
            self.conformal.predict(p_fraud)

        # 4. Early exit decision
        routing, reason = self._route(p_fraud, uncertainty, req.has_cold_start)

        # 5. Top-3 SHAP features (fast, gain-based fallback if SHAP unavailable)
        top_features = self._top_features(X, req)

        elapsed_ms = (time.perf_counter() - t_start) * 1000

        # 6. Prometheus
        PRED_TOTAL.labels(routing=routing.value).inc()
        PRED_LATENCY.observe(elapsed_ms)
        if routing == Stage1Routing.EARLY_EXIT_APPROVE:
            EARLY_EXIT.inc()

        return PredictResponse(
            txn_id      = req.txn_id,
            customer_id = req.customer_id,
            amount      = req.amount,
            p_fraud     = round(p_fraud, 6),
            uncertainty = round(uncertainty, 6),
            conformal_includes_fraud = includes_fraud,
            routing     = routing,
            routing_reason = reason,
            theta_low   = config.theta_low,
            theta_high  = config.theta_high,
            top_features      = top_features,
            model_version     = self.artifact.model_version,
            inference_time_ms = round(elapsed_ms, 3),
            pipeline_stage    = 1,
        )

    # -------------------------------------------------------------------------
    # Routing logic (the early exit gate)
    # -------------------------------------------------------------------------

    def _route(
        self, p_fraud: float, uncertainty: float, has_cold_start: bool
    ) -> tuple[Stage1Routing, str]:
        """
        Apply the Stage 1 decision gate.
        Returns (routing, human-readable reason).
        """
        # Rule 1: High uncertainty → always escalate to Stage 2
        if uncertainty > config.uncertainty_escalate:
            return (
                Stage1Routing.UNCERTAIN_ESCALATE,
                f"Uncertainty {uncertainty:.3f} > threshold {config.uncertainty_escalate}",
            )

        # Rule 2: Cold start → escalate (no history to rely on)
        if has_cold_start:
            return (
                Stage1Routing.PASS_TO_STAGE2,
                "Cold start — no customer history available",
            )

        # Rule 3: Clear low risk → EARLY EXIT (main latency optimisation)
        if p_fraud < config.theta_low:
            return (
                Stage1Routing.EARLY_EXIT_APPROVE,
                f"P(fraud)={p_fraud:.4f} < θ_low={config.theta_low} — low risk",
            )

        # Rule 4: Clear high risk
        if p_fraud > config.theta_high:
            return (
                Stage1Routing.HIGH_RISK_STAGE2,
                f"P(fraud)={p_fraud:.4f} > θ_high={config.theta_high} — high risk",
            )

        # Rule 5: Uncertain middle band
        return (
            Stage1Routing.PASS_TO_STAGE2,
            f"P(fraud)={p_fraud:.4f} in [{config.theta_low}, {config.theta_high}] — needs Stage 2",
        )

    # -------------------------------------------------------------------------
    # Feature attributions
    # -------------------------------------------------------------------------

    def _top_features(
        self, X: np.ndarray, req: PredictRequest, top_n: int = 3
    ) -> Dict[str, float]:
        """
        Return top-N features by importance.
        Uses SHAP TreeExplainer if available (exact), otherwise gain-based
        feature importance (approximate but fast).
        """
        # SHAP path (exact Shapley values)
        if _SHAP_AVAILABLE:
            try:
                if self._shap_explainer is None:
                    self._shap_explainer = shap.TreeExplainer(self.artifact.booster)
                shap_vals = self._shap_explainer.shap_values(X)[0]
                names     = config.feature_names
                pairs     = sorted(
                    zip(names, shap_vals.tolist()),
                    key=lambda x: abs(x[1]),
                    reverse=True,
                )
                return {k: round(v, 5) for k, v in pairs[:top_n]}
            except Exception as e:
                logger.debug("SHAP failed, falling back to gain: %s", e)

        # Gain-based fallback (pre-computed at init)
        if self._feature_importances:
            top = sorted(
                self._feature_importances.items(),
                key=lambda x: x[1], reverse=True
            )[:top_n]
            return {k: round(v, 5) for k, v in top}

        return {}


# ---------------------------------------------------------------------------
# Predictor factory — initialise model + conformal predictor
# ---------------------------------------------------------------------------

def build_predictor() -> Stage1Predictor:
    """
    Construct Stage1Predictor following the configured init strategy:
      "auto"  → try MLflow, fall back to training from scratch
      "train" → always train from scratch
      "load"  → always load from MLflow (raises if unavailable)
    """
    from model.trainer import Stage1Trainer, load_from_mlflow, SyntheticDataGenerator

    artifact = None
    strategy = config.model_init_strategy

    # --- Try MLflow first (auto or load) ---
    if strategy in ("auto", "load"):
        logger.info("Attempting to load model from MLflow...")
        artifact = load_from_mlflow()
        if artifact:
            logger.info("Model loaded from MLflow: %s", artifact.model_version)
        elif strategy == "load":
            raise RuntimeError("MODEL_INIT_STRATEGY=load but no model in MLflow")

    # --- Train from scratch (auto fallback or explicit train) ---
    if artifact is None:
        logger.info("Training LightGBM from synthetic data...")
        trainer  = Stage1Trainer()
        artifact = trainer.train()

    # --- Calibrate Conformal Predictor on a held-out calibration set ---
    logger.info("Calibrating conformal predictor (n=%d)...", config.conformal_cal_samples)
    rng_cal = np.random.RandomState(config.random_seed + 1)
    gen     = SyntheticDataGenerator(rng_cal)
    X_cal, y_cal = gen.generate(
        n_samples  = config.conformal_cal_samples,
        fraud_rate = config.train_fraud_rate,
    )
    y_prob_cal = artifact.predict_proba(X_cal)

    cp = ConformalPredictor(alpha=config.conformal_alpha)
    cp.calibrate(y_prob_cal, y_cal)

    return Stage1Predictor(artifact, cp)
