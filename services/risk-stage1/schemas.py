"""
schemas.py — Pydantic I/O contracts for Stage 1 Fast Risk service.

PredictRequest  → POST /predict  (accepts a FeatureVector JSON)
PredictResponse → returned immediately with P(fraud), uncertainty, routing
"""
from __future__ import annotations

from enum import Enum
from typing import Dict, List, Optional
from pydantic import BaseModel, Field


class Stage1Routing(str, Enum):
    EARLY_EXIT_APPROVE = "EARLY_EXIT_APPROVE"   # p < θ_low  → skip Stage 2+3
    PASS_TO_STAGE2     = "PASS_TO_STAGE2"       # θ_low ≤ p ≤ θ_high
    HIGH_RISK_STAGE2   = "HIGH_RISK_STAGE2"     # p > θ_high
    UNCERTAIN_ESCALATE = "UNCERTAIN_ESCALATE"   # uncertainty > threshold


class PredictRequest(BaseModel):
    """
    Input: enriched FeatureVector from the txn-enriched Kafka topic.
    Fields map 1:1 to FeatureVector in the feature-engine.
    """
    # Transaction identity
    txn_id:          str
    customer_id:     str
    amount:          float
    currency:        str = "USD"
    channel:         str = ""
    merchant_category: str = ""
    country_code:    str = ""

    # Customer profile
    clv:             float = 0.0
    trust_score:     float = 0.5
    customer_segment: str = "standard"
    account_age_days: int = 0

    # Device
    device_id:       str = ""
    ip_address:      str = ""
    is_new_device:   bool = False
    is_new_ip:       bool = False

    # --- 18 Computed features (Group 1: Velocity) ---
    txn_count_1m:    int   = 0
    txn_count_5m:    int   = 0
    txn_count_1h:    int   = 0
    txn_count_24h:   int   = 0
    amount_sum_1m:   float = 0.0
    amount_sum_5m:   float = 0.0
    amount_sum_1h:   float = 0.0
    amount_sum_24h:  float = 0.0

    # Group 2: Geography
    geo_velocity_kmh:     float = 0.0
    is_new_country:       bool  = False
    unique_countries_24h: int   = 1

    # Group 3: Device & Network
    device_trust_score:  float = 0.5
    ip_txn_count_1h:     int   = 0
    unique_devices_24h:  int   = 1

    # Group 4: Behavioral
    amount_vs_avg_ratio:  float = 1.0
    merchant_familiarity: float = 0.5
    hours_since_last_txn: float = 24.0

    # Metadata
    has_cold_start: bool = False
    txn_ts:         str  = ""

    # Ground truth (training data only — ignored in production)
    is_fraud:       Optional[bool] = None
    fraud_pattern:  Optional[str]  = None

    def to_feature_array(self) -> List[float]:
        """Extract features in canonical order for LightGBM input."""
        return [
            float(self.txn_count_1m),
            float(self.txn_count_5m),
            float(self.txn_count_1h),
            float(self.txn_count_24h),
            self.amount_sum_1m,
            self.amount_sum_5m,
            self.amount_sum_1h,
            self.amount_sum_24h,
            self.geo_velocity_kmh,
            float(self.is_new_country),
            float(self.unique_countries_24h),
            self.device_trust_score,
            float(self.is_new_device),
            float(self.ip_txn_count_1h),
            float(self.unique_devices_24h),
            self.amount_vs_avg_ratio,
            self.merchant_familiarity,
            self.hours_since_last_txn,
        ]


class PredictResponse(BaseModel):
    """
    Stage 1 output — published to txn-stage1 topic and returned via REST.
    """
    txn_id:      str
    customer_id: str
    amount:      float

    # Core ML outputs
    p_fraud:     float = Field(ge=0.0, le=1.0, description="Fraud probability")
    uncertainty: float = Field(ge=0.0, le=1.0, description="Prediction uncertainty (ICP)")

    # Conformal prediction set
    # True  → fraud class is in the 95% prediction set
    # False → model is confident it is NOT fraud
    conformal_includes_fraud: bool = False

    # Routing decision
    routing:     Stage1Routing
    routing_reason: str = ""

    # Thresholds used (for auditability)
    theta_low:   float
    theta_high:  float

    # Top features that drove this prediction (SHAP top-3)
    top_features: Dict[str, float] = Field(default_factory=dict)

    # Metadata
    model_version:    str   = ""
    inference_time_ms: float = 0.0
    pipeline_stage:   int   = 1


class ModelInfoResponse(BaseModel):
    model_name:      str
    model_version:   str
    model_stage:     str
    n_features:      int
    feature_names:   List[str]
    theta_low:       float
    theta_high:      float
    conformal_alpha: float
    train_samples:   int
    val_auc:         Optional[float] = None
    val_precision:   Optional[float] = None
    val_recall:      Optional[float] = None
    loaded_at:       str = ""
