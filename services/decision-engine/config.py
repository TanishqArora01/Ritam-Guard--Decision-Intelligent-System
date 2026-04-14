"""
config.py — Stage 3 Decision Optimization Engine configuration.
All parameters overridable at runtime via environment variables.
"""
from __future__ import annotations
import os
from dataclasses import dataclass, field
from typing import Dict


@dataclass
class Stage3Config:

    service_name:    str = "stage3-decision-engine"
    service_version: str = "1.0.0"
    host:            str = os.getenv("HOST", "0.0.0.0")
    port:            int = int(os.getenv("PORT", "8300"))

    # Kafka
    kafka_bootstrap_servers: str  = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
    kafka_topic_stage2:      str  = os.getenv("KAFKA_TOPIC_STAGE2",   "txn-stage2")
    kafka_topic_decisions:   str  = os.getenv("KAFKA_TOPIC_DECISIONS","decisions")
    kafka_topic_ab:          str  = os.getenv("KAFKA_TOPIC_AB",       "decisions-ab")
    kafka_consumer_group:    str  = os.getenv("KAFKA_CONSUMER_GROUP", "stage3-service-v1")
    kafka_auto_offset_reset: str  = os.getenv("KAFKA_AUTO_OFFSET_RESET", "latest")
    kafka_enabled:           bool = os.getenv("KAFKA_ENABLED", "true").lower() == "true"

    # -------------------------------------------------------------------------
    # Cost function parameters  (all in USD)
    # -------------------------------------------------------------------------

    # Cost of manually reviewing one transaction (analyst time)
    cost_manual_review: float = float(os.getenv("COST_MANUAL_REVIEW",   "15.0"))

    # Cost of sending a step-up auth challenge (SMS + user friction)
    cost_stepup:        float = float(os.getenv("COST_STEPUP",           "2.0"))

    # Probability that step-up auth challenge is successfully completed
    # (legitimate users almost always complete; fraudsters often abandon)
    p_stepup_legit_completes: float = float(os.getenv("P_STEPUP_LEGIT", "0.92"))
    p_stepup_fraud_blocked:   float = float(os.getenv("P_STEPUP_FRAUD", "0.80"))

    # -------------------------------------------------------------------------
    # CLV friction multiplier
    # Friction cost = p_false_positive * CLV * friction_multiplier
    # Represents the expected future revenue lost by annoying a good customer
    # -------------------------------------------------------------------------
    clv_friction_multiplier: float = float(os.getenv("CLV_FRICTION_MULT", "0.001"))

    # -------------------------------------------------------------------------
    # Action thresholds — override the cost engine for specific rules
    # -------------------------------------------------------------------------
    # Hard block threshold: regardless of cost, always block above this
    hard_block_threshold:   float = float(os.getenv("HARD_BLOCK_THRESHOLD",  "0.95"))

    # Hard approve threshold: regardless of cost, always approve below this
    hard_approve_threshold: float = float(os.getenv("HARD_APPROVE_THRESHOLD","0.02"))

    # Minimum uncertainty to always escalate to manual review
    uncertainty_review_threshold: float = float(os.getenv("UNCERTAINTY_REVIEW","0.40"))

    # -------------------------------------------------------------------------
    # A/B Experimentation
    # -------------------------------------------------------------------------
    ab_enabled:         bool  = os.getenv("AB_ENABLED", "true").lower() == "true"
    ab_experiment_id:   str   = os.getenv("AB_EXPERIMENT_ID",   "exp-001")
    ab_control_weight:  float = float(os.getenv("AB_CONTROL_WEIGHT",  "0.50"))
    ab_treatment_weight:float = float(os.getenv("AB_TREATMENT_WEIGHT","0.50"))
    # Shadow mode: run both policies but only execute the control action
    ab_shadow_mode:     bool  = os.getenv("AB_SHADOW_MODE", "false").lower() == "true"

    # -------------------------------------------------------------------------
    # Trust score thresholds
    # -------------------------------------------------------------------------
    # Below this trust score, step-up auth is triggered more aggressively
    low_trust_threshold: float = float(os.getenv("LOW_TRUST_THRESHOLD", "0.40"))

    # -------------------------------------------------------------------------
    # Segment-based CLV overrides (USD) — used when CLV is 0 (cold start)
    # -------------------------------------------------------------------------
    clv_defaults: Dict[str, float] = field(default_factory=lambda: {
        "premium":  float(os.getenv("CLV_DEFAULT_PREMIUM",  "75000")),
        "standard": float(os.getenv("CLV_DEFAULT_STANDARD", "12000")),
        "new":      float(os.getenv("CLV_DEFAULT_NEW",       "1500")),
        "risky":    float(os.getenv("CLV_DEFAULT_RISKY",     "2000")),
    })

    # -------------------------------------------------------------------------
    # SHAP explanation config
    # -------------------------------------------------------------------------
    max_explanation_signals: int = int(os.getenv("MAX_EXPLANATION_SIGNALS", "5"))

    # -------------------------------------------------------------------------
    # Observability
    # -------------------------------------------------------------------------
    log_level:    str = os.getenv("LOG_LEVEL",    "INFO")
    metrics_port: int = int(os.getenv("METRICS_PORT", "9105"))


config = Stage3Config()
