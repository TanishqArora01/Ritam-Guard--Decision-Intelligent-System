"""
feast/features.py
Feast Feature Definitions — Fraud Detection System

Defines:
  - Entities:      Customer (by customer_id)
  - Data Sources:  MinIO Parquet files (offline) / Redis (online)
  - Feature Views: velocity, geography, device_network, behavioral
  - Feature Service: fraud_detection_v1 (all 18 features bundled)

Usage:
  # Apply feature definitions to registry
  cd feast && feast apply

  # Materialize features to Redis online store
  feast materialize-incremental $(date -u +"%Y-%m-%dT%H:%M:%S")

  # Get online features for inference
  from feast import FeatureStore
  store = FeatureStore(repo_path="feast/")
  features = store.get_online_features(
      features=["velocity_features:txn_count_1h"],
      entity_rows=[{"customer_id": "cust-001"}],
  ).to_dict()
"""
from __future__ import annotations

from datetime import timedelta

from feast import (
    Entity,
    Feature,
    FeatureService,
    FeatureView,
    Field,
    FileSource,
    ValueType,
)
from feast.types import Float32, Int32, Bool, String


# ---------------------------------------------------------------------------
# Entity
# ---------------------------------------------------------------------------

customer = Entity(
    name        = "customer",
    join_keys   = ["customer_id"],
    description = "Bank customer identified by customer_id",
)


# ---------------------------------------------------------------------------
# Data sources (MinIO Parquet offline store)
# ---------------------------------------------------------------------------

velocity_source = FileSource(
    name        = "velocity_source",
    path        = "s3://feast-offline/customer_features/",
    timestamp_field = "event_timestamp",
    created_timestamp_column = "created_timestamp",
)

geography_source = FileSource(
    name        = "geography_source",
    path        = "s3://feast-offline/customer_features/",
    timestamp_field = "event_timestamp",
    created_timestamp_column = "created_timestamp",
)

device_source = FileSource(
    name        = "device_source",
    path        = "s3://feast-offline/customer_features/",
    timestamp_field = "event_timestamp",
    created_timestamp_column = "created_timestamp",
)

behavioral_source = FileSource(
    name        = "behavioral_source",
    path        = "s3://feast-offline/customer_features/",
    timestamp_field = "event_timestamp",
    created_timestamp_column = "created_timestamp",
)


# ---------------------------------------------------------------------------
# Feature Views
# ---------------------------------------------------------------------------

velocity_features = FeatureView(
    name     = "velocity_features",
    entities = [customer],
    ttl      = timedelta(hours=25),
    schema   = [
        Field(name="txn_count_1m",   dtype=Int32,   description="Transaction count last 1 minute"),
        Field(name="txn_count_5m",   dtype=Int32,   description="Transaction count last 5 minutes"),
        Field(name="txn_count_1h",   dtype=Int32,   description="Transaction count last 1 hour"),
        Field(name="txn_count_24h",  dtype=Int32,   description="Transaction count last 24 hours"),
        Field(name="amount_sum_1m",  dtype=Float32, description="Amount sum last 1 minute USD"),
        Field(name="amount_sum_5m",  dtype=Float32, description="Amount sum last 5 minutes USD"),
        Field(name="amount_sum_1h",  dtype=Float32, description="Amount sum last 1 hour USD"),
        Field(name="amount_sum_24h", dtype=Float32, description="Amount sum last 24 hours USD"),
    ],
    source      = velocity_source,
    online      = True,
    description = "Sliding window transaction velocity features",
    tags        = {"team": "fraud-ml", "group": "velocity"},
)

geography_features = FeatureView(
    name     = "geography_features",
    entities = [customer],
    ttl      = timedelta(hours=25),
    schema   = [
        Field(name="geo_velocity_kmh",     dtype=Float32, description="Speed between consecutive txn locations km/h"),
        Field(name="is_new_country",       dtype=Bool,    description="Country not seen before for this customer"),
        Field(name="unique_countries_24h", dtype=Int32,   description="Distinct countries last 24 hours"),
    ],
    source      = geography_source,
    online      = True,
    description = "Geographic pattern features",
    tags        = {"team": "fraud-ml", "group": "geography"},
)

device_network_features = FeatureView(
    name     = "device_network_features",
    entities = [customer],
    ttl      = timedelta(hours=25),
    schema   = [
        Field(name="device_trust_score", dtype=Float32, description="Device trust score 0-1 history-based"),
        Field(name="is_new_device",      dtype=Bool,    description="Device never seen for this customer"),
        Field(name="ip_txn_count_1h",    dtype=Int32,   description="Transactions from this IP last 1 hour"),
        Field(name="unique_devices_24h", dtype=Int32,   description="Distinct devices used last 24 hours"),
    ],
    source      = device_source,
    online      = True,
    description = "Device and network trust features",
    tags        = {"team": "fraud-ml", "group": "device"},
)

behavioral_features = FeatureView(
    name     = "behavioral_features",
    entities = [customer],
    ttl      = timedelta(days=8),
    schema   = [
        Field(name="amount_vs_avg_ratio",  dtype=Float32, description="Current amount / historical average"),
        Field(name="merchant_familiarity", dtype=Float32, description="Merchant familiarity score 0-1"),
        Field(name="hours_since_last_txn", dtype=Float32, description="Hours since last transaction"),
    ],
    source      = behavioral_source,
    online      = True,
    description = "Personalised customer behavioral baseline features",
    tags        = {"team": "fraud-ml", "group": "behavioral"},
)


# ---------------------------------------------------------------------------
# Feature Service — bundles all 18 features for model inference
# ---------------------------------------------------------------------------

fraud_detection_v1 = FeatureService(
    name        = "fraud_detection_v1",
    features    = [
        velocity_features,
        geography_features,
        device_network_features,
        behavioral_features,
    ],
    description = "All 18 fraud detection features for Stage 1/2 model inference",
    tags        = {"version": "1", "model": "lgbm+xgb+mlp"},
)
