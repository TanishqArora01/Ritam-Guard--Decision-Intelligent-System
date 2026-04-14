"""
dataset-pipeline/quality_report.py
Dataset Quality Report Generator

Computes per-dataset quality metrics:
  - Row counts and completeness per field
  - Fraud rate and label source breakdown
  - Temporal coverage (min/max date, gaps)
  - Feature distribution stats (mean, std, p5, p50, p95)
  - Consistency checks (feature range violations)

Outputs: quality_report.json
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import numpy as np

logger = logging.getLogger(__name__)


def compute_field_stats(values: List[Any]) -> dict:
    """Compute stats for a single numeric field."""
    arr = np.array([v for v in values if v is not None], dtype=np.float64)
    if len(arr) == 0:
        return {"count": 0, "null_count": len(values), "completeness_pct": 0.0}
    return {
        "count":            int(len(arr)),
        "null_count":       int(len(values) - len(arr)),
        "completeness_pct": round(len(arr) / len(values) * 100, 2),
        "mean":             round(float(np.mean(arr)), 4),
        "std":              round(float(np.std(arr)), 4),
        "min":              round(float(np.min(arr)), 4),
        "p5":               round(float(np.percentile(arr, 5)),  4),
        "p25":              round(float(np.percentile(arr, 25)), 4),
        "p50":              round(float(np.percentile(arr, 50)), 4),
        "p75":              round(float(np.percentile(arr, 75)), 4),
        "p95":              round(float(np.percentile(arr, 95)), 4),
        "max":              round(float(np.max(arr)), 4),
    }


# Expected feature ranges for consistency checks
FEATURE_RANGES = {
    "txn_count_1m":       (0, 10_000),
    "device_trust_score": (0.0, 1.0),
    "amount_vs_avg_ratio":(0.0, 100.0),
    "merchant_familiarity":(0.0, 1.0),
    "p_fraud":            (0.0, 1.0),
    "confidence":         (0.0, 1.0),
    "graph_risk_score":   (0.0, 1.0),
    "anomaly_score":      (0.0, 1.0),
}


def generate_quality_report(
    rows:          List[Dict],
    dataset_name:  str,
    dataset_type:  str,   # "synthetic" or "real"
    version:       str,
) -> Dict:
    """
    Generate a quality report for a list of row dicts.
    Returns the report dict (also written to quality_report.json by packager).
    """
    n = len(rows)
    if n == 0:
        return {"error": "Empty dataset", "row_count": 0}

    report: Dict = {
        "dataset_name":  dataset_name,
        "dataset_type":  dataset_type,
        "version":       version,
        "generated_at":  datetime.now(timezone.utc).isoformat(),
        "row_count":     n,
    }

    # ---- Label distribution ----
    labels     = [r.get("is_fraud") for r in rows]
    labeled    = [l for l in labels if l is not None]
    fraud_ct   = sum(1 for l in labeled if l is True)
    legit_ct   = sum(1 for l in labeled if l is False)
    fraud_rate = fraud_ct / max(len(labeled), 1)

    label_sources: Dict[str, int] = {}
    for r in rows:
        src = r.get("label_source", "UNKNOWN") or "UNKNOWN"
        label_sources[src] = label_sources.get(src, 0) + 1

    report["label_quality"] = {
        "labeled_rows":      len(labeled),
        "unlabeled_rows":    n - len(labeled),
        "label_rate_pct":    round(len(labeled) / n * 100, 2),
        "fraud_count":       fraud_ct,
        "legit_count":       legit_ct,
        "fraud_rate_pct":    round(fraud_rate * 100, 4),
        "label_sources":     label_sources,
    }

    # ---- Temporal coverage ----
    timestamps = []
    for r in rows:
        ts = r.get("decided_at") or r.get("txn_ts")
        if ts:
            try:
                timestamps.append(str(ts)[:19])
            except Exception:
                pass

    if timestamps:
        timestamps.sort()
        report["temporal_coverage"] = {
            "earliest":      timestamps[0],
            "latest":        timestamps[-1],
            "total_records": n,
        }

    # ---- Action distribution (decision rows) ----
    actions: Dict[str, int] = {}
    for r in rows:
        a = r.get("action")
        if a: actions[a] = actions.get(a, 0) + 1
    if actions:
        report["action_distribution"] = {
            k: {"count": v, "pct": round(v/n*100, 2)}
            for k, v in sorted(actions.items(), key=lambda x: -x[1])
        }

    # ---- Field completeness ----
    if rows:
        all_fields = set().union(*[r.keys() for r in rows[:100]])
        completeness = {}
        for field in sorted(all_fields):
            vals       = [r.get(field) for r in rows]
            null_ct    = sum(1 for v in vals if v is None or v == "")
            completeness[field] = round((n - null_ct) / n * 100, 2)
        report["field_completeness_pct"] = completeness

    # ---- Feature distribution stats ----
    numeric_fields = [
        "txn_count_1m","txn_count_5m","txn_count_1h","txn_count_24h",
        "amount_sum_1h","amount_sum_24h","geo_velocity_kmh",
        "device_trust_score","ip_txn_count_1h",
        "amount_vs_avg_ratio","merchant_familiarity","hours_since_last_txn",
        "p_fraud","confidence","graph_risk_score","anomaly_score","amount",
    ]
    feature_stats: Dict[str, dict] = {}
    for field in numeric_fields:
        vals = [r.get(field) for r in rows]
        if any(v is not None for v in vals):
            feature_stats[field] = compute_field_stats(vals)
    report["feature_statistics"] = feature_stats

    # ---- Consistency checks ----
    violations: Dict[str, int] = {}
    for field, (lo, hi) in FEATURE_RANGES.items():
        count = sum(
            1 for r in rows
            if r.get(field) is not None and not (lo <= float(r[field]) <= hi)
        )
        if count > 0:
            violations[field] = count
    report["consistency_violations"] = violations
    report["data_quality_score"] = round(
        100 * (1 - sum(violations.values()) / max(n * len(FEATURE_RANGES), 1)), 2
    )

    return report
