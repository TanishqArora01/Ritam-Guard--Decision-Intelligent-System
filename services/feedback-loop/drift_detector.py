"""
feedback/drift_detector.py
Feature Distribution Drift Detection

Two statistical tests:
  1. Population Stability Index (PSI)
     PSI = Σ (P_actual - P_expected) × ln(P_actual / P_expected)
     Thresholds: PSI < 0.1 = no change, 0.1–0.2 = slight, > 0.2 = significant

  2. KL Divergence (Kullback-Leibler)
     KL(P||Q) = Σ P(x) × log(P(x) / Q(x))
     Measures information lost when Q is used to approximate P.

Both compare the distribution of each feature in the latest hour's
transactions against the training data distribution.

Used by the model_monitoring DAG to auto-trigger retraining.
"""
from __future__ import annotations

import json
import logging
import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)

# Feature names in canonical order (same as feature-engine)
FEATURE_NAMES = [
    "txn_count_1m", "txn_count_5m", "txn_count_1h", "txn_count_24h",
    "amount_sum_1m", "amount_sum_5m", "amount_sum_1h", "amount_sum_24h",
    "geo_velocity_kmh", "is_new_country", "unique_countries_24h",
    "device_trust_score", "is_new_device", "ip_txn_count_1h", "unique_devices_24h",
    "amount_vs_avg_ratio", "merchant_familiarity", "hours_since_last_txn",
]

# PSI thresholds
PSI_NO_CHANGE    = 0.10
PSI_SLIGHT       = 0.20
PSI_SIGNIFICANT  = 0.25  # triggers retraining alert

N_BINS = 10


@dataclass
class FeatureDriftResult:
    feature_name: str
    psi:          float
    kl_div:       float
    drift_level:  str   # "none", "slight", "significant"
    is_drifted:   bool


@dataclass
class DriftReport:
    run_timestamp:    str
    n_reference:      int
    n_current:        int
    features:         List[FeatureDriftResult] = field(default_factory=list)
    overall_psi:      float = 0.0
    max_psi:          float = 0.0
    drifted_features: List[str] = field(default_factory=list)
    retraining_recommended: bool = False

    def to_dict(self) -> Dict:
        return {
            "run_timestamp":          self.run_timestamp,
            "n_reference":            self.n_reference,
            "n_current":              self.n_current,
            "overall_psi":            self.overall_psi,
            "max_psi":                self.max_psi,
            "drifted_features":       self.drifted_features,
            "retraining_recommended": self.retraining_recommended,
            "feature_details": [
                {
                    "name":       f.feature_name,
                    "psi":        f.psi,
                    "kl_div":     f.kl_div,
                    "drift_level":f.drift_level,
                }
                for f in self.features
            ],
        }


# ---------------------------------------------------------------------------
# Core PSI calculation
# ---------------------------------------------------------------------------

def _compute_psi(reference: np.ndarray, current: np.ndarray,
                 n_bins: int = N_BINS) -> float:
    """
    Compute Population Stability Index between reference and current distributions.
    Uses equal-width bins over the combined range.
    """
    if len(reference) == 0 or len(current) == 0:
        return 0.0

    combined_min = min(reference.min(), current.min())
    combined_max = max(reference.max(), current.max())

    if combined_min == combined_max:
        return 0.0

    bins = np.linspace(combined_min, combined_max, n_bins + 1)

    ref_counts, _ = np.histogram(reference, bins=bins)
    cur_counts, _ = np.histogram(current,   bins=bins)

    # Avoid division by zero — replace 0 counts with small epsilon
    eps = 1e-6
    ref_pct = (ref_counts / max(ref_counts.sum(), 1)) + eps
    cur_pct = (cur_counts / max(cur_counts.sum(), 1)) + eps

    psi = np.sum((cur_pct - ref_pct) * np.log(cur_pct / ref_pct))
    return float(round(abs(psi), 6))


def _compute_kl_div(reference: np.ndarray, current: np.ndarray,
                    n_bins: int = N_BINS) -> float:
    """KL divergence D_KL(current || reference)."""
    if len(reference) == 0 or len(current) == 0:
        return 0.0

    combined_min = min(reference.min(), current.min())
    combined_max = max(reference.max(), current.max())

    if combined_min == combined_max:
        return 0.0

    bins = np.linspace(combined_min, combined_max, n_bins + 1)
    ref_counts, _ = np.histogram(reference, bins=bins)
    cur_counts, _ = np.histogram(current,   bins=bins)

    eps = 1e-6
    P = cur_counts / max(cur_counts.sum(), 1) + eps   # current
    Q = ref_counts / max(ref_counts.sum(), 1) + eps   # reference

    kl = np.sum(P * np.log(P / Q))
    return float(round(abs(kl), 6))


# ---------------------------------------------------------------------------
# Drift detector
# ---------------------------------------------------------------------------

class DriftDetector:

    def __init__(self, psi_threshold: float = PSI_SIGNIFICANT):
        self.psi_threshold = psi_threshold

    def detect(
        self,
        reference_data: np.ndarray,   # (n_ref, n_features) — training distribution
        current_data:   np.ndarray,   # (n_cur, n_features) — recent production data
        feature_names:  List[str] = None,
    ) -> DriftReport:
        """
        Run PSI + KL divergence on all features.

        Args:
            reference_data: Training data feature matrix
            current_data:   Recent production feature matrix (last N hours)
            feature_names:  Feature column names

        Returns:
            DriftReport with per-feature scores and overall assessment
        """
        from datetime import datetime, timezone
        names = feature_names or FEATURE_NAMES

        assert reference_data.shape[1] == current_data.shape[1], \
            f"Feature count mismatch: ref={reference_data.shape[1]} cur={current_data.shape[1]}"

        n_features = min(reference_data.shape[1], len(names))
        results    = []

        for i in range(n_features):
            ref_col = reference_data[:, i].astype(float)
            cur_col = current_data[:, i].astype(float)

            psi    = _compute_psi(ref_col, cur_col)
            kl_div = _compute_kl_div(ref_col, cur_col)

            if psi < PSI_NO_CHANGE:
                drift_level = "none"
            elif psi < PSI_SLIGHT:
                drift_level = "slight"
            else:
                drift_level = "significant"

            results.append(FeatureDriftResult(
                feature_name = names[i],
                psi          = psi,
                kl_div       = kl_div,
                drift_level  = drift_level,
                is_drifted   = psi >= self.psi_threshold,
            ))

        drifted = [r.feature_name for r in results if r.is_drifted]
        all_psi = [r.psi for r in results]
        overall_psi = float(np.mean(all_psi))
        max_psi     = float(np.max(all_psi))

        report = DriftReport(
            run_timestamp           = datetime.now(timezone.utc).isoformat(),
            n_reference             = len(reference_data),
            n_current               = len(current_data),
            features                = results,
            overall_psi             = round(overall_psi, 6),
            max_psi                 = round(max_psi,     6),
            drifted_features        = drifted,
            retraining_recommended  = len(drifted) >= 3 or max_psi > PSI_SIGNIFICANT,
        )

        logger.info(
            "Drift detection: overall_psi=%.4f max_psi=%.4f drifted=%d/%d retrain=%s",
            overall_psi, max_psi, len(drifted), n_features,
            report.retraining_recommended,
        )
        return report

    def load_reference_from_minio(
        self,
        minio_endpoint:  str,
        access_key:      str,
        secret_key:      str,
        bucket:          str  = "feature-snapshots",
        n_snapshots:     int  = 24,   # last 24 hourly snapshots = 1 day
    ) -> Optional[np.ndarray]:
        """Load reference feature distribution from MinIO Parquet snapshots."""
        try:
            import io
            from minio import Minio
            import pyarrow.parquet as pq

            endpoint = minio_endpoint.replace("http://", "").replace("https://", "")
            client   = Minio(endpoint, access_key=access_key,
                             secret_key=secret_key, secure=False)

            objects = sorted(
                client.list_objects(bucket, prefix="hourly/", recursive=True),
                key=lambda o: o.object_name,
                reverse=True,
            )[:n_snapshots]

            frames = []
            for obj in objects:
                try:
                    data = client.get_object(bucket, obj.object_name)
                    buf  = io.BytesIO(data.read())
                    tbl  = pq.read_table(buf)
                    frames.append(tbl.to_pandas())
                except Exception as e:
                    logger.debug("Could not load snapshot %s: %s", obj.object_name, e)

            if not frames:
                logger.warning("No snapshots found in MinIO")
                return None

            import pandas as pd
            combined = pd.concat(frames, ignore_index=True)
            cols     = [c for c in FEATURE_NAMES if c in combined.columns]
            return combined[cols].to_numpy(dtype=float)

        except Exception as e:
            logger.warning("Could not load reference from MinIO: %s", e)
            return None
