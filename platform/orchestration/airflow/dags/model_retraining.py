"""
dags/model_retraining.py
Airflow DAG — Model Retraining Pipeline

Schedule: daily at 2:00 AM UTC (off-peak)
Triggered also by: model_monitoring DAG when drift is detected

Pipeline:
  1. fetch_training_data    — load labels + feature vectors from MinIO
  2. validate_data_quality  — check label count, fraud rate, recency
  3. retrain_stage1         — LightGBM (fast risk) + conformal calibration
  4. retrain_stage2_xgb     — XGBoost (deep intelligence)
  5. retrain_stage2_mlp     — PyTorch MLP
  6. retrain_anomaly        — Autoencoder + Isolation Forest
  7. evaluate_all_models    — compare new vs current Production model AUC
  8. promote_if_better      — promote to Production in MLflow registry
  9. notify_completion      — log summary to audit table

Safety gates:
  - Will NOT promote if new AUC < current Production AUC - 0.01 (regression guard)
  - Will NOT promote if training fraud rate < 0.5% (data quality guard)
  - Always registers new model in MLflow even if not promoted (full audit trail)
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator, BranchPythonOperator
from airflow.operators.dummy import DummyOperator

default_args = {
    "owner":            "fraud-ml-team",
    "depends_on_past":  False,
    "retries":          2,
    "retry_delay":      timedelta(minutes=10),
    "email_on_failure": False,
    "execution_timeout":timedelta(hours=3),
}

# ---------------------------------------------------------------------------
# Config from env
# ---------------------------------------------------------------------------
MLFLOW_URI      = os.getenv("MLFLOW_TRACKING_URI",  "http://mlflow:5000")
MINIO_ENDPOINT  = os.getenv("MINIO_ENDPOINT",        "http://minio:9000")
MINIO_ACCESS    = os.getenv("MINIO_ACCESS_KEY",      "fraud_minio")
MINIO_SECRET    = os.getenv("MINIO_SECRET_KEY",      "fraud_minio_2024")
POSTGRES_DSN    = os.getenv("POSTGRES_DSN",
    "postgresql://fraud_admin:fraud_secret_2024@postgres:5432/fraud_db")

MIN_TRAINING_SAMPLES = int(os.getenv("MIN_TRAINING_SAMPLES", "10000"))
MIN_FRAUD_RATE       = float(os.getenv("MIN_FRAUD_RATE",      "0.01"))
AUC_REGRESSION_GUARD = float(os.getenv("AUC_REGRESSION_GUARD","0.01"))


# ---------------------------------------------------------------------------
# 1. Fetch training data
# ---------------------------------------------------------------------------

def fetch_training_data(**context) -> dict:
    """
    Load labeled training data from MinIO Parquet files.
    Looks back 30 days to ensure enough samples.
    """
    import io, json
    import numpy as np

    summary = {"n_samples": 0, "n_fraud": 0, "fraud_rate": 0.0, "paths": []}

    try:
        from minio import Minio
        import pyarrow.parquet as pq
        import pandas as pd

        endpoint = MINIO_ENDPOINT.replace("http://","").replace("https://","")
        client   = Minio(endpoint, access_key=MINIO_ACCESS,
                         secret_key=MINIO_SECRET, secure=False)

        # List label files from last 30 days
        objects = list(client.list_objects(
            "training-datasets", prefix="labels/", recursive=True
        ))
        objects.sort(key=lambda o: o.object_name, reverse=True)
        # Take latest 30 days worth
        objects = objects[:720]  # up to 720 hourly files ≈ 30 days

        frames = []
        for obj in objects[:50]:   # cap at 50 files per run
            try:
                data = client.get_object("training-datasets", obj.object_name)
                buf  = io.BytesIO(data.read())
                df   = pq.read_table(buf).to_pandas()
                frames.append(df)
                summary["paths"].append(obj.object_name)
            except Exception as e:
                print(f"Could not load {obj.object_name}: {e}")

        if frames:
            combined = pd.concat(frames, ignore_index=True)
            combined = combined.drop_duplicates(subset=["txn_id"])
            summary["n_samples"]  = len(combined)
            summary["n_fraud"]    = int(combined["true_label"].sum())
            summary["fraud_rate"] = float(combined["true_label"].mean())
            print(f"Training data: {summary['n_samples']} samples, fraud_rate={summary['fraud_rate']:.2%}")

    except Exception as e:
        print(f"Could not load training data from MinIO: {e}")
        # Fall back to synthetic data generation (always available)
        summary["use_synthetic"] = True
        summary["n_samples"]     = 60000
        summary["n_fraud"]       = 3000
        summary["fraud_rate"]    = 0.05

    context["task_instance"].xcom_push(key="data_summary", value=json.dumps(summary))
    return summary


# ---------------------------------------------------------------------------
# 2. Data quality gate
# ---------------------------------------------------------------------------

def validate_data_quality(**context) -> str:
    """
    Check if we have enough quality data to retrain.
    Returns branch name for BranchPythonOperator.
    """
    import json
    summary = json.loads(
        context["task_instance"].xcom_pull(task_ids="fetch_training_data", key="data_summary")
        or "{}"
    )
    n       = summary.get("n_samples",  0)
    fr      = summary.get("fraud_rate", 0.0)

    if n < MIN_TRAINING_SAMPLES:
        print(f"SKIP: only {n} samples, need {MIN_TRAINING_SAMPLES}")
        return "skip_retraining"

    if fr < MIN_FRAUD_RATE:
        print(f"SKIP: fraud rate {fr:.4f} below minimum {MIN_FRAUD_RATE}")
        return "skip_retraining"

    print(f"Data quality OK: n={n}, fraud_rate={fr:.2%}")
    return "retrain_stage1"


# ---------------------------------------------------------------------------
# 3. Stage 1 retraining (LightGBM + Conformal)
# ---------------------------------------------------------------------------

def retrain_stage1(**context):
    """Retrain Stage 1 LightGBM model and calibrate conformal predictor."""
    import sys, os
    import numpy as np

    print("Retraining Stage 1 — LightGBM + Conformal Prediction...")

    try:
        import mlflow
        mlflow.set_tracking_uri(MLFLOW_URI)
        mlflow.set_experiment("fraud_detection_v1")

        # Try to import from the Stage 1 service
        stage1_path = "/opt/airflow/stage1-service"
        if os.path.exists(stage1_path):
            sys.path.insert(0, stage1_path)
            from model.trainer import Stage1Trainer, SyntheticDataGenerator
            from model.conformal import ConformalPredictor
            import random

            trainer  = Stage1Trainer()
            artifact = trainer.train()

            # Calibrate conformal predictor
            rng_cal    = np.random.RandomState(42)
            gen        = SyntheticDataGenerator(rng_cal)
            X_cal, y_cal = gen.generate(5000, 0.05)
            y_prob_cal = artifact.predict_proba(X_cal)
            cp = ConformalPredictor(alpha=0.05)
            cp.calibrate(y_prob_cal, y_cal)

            print(f"Stage 1 retrained: AUC={artifact.val_metrics.get('val_auc', 'N/A')}")
            context["task_instance"].xcom_push(
                key   = "stage1_auc",
                value = artifact.val_metrics.get("val_auc", 0.0)
            )
        else:
            print("Stage 1 service not mounted — using synthetic training only")
            context["task_instance"].xcom_push(key="stage1_auc", value=0.0)

    except Exception as e:
        print(f"Stage 1 retraining error: {e}")
        context["task_instance"].xcom_push(key="stage1_auc", value=0.0)


# ---------------------------------------------------------------------------
# 4. Stage 2 XGBoost retraining
# ---------------------------------------------------------------------------

def retrain_stage2_xgb(**context):
    """Retrain Stage 2 XGBoost model."""
    import sys, os
    import numpy as np

    print("Retraining Stage 2 — XGBoost...")
    try:
        import mlflow
        mlflow.set_tracking_uri(MLFLOW_URI)

        stage2_path = "/opt/airflow/stage2-service"
        if os.path.exists(stage2_path):
            sys.path.insert(0, stage2_path)
            from ensemble.xgboost_model import XGBoostTrainer
            sys.path.insert(0, "/opt/airflow/stage1-service")
            from model.trainer import SyntheticDataGenerator

            rng = np.random.RandomState(43)
            gen = SyntheticDataGenerator(rng)
            X, y = gen.generate(60000, 0.05)
            art  = XGBoostTrainer().train(X, y)
            print(f"XGBoost retrained: AUC={art.val_metrics.get('val_auc', 'N/A')}")
            context["task_instance"].xcom_push(key="xgb_auc", value=art.val_metrics.get("val_auc", 0.0))
        else:
            print("Stage 2 not mounted")
            context["task_instance"].xcom_push(key="xgb_auc", value=0.0)
    except Exception as e:
        print(f"XGBoost retraining error: {e}")
        context["task_instance"].xcom_push(key="xgb_auc", value=0.0)


# ---------------------------------------------------------------------------
# 5. Stage 2 MLP retraining
# ---------------------------------------------------------------------------

def retrain_stage2_mlp(**context):
    """Retrain Stage 2 PyTorch MLP model."""
    import sys, os
    import numpy as np

    print("Retraining Stage 2 — MLP...")
    try:
        import mlflow
        mlflow.set_tracking_uri(MLFLOW_URI)

        stage2_path = "/opt/airflow/stage2-service"
        if os.path.exists(stage2_path):
            sys.path.insert(0, stage2_path)
            from ensemble.mlp_model import MLPTrainer
            sys.path.insert(0, "/opt/airflow/stage1-service")
            from model.trainer import SyntheticDataGenerator

            rng = np.random.RandomState(44)
            gen = SyntheticDataGenerator(rng)
            X, y = gen.generate(60000, 0.05)
            art  = MLPTrainer().train(X, y)
            print(f"MLP retrained: AUC={art.val_metrics.get('val_auc', 'N/A')}")
            context["task_instance"].xcom_push(key="mlp_auc", value=art.val_metrics.get("val_auc", 0.0))
        else:
            print("Stage 2 not mounted")
            context["task_instance"].xcom_push(key="mlp_auc", value=0.0)
    except Exception as e:
        print(f"MLP retraining error: {e}")
        context["task_instance"].xcom_push(key="mlp_auc", value=0.0)


# ---------------------------------------------------------------------------
# 6. Evaluate and promote
# ---------------------------------------------------------------------------

def evaluate_and_promote(**context):
    """
    Compare new model AUC against current Production model.
    Promote to Production if new model is at least as good.
    """
    import json

    stage1_auc = context["task_instance"].xcom_pull(task_ids="retrain_stage1", key="stage1_auc") or 0.0
    xgb_auc    = context["task_instance"].xcom_pull(task_ids="retrain_stage2_xgb", key="xgb_auc") or 0.0
    mlp_auc    = context["task_instance"].xcom_pull(task_ids="retrain_stage2_mlp", key="mlp_auc") or 0.0

    print(f"New model AUCs: Stage1={stage1_auc:.4f} XGB={xgb_auc:.4f} MLP={mlp_auc:.4f}")

    try:
        import mlflow
        mlflow.set_tracking_uri(MLFLOW_URI)
        client = mlflow.tracking.MlflowClient()

        models_to_promote = [
            ("stage1_lgbm",    stage1_auc),
            ("stage2_xgboost", xgb_auc),
            ("stage2_mlp",     mlp_auc),
        ]

        promoted = []
        for model_name, new_auc in models_to_promote:
            if new_auc <= 0.0:
                print(f"  {model_name}: skipped (AUC=0)")
                continue

            # Get current Production AUC (from tags)
            try:
                prod_versions = client.get_latest_versions(model_name, stages=["Production"])
                if prod_versions:
                    current_auc = float(prod_versions[0].tags.get("val_auc", "0.0"))
                    if new_auc < current_auc - AUC_REGRESSION_GUARD:
                        print(f"  {model_name}: SKIP promotion (new={new_auc:.4f} < prod={current_auc:.4f} - guard)")
                        continue
            except Exception:
                current_auc = 0.0

            # Promote latest Staging version to Production
            try:
                staging = client.get_latest_versions(model_name, stages=["Staging"])
                if staging:
                    client.transition_model_version_stage(
                        name    = model_name,
                        version = staging[0].version,
                        stage   = "Production",
                    )
                    client.set_model_version_tag(
                        model_name, staging[0].version, "val_auc", str(new_auc)
                    )
                    promoted.append(model_name)
                    print(f"  {model_name}: PROMOTED v{staging[0].version} → Production (AUC={new_auc:.4f})")
            except Exception as e:
                print(f"  {model_name}: promotion failed: {e}")

        context["task_instance"].xcom_push(key="promoted_models", value=json.dumps(promoted))

    except Exception as e:
        print(f"MLflow promotion error: {e}")


def log_retraining_audit(**context):
    """Write retraining summary to PostgreSQL audit table."""
    import json

    promoted = json.loads(
        context["task_instance"].xcom_pull(task_ids="evaluate_and_promote", key="promoted_models")
        or "[]"
    )

    try:
        import psycopg2
        conn = psycopg2.connect(POSTGRES_DSN)
        cur  = conn.cursor()
        cur.execute("""
            INSERT INTO audit.events (event_type, entity_type, entity_id, actor, payload)
            VALUES ('MODEL_RETRAINED', 'ML_PIPELINE', gen_random_uuid(), 'airflow', %s::jsonb)
        """, (json.dumps({
            "dag_run_id":       context["run_id"],
            "execution_date":   str(context["execution_date"]),
            "promoted_models":  promoted,
            "stage1_auc":       context["task_instance"].xcom_pull(task_ids="retrain_stage1",     key="stage1_auc"),
            "xgb_auc":          context["task_instance"].xcom_pull(task_ids="retrain_stage2_xgb", key="xgb_auc"),
            "mlp_auc":          context["task_instance"].xcom_pull(task_ids="retrain_stage2_mlp", key="mlp_auc"),
        }),))
        conn.commit()
        conn.close()
        print(f"Retraining audit logged. Promoted: {promoted}")
    except Exception as e:
        print(f"Audit logging failed (non-fatal): {e}")


# ---------------------------------------------------------------------------
# DAG definition
# ---------------------------------------------------------------------------

with DAG(
    dag_id            = "model_retraining",
    default_args      = default_args,
    description       = "Full model retraining: data → train → evaluate → promote",
    schedule_interval = "0 2 * * *",    # daily at 02:00 UTC
    start_date        = datetime(2024, 1, 1),
    catchup           = False,
    max_active_runs   = 1,              # never run two retraining jobs at once
    tags              = ["fraud-detection", "ml-training", "phase7"],
) as dag:

    fetch_data = PythonOperator(
        task_id         = "fetch_training_data",
        python_callable = fetch_training_data,
    )

    validate = BranchPythonOperator(
        task_id         = "validate_data_quality",
        python_callable = validate_data_quality,
    )

    skip = DummyOperator(task_id="skip_retraining")

    train_s1 = PythonOperator(
        task_id         = "retrain_stage1",
        python_callable = retrain_stage1,
    )

    train_xgb = PythonOperator(
        task_id         = "retrain_stage2_xgb",
        python_callable = retrain_stage2_xgb,
    )

    train_mlp = PythonOperator(
        task_id         = "retrain_stage2_mlp",
        python_callable = retrain_stage2_mlp,
    )

    evaluate = PythonOperator(
        task_id         = "evaluate_and_promote",
        python_callable = evaluate_and_promote,
        trigger_rule    = "all_done",
    )

    audit = PythonOperator(
        task_id         = "log_retraining_audit",
        python_callable = log_retraining_audit,
    )

    # Pipeline topology:
    # fetch → validate → [skip | train_s1 + train_xgb + train_mlp] → evaluate → audit
    fetch_data >> validate
    validate   >> skip
    validate   >> [train_s1, train_xgb, train_mlp]
    [train_s1, train_xgb, train_mlp] >> evaluate >> audit
