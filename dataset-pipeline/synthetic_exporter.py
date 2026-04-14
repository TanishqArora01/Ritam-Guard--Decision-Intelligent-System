"""
dataset-pipeline/synthetic_exporter.py
Synthetic Dataset Exporter

Generates a reproducible synthetic dataset using the same
SyntheticDataGenerator as the Stage 1 training pipeline.
Seeds are fixed so the same version always produces the same data.

Output files:
  synthetic_transactions.parquet   (columnar, compressed with snappy)
  synthetic_transactions.csv       (for non-Parquet consumers)
  synthetic_transactions_sample.csv (first 1000 rows for quick preview)
"""
from __future__ import annotations

import csv
import io
import json
import logging
import os
import sys
from datetime import datetime, timezone, timedelta
from typing import List, Dict

import numpy as np

from config import config
from anonymiser import Anonymiser

logger = logging.getLogger(__name__)

# Fraud patterns names aligned with generator patterns
FRAUD_PATTERNS = [
    "card_testing", "account_takeover", "velocity_attack",
    "fraud_ring", "geo_impossibility", "large_amount",
]
CHANNELS       = ["WEB", "MOBILE", "POS", "ATM", "CARD_NETWORK"]
COUNTRIES      = ["IN", "US", "GB", "AE", "DE", "SG", "AU", "NG", "RO", "RU"]
CATEGORIES     = ["grocery", "electronics", "restaurants", "fuel", "online_retail", "jewelry", "transfer"]
SEGMENTS       = ["standard", "premium", "new", "risky"]


def _generate_synthetic_rows(n: int, fraud_rate: float, seed: int) -> List[Dict]:
    """
    Generate n synthetic transaction rows with realistic distributions.
    Deterministic for a given seed.
    """
    rng = np.random.RandomState(seed)

    # Import the same generator used in training if available
    try:
        parent = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        sys.path.insert(0, os.path.join(parent, "stage1-service"))
        from model.trainer import SyntheticDataGenerator
        gen  = SyntheticDataGenerator(rng)
        X, y = gen.generate(n, fraud_rate)
        use_trainer = True
    except ImportError:
        use_trainer = False
        X = rng.randn(n, 18).astype(np.float32)
        y = (rng.rand(n) < fraud_rate).astype(float)

    rows = []
    base_ts = datetime(2024, 1, 1, tzinfo=timezone.utc)
    feature_names = config.feature_names

    for i in range(n):
        is_fraud = bool(y[i] == 1)
        features = dict(zip(feature_names, [float(v) for v in X[i]]))

        # Clamp feature values to valid ranges
        features["device_trust_score"]  = float(np.clip(features.get("device_trust_score",  0.5), 0, 1))
        features["merchant_familiarity"]= float(np.clip(features.get("merchant_familiarity", 0.5), 0, 1))
        features["amount_vs_avg_ratio"] = float(np.clip(features.get("amount_vs_avg_ratio",  1.0), 0, 100))
        features["hours_since_last_txn"]= float(np.clip(abs(features.get("hours_since_last_txn", 24)), 0, 720))
        features["geo_velocity_kmh"]    = float(max(0, features.get("geo_velocity_kmh", 0)))
        for cnt_field in ["txn_count_1m","txn_count_5m","txn_count_1h","txn_count_24h",
                          "ip_txn_count_1h","unique_devices_24h","unique_countries_24h"]:
            features[cnt_field] = int(max(0, round(features.get(cnt_field, 0))))
        features["is_new_country"] = bool(round(abs(features.get("is_new_country", 0))))
        features["is_new_device"]  = bool(round(abs(features.get("is_new_device",  0))))

        amount  = abs(float(rng.lognormal(4.5, 0.8)))
        segment = rng.choice(SEGMENTS)
        channel = rng.choice(CHANNELS)

        row = {
            "txn_id":           f"syn-{i:09d}",
            "customer_id":      f"cust-{rng.randint(1, n//10):07d}",
            "amount":           round(amount, 2),
            "currency":         "USD",
            "channel":          channel,
            "merchant_category":rng.choice(CATEGORIES),
            "country_code":     rng.choice(COUNTRIES),
            "account_age_days": int(rng.randint(1, 1825)),
            "customer_segment": segment,
            "txn_ts":           (base_ts + timedelta(seconds=int(rng.uniform(0, 365*24*3600)))).isoformat(),
            "is_fraud":         is_fraud,
            "label_source":     "SYNTHETIC",
            **features,
        }
        rows.append(row)

    return rows


def export_synthetic(output_dir: str) -> Dict[str, str]:
    """
    Generate synthetic dataset, anonymise, write Parquet + CSV.
    Returns dict of {filename: abs_path}.
    """
    logger.info("Generating %d synthetic rows (seed=%d, fraud_rate=%.2f)…",
                config.synthetic_rows, config.synthetic_seed, config.synthetic_fraud_rate)

    rows    = _generate_synthetic_rows(
        config.synthetic_rows, config.synthetic_fraud_rate, config.synthetic_seed
    )
    anon    = Anonymiser(config.anon_salt)
    rows    = anon.anonymise_batch(rows)

    fraud_ct = sum(1 for r in rows if r.get("is_fraud"))
    logger.info("Generated %d rows (%d fraud, %d legit)", len(rows), fraud_ct, len(rows)-fraud_ct)

    os.makedirs(output_dir, exist_ok=True)
    paths: Dict[str, str] = {}

    # Parquet
    parquet_path = os.path.join(output_dir, "synthetic_transactions.parquet")
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
        table = pa.Table.from_pylist(rows)
        pq.write_table(table, parquet_path, compression="snappy")
        paths["synthetic_parquet"] = parquet_path
        logger.info("Parquet written: %s (%d KB)", parquet_path, os.path.getsize(parquet_path)//1024)
    except ImportError:
        logger.warning("pyarrow not available — skipping Parquet")

    # CSV (full)
    csv_path = os.path.join(output_dir, "synthetic_transactions.csv")
    if rows:
        with open(csv_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)
        paths["synthetic_csv"] = csv_path
        logger.info("CSV written: %s", csv_path)

    # CSV sample (first 1000 rows)
    sample_path = os.path.join(output_dir, "synthetic_transactions_sample.csv")
    sample      = rows[:1000]
    if sample:
        with open(sample_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(sample[0].keys()))
            writer.writeheader()
            writer.writerows(sample)
        paths["synthetic_sample"] = sample_path

    return paths, rows
