"""
schemas.py — Stage 3 Decision Optimization Engine I/O contracts.
"""
from __future__ import annotations
from enum import Enum
from typing import Dict, List, Optional
from pydantic import BaseModel, Field


class Action(str, Enum):
    APPROVE       = "APPROVE"
    BLOCK         = "BLOCK"
    STEP_UP_AUTH  = "STEP_UP_AUTH"
    MANUAL_REVIEW = "MANUAL_REVIEW"


class ABVariant(str, Enum):
    CONTROL   = "control"
    TREATMENT = "treatment"
    SHADOW    = "shadow"


class CostBreakdown(BaseModel):
    """Per-action expected cost breakdown — the argmin target."""
    action:              Action
    expected_loss:       float  # P(fraud) × amount  (if approved)
    expected_friction:   float  # P(legit) × CLV × multiplier  (if blocked/stepped)
    expected_review:     float  # fixed review cost  (if manual)
    expected_stepup:     float  # fixed stepup cost  (if stepped)
    total_expected_cost: float  # sum of applicable components
    is_optimal:          bool = False


class Stage3Request(BaseModel):
    """Input: Stage 2 full output + original transaction context."""
    txn_id:          str
    customer_id:     str
    amount:          float
    currency:        str   = "USD"
    channel:         str   = ""
    merchant_category: str = ""
    country_code:    str   = ""
    txn_ts:          str   = ""

    # Customer profile
    clv:             float = 0.0
    trust_score:     float = 0.5
    account_age_days:int   = 0
    customer_segment:str   = "standard"

    # Stage 1 output
    p_fraud_stage1:       float = 0.5
    uncertainty_stage1:   float = 0.5
    stage1_routing:       str   = "PASS_TO_STAGE2"

    # Stage 2 output — the refined signals
    p_fraud:              float = 0.5   # ensemble P(fraud)
    confidence:           float = 0.5
    xgb_score:            float = 0.5
    mlp_score:            float = 0.5
    graph_risk_score:     float = 0.0
    fraud_ring_score:     float = 0.0
    mule_account_score:   float = 0.0
    synthetic_identity_score: float = 0.0
    velocity_graph_score: float = 0.0
    multi_hop_score:      float = 0.0
    anomaly_score:        float = 0.0
    autoencoder_score:    float = 0.0
    isolation_forest_score: float = 0.0
    is_anomaly:           bool  = False
    neo4j_available:      bool  = True

    # Stage 2 explanation pass-through
    stage2_explanation:   Dict[str, str]   = Field(default_factory=dict)
    top_features:         Dict[str, float] = Field(default_factory=dict)

    # Ground truth (training/evaluation only)
    is_fraud:      Optional[bool] = None
    fraud_pattern: Optional[str]  = None


class Stage3Response(BaseModel):
    """Final decision output — published to decisions topic and REST response."""
    txn_id:      str
    customer_id: str
    amount:      float
    currency:    str = "USD"

    # THE DECISION
    action:      Action
    action_reason: str = ""

    # Cost optimization details
    optimal_cost:   float  # cost of the chosen action
    cost_breakdown: List[CostBreakdown] = Field(default_factory=list)

    # Risk scores (pass-through for audit)
    p_fraud:         float = 0.0
    uncertainty:     float = 0.0
    graph_risk_score:float = 0.0
    anomaly_score:   float = 0.0
    confidence:      float = 0.0

    # CLV used in calculation
    clv_used:        float = 0.0
    trust_score:     float = 0.0

    # A/B experiment info
    ab_experiment_id: str      = ""
    ab_variant:       ABVariant = ABVariant.CONTROL
    ab_shadow_action: Optional[Action] = None  # what treatment would have done

    # Full explainability
    explanation: Dict[str, str] = Field(default_factory=dict)

    # Metadata
    pipeline_stage:    int   = 3
    decision_time_ms:  float = 0.0
    model_version:     str   = "1.0.0"
