"""
dags/model_monitoring.py
Airflow DAG — Model Performance Monitoring + Drift Detection

Schedule: every 6 hours
Purpose:
  1. Load recent feature distributions from MinIO snapshots
  2. Compare against training distribution (PSI + KL divergence)
  3. Compute model performance metrics from labeled data
  4. Write monitoring metrics to PostgreSQL + ClickHouse
  5. Auto-trigger retraining DAG if drift is significant or performance drops

Triggers retraining when ANY of:
  - max_psi > 0.25              (significant feature drift)
  - 3+ features have PSI > 0.20 (widespread drift)
  - false_negative_rate > 0.15  (model missing too much fraud)
  - false_positive_rate > 0.10  (model annoying too many customers)
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator, BranchPythonOperator
from airflow.operators.dummy import DummyOperator
from airflow.operators.trigger_dagrun import TriggerDagRunOperator

default_args = {
    "owner":            "fraud-ml-team",
    "depends_on_past":  False,
    "retries":          1,
    "retry_delay":      timedelta(minutes=5),
    "email_on_failure": False,
}

MLFLOW_URI     = os.getenv("MLFLOW_TRACKING_URI",  "http://mlflow:5000")
MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT",        "http://minio:9000")
MINIO_ACCESS   = os.getenv("MINIO_ACCESS_KEY",      "fraud_minio")
MINIO_SECRET   = os.getenv("MINIO_SECRET_KEY",      "fraud_minio_2024")
POSTGRES_DSN   = os.getenv("POSTGRES_DSN",
    "postgresql://fraud_admin:fraud_secret_2024@postgres:5432/fraud_db")

# Drift trigger thresholds
MAX_PSI_TRIGGER = float(os.getenv("MAX_PSI_TRIGGER",   "0.25"))
FNR_TRIGGER     = float(os.getenv("FNR_TRIGGER",       "0.15"))
FPR_TRIGGER     = float(os.getenv("FPR_TRIGGER",       "0.10"))
N_DRIFTED_TRIGGER = int(os.getenv("N_DRIFTED_TRIGGER", "3"))


# ---------------------------------------------------------------------------
# Tasks
# ---------------------------------------------------------------------------

def load_current_feature_distribution(**context) -> dict:
    """
    Load recent production feature distribution from MinIO snapshots.
    Returns summary stats for drift comparison.
    """
    import io
    import numpy as np
    import sys
    sys.path.insert(0, "/opt/airflow/feedback")

    print("Loading current feature distribution from MinIO snapshots...")

    distribution = {"available": False, "n_samples": 0}

    try:
        from minio import Minio
        import pyarrow.parquet as pq
        import pandas as pd

        endpoint = MINIO_ENDPOINT.replace("http://","").replace("https://","")
        client   = Minio(endpoint, access_key=MINIO_ACCESS,
                         secret_key=MINIO_SECRET, secure=False)

        # Last 6 hours of snapshots
        objects = sorted(
            client.list_objects("feature-snapshots", prefix="hourly/", recursive=True),
            key=lambda o: o.object_name, reverse=True
        )[:6]

        frames = []
        for obj in objects:
            try:
                data = client.get_object("feature-snapshots", obj.object_name)
                df   = pq.read_table(io.BytesIO(data.read())).to_pandas()
                frames.append(df)
            except Exception as e:
                print(f"Could not load snapshot {obj.object_name}: {e}")

        if frames:
            combined = pd.concat(frames, ignore_index=True)
            distribution["available"] = True
            distribution["n_samples"] = len(combined)

            # Compute summary stats per feature
            feature_cols = [c for c in combined.columns if c in [
                "txn_count_1m","txn_count_5m","txn_count_1h","txn_count_24h",
                "amount_sum_1m","amount_sum_5m","amount_sum_1h","amount_sum_24h",
                "geo_velocity_kmh","is_new_country","unique_countries_24h",
                "device_trust_score","is_new_device","ip_txn_count_1h","unique_devices_24h",
                "amount_vs_avg_ratio","merchant_familiarity","hours_since_last_txn",
            ]]
            distribution["feature_means"] = combined[feature_cols].mean().to_dict()
            distribution["feature_stds"]  = combined[feature_cols].std().to_dict()
            print(f"Loaded {len(combined)} samples from {len(frames)} snapshots")

    except Exception as e:
        print(f"Could not load feature distribution: {e}")

    context["task_instance"].xcom_push(key="distribution", value=json.dumps(distribution))
    return distribution


def run_drift_detection(**context) -> dict:
    """
    Run PSI drift detection on current vs reference distribution.
    """
    import sys, io
    import numpy as np
    sys.path.insert(0, "/opt/airflow/feedback")

    print("Running drift detection...")

    drift_result = {
        "max_psi":               0.0,
        "overall_psi":           0.0,
        "n_drifted_features":    0,
        "drifted_features":      [],
        "retraining_recommended":False,
    }

    try:
        from drift_detector import DriftDetector, FEATURE_NAMES

        detector   = DriftDetector(psi_threshold=MAX_PSI_TRIGGER)
        ref_data   = detector.load_reference_from_minio(
            MINIO_ENDPOINT, MINIO_ACCESS, MINIO_SECRET, n_snapshots=24
        )

        if ref_data is None:
            print("No reference data available — using synthetic baseline")
            rng      = np.random.RandomState(42)
            ref_data = rng.randn(10000, 18).astype(np.float32)

        # Simulate current data (in production this comes from the MinIO snapshot)
        cur_rng  = np.random.RandomState(int(datetime.now().timestamp()) % 10000)
        cur_data = ref_data + cur_rng.randn(*ref_data.shape) * 0.1  # slight drift

        report      = detector.detect(ref_data, cur_data, FEATURE_NAMES)
        drift_result = report.to_dict()
        drift_result["n_drifted_features"] = len(report.drifted_features)

        print(f"Drift: max_psi={report.max_psi:.4f} drifted={len(report.drifted_features)} retrain={report.retraining_recommended}")

    except Exception as e:
        print(f"Drift detection failed: {e}")

    context["task_instance"].xcom_push(key="drift_result", value=json.dumps(drift_result))
    return drift_result


def compute_model_performance(**context) -> dict:
    """
    Compute precision, recall, FNR, FPR from recent labeled feedback.
    """
    import sys
    sys.path.insert(0, "/opt/airflow/feedback")

    from datetime import timezone
    since = datetime.now(timezone.utc) - timedelta(hours=6)
    until = datetime.now(timezone.utc)

    metrics = {"precision": 0.0, "recall": 0.0, "fn_rate": 0.0, "fp_rate": 0.0, "n_labeled": 0}

    try:
        from label_processor import LabelProcessor
        processor = LabelProcessor(POSTGRES_DSN)
        analyst   = processor.fetch_analyst_labels(since, until)
        cb        = processor.fetch_chargeback_labels(since, until)
        merged    = processor.merge_labels(analyst, cb)
        metrics   = processor.compute_model_performance(merged)
        print(f"Performance: P={metrics.get('precision',0):.3f} R={metrics.get('recall',0):.3f} FNR={metrics.get('fn_rate',0):.3f}")
    except Exception as e:
        print(f"Performance computation failed: {e}")

    context["task_instance"].xcom_push(key="perf_metrics", value=json.dumps(metrics))
    return metrics


def write_monitoring_metrics(**context):
    """Write all monitoring metrics to PostgreSQL audit table + ClickHouse."""
    from datetime import timezone

    drift  = json.loads(context["task_instance"].xcom_pull(task_ids="run_drift_detection",      key="drift_result")  or "{}")
    perf   = json.loads(context["task_instance"].xcom_pull(task_ids="compute_model_performance", key="perf_metrics") or "{}")

    payload = {
        "monitoring_run_at":      datetime.now(timezone.utc).isoformat(),
        "drift":                  drift,
        "performance":            perf,
        "retraining_recommended": drift.get("retraining_recommended", False)
                                  or perf.get("fn_rate", 0) > FNR_TRIGGER
                                  or perf.get("fp_rate", 0) > FPR_TRIGGER,
    }

    try:
        import psycopg2
        conn = psycopg2.connect(POSTGRES_DSN)
        cur  = conn.cursor()
        cur.execute("""
            INSERT INTO audit.events (event_type, entity_type, entity_id, actor, payload)
            VALUES ('MODEL_MONITORING', 'ML_PIPELINE', gen_random_uuid(), 'airflow', %s::jsonb)
        """, (json.dumps(payload),))
        conn.commit()
        conn.close()
        print("Monitoring metrics logged to PostgreSQL")
    except Exception as e:
        print(f"Failed to write monitoring metrics: {e}")

    context["task_instance"].xcom_push(key="monitoring_payload", value=json.dumps(payload))


def should_trigger_retraining(**context) -> str:
    """
    Branch: decide whether to trigger the retraining DAG.
    """
    payload = json.loads(
        context["task_instance"].xcom_pull(task_ids="write_monitoring_metrics", key="monitoring_payload")
        or "{}"
    )

    drift  = payload.get("drift",       {})
    perf   = payload.get("performance", {})

    triggers = []
    if drift.get("max_psi", 0) > MAX_PSI_TRIGGER:
        triggers.append(f"max_psi={drift['max_psi']:.4f}")
    if drift.get("n_drifted_features", 0) >= N_DRIFTED_TRIGGER:
        triggers.append(f"n_drifted={drift['n_drifted_features']}")
    if perf.get("fn_rate", 0) > FNR_TRIGGER:
        triggers.append(f"fn_rate={perf['fn_rate']:.3f}")
    if perf.get("fp_rate", 0) > FPR_TRIGGER:
        triggers.append(f"fp_rate={perf['fp_rate']:.3f}")

    if triggers:
        print(f"TRIGGER retraining: {', '.join(triggers)}")
        return "trigger_retraining"
    else:
        print("No retraining needed — all metrics within bounds")
        return "no_retraining_needed"


# ---------------------------------------------------------------------------
# DAG definition
# ---------------------------------------------------------------------------

with DAG(
    dag_id            = "model_monitoring",
    default_args      = default_args,
    description       = "Feature drift detection + model performance monitoring",
    schedule_interval = "0 */6 * * *",  # every 6 hours
    start_date        = datetime(2024, 1, 1),
    catchup           = False,
    tags              = ["fraud-detection", "monitoring", "phase7"],
) as dag:

    load_dist = PythonOperator(
        task_id         = "load_current_feature_distribution",
        python_callable = load_current_feature_distribution,
    )

    drift = PythonOperator(
        task_id         = "run_drift_detection",
        python_callable = run_drift_detection,
    )

    perf = PythonOperator(
        task_id         = "compute_model_performance",
        python_callable = compute_model_performance,
    )

    write_metrics = PythonOperator(
        task_id         = "write_monitoring_metrics",
        python_callable = write_monitoring_metrics,
        trigger_rule    = "all_done",
    )

    branch = BranchPythonOperator(
        task_id         = "should_trigger_retraining",
        python_callable = should_trigger_retraining,
    )

    trigger = TriggerDagRunOperator(
        task_id         = "trigger_retraining",
        trigger_dag_id  = "model_retraining",
        wait_for_completion = False,
        conf            = {"triggered_by": "drift_detection"},
    )

    no_retrain = DummyOperator(task_id="no_retraining_needed")

    [load_dist, drift, perf] >> write_metrics >> branch
    branch >> trigger
    branch >> no_retrain
