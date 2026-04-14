"""
features/registry.py
Canonical feature registry for the fraud detection system.

Defines:
  - FeatureVector: the enriched transaction object published to txn-enriched
  - FEATURE_SCHEMA: metadata for every feature (group, dtype, description)

This is the contract between the feature engine and Stage 1/2/3 consumers.
18 features across 4 groups.
"""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Dict, Any, Optional


# ---------------------------------------------------------------------------
# Feature metadata registry
# ---------------------------------------------------------------------------
FEATURE_SCHEMA: Dict[str, Dict[str, str]] = {
    # --- Group 1: Velocity (8 features) ---
    "txn_count_1m":    {"group": "velocity",  "dtype": "int",   "desc": "Transaction count in last 1 minute"},
    "txn_count_5m":    {"group": "velocity",  "dtype": "int",   "desc": "Transaction count in last 5 minutes"},
    "txn_count_1h":    {"group": "velocity",  "dtype": "int",   "desc": "Transaction count in last 1 hour"},
    "txn_count_24h":   {"group": "velocity",  "dtype": "int",   "desc": "Transaction count in last 24 hours"},
    "amount_sum_1m":   {"group": "velocity",  "dtype": "float", "desc": "Total spend in last 1 minute (USD)"},
    "amount_sum_5m":   {"group": "velocity",  "dtype": "float", "desc": "Total spend in last 5 minutes (USD)"},
    "amount_sum_1h":   {"group": "velocity",  "dtype": "float", "desc": "Total spend in last 1 hour (USD)"},
    "amount_sum_24h":  {"group": "velocity",  "dtype": "float", "desc": "Total spend in last 24 hours (USD)"},

    # --- Group 2: Geography (3 features) ---
    "geo_velocity_kmh":    {"group": "geography", "dtype": "float", "desc": "Speed between last and current location (km/h)"},
    "is_new_country":      {"group": "geography", "dtype": "bool",  "desc": "Country never seen for this customer"},
    "unique_countries_24h":{"group": "geography", "dtype": "int",   "desc": "Distinct countries in last 24 hours"},

    # --- Group 3: Device & Network (4 features) ---
    "device_trust_score":  {"group": "device",    "dtype": "float", "desc": "Device trust score 0–1 (history-based)"},
    "is_new_device":       {"group": "device",    "dtype": "bool",  "desc": "Device not seen before for this customer"},
    "ip_txn_count_1h":     {"group": "device",    "dtype": "int",   "desc": "Transactions from this IP in last 1 hour"},
    "unique_devices_24h":  {"group": "device",    "dtype": "int",   "desc": "Distinct devices used in last 24 hours"},

    # --- Group 4: Behavioral (3 features) ---
    "amount_vs_avg_ratio": {"group": "behavioral","dtype": "float", "desc": "Current amount / customer historical average"},
    "merchant_familiarity":{"group": "behavioral","dtype": "float", "desc": "Merchant familiarity score 0–1"},
    "hours_since_last_txn":{"group": "behavioral","dtype": "float", "desc": "Hours elapsed since customer's last transaction"},
}

FEATURE_NAMES = list(FEATURE_SCHEMA.keys())  # canonical ordering for ML models


# ---------------------------------------------------------------------------
# FeatureVector — enriched transaction with all 18 computed features
# ---------------------------------------------------------------------------
@dataclass
class FeatureVector:
    """
    Published to: txn-enriched topic
    Consumed by:  Stage 1 (fast risk), Stage 2 (deep intel), ClickHouse sink

    Contains the original transaction fields + all 18 computed features
    + feature computation metadata.
    """

    # --- Original transaction fields (pass-through) ---
    txn_id:            str = ""
    external_txn_id:   str = ""
    customer_id:       str = ""
    customer_segment:  str = ""
    clv:               float = 0.0
    trust_score:       float = 0.5
    account_age_days:  int   = 0
    amount:            float = 0.0
    currency:          str   = "USD"
    channel:           str   = ""
    merchant_id:       str   = ""
    merchant_category: str   = ""
    device_id:         str   = ""
    ip_address:        str   = ""
    country_code:      str   = ""
    city:              str   = ""
    lat:               float = 0.0
    lng:               float = 0.0
    txn_ts:            str   = ""
    is_fraud:          bool  = False          # ground truth (training only)
    fraud_pattern:     Optional[str] = None  # ground truth (training only)
    fraud_scenario_id: Optional[str] = None  # ground truth (training only)

    # --- Group 1: Velocity features ---
    txn_count_1m:   int   = 0
    txn_count_5m:   int   = 0
    txn_count_1h:   int   = 0
    txn_count_24h:  int   = 0
    amount_sum_1m:  float = 0.0
    amount_sum_5m:  float = 0.0
    amount_sum_1h:  float = 0.0
    amount_sum_24h: float = 0.0

    # --- Group 2: Geography features ---
    geo_velocity_kmh:     float = 0.0
    is_new_country:       bool  = False
    unique_countries_24h: int   = 1

    # --- Group 3: Device & Network features ---
    device_trust_score: float = 0.5
    is_new_device:      bool  = False
    ip_txn_count_1h:    int   = 0
    unique_devices_24h: int   = 1

    # --- Group 4: Behavioral features ---
    amount_vs_avg_ratio:  float = 1.0
    merchant_familiarity: float = 0.0
    hours_since_last_txn: float = 24.0

    # --- Computation metadata ---
    feature_engine_version: str = "1.0.0"
    features_computed_at:   str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    feature_latency_ms: float = 0.0

    # --- Uncertainty signal for Stage 1 ---
    # Set True if any feature could not be computed (cold start / Redis miss)
    has_cold_start: bool = False

    def to_feature_array(self) -> list:
        """Return features in canonical order for ML model input."""
        return [getattr(self, name) for name in FEATURE_NAMES]

    def to_kafka_bytes(self) -> bytes:
        return json.dumps(asdict(self)).encode("utf-8")

    @property
    def partition_key(self) -> bytes:
        return self.customer_id.encode("utf-8")

    @classmethod
    def from_raw_event(cls, raw: Dict[str, Any]) -> "FeatureVector":
        """Construct a FeatureVector from a raw transaction event dict."""
        fv = cls()
        for field_name in [
            "txn_id", "external_txn_id", "customer_id", "customer_segment",
            "clv", "trust_score", "account_age_days", "amount", "currency",
            "channel", "merchant_id", "merchant_category", "device_id",
            "ip_address", "country_code", "city", "lat", "lng", "txn_ts",
            "is_fraud", "fraud_pattern", "fraud_scenario_id",
        ]:
            if field_name in raw:
                setattr(fv, field_name, raw[field_name])
        return fv
