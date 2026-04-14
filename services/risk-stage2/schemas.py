"""
schemas.py — Stage 2 I/O contracts.
"""
from __future__ import annotations
from typing import Dict, List, Optional
from pydantic import BaseModel, Field


class Stage2Request(BaseModel):
    txn_id:          str
    customer_id:     str
    amount:          float
    device_id:       str   = ""
    ip_address:      str   = ""
    country_code:    str   = ""
    merchant_id:     str   = ""
    channel:         str   = ""
    txn_ts:          str   = ""
    clv:             float = 0.0
    trust_score:     float = 0.5
    account_age_days:int   = 0
    customer_segment:str   = "standard"
    p_fraud_stage1:  float = 0.5
    uncertainty_stage1: float = 0.5
    stage1_routing:  str   = "PASS_TO_STAGE2"

    txn_count_1m:    int   = 0
    txn_count_5m:    int   = 0
    txn_count_1h:    int   = 0
    txn_count_24h:   int   = 0
    amount_sum_1m:   float = 0.0
    amount_sum_5m:   float = 0.0
    amount_sum_1h:   float = 0.0
    amount_sum_24h:  float = 0.0
    geo_velocity_kmh:     float = 0.0
    is_new_country:       bool  = False
    unique_countries_24h: int   = 1
    device_trust_score:   float = 0.5
    is_new_device:        bool  = False
    ip_txn_count_1h:      int   = 0
    unique_devices_24h:   int   = 1
    amount_vs_avg_ratio:  float = 1.0
    merchant_familiarity: float = 0.5
    hours_since_last_txn: float = 24.0
    has_cold_start:       bool  = False
    is_fraud:      Optional[bool] = None
    fraud_pattern: Optional[str]  = None

    def to_feature_array(self) -> List[float]:
        return [
            float(self.txn_count_1m), float(self.txn_count_5m),
            float(self.txn_count_1h), float(self.txn_count_24h),
            self.amount_sum_1m, self.amount_sum_5m,
            self.amount_sum_1h, self.amount_sum_24h,
            self.geo_velocity_kmh, float(self.is_new_country),
            float(self.unique_countries_24h),
            self.device_trust_score, float(self.is_new_device),
            float(self.ip_txn_count_1h), float(self.unique_devices_24h),
            self.amount_vs_avg_ratio, self.merchant_familiarity,
            self.hours_since_last_txn,
        ]


class GraphRiskResult(BaseModel):
    graph_risk_score:          float = 0.0
    fraud_ring_score:          float = 0.0
    mule_account_score:        float = 0.0
    synthetic_identity_score:  float = 0.0
    velocity_graph_score:      float = 0.0
    multi_hop_score:           float = 0.0
    shared_devices:            List[str] = Field(default_factory=list)
    shared_ips:                List[str] = Field(default_factory=list)
    connected_customers:       List[str] = Field(default_factory=list)
    hop_path_summary:          str       = ""
    neo4j_available:           bool      = True


class AnomalyResult(BaseModel):
    anomaly_score:           float = 0.0
    autoencoder_score:       float = 0.0
    isolation_forest_score:  float = 0.0
    is_anomaly:              bool  = False


class Stage2Response(BaseModel):
    txn_id:      str
    customer_id: str
    amount:      float
    p_fraud:     float = Field(ge=0.0, le=1.0)
    confidence:  float = Field(ge=0.0, le=1.0)
    xgb_score:   float = 0.0
    mlp_score:   float = 0.0
    graph_risk:  GraphRiskResult = Field(default_factory=GraphRiskResult)
    anomaly:     AnomalyResult   = Field(default_factory=AnomalyResult)
    p_fraud_stage1:    float = 0.5
    explanation:       Dict[str, str]   = Field(default_factory=dict)
    top_features:      Dict[str, float] = Field(default_factory=dict)
    model_versions:    Dict[str, str]   = Field(default_factory=dict)
    inference_time_ms: float = 0.0
    pipeline_stage:    int   = 2


class ModelInfoResponse(BaseModel):
    xgb_version:      str
    mlp_version:      str
    ae_version:       str
    feature_names:    List[str]
    ensemble_weights: Dict[str, float]
    neo4j_available:  bool
    loaded_at:        str = ""
