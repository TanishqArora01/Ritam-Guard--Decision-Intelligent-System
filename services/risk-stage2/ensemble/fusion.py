"""
ensemble/fusion.py
Weighted score fusion for Stage 2 ensemble.
Combines XGBoost, MLP, Anomaly, and Graph scores into a final P(fraud).
"""
from __future__ import annotations
import logging
from typing import Dict, Tuple
import numpy as np
from config import config
logger = logging.getLogger(__name__)


class EnsembleFusion:

    def __init__(self):
        self.weights = {
            "xgb":     config.ensemble_xgb_weight,
            "mlp":     config.ensemble_mlp_weight,
            "anomaly": config.ensemble_anomaly_weight,
            "graph":   config.ensemble_graph_weight,
        }

    def fuse(self, xgb_score: float, mlp_score: float,
             anomaly_score: float, graph_score: float,
             graph_available: bool = True) -> Tuple[float, float, Dict[str, float]]:
        """
        Fuse component scores. Redistributes weight if graph unavailable.
        Returns (fused_p_fraud, confidence, component_scores_dict).
        """
        scores = {
            "xgb":     float(np.clip(xgb_score,     0.0, 1.0)),
            "mlp":     float(np.clip(mlp_score,     0.0, 1.0)),
            "anomaly": float(np.clip(anomaly_score, 0.0, 1.0)),
        }
        if graph_available:
            scores["graph"] = float(np.clip(graph_score, 0.0, 1.0))
            active = dict(self.weights)
        else:
            active = {k: v for k, v in self.weights.items() if k != "graph"}

        total_w = sum(active.values())
        norm_w  = {k: v / total_w for k, v in active.items()}

        fused  = float(np.clip(sum(norm_w[k] * scores[k] for k in active), 0.0, 1.0))
        spread = float(np.std([scores[k] for k in active]))
        confidence = float(np.clip(1.0 - spread * 2.0, 0.0, 1.0))

        return fused, confidence, {k: round(v, 5) for k, v in scores.items()}

    def build_explanation(
        self, p_fraud: float, xgb_score: float, mlp_score: float,
        anomaly_score: float, graph_risk, top_features: Dict[str, float],
    ) -> Dict[str, str]:
        """Build human-readable explanation for Stage 2 decision."""
        expl: Dict[str, str] = {}
        if xgb_score > 0.7:
            expl["xgboost"] = f"XGBoost flags high risk ({xgb_score:.2f})"
        if mlp_score > 0.7:
            expl["mlp"] = f"Neural network confirms elevated risk ({mlp_score:.2f})"
        if anomaly_score > 0.6:
            expl["anomaly"] = f"Unusual transaction pattern (anomaly score: {anomaly_score:.2f})"
        if getattr(graph_risk, 'fraud_ring_score', 0) > 0.5:
            devs = ", ".join(getattr(graph_risk,'shared_devices',[])[:3])
            expl["fraud_ring"] = f"Shares device(s) [{devs}] with other flagged customers"
        if getattr(graph_risk, 'mule_account_score', 0) > 0.5:
            expl["mule_account"] = "High inbound transaction volume consistent with mule activity"
        if getattr(graph_risk, 'synthetic_identity_score', 0) > 0.5:
            expl["synthetic_identity"] = "Account age vs activity inconsistent with real customer"
        if getattr(graph_risk, 'velocity_graph_score', 0) > 0.5:
            expl["velocity_burst"] = "Burst of transaction edges detected in short window"
        if getattr(graph_risk, 'multi_hop_score', 0) > 0.5:
            summary = getattr(graph_risk,'hop_path_summary','')
            expl["multi_hop"] = f"Fraud network connection: {summary}"
        for feat, val in list(top_features.items())[:2]:
            if abs(val) > 0.1:
                direction = "elevated" if val > 0 else "suppressed"
                expl[f"feature_{feat}"] = f"{feat.replace('_',' ').title()} is {direction} (impact: {val:+.3f})"
        if not expl:
            expl["summary"] = f"Ensemble consensus: P(fraud)={p_fraud:.3f}"
        return expl
