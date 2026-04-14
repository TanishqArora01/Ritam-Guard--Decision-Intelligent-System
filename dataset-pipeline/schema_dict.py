"""
dataset-pipeline/schema_dict.py
Schema Dictionary Generator

Produces two outputs:
  schema_dictionary.json   — machine-readable field definitions
  schema_dictionary.html   — human-readable HTML report for data consumers

Covers:
  - 18 computed features (velocity, geography, device, behavioral)
  - Decision output fields (action, p_fraud, confidence, costs)
  - Transaction context fields (amount, channel, country_code, etc.)
  - Anonymisation notes per field
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Dict, List


SCHEMA: List[Dict] = [
    # ---- Transaction context ----
    {"field": "txn_id",          "group": "identity",   "dtype": "string",  "pii": False,
     "description": "Unique transaction identifier. Not anonymised — needed for audit joins.",
     "example": "550e8400-e29b-41d4-a716-446655440000"},
    {"field": "customer_id",     "group": "identity",   "dtype": "string",  "pii": True,
     "description": "Pseudonymous customer identifier (SHA-256 of original, salted). Deterministic within a release.",
     "example": "anon_a3f2b1c4d5e6f7a8"},
    {"field": "amount",          "group": "transaction","dtype": "float64", "pii": False,
     "description": "Transaction amount in the specified currency. Not bucketed — exact value preserved for ML training.",
     "example": 149.99, "range": "[0.01, unlimited]"},
    {"field": "currency",        "group": "transaction","dtype": "string",  "pii": False,
     "description": "ISO 4217 currency code.", "example": "USD"},
    {"field": "channel",         "group": "transaction","dtype": "string",  "pii": False,
     "description": "Transaction channel.", "example": "WEB",
     "enum": ["WEB","MOBILE","POS","ATM","CARD_NETWORK"]},
    {"field": "merchant_category","group": "transaction","dtype": "string", "pii": False,
     "description": "MCC-derived merchant category.", "example": "electronics"},
    {"field": "country_code",    "group": "transaction","dtype": "string",  "pii": False,
     "description": "ISO 3166-1 alpha-2 country code of the transaction.", "example": "IN"},
    {"field": "lat",             "group": "transaction","dtype": "float32", "pii": True,
     "description": "Latitude rounded to 2 decimal places (~1km precision).",
     "example": 19.08, "range": "[-90, 90]"},
    {"field": "lng",             "group": "transaction","dtype": "float32", "pii": True,
     "description": "Longitude rounded to 2 decimal places (~1km precision).",
     "example": 72.88, "range": "[-180, 180]"},
    {"field": "txn_ts",          "group": "transaction","dtype": "datetime","pii": False,
     "description": "Transaction timestamp (UTC ISO 8601).",
     "example": "2024-06-15T10:30:00+00:00"},
    {"field": "account_age_days","group": "transaction","dtype": "int32",   "pii": False,
     "description": "Age of the customer account in days at transaction time.",
     "example": 365, "range": "[0, unlimited]"},
    {"field": "customer_segment","group": "transaction","dtype": "string",  "pii": False,
     "description": "Customer tier.", "example": "standard",
     "enum": ["new","standard","premium","risky"]},

    # ---- Velocity features ----
    {"field": "txn_count_1m",    "group": "velocity",   "dtype": "int32",   "pii": False,
     "description": "Number of transactions by this customer in the last 1 minute (sliding window).",
     "example": 2, "range": "[0, unlimited]"},
    {"field": "txn_count_5m",    "group": "velocity",   "dtype": "int32",   "pii": False,
     "description": "Transaction count in last 5 minutes.", "example": 4},
    {"field": "txn_count_1h",    "group": "velocity",   "dtype": "int32",   "pii": False,
     "description": "Transaction count in last 1 hour.", "example": 8},
    {"field": "txn_count_24h",   "group": "velocity",   "dtype": "int32",   "pii": False,
     "description": "Transaction count in last 24 hours.", "example": 15},
    {"field": "amount_sum_1m",   "group": "velocity",   "dtype": "float32", "pii": False,
     "description": "Total spend in last 1 minute (USD).", "example": 199.98},
    {"field": "amount_sum_5m",   "group": "velocity",   "dtype": "float32", "pii": False,
     "description": "Total spend in last 5 minutes (USD).", "example": 450.50},
    {"field": "amount_sum_1h",   "group": "velocity",   "dtype": "float32", "pii": False,
     "description": "Total spend in last 1 hour (USD).", "example": 1200.00},
    {"field": "amount_sum_24h",  "group": "velocity",   "dtype": "float32", "pii": False,
     "description": "Total spend in last 24 hours (USD).", "example": 3500.00},

    # ---- Geography features ----
    {"field": "geo_velocity_kmh","group": "geography",  "dtype": "float32", "pii": False,
     "description": "Inferred travel speed between consecutive transaction locations (km/h). Values >800 suggest geographic impossibility.",
     "example": 12.5, "range": "[0, unlimited]"},
    {"field": "is_new_country",  "group": "geography",  "dtype": "bool",    "pii": False,
     "description": "True if this country code has not been seen for this customer in the last 24h.",
     "example": False},
    {"field": "unique_countries_24h","group": "geography","dtype": "int32",  "pii": False,
     "description": "Number of distinct countries seen for this customer in the last 24 hours.",
     "example": 1, "range": "[1, unlimited]"},

    # ---- Device & Network features ----
    {"field": "device_trust_score","group": "device",   "dtype": "float32", "pii": False,
     "description": "Device trust score [0,1]. 0=brand new device, 1=device seen 5+ times.",
     "example": 0.8, "range": "[0.0, 1.0]"},
    {"field": "is_new_device",   "group": "device",     "dtype": "bool",    "pii": False,
     "description": "True if this device has never been used by this customer before.",
     "example": False},
    {"field": "ip_txn_count_1h", "group": "device",     "dtype": "int32",   "pii": False,
     "description": "Number of transactions from this IP address in the last hour (all customers).",
     "example": 3, "range": "[0, unlimited]"},
    {"field": "unique_devices_24h","group": "device",   "dtype": "int32",   "pii": False,
     "description": "Number of distinct devices used by this customer in the last 24 hours.",
     "example": 1, "range": "[1, unlimited]"},

    # ---- Behavioral features ----
    {"field": "amount_vs_avg_ratio","group": "behavioral","dtype": "float32","pii": False,
     "description": "Current transaction amount divided by this customer's historical average. Welford online mean.",
     "example": 1.2, "range": "[0.01, 100.0]"},
    {"field": "merchant_familiarity","group": "behavioral","dtype": "float32","pii": False,
     "description": "Merchant familiarity score [0,1]. 0=never visited, 1=frequently visited.",
     "example": 0.7, "range": "[0.0, 1.0]"},
    {"field": "hours_since_last_txn","group": "behavioral","dtype": "float32","pii": False,
     "description": "Hours elapsed since this customer's previous transaction. Capped at 720h (30 days).",
     "example": 6.5, "range": "[0.0, 720.0]"},

    # ---- Decision outputs ----
    {"field": "action",          "group": "decision",   "dtype": "string",  "pii": False,
     "description": "Final system decision.", "example": "APPROVE",
     "enum": ["APPROVE","BLOCK","STEP_UP_AUTH","MANUAL_REVIEW"]},
    {"field": "p_fraud",         "group": "decision",   "dtype": "float32", "pii": False,
     "description": "Ensemble fraud probability from Stage 2 (XGBoost+MLP+Graph+Anomaly).",
     "example": 0.142, "range": "[0.0, 1.0]"},
    {"field": "confidence",      "group": "decision",   "dtype": "float32", "pii": False,
     "description": "1 - ensemble uncertainty. Low values → model components disagreed.",
     "example": 0.87, "range": "[0.0, 1.0]"},
    {"field": "graph_risk_score","group": "decision",   "dtype": "float32", "pii": False,
     "description": "Combined Neo4j graph risk score from 5 patterns (fraud_ring, mule, synthetic_id, velocity, multi_hop).",
     "example": 0.0, "range": "[0.0, 1.0]"},
    {"field": "anomaly_score",   "group": "decision",   "dtype": "float32", "pii": False,
     "description": "Combined anomaly score: 0.6×autoencoder_reconstruction_error + 0.4×isolation_forest.",
     "example": 0.05, "range": "[0.0, 1.0]"},
    {"field": "optimal_cost_usd","group": "decision",   "dtype": "float32", "pii": False,
     "description": "Expected cost of the chosen action in USD (argmin of cost function).",
     "example": 2.14},
    {"field": "latency_ms",      "group": "decision",   "dtype": "float32", "pii": False,
     "description": "End-to-end pipeline latency in milliseconds.",
     "example": 87.3, "range": "[0, unlimited]"},
    {"field": "model_version",   "group": "decision",   "dtype": "string",  "pii": False,
     "description": "MLflow model version string at decision time.", "example": "mlflow-v12"},
    {"field": "decided_at",      "group": "decision",   "dtype": "datetime","pii": False,
     "description": "Decision timestamp (UTC ISO 8601).",
     "example": "2024-06-15T10:30:00.123+00:00"},
    {"field": "is_fraud",        "group": "label",      "dtype": "bool",    "pii": False,
     "description": "Ground truth fraud label. Source: chargebacks (highest confidence) or analyst verdict. NULL = unlabeled.",
     "example": False},
    {"field": "label_source",    "group": "label",      "dtype": "string",  "pii": False,
     "description": "Origin of the ground truth label.",
     "enum": ["CHARGEBACK","ANALYST_FRAUD","ANALYST_LEGIT","SYNTHETIC"],
     "example": "CHARGEBACK"},
]


def generate_schema_dict(version: str) -> dict:
    groups = {}
    for f in SCHEMA:
        g = f["group"]
        groups.setdefault(g, []).append(f)
    return {
        "dataset_name":   "Fraud Detection Decision Dataset",
        "version":        version,
        "generated_at":   datetime.now(timezone.utc).isoformat(),
        "total_fields":   len(SCHEMA),
        "groups":         list(groups.keys()),
        "pii_fields":     [f["field"] for f in SCHEMA if f.get("pii")],
        "anonymised_fields": [f["field"] for f in SCHEMA if f.get("pii")],
        "fields":         SCHEMA,
        "feature_groups": {
            "velocity":   {"count": 8, "description": "Sliding window transaction counts and sums"},
            "geography":  {"count": 3, "description": "Location-based signals"},
            "device":     {"count": 4, "description": "Device trust and network signals"},
            "behavioral": {"count": 3, "description": "Customer baseline deviation signals"},
        },
    }


def generate_html(schema: dict) -> str:
    group_colors = {
        "identity":"#dbeafe","transaction":"#f0fdf4","velocity":"#fef9c3",
        "geography":"#fce7f3","device":"#ede9fe","behavioral":"#ffedd5",
        "decision":"#f1f5f9","label":"#dcfce7",
    }
    rows = ""
    for f in schema["fields"]:
        color = group_colors.get(f["group"], "#fff")
        pii   = "⚠ Anonymised" if f.get("pii") else "—"
        enums = ", ".join(f.get("enum", [])) or "—"
        rows += f"""
        <tr style="background:{color}">
          <td><code>{f['field']}</code></td>
          <td>{f['group']}</td>
          <td><code>{f['dtype']}</code></td>
          <td>{f['description']}</td>
          <td><code>{f.get('example','—')}</code></td>
          <td>{f.get('range','—')}</td>
          <td>{enums}</td>
          <td>{pii}</td>
        </tr>"""

    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8">
<title>Schema Dictionary v{schema['version']}</title>
<style>
  body {{font-family:system-ui,sans-serif;max-width:1400px;margin:0 auto;padding:2rem;color:#1e293b}}
  h1{{color:#1e40af}} table{{width:100%;border-collapse:collapse;font-size:13px}}
  th{{background:#1e40af;color:#fff;padding:8px;text-align:left}}
  td{{padding:6px 8px;border-bottom:1px solid #e2e8f0;vertical-align:top}}
  code{{background:#f1f5f9;padding:1px 4px;border-radius:3px;font-size:12px}}
  .badge{{display:inline-block;padding:2px 8px;border-radius:999px;font-size:11px;font-weight:600}}
</style></head><body>
<h1>Fraud Detection Dataset — Schema Dictionary</h1>
<p><strong>Version:</strong> {schema['version']} &nbsp;|&nbsp;
   <strong>Generated:</strong> {schema['generated_at']} &nbsp;|&nbsp;
   <strong>Fields:</strong> {schema['total_fields']} &nbsp;|&nbsp;
   <strong>Anonymised PII fields:</strong> {len(schema['pii_fields'])}</p>
<table>
<tr><th>Field</th><th>Group</th><th>Type</th><th>Description</th>
    <th>Example</th><th>Range</th><th>Enum values</th><th>PII</th></tr>
{rows}
</table>
</body></html>"""
