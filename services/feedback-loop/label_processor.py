"""
feedback/label_processor.py
Feedback Label Processor

Combines two ground-truth label sources into training-ready rows:

  1. Analyst Labels (from manual review queue)
       Source: audit.analyst_labels table
       Quality: HIGH — human-verified, but slow (hours to days lag)
       Label: FRAUD | LEGITIMATE | UNCERTAIN

  2. Chargeback Labels (from payment processor)
       Source: audit.chargebacks table
       Quality: HIGHEST — confirmed by bank, no ambiguity
       Label: always FRAUD

Merging strategy:
  - Chargeback labels always win (highest confidence)
  - Analyst FRAUD labels win over analyst LEGITIMATE
  - UNCERTAIN labels are excluded from training
  - De-duplicate by txn_id — take the most confident label

Output:
  - Parquet files written to MinIO: training-datasets/labels/YYYY-MM-DD/
  - One row per labeled transaction with:
    txn_id, true_label (0/1), label_source, confidence, feature_vector
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)

LABEL_PRIORITY = {"CHARGEBACK": 3, "ANALYST_FRAUD": 2, "ANALYST_LEGIT": 1}


@dataclass
class LabeledRow:
    txn_id:       str
    customer_id:  str
    true_label:   int     # 1=fraud, 0=legitimate
    label_source: str     # CHARGEBACK | ANALYST | DISPUTE
    confidence:   float   # 0-1
    labeled_at:   str
    model_p_fraud:     float = 0.0
    model_action:      str   = ""
    model_version:     str   = ""
    ab_experiment_id:  str   = ""
    feature_vector:    Optional[List[float]] = None


class LabelProcessor:

    def __init__(self, pg_dsn: str):
        self.pg_dsn = pg_dsn

    def _get_connection(self):
        import psycopg2
        return psycopg2.connect(self.pg_dsn)

    def fetch_analyst_labels(
        self,
        since: datetime,
        until: datetime,
    ) -> List[LabeledRow]:
        """Pull analyst labels from PostgreSQL."""
        sql = """
        SELECT
            al.txn_id,
            te.customer_id,
            al.label,
            al.confidence,
            al.labeled_at,
            dr.p_fraud     AS model_p_fraud,
            dr.action      AS model_action,
            dr.model_version,
            dr.ab_experiment_id
        FROM audit.analyst_labels al
        LEFT JOIN transactions.events te ON te.external_txn_id = al.txn_id
        LEFT JOIN decisions.records   dr ON dr.txn_id = al.txn_id
        WHERE al.labeled_at BETWEEN %(since)s AND %(until)s
          AND al.label != 'UNCERTAIN'
        ORDER BY al.labeled_at DESC
        """
        rows = []
        try:
            conn = self._get_connection()
            cur  = conn.cursor()
            cur.execute(sql, {"since": since, "until": until})
            for row in cur.fetchall():
                label = 1 if row[2] == "FRAUD" else 0
                rows.append(LabeledRow(
                    txn_id        = str(row[0]),
                    customer_id   = str(row[1] or ""),
                    true_label    = label,
                    label_source  = f"ANALYST_{'FRAUD' if label else 'LEGIT'}",
                    confidence    = float(row[3] or 0.8),
                    labeled_at    = str(row[4]),
                    model_p_fraud = float(row[5] or 0.0),
                    model_action  = str(row[6] or ""),
                    model_version = str(row[7] or ""),
                    ab_experiment_id = str(row[8] or ""),
                ))
            conn.close()
        except Exception as e:
            logger.error("Failed to fetch analyst labels: %s", e)
        logger.info("Fetched %d analyst labels", len(rows))
        return rows

    def fetch_chargeback_labels(
        self,
        since: datetime,
        until: datetime,
    ) -> List[LabeledRow]:
        """Pull chargeback ground truth from PostgreSQL."""
        sql = """
        SELECT
            cb.txn_id,
            te.customer_id,
            cb.amount,
            cb.reason_code,
            cb.reported_at,
            dr.p_fraud     AS model_p_fraud,
            dr.action      AS model_action,
            dr.model_version,
            dr.ab_experiment_id
        FROM audit.chargebacks cb
        LEFT JOIN transactions.events te ON te.external_txn_id = cb.txn_id
        LEFT JOIN decisions.records   dr ON dr.txn_id = cb.txn_id
        WHERE cb.processed_at BETWEEN %(since)s AND %(until)s
        """
        rows = []
        try:
            conn = self._get_connection()
            cur  = conn.cursor()
            cur.execute(sql, {"since": since, "until": until})
            for row in cur.fetchall():
                rows.append(LabeledRow(
                    txn_id        = str(row[0]),
                    customer_id   = str(row[1] or ""),
                    true_label    = 1,          # chargebacks are always fraud
                    label_source  = "CHARGEBACK",
                    confidence    = 1.0,        # highest confidence
                    labeled_at    = str(row[4]),
                    model_p_fraud = float(row[5] or 0.0),
                    model_action  = str(row[6] or ""),
                    model_version = str(row[7] or ""),
                    ab_experiment_id = str(row[8] or ""),
                ))
            conn.close()
        except Exception as e:
            logger.error("Failed to fetch chargeback labels: %s", e)
        logger.info("Fetched %d chargeback labels", len(rows))
        return rows

    def merge_labels(self, *label_lists: List[LabeledRow]) -> List[LabeledRow]:
        """
        De-duplicate by txn_id, keeping highest-priority label.
        Priority: CHARGEBACK > ANALYST_FRAUD > ANALYST_LEGIT
        """
        best: Dict[str, LabeledRow] = {}
        for label_list in label_lists:
            for row in label_list:
                if row.txn_id not in best:
                    best[row.txn_id] = row
                else:
                    existing_priority = LABEL_PRIORITY.get(best[row.txn_id].label_source, 0)
                    new_priority      = LABEL_PRIORITY.get(row.label_source, 0)
                    if new_priority > existing_priority:
                        best[row.txn_id] = row

        merged = list(best.values())
        n_fraud = sum(1 for r in merged if r.true_label == 1)
        n_legit = sum(1 for r in merged if r.true_label == 0)
        logger.info("Merged: %d total (%d fraud, %d legit)", len(merged), n_fraud, n_legit)
        return merged

    def write_to_minio(
        self,
        labels:       List[LabeledRow],
        minio_endpoint: str,
        access_key:   str,
        secret_key:   str,
        bucket:       str = "training-datasets",
    ) -> Optional[str]:
        """
        Write merged labels as Parquet to MinIO.
        Path: training-datasets/labels/YYYY-MM-DD/labels_{timestamp}.parquet
        Returns the MinIO object path or None on failure.
        """
        if not labels:
            logger.info("No labels to write")
            return None

        try:
            import io
            import pyarrow as pa
            import pyarrow.parquet as pq
            from minio import Minio

            now  = datetime.now(timezone.utc)
            path = f"labels/{now.strftime('%Y-%m-%d')}/labels_{now.strftime('%Y%m%d_%H%M%S')}.parquet"

            # Build Arrow table
            data = {
                "txn_id":       [r.txn_id        for r in labels],
                "customer_id":  [r.customer_id   for r in labels],
                "true_label":   [r.true_label     for r in labels],
                "label_source": [r.label_source   for r in labels],
                "confidence":   [r.confidence     for r in labels],
                "labeled_at":   [r.labeled_at     for r in labels],
                "model_p_fraud":[r.model_p_fraud  for r in labels],
                "model_action": [r.model_action   for r in labels],
                "model_version":[r.model_version  for r in labels],
            }
            table = pa.table(data)
            buf   = io.BytesIO()
            pq.write_table(table, buf, compression="snappy")
            buf.seek(0)

            endpoint = minio_endpoint.replace("http://","").replace("https://","")
            client   = Minio(endpoint, access_key=access_key,
                             secret_key=secret_key, secure=False)

            if not client.bucket_exists(bucket):
                client.make_bucket(bucket)

            size = buf.getbuffer().nbytes
            client.put_object(bucket, path, buf, size)
            logger.info("Wrote %d labels to minio://%s/%s (%d bytes)",
                        len(labels), bucket, path, size)
            return f"s3://{bucket}/{path}"

        except Exception as e:
            logger.error("Failed to write labels to MinIO: %s", e)
            return None

    def compute_model_performance(self, labels: List[LabeledRow]) -> Dict:
        """
        Compute precision, recall, F1, and false negative rate
        based on what the model decided vs ground truth.
        """
        if not labels:
            return {}

        tp = sum(1 for r in labels if r.true_label==1 and r.model_action in ("BLOCK","STEP_UP_AUTH","MANUAL_REVIEW"))
        fp = sum(1 for r in labels if r.true_label==0 and r.model_action in ("BLOCK","STEP_UP_AUTH"))
        fn = sum(1 for r in labels if r.true_label==1 and r.model_action=="APPROVE")
        tn = sum(1 for r in labels if r.true_label==0 and r.model_action=="APPROVE")

        precision    = tp / max(tp + fp, 1)
        recall       = tp / max(tp + fn, 1)
        f1           = 2 * precision * recall / max(precision + recall, 1e-9)
        fn_rate      = fn / max(tp + fn, 1)
        fp_rate      = fp / max(fp + tn, 1)

        metrics = {
            "n_labeled":   len(labels),
            "n_fraud":     tp + fn,
            "n_legit":     fp + tn,
            "true_pos":    tp,
            "false_pos":   fp,
            "false_neg":   fn,
            "true_neg":    tn,
            "precision":   round(precision, 4),
            "recall":      round(recall,    4),
            "f1":          round(f1,        4),
            "fn_rate":     round(fn_rate,   4),
            "fp_rate":     round(fp_rate,   4),
        }
        logger.info("Model performance on %d labeled samples: P=%.3f R=%.3f F1=%.3f FNR=%.3f",
                    len(labels), precision, recall, f1, fn_rate)
        return metrics
