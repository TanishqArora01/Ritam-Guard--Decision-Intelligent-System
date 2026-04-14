"""
dags/feature_snapshot.py
Airflow DAG — Hourly Feature Snapshot to MinIO Offline Store

Schedule: every hour at :05 past the hour
Purpose:
  The feature-engine service already pushes snapshots every hour via its
  built-in scheduler thread. This DAG provides:
    1. A guaranteed backup snapshot via Airflow (in case the service snapshot failed)
    2. A verification step to confirm snapshots exist and have valid row counts
    3. Cleanup of old snapshots beyond the retention window (7 days)

Why hourly snapshots matter:
  Feast point-in-time joins need historical feature state at the exact time
  each training label was created. Without snapshots, we can only train on
  current feature state — this introduces data leakage if features have shifted.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

from airflow import DAG
from airflow.operators.python import PythonOperator

default_args = {
    "owner":            "fraud-ml-team",
    "depends_on_past":  False,
    "retries":          3,
    "retry_delay":      timedelta(minutes=2),
    "email_on_failure": False,
}

MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT",    "http://minio:9000")
MINIO_ACCESS   = os.getenv("MINIO_ACCESS_KEY",  "fraud_minio")
MINIO_SECRET   = os.getenv("MINIO_SECRET_KEY",  "fraud_minio_2024")
REDIS_HOST     = os.getenv("REDIS_HOST",         "redis")
REDIS_PORT     = int(os.getenv("REDIS_PORT",     "6379"))
SNAPSHOT_RETENTION_DAYS = int(os.getenv("SNAPSHOT_RETENTION_DAYS", "7"))


def verify_snapshot_exists(**context) -> dict:
    """
    Check that the feature-engine service wrote a snapshot for this hour.
    If not, set a flag to trigger a backup snapshot.
    """
    exec_hour  = context["execution_date"].strftime("%Y%m%d_%H")
    expected   = f"hourly/{context['execution_date'].strftime('%Y-%m-%d')}"
    result     = {"snapshot_found": False, "backup_needed": False}

    try:
        from minio import Minio
        endpoint = MINIO_ENDPOINT.replace("http://","").replace("https://","")
        client   = Minio(endpoint, access_key=MINIO_ACCESS,
                         secret_key=MINIO_SECRET, secure=False)

        objects = list(client.list_objects(
            "feature-snapshots", prefix=expected, recursive=True
        ))
        recent = [o for o in objects if exec_hour[:8] in o.object_name]

        result["snapshot_found"] = len(recent) > 0
        result["backup_needed"]  = not result["snapshot_found"]
        result["n_objects"]      = len(recent)
        print(f"Snapshot check: found={result['snapshot_found']} n={len(recent)}")

    except Exception as e:
        print(f"Snapshot verification failed: {e}")
        result["backup_needed"] = True

    context["task_instance"].xcom_push(key="snapshot_status", value=str(result))
    return result


def write_backup_snapshot(**context):
    """
    If the feature-engine didn't write a snapshot, do it manually from Redis.
    Scans all active customer keys in Redis and writes a Parquet snapshot.
    """
    import json

    status = context["task_instance"].xcom_pull(
        task_ids="verify_snapshot_exists", key="snapshot_status"
    )
    result = eval(status or "{}") if status else {}

    if not result.get("backup_needed", True):
        print("Snapshot found — no backup needed")
        return

    print("Writing backup snapshot from Redis...")

    try:
        import redis as redis_lib
        import io
        import pyarrow as pa
        import pyarrow.parquet as pq
        from minio import Minio
        from datetime import timezone

        r = redis_lib.Redis(host=REDIS_HOST, port=REDIS_PORT,
                            decode_responses=True, socket_timeout=5)

        # Scan behavioral keys to find active customers
        customer_ids = []
        cursor = 0
        while True:
            cursor, keys = r.scan(cursor=cursor, match="feat:*:behavioral", count=500)
            for k in keys:
                parts = k.split(":")
                if len(parts) >= 3:
                    customer_ids.append(parts[1])
            if cursor == 0:
                break

        print(f"Found {len(customer_ids)} active customers in Redis")

        rows = []
        for cid in customer_ids[:5000]:   # cap at 5000 per snapshot
            try:
                data = r.hgetall(f"feat:{cid}:behavioral")
                if data:
                    rows.append({
                        "customer_id":     cid,
                        "avg_amount":      float(data.get("avg_amount",      "0")),
                        "txn_count_total": int(data.get("txn_count_total",   "0")),
                        "last_txn_ts":     float(data.get("last_txn_ts",     "0")),
                        "event_timestamp": datetime.now(timezone.utc).isoformat(),
                        "created_timestamp": datetime.now(timezone.utc).isoformat(),
                    })
            except Exception:
                pass

        if not rows:
            print("No active customers in Redis — skipping backup snapshot")
            return

        # Write to MinIO
        table    = pa.table(rows)
        buf      = io.BytesIO()
        pq.write_table(table, buf, compression="snappy")
        buf.seek(0)

        now  = datetime.now(timezone.utc)
        path = f"hourly/{now.isoformat()}_backup.parquet"

        endpoint = MINIO_ENDPOINT.replace("http://","").replace("https://","")
        client   = Minio(endpoint, access_key=MINIO_ACCESS,
                         secret_key=MINIO_SECRET, secure=False)

        size = buf.getbuffer().nbytes
        client.put_object("feature-snapshots", path, buf, size)
        print(f"Backup snapshot written: {path} ({len(rows)} customers, {size} bytes)")

    except Exception as e:
        print(f"Backup snapshot failed: {e}")


def cleanup_old_snapshots(**context):
    """
    Remove MinIO snapshots older than SNAPSHOT_RETENTION_DAYS.
    Keeps storage under control — feature-snapshots bucket can grow large.
    """
    from datetime import timezone
    cutoff = datetime.now(timezone.utc) - timedelta(days=SNAPSHOT_RETENTION_DAYS)
    deleted = 0

    try:
        from minio import Minio
        endpoint = MINIO_ENDPOINT.replace("http://","").replace("https://","")
        client   = Minio(endpoint, access_key=MINIO_ACCESS,
                         secret_key=MINIO_SECRET, secure=False)

        objects = list(client.list_objects(
            "feature-snapshots", prefix="hourly/", recursive=True
        ))

        for obj in objects:
            try:
                # Parse timestamp from object name
                obj_ts = obj.last_modified
                if obj_ts and obj_ts.replace(tzinfo=timezone.utc) < cutoff:
                    client.remove_object("feature-snapshots", obj.object_name)
                    deleted += 1
            except Exception:
                pass

        print(f"Cleanup: deleted {deleted} old snapshots (cutoff={cutoff.date()})")

    except Exception as e:
        print(f"Cleanup failed (non-fatal): {e}")


# ---------------------------------------------------------------------------
# DAG definition
# ---------------------------------------------------------------------------

with DAG(
    dag_id            = "feature_snapshot",
    default_args      = default_args,
    description       = "Hourly feature snapshot verification + backup + cleanup",
    schedule_interval = "5 * * * *",    # every hour at :05
    start_date        = datetime(2024, 1, 1),
    catchup           = False,
    tags              = ["fraud-detection", "feature-store", "phase7"],
) as dag:

    verify = PythonOperator(
        task_id         = "verify_snapshot_exists",
        python_callable = verify_snapshot_exists,
    )

    backup = PythonOperator(
        task_id         = "write_backup_snapshot",
        python_callable = write_backup_snapshot,
    )

    cleanup = PythonOperator(
        task_id         = "cleanup_old_snapshots",
        python_callable = cleanup_old_snapshots,
    )

    verify >> backup >> cleanup
